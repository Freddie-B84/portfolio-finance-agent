"""The evaluation's hallucination check must catch invented numbers and accept real ones."""

import json

from eval.run_eval import ungrounded_numbers

TOOL_RESULT = [json.dumps({
    "projects": [{"project_name": "X", "gross_margin": 462933.0, "gross_margin_percent": 29.4,
                  "overdue_share": 0.733}]
})]


def test_real_numbers_are_grounded():
    answer = "Project X has a gross margin of £462,933 (29.4%), and 73.3% of invoices are overdue."
    assert ungrounded_numbers(answer, TOOL_RESULT) == []


def test_rounded_money_is_accepted():
    assert ungrounded_numbers("about £462,900", TOOL_RESULT) == []


def test_invented_money_is_caught():
    assert ungrounded_numbers("Margin is £500,000.", TOOL_RESULT) == ["£500,000"]


def test_invented_percent_is_caught():
    assert ungrounded_numbers("Margin is 31.0%.", TOOL_RESULT) == ["31.0%"]


def test_no_tool_results_means_any_number_is_ungrounded():
    assert ungrounded_numbers("Revenue was £1,000,000.", []) == ["£1,000,000"]


def test_numbers_quoted_from_tool_descriptions_are_allowed():
    from eval.run_eval import reference_numbers

    answer = "Admin cost is normally 2-4% of revenue."
    assert ungrounded_numbers(answer, [], allowed=reference_numbers()) == []


def test_abbreviated_amounts_are_understood():
    result = [json.dumps({"total_costs": 20803259.0, "gross_margin": 4947755.0})]
    assert ungrounded_numbers("Costs of £20.8 m and margin of about £5m.", result) == []
    assert ungrounded_numbers("Costs of £25.0m.", result) == ["£25.0m"]


def test_special_spaces_and_hyphens_are_normalised():
    from eval.run_eval import normalise

    assert normalise("Harbourline Station Accessibility") == "Harbourline Station Accessibility"
    assert normalise("‑£96,808") == "-£96,808"


def test_truncated_abbreviations_are_accepted_but_wrong_ones_are_not():
    result = [json.dumps({"revenue_added": 41631.0})]
    assert ungrounded_numbers("about £41k", result) == []
    assert ungrounded_numbers("about £45k", result) == ["£45k"]
