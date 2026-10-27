"""
Evaluate the agent on eval/questions.yaml and write eval/results.md.

For every question it measures:
  - tool choice   did the agent call an appropriate tool?
  - recall        did the answer name every project with the planted problem?
  - grounding     does every £ amount and % in the answer appear in a tool result?
                  (catches invented numbers - the main hallucination risk for finance)
  - refusal       for a project that doesn't exist, did it say so instead of making figures up?

    python -m eval.run_eval            # uses the real LLM from .env
    python -m eval.run_eval --fake     # offline keyword baseline, no API key needed
"""

from __future__ import annotations

import argparse
import json
import re
import time
import unicodedata
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
QUESTIONS = ROOT / "eval" / "questions.yaml"
TRUTH = ROOT / "data" / "ground_truth.csv"
RESULTS_MD = ROOT / "eval" / "results.md"

REFUSAL_WORDS = ("no project", "not find", "couldn't find", "could not find", "can't find", "cannot find",
                 "unable to find", "unable to locate", "couldn't locate", "could not locate", "doesn't exist",
                 "does not exist", "no match", "not found", "no record", "don't have", "do not have")
# £1,234 / £1.2m / £20.8 m / £88k
MONEY_RE = re.compile(r"£\s?([\d,]+(?:\.\d+)?)\s?(bn|m|k)?\b", re.IGNORECASE)
MULTIPLIERS = {"": 1, "k": 1_000, "m": 1_000_000, "bn": 1_000_000_000}


def normalise(text: str) -> str:
    """Models often use non-breaking spaces and hyphens; make them plain so text matching works."""
    text = unicodedata.normalize("NFKC", text)
    for ch in ("\u00a0", "\u202f", "\u2009", "\u2007"):
        text = text.replace(ch, " ")
    for ch in ("\u2010", "\u2011", "\u2012", "\u2013", "\u2014", "\u2212"):
        text = text.replace(ch, "-")
    return text
PERCENT_RE = re.compile(r"-?\d+(?:\.\d+)?\s?%")


# ---- grounding check ---------------------------------------------------------

def numbers_in(obj) -> list[float]:
    """Every number anywhere in a (nested) tool result."""
    if isinstance(obj, bool):
        return []
    if isinstance(obj, (int, float)):
        return [float(obj)]
    if isinstance(obj, dict):
        return [n for v in obj.values() for n in numbers_in(v)]
    if isinstance(obj, list):
        return [n for v in obj for n in numbers_in(v)]
    return []


def _parse_results(tool_results: list[str]) -> list[float]:
    nums = []
    for content in tool_results:
        try:
            nums += numbers_in(json.loads(content))
        except (json.JSONDecodeError, TypeError):
            nums += [float(x) for x in re.findall(r"-?\d+(?:\.\d+)?", str(content))]
    return nums


def reference_numbers() -> list[float]:
    """
    Numbers stated in the system prompt and tool descriptions (e.g. "normal admin cost is 2-4%").
    Quoting these is not inventing data, so the grounding check accepts them.
    """
    from src.agent.prompts import SYSTEM_PROMPT
    from src.tools import ALL_TOOLS

    text = SYSTEM_PROMPT + " ".join(tool.__doc__ or "" for tool in ALL_TOOLS)
    return [float(x) for x in re.findall(r"\d+(?:\.\d+)?", text)]


def ungrounded_numbers(answer: str, tool_results: list[str], allowed: list[float] | None = None) -> list[str]:
    """£ amounts and percentages in the answer that don't match any tool output (or `allowed`)."""
    answer = normalise(answer)
    source = _parse_results(tool_results) + list(allowed or [])
    bad = []
    for match in MONEY_RE.finditer(answer):
        number, suffix = match.group(1), (match.group(2) or "").lower()
        value = float(number.replace(",", "")) * MULTIPLIERS[suffix]
        # allow for the rounding the model applied: £1 for exact figures, and less than one unit of
        # the last shown digit for abbreviated ones (£20.8m -> within £100k, £41k -> within £1k),
        # which accepts both rounding and truncation but not a different number
        decimals = len(number.split(".")[1]) if "." in number else 0
        tolerance = max(1.0, MULTIPLIERS[suffix] / (10 ** decimals)) if suffix else 1.0
        tolerance = max(tolerance, abs(value) * 0.005)
        if not any(abs(abs(value) - abs(s)) <= tolerance for s in source):
            bad.append(match.group(0).strip())
    for raw in PERCENT_RE.findall(answer):
        value = float(raw.replace("%", "").strip())
        derived = source + [s * 100 for s in source]  # shares stored as 0-1
        if not any(abs(abs(value) - abs(s)) <= 0.051 for s in derived):
            bad.append(raw)
    return bad


# ---- offline baseline ------------------------------------------------------------

def keyword_baseline():
    """
    A deterministic 'model' that routes by keywords and lists project names from the tool
    result. It shows the harness works without an API key, and gives the LLM a baseline to beat.
    """
    from langchain_core.language_models import BaseChatModel
    from langchain_core.messages import AIMessage, ToolMessage
    from langchain_core.outputs import ChatGeneration, ChatResult

    routes = [
        (("worried", "risk", "attention"), "risk_overview", {}),
        (("slipping", "declin", "worse"), "declining_margin_projects", {}),
        (("losing", "loss"), "lowest_margin_projects", {}),
        (("paid", "invoice", "owe"), "overdue_invoice_projects", {}),
        (("billed", "billing", "wip"), "overdue_wip_projects", {}),
        (("contingency",), "contingency_erosion_projects", {}),
        (("admin",), "admin_cost_outliers", {}),
        (("over the year", "trend", "changed"), "portfolio_trend", {}),
        (("overall", "portfolio"), "portfolio_summary", {}),
    ]

    class KeywordModel(BaseChatModel):
        @property
        def _llm_type(self) -> str:
            return "keyword-baseline"

        def bind_tools(self, tools, **kwargs):
            return self

        def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
            last = messages[-1]
            if isinstance(last, ToolMessage):
                data = json.loads(last.content) if last.content.startswith("{") else {}
                names = [p.get("project_name") for p in data.get("projects", []) if p.get("project_name")]
                text = ("Projects: " + "; ".join(names)) if names else (
                    data.get("error") or "Here are the figures from the report.")
                return ChatResult(generations=[ChatGeneration(message=AIMessage(content=text))])
            q = last.content.lower()
            match = re.search(r"(?:about|on|doing\.?|is)\s+(.+?)(?: is doing|\?|\.|$)", last.content)
            for words, tool, args in routes:
                if any(w in q for w in words) and not ("month by month" in q or "how is" in q):
                    break
            else:
                tool, args = "project_details", {"project": (match.group(1) if match else last.content)}
            if "month by month" in q and match:
                tool, args = "project_history", {"project": match.group(1)}
            call = {"name": tool, "args": args, "id": "call_1"}
            return ChatResult(generations=[ChatGeneration(message=AIMessage(content="", tool_calls=[call]))])

    return KeywordModel()


# ---- runner -----------------------------------------------------------------------

def load_cases() -> list[dict]:
    truth = pd.read_csv(TRUTH, dtype={"contract_number": str})
    last = truth[truth["period"] == truth["period"].max()]
    names_by_scenario = last.groupby("scenario")["project_name"].apply(sorted).to_dict()

    cases = []
    for q in yaml.safe_load(QUESTIONS.read_text(encoding="utf-8")):
        q = dict(q)
        if q.get("project_from"):
            project = names_by_scenario[q["project_from"]][0]
            q["question"] = q["question"].format(project=project)
            q["expected_projects"] = [project]
        else:
            q["expected_projects"] = [n for s in q.get("expected_scenarios", []) for n in names_by_scenario.get(s, [])]
        cases.append(q)
    return cases


def score(case: dict, out: dict) -> dict:
    called = [c["name"] for c in out["tool_calls"]]
    answer = out["answer"]
    plain = normalise(answer).lower()
    found = [p for p in case["expected_projects"] if p.lower() in plain]
    bad_numbers = ungrounded_numbers(answer, out["tool_results"], allowed=reference_numbers())
    result = {
        "id": case["id"],
        "question": case["question"],
        "tools_called": called,
        "tool_ok": any(t in case["expected_tools"] for t in called),
        "recall": len(found) / len(case["expected_projects"]) if case["expected_projects"] else None,
        "missed_projects": [p for p in case["expected_projects"] if p not in found],
        "ungrounded_numbers": bad_numbers,
        "grounded": not bad_numbers,
        "answer": answer,
    }
    if case.get("must_refuse"):
        result["refused_ok"] = any(w in plain for w in REFUSAL_WORDS) and not bad_numbers
    return result


def write_markdown(rows: list[dict], model_name: str, seconds: float) -> str:
    n = len(rows)
    tool_acc = sum(r["tool_ok"] for r in rows) / n
    recalls = [r["recall"] for r in rows if r["recall"] is not None]
    grounded = sum(r["grounded"] for r in rows) / n
    refusals = [r["refused_ok"] for r in rows if "refused_ok" in r]

    lines = [
        f"# Evaluation results ({model_name})",
        "",
        "| Metric | Score |",
        "|---|---|",
        f"| Questions | {n} |",
        f"| Tool choice accuracy | {tool_acc:.0%} |",
        f"| Project recall (planted problems found) | {sum(recalls) / len(recalls):.0%} |",
        f"| Answers with no invented numbers | {grounded:.0%} |",
        f"| Correctly refused unknown project | {sum(refusals)}/{len(refusals)} |",
        f"| Total time | {seconds:.0f}s |",
        "",
        "| Question | Tools called | Tool OK | Recall | Grounded |",
        "|---|---|---|---|---|",
    ]
    for r in rows:
        recall = "-" if r["recall"] is None else f"{r['recall']:.0%}"
        lines.append(f"| {r['question']} | {', '.join(r['tools_called']) or '-'} | "
                     f"{'✅' if r['tool_ok'] else '❌'} | {recall} | {'✅' if r['grounded'] else '❌ ' + ', '.join(r['ungrounded_numbers'])} |")
    return "\n".join(lines) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fake", action="store_true", help="use the offline keyword baseline instead of an LLM")
    ap.add_argument("--limit", type=int, help="only run the first N questions")
    ap.add_argument("--pause", type=float, default=None,
                    help="seconds to wait between questions (default 20 with a real LLM, to stay "
                         "under free-tier rate limits; 0 with --fake)")
    args = ap.parse_args()

    from src.agent.graph import ask, build_agent

    model = keyword_baseline() if args.fake else None
    agent = build_agent(model)
    model_name = "keyword baseline" if args.fake else "LLM agent"

    pause = args.pause if args.pause is not None else (0 if args.fake else 20)
    cases = load_cases()[: args.limit]
    rows, start = [], time.time()
    for i, case in enumerate(cases):
        if i and pause:
            time.sleep(pause)
        try:
            out = ask(case["question"], agent=agent)
        except Exception as exc:  # record the failure and keep going
            print(f"!! {case['id']:<28} ERROR: {type(exc).__name__}: {str(exc)[:120]}")
            out = {"answer": f"ERROR: {exc}", "tool_calls": [], "tool_results": []}
        row = score(case, out)
        rows.append(row)
        status = "ok " if row["tool_ok"] and row["grounded"] and row["recall"] in (None, 1.0) else "!! "
        print(f"{status}{case['id']:<28} tools={row['tools_called']} recall={row['recall']} grounded={row['grounded']}")

    md = write_markdown(rows, model_name, time.time() - start)
    RESULTS_MD.write_text(md, encoding="utf-8")
    (ROOT / "eval" / "results.json").write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
    print("\n" + md.split("\n\n| Question")[0])
    print(f"Wrote {RESULTS_MD.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
