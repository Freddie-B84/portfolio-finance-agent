"""
The tools must find exactly the problems the generator planted: no misses, no false alarms.
"""

import json

import pytest

from src.tools import (
    ALL_TOOLS,
    admin_cost_outliers,
    contingency_erosion_projects,
    declining_margin_projects,
    lowest_margin_projects,
    overdue_invoice_projects,
    overdue_wip_projects,
    portfolio_summary,
    project_details,
    project_history,
    risk_overview,
    search_projects,
    unbilled_revenue_projects,
)


def contracts(result: dict) -> set[str]:
    return {p["contract_number"] for p in result["projects"]}


@pytest.mark.parametrize("tool, scenario", [
    (declining_margin_projects, "margin_collapse"),
    (overdue_invoice_projects, "overdue_invoices"),
    (overdue_wip_projects, "wip_no_invoicing"),
    (unbilled_revenue_projects, "wip_no_invoicing"),
    (contingency_erosion_projects, "contingency_erosion"),
    (admin_cost_outliers, "admin_overrun"),
])
def test_tool_finds_exactly_the_planted_projects(tool, scenario, planted):
    assert contracts(tool()) == planted.get(scenario, set())


def test_lowest_margins_are_the_collapsing_projects(planted):
    collapsing = planted["margin_collapse"]
    worst = contracts(lowest_margin_projects(count=len(collapsing)))
    assert worst == collapsing


def test_risk_overview_covers_every_planted_problem(planted):
    flagged = contracts(risk_overview())
    every_problem = set().union(*(v for k, v in planted.items() if k != "healthy"))
    assert flagged == every_problem


def test_portfolio_summary(database):
    s = portfolio_summary()
    assert s["active_projects"] > 0
    assert s["gross_margin_percent"] == pytest.approx(s["gross_margin"] / s["total_revenue"] * 100, abs=0.01)


def any_contract() -> str:
    from src.storage.db import query

    return query("SELECT contract_number FROM latest ORDER BY contract_number LIMIT 1")["contract_number"].iloc[0]


def test_project_lookup_by_contract_number(database):
    contract = any_contract()
    assert search_projects(contract)["matches"][0]["contract_number"] == contract
    details = project_details(contract)
    assert details["contract_number"] == contract
    history = project_history(contract)["history"]
    assert len(history) >= 1 and history == sorted(history, key=lambda h: h["period"])


def test_unknown_project_returns_error_not_exception(database):
    assert "error" in project_details("no such project xyz")


def test_history_rejects_unknown_fields(database):
    assert "error" in project_history(any_contract(), fields=["DROP TABLE cvr"])


@pytest.mark.parametrize("tool", ALL_TOOLS, ids=lambda t: t.__name__)
def test_every_tool_has_a_docstring_for_the_llm(tool):
    assert tool.__doc__ and len(tool.__doc__.strip()) > 40


def test_results_are_json_serialisable(database):
    for tool in [portfolio_summary, risk_overview, lowest_margin_projects]:
        json.dumps(tool())


def test_project_tools_return_totals_so_the_model_never_does_maths(database):
    contract = any_contract()
    d = project_details(contract)
    assert d["total_invoiced"] == pytest.approx(d["invoices_paid"] + d["invoices_not_due"] + d["invoices_overdue"], abs=0.02)
    h = project_history(contract, fields=["cost_contingency"])
    c = h["change_over_period"]["cost_contingency"]
    assert c["change"] == pytest.approx(c["latest_value"] - c["first_value"], abs=0.02)
