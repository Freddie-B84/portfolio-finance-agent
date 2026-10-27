"""Work in progress (WIP) and invoicing tools: where is cash stuck?"""

from __future__ import annotations

from src.storage.db import query
from src.tools.common import latest_period, records


def overdue_invoice_projects(min_overdue_share: float = 0.10) -> dict:
    """
    Projects where a large share of everything invoiced is overdue (the client isn't paying).

    Use for "Who owes us money?", "Which projects have overdue invoices?", "Cash collection problems".

    Args:
        min_overdue_share: overdue invoices / total invoiced, between 0 and 1 (default 0.10 = 10%).
    """
    df = query(
        """
        SELECT contract_number, project_name, client, sector,
               invoices_overdue,
               invoices_paid + invoices_not_due + invoices_overdue AS total_invoiced,
               invoices_overdue / NULLIF(invoices_paid + invoices_not_due + invoices_overdue, 0) * 100
                   AS overdue_percent_of_invoiced
        FROM latest
        WHERE invoices_overdue / NULLIF(invoices_paid + invoices_not_due + invoices_overdue, 0) >= ?
        ORDER BY invoices_overdue DESC
        """,
        [min_overdue_share],
    )
    return {"as_of": latest_period(), "projects": records(df)}


def overdue_wip_projects(min_overdue_share: float = 0.50) -> dict:
    """
    Projects where most work in progress (work done but not yet invoiced) is overdue for billing.

    Use for "Where is WIP overdue?", "Which projects haven't billed for work done?".

    Args:
        min_overdue_share: WIP overdue / total WIP, between 0 and 1 (default 0.50 = 50%).
    """
    df = query(
        """
        SELECT contract_number, project_name, client, sector,
               wip_due, wip_overdue,
               wip_overdue / NULLIF(wip_due + wip_overdue, 0) * 100 AS overdue_percent_of_wip
        FROM latest
        WHERE wip_overdue / NULLIF(wip_due + wip_overdue, 0) >= ?
        ORDER BY wip_overdue DESC
        """,
        [min_overdue_share],
    )
    return {"as_of": latest_period(), "projects": records(df)}


def unbilled_revenue_projects(months: int = 3) -> dict:
    """
    Projects that kept earning revenue over the last `months` months but raised (almost) no new
    invoices in that time - money earned that the client hasn't been billed for.

    Use for "Revenue with no invoicing", "Who is doing work but not billing?".

    Args:
        months: look-back window in months (default 3).
    """
    df = query(
        """
        WITH bounds AS (SELECT MAX(period) AS last_p FROM cvr),
        base AS (
            SELECT c.contract_number, c.total_revenue AS revenue_before,
                   c.invoices_paid + c.invoices_not_due + c.invoices_overdue AS invoiced_before
            FROM cvr c, bounds b
            WHERE c.period = b.last_p - (? * INTERVAL 1 MONTH)
        )
        SELECT l.contract_number, l.project_name, l.client, l.sector,
               l.total_revenue - base.revenue_before AS revenue_added,
               (l.invoices_paid + l.invoices_not_due + l.invoices_overdue) - base.invoiced_before
                   AS invoiced_added
        FROM latest l JOIN base USING (contract_number)
        WHERE l.total_revenue - base.revenue_before > 0
          AND (l.invoices_paid + l.invoices_not_due + l.invoices_overdue) - base.invoiced_before
              < 0.10 * (l.total_revenue - base.revenue_before)
        ORDER BY revenue_added DESC
        """,
        [months],
    )
    return {"as_of": latest_period(), "window_months": months, "projects": records(df)}
