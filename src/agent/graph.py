"""
The agent: a LangGraph loop where the LLM decides which analysis tools to call,
reads their results, and writes a grounded answer.

    question -> [agent] --tool calls--> [tools] --results--> [agent] -> answer
                   ^___________________________________________|

Run a single question from the command line:
    python -m src.agent.graph "Which projects are losing money?"
"""

from __future__ import annotations

import json
import os
import sys

from dotenv import load_dotenv
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import StructuredTool
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from src.agent.prompts import SYSTEM_PROMPT
from src.tools import ALL_TOOLS

load_dotenv(override=True)  # .env wins over any system-wide OPENAI_API_KEY

MAX_STEPS = 12  # hard stop so a confused model can't loop forever
MAX_RETRIES = int(os.getenv("MAX_RETRIES", "8"))


def make_tools() -> list[StructuredTool]:
    """Wrap the plain Python tools so the LLM sees their names, docstrings and arguments."""
    return [StructuredTool.from_function(fn, parse_docstring=True) for fn in ALL_TOOLS]


def get_llm() -> BaseChatModel:
    """
    Pick the chat model from environment variables (see .env.example):
      - Azure OpenAI if AZURE_OPENAI_ENDPOINT is set
      - otherwise any OpenAI-compatible API (OpenAI, Groq, a local server) via OPENAI_BASE_URL
    """
    if os.getenv("AZURE_OPENAI_ENDPOINT"):
        from langchain_openai import AzureChatOpenAI

        return AzureChatOpenAI(
            azure_deployment=os.environ["AZURE_OPENAI_DEPLOYMENT"],
            api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2024-10-21"),
            temperature=0,
            max_retries=MAX_RETRIES,
        )

    from langchain_openai import ChatOpenAI

    return ChatOpenAI(
        model=os.getenv("MODEL", "gpt-4o-mini"),
        base_url=os.getenv("OPENAI_BASE_URL") or None,
        temperature=0,
        max_retries=MAX_RETRIES,  # waits and retries on rate limits (HTTP 429), e.g. Groq's free tier
    )


def build_agent(llm: BaseChatModel | None = None):
    """Compile the graph. Pass `llm` to use a specific (or fake, for tests) model."""
    tools = make_tools()
    model = (llm or get_llm()).bind_tools(tools)

    def agent_node(state: MessagesState) -> dict:
        messages = state["messages"]
        if not messages or not isinstance(messages[0], SystemMessage):
            messages = [SystemMessage(SYSTEM_PROMPT), *messages]
        return {"messages": [model.invoke(messages)]}

    graph = StateGraph(MessagesState)
    graph.add_node("agent", agent_node)
    graph.add_node("tools", ToolNode(tools, handle_tool_errors=True))
    graph.add_edge(START, "agent")
    graph.add_conditional_edges("agent", tools_condition)  # tool calls -> "tools", else END
    graph.add_edge("tools", "agent")
    return graph.compile()


def ask(question: str, history: list[BaseMessage] | None = None, agent=None) -> dict:
    """
    Ask one question. Returns the answer plus a trace of which tools were called,
    which the evaluation and the UI use.
    """
    agent = agent or build_agent()
    messages = [*(history or []), HumanMessage(question)]
    result = agent.invoke({"messages": messages}, config={"recursion_limit": MAX_STEPS * 2})

    new = result["messages"][len(messages):]
    tool_calls = [
        {"name": call["name"], "args": call["args"]}
        for msg in new if isinstance(msg, AIMessage)
        for call in msg.tool_calls
    ]
    tool_results = [msg.content for msg in new if isinstance(msg, ToolMessage)]
    answer = next((m.content for m in reversed(new) if isinstance(m, AIMessage) and not m.tool_calls), "")
    return {
        "answer": answer,
        "tool_calls": tool_calls,
        "tool_results": tool_results,
        "messages": result["messages"],
    }


if __name__ == "__main__":
    question = " ".join(sys.argv[1:]) or "What should I be worried about in the portfolio?"
    out = ask(question)
    print("Tools called:", json.dumps(out["tool_calls"], indent=2))
    print("\n" + out["answer"])
