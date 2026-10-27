"""
Tests the agent's wiring without calling a real LLM (no API key or cost needed):
a scripted fake model asks for a tool, the graph runs it, and the model answers.
"""

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from src.agent.graph import ask, build_agent


class ScriptedModel(BaseChatModel):
    """Returns pre-written messages in order, ignoring the input."""

    script: list[AIMessage]
    seen: list = []

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        self.seen.append(messages)
        reply = self.script.pop(0)
        return ChatResult(generations=[ChatGeneration(message=reply)])


def test_agent_calls_tool_then_answers(database):
    model = ScriptedModel(script=[
        AIMessage(content="", tool_calls=[{"name": "lowest_margin_projects", "args": {"count": 2}, "id": "call_1"}]),
        AIMessage(content="Two projects are loss-making."),
    ])
    out = ask("Which projects are losing money?", agent=build_agent(model))

    assert out["tool_calls"] == [{"name": "lowest_margin_projects", "args": {"count": 2}}]
    assert '"projects"' in out["tool_results"][0]          # the real tool ran against DuckDB
    assert out["answer"] == "Two projects are loss-making."
    # the second model call saw the tool result, so its answer can be grounded in it
    assert any(m.type == "tool" for m in model.seen[-1])


def test_system_prompt_is_sent(database):
    model = ScriptedModel(script=[AIMessage(content="Hello")])
    ask("hi", agent=build_agent(model))
    assert model.seen[0][0].type == "system"
    assert "Every number in your answer must come from a tool result" in model.seen[0][0].content


def test_bad_tool_arguments_dont_crash_the_agent(database):
    model = ScriptedModel(script=[
        AIMessage(content="", tool_calls=[{"name": "project_details", "args": {"wrong": 1}, "id": "call_1"}]),
        AIMessage(content="Sorry, which project did you mean?"),
    ])
    out = ask("Tell me about it", agent=build_agent(model))
    assert "error" in out["tool_results"][0].lower()
    assert out["answer"].startswith("Sorry")
