"""Gross margin tools."""

from __future__ import annotations

from src.storage.db import query
from src.tools.common import latest_period, records

_MARGIN_COLUMNS = """
    contract_number, project_name, client, sector,
    total_revenue, gross_margin, gross_margin_percent, planned_margin_percent,
    gross_margin_percent - planned_margin_percent AS variance_to_plan_points
"""


def lowest_margin_projects(count: int = 5) -> dict:
    """
    Projects with the lowest gross margin % in the latest report (worst performers).

    Use for "Which projects are losing money?", "Bottom performers by margin".

    Args:
        count: how many projects to return (default 5).
    """
    df = query(f"SELECT {_MARGIN_COLUMNS} FROM latest ORDER BY gross_margin_percent ASC LIMIT ?", [count])
    return {"as_of": latest_period(), "projects": records(df)}


def highest_margin_projects(count: int = 5) -> dict:
    """
    Projects with the highest gross margin % in the latest report (best performers).

    Args:
        count: how many projects to return (default 5).
    """
    df = query(f"SELECT {_MARGIN_COLUMNS} FROM latest ORDER BY gross_margin_percent DESC LIMIT ?", [count])
    return {"as_of": latest_period(), "projects": records(df)}


def declining_margin_projects(months: int = 3, min_drop_points: float = 3.0) -> dict:
    """
    Projects whose gross margin % has fallen by at least `min_drop_points` percentage points
    over the last `months` months. This catches problems early, before a project is loss-making.

    Use for "Which projects are getting worse?", "Where is margin slipping?".

    Args:
        months: look-back window in months (default 3).
        min_drop_points: minimum fall in margin percentage points (default 3).
    """
    df = query(
        """
        WITH bounds AS (SELECT MAX(period) AS last_p FROM cvr),
        base AS (
            SELECT c.contract_number, c.gross_margin_percent AS margin_before
            FROM cvr c, bounds b
            WHERE c.period = b.last_p - (? * INTERVAL 1 MONTH)
        )
        SELECT l.contract_number, l.project_name, l.client, l.sector,
               base.margin_before, l.gross_margin_percent AS margin_now,
               l.gross_margin_percent - base.margin_before AS change_points
        FROM latest l JOIN base USING (contract_number)
        WHERE base.margin_before - l.gross_margin_percent >= ?
        ORDER BY change_points ASC
        """,
        [months, min_drop_points],
    )
    return {"as_of": latest_period(), "window_months": months, "projects": records(df)}
