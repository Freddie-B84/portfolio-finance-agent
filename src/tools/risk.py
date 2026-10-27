"""Risk tools: contingency, admin cost, and a combined risk overview."""

from __future__ import annotations

from src.storage.db import query
from src.tools.common import latest_period, records
from src.tools.margins import declining_margin_projects
from src.tools.wip_invoices import overdue_invoice_projects, overdue_wip_projects, unbilled_revenue_projects


def contingency_erosion_projects(min_drop_percent: float = 50.0) -> dict:
    """
    Projects that have used up a large share of their cost contingency since their first report.
    Contingency is the risk budget; when it's gone, any further problem hits margin directly.

    Use for "Where is contingency being eroded?", "Which projects have used their risk budget?".

    Args:
        min_drop_percent: minimum % of the starting contingency used (default 50).
    """
    df = query(
        """
        WITH first_month AS (
            SELECT contract_number, cost_contingency AS contingency_start
            FROM cvr
            QUALIFY ROW_NUMBER() OVER (PARTITION BY contract_number ORDER BY period) = 1
        )
        SELECT l.contract_number, l.project_name, l.client, l.sector,
               f.contingency_start, l.cost_contingency AS contingency_now,
               (1 - l.cost_contingency / NULLIF(f.contingency_start, 0)) * 100 AS percent_used
        FROM latest l JOIN first_month f USING (contract_number)
        WHERE (1 - l.cost_contingency / NULLIF(f.contingency_start, 0)) * 100 >= ?
        ORDER BY percent_used DESC
        """,
        [min_drop_percent],
    )
    return {"as_of": latest_period(), "projects": records(df)}


def admin_cost_outliers(max_admin_percent: float = 8.0) -> dict:
    """
    Projects whose project admin cost is unusually high relative to revenue (normal is 2-4%).

    Use for "Which projects have high admin costs?", "Overheads out of line".

    Args:
        max_admin_percent: flag projects where admin cost / revenue is above this % (default 8).
    """
    df = query(
        """
        SELECT contract_number, project_name, client, sector,
               project_admin_cost, total_revenue,
               project_admin_cost / NULLIF(total_revenue, 0) * 100 AS admin_percent_of_revenue
        FROM latest
        WHERE project_admin_cost / NULLIF(total_revenue, 0) * 100 > ?
        ORDER BY admin_percent_of_revenue DESC
        """,
        [max_admin_percent],
    )
    portfolio_avg = query(
        "SELECT SUM(project_admin_cost) / SUM(total_revenue) * 100 AS pct FROM latest"
    )["pct"].iloc[0]
    return {
        "as_of": latest_period(),
        "portfolio_admin_percent": round(float(portfolio_avg), 2),
        "projects": records(df),
    }


def risk_overview() -> dict:
    """
    One list of every project with at least one warning sign, and which signs it has:
    loss-making, declining margin, contingency erosion, overdue invoices, overdue WIP,
    unbilled revenue, high admin cost.

    Use for broad questions: "What should I be worried about?", "Give me the risk register",
    "Which projects need attention?".
    """
    flags: dict[str, dict] = {}

    def add(result: dict, flag: str) -> None:
        for p in result["projects"]:
            entry = flags.setdefault(p["contract_number"], {
                "contract_number": p["contract_number"],
                "project_name": p["project_name"],
                "client": p["client"],
                "flags": [],
            })
            if flag not in entry["flags"]:
                entry["flags"].append(flag)

    loss = query("SELECT contract_number, project_name, client FROM latest WHERE gross_margin_percent < 0")
    add({"projects": records(loss)}, "loss_making")
    add(declining_margin_projects(), "declining_margin")
    add(contingency_erosion_projects(), "contingency_erosion")
    add(overdue_invoice_projects(), "overdue_invoices")
    add(overdue_wip_projects(), "overdue_wip")
    add(unbilled_revenue_projects(), "unbilled_revenue")
    add(admin_cost_outliers(), "high_admin_cost")

    projects = sorted(flags.values(), key=lambda e: (-len(e["flags"]), e["project_name"]))
    return {"as_of": latest_period(), "projects_with_flags": len(projects), "projects": projects}
