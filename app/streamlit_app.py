"""
Chat UI for the agent.

    streamlit run app/streamlit_app.py
"""

import sys
from pathlib import Path

import streamlit as st
from langchain_core.messages import AIMessage, HumanMessage

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.agent.graph import ask, build_agent  # noqa: E402
from src.tools import portfolio_summary  # noqa: E402

st.set_page_config(page_title="Portfolio Finance Agent", page_icon="📊", layout="wide")


@st.cache_resource
def get_agent():
    return build_agent()


# ---- Sidebar: headline numbers straight from the data (no LLM) ----
with st.sidebar:
    s = portfolio_summary()
    st.header("Portfolio")
    st.caption(f"As of {s['period']}")
    st.metric("Active projects", s["active_projects"])
    st.metric("Gross margin", f"{s['gross_margin_percent']:.1f}%")
    st.metric("Loss-making projects", s["loss_making_projects"])
    st.metric("Invoices overdue", f"£{s['invoices_overdue']:,.0f}")
    st.divider()
    st.caption("Try asking:")
    examples = [
        "What should I be worried about?",
        "Which projects are losing money?",
        "Where is contingency being eroded?",
        "Who owes us money?",
    ]
    for ex in examples:
        if st.button(ex, use_container_width=True):
            st.session_state.pending = ex
    if st.button("Clear chat", type="secondary"):
        st.session_state.chat = []

st.title("📊 Portfolio Finance Agent")
st.caption("Answers come only from the monthly CVR reports. Synthetic data for Acme Engineering.")

st.session_state.setdefault("chat", [])  # list of (role, text, tool_calls)

for role, text, calls in st.session_state.chat:
    with st.chat_message(role):
        st.markdown(text)
        if calls:
            with st.expander(f"Tools used ({len(calls)})"):
                st.json(calls)

question = st.chat_input("Ask about margins, contingency, WIP or invoices…") or st.session_state.pop("pending", None)

if question:
    with st.chat_message("user"):
        st.markdown(question)
    history = [
        HumanMessage(t) if r == "user" else AIMessage(t) for r, t, _ in st.session_state.chat
    ]
    with st.chat_message("assistant"):
        with st.spinner("Checking the reports…"):
            try:
                out = ask(question, history=history, agent=get_agent())
                answer, calls = out["answer"], out["tool_calls"]
            except Exception as exc:
                answer, calls = f"Sorry, something went wrong: `{exc}`", []
        st.markdown(answer)
        if calls:
            with st.expander(f"Tools used ({len(calls)})"):
                st.json(calls)
    st.session_state.chat += [("user", question, []), ("assistant", answer, calls)]
