"""Portfolio-level tools."""

from __future__ import annotations

from src.storage.db import query
from src.tools.common import latest_period, records


def portfolio_summary(period: str | None = None) -> dict:
    """
    Headline financial health of the whole portfolio for one month.

    Use for questions like "How is the portfolio doing?", "What's our overall margin?",
    "How much is overdue across all projects?".

    Args:
        period: month as YYYY-MM-DD (first of the month). Defaults to the latest report.
    """
    period = period or latest_period()
    df = query(
        """
        SELECT
            COUNT(*)                                   AS active_projects,
            SUM(total_revenue)                         AS total_revenue,
            SUM(total_costs)                           AS total_costs,
            SUM(gross_margin)                          AS gross_margin,
            SUM(gross_margin) / SUM(total_revenue) * 100 AS gross_margin_percent,
            SUM(cost_contingency)                      AS cost_contingency,
            SUM(wip_due)                               AS wip_due,
            SUM(wip_overdue)                           AS wip_overdue,
            SUM(invoices_overdue)                      AS invoices_overdue,
            CAST(SUM(CASE WHEN gross_margin_percent < 0 THEN 1 ELSE 0 END) AS INTEGER) AS loss_making_projects
        FROM cvr WHERE period = CAST(? AS DATE)
        """,
        [period],
    )
    if df["active_projects"].iloc[0] == 0:
        return {"error": f"No reports for period {period}."}
    return {"period": period, **records(df)[0]}


def portfolio_trend() -> dict:
    """
    Month-by-month portfolio totals: revenue, gross margin %, contingency and overdue amounts.

    Use for "How has the portfolio changed over the year?" or "Is margin improving?".
    """
    df = query(
        """
        SELECT period,
               COUNT(*) AS active_projects,
               SUM(total_revenue) AS total_revenue,
               SUM(gross_margin) / SUM(total_revenue) * 100 AS gross_margin_percent,
               SUM(cost_contingency) AS cost_contingency,
               SUM(wip_overdue) AS wip_overdue,
               SUM(invoices_overdue) AS invoices_overdue
        FROM cvr GROUP BY period ORDER BY period
        """
    )
    return {"months": records(df)}
