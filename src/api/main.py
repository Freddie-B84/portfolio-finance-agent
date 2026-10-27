"""
HTTP API for the agent.

    uvicorn src.api.main:app --reload
    curl -X POST localhost:8000/ask -H "Content-Type: application/json" \
         -d '{"question": "Which projects have overdue invoices?"}'

Interactive docs at http://localhost:8000/docs
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from fastapi import FastAPI, HTTPException
from langchain_core.messages import AIMessage, HumanMessage
from pydantic import BaseModel, Field

from src.agent.graph import ask, build_agent
from src.tools import portfolio_summary

app = FastAPI(title="Portfolio Finance Agent", version="1.0")


class Turn(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    history: list[Turn] = Field(default_factory=list, description="Earlier turns, oldest first")


class ToolCall(BaseModel):
    name: str
    args: dict


class AskResponse(BaseModel):
    answer: str
    tool_calls: list[ToolCall]


@lru_cache
def get_agent():
    return build_agent()


@app.get("/health")
def health() -> dict:
    summary = portfolio_summary()
    return {"status": "ok", "latest_period": summary.get("period"), "projects": summary.get("active_projects")}


@app.post("/ask", response_model=AskResponse)
def ask_endpoint(req: AskRequest) -> AskResponse:
    history = [HumanMessage(t.content) if t.role == "user" else AIMessage(t.content) for t in req.history]
    try:
        out = ask(req.question, history=history, agent=get_agent())
    except Exception as exc:  # surface model/config errors clearly instead of a bare 500
        raise HTTPException(status_code=502, detail=f"Agent error: {exc}") from exc
    return AskResponse(answer=out["answer"], tool_calls=out["tool_calls"])
