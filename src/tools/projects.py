"""Single-project tools: search, details and history."""

from __future__ import annotations

from src.storage.db import query
from src.tools.common import find_projects, records, resolve_project

HISTORY_FIELDS = {
    "total_revenue", "total_costs", "gross_margin", "gross_margin_percent", "monthly_movement",
    "cost_contingency", "cost_contingency_movement", "wip_due", "wip_overdue",
    "invoices_paid", "invoices_not_due", "invoices_overdue", "project_admin_cost",
}


def search_projects(text: str) -> dict:
    """
    Find projects by contract number, part of the project name, or client name.
    Use this first when the user mentions a project or client loosely (e.g. "the Kestrel job").

    Args:
        text: contract number, or a fragment of the project or client name.
    """
    return {"matches": records(find_projects(text))}


def project_details(project: str) -> dict:
    """
    Everything in the latest report for one project: client, lead, contract value,
    revenue, costs, margin, contingency, WIP and invoices.

    Args:
        project: contract number or a unique part of the project name.
    """
    contract, error = resolve_project(project)
    if error:
        return error
    # Totals and ratios are calculated here, so the model never has to do arithmetic itself.
    df = query(
        """
        SELECT *,
               invoices_paid + invoices_not_due + invoices_overdue AS total_invoiced,
               wip_due + wip_overdue AS total_wip,
               gross_margin_percent - planned_margin_percent AS variance_to_plan_points,
               contract_value - total_revenue AS contract_value_remaining,
               invoices_overdue / NULLIF(invoices_paid + invoices_not_due + invoices_overdue, 0) * 100
                   AS overdue_percent_of_invoiced,
               wip_overdue / NULLIF(wip_due + wip_overdue, 0) * 100 AS overdue_percent_of_wip,
               project_admin_cost / NULLIF(total_revenue, 0) * 100 AS admin_percent_of_revenue
        FROM latest WHERE contract_number = ?
        """,
        [contract],
    )
    return records(df)[0]


def project_history(project: str, fields: list[str] | None = None) -> dict:
    """
    Month-by-month history for one project, to see trends (e.g. how its margin or
    contingency changed over time).

    Args:
        project: contract number or a unique part of the project name.
        fields: which figures to include (default: margin %, gross margin, contingency,
            WIP overdue, invoices overdue). Allowed: total_revenue, total_costs, gross_margin,
            gross_margin_percent, monthly_movement, cost_contingency, cost_contingency_movement,
            wip_due, wip_overdue, invoices_paid, invoices_not_due, invoices_overdue,
            project_admin_cost.
    """
    contract, error = resolve_project(project)
    if error:
        return error
    fields = fields or ["gross_margin_percent", "gross_margin", "cost_contingency", "wip_overdue", "invoices_overdue"]
    unknown = [f for f in fields if f not in HISTORY_FIELDS]
    if unknown:
        return {"error": f"Unknown fields: {unknown}. Allowed: {sorted(HISTORY_FIELDS)}"}
    columns = ", ".join(["period"] + fields)  # safe: only whitelisted names
    df = query(f"SELECT {columns} FROM cvr WHERE contract_number = ? ORDER BY period", [contract])
    name = query("SELECT project_name FROM latest WHERE contract_number = ?", [contract])["project_name"].iloc[0]

    # First-to-last change for each figure, so the model never has to subtract.
    first, last = df.iloc[0], df.iloc[-1]
    change = {
        f: {
            "first_period": first["period"].strftime("%Y-%m-%d"),
            "first_value": round(float(first[f]), 2),
            "latest_value": round(float(last[f]), 2),
            "change": round(float(last[f] - first[f]), 2),
            "change_percent": round(float((last[f] - first[f]) / first[f] * 100), 1) if first[f] else None,
        }
        for f in fields
    }
    return {"contract_number": contract, "project_name": name, "change_over_period": change, "history": records(df)}
