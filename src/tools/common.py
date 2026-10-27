"""Shared helpers for the analysis tools."""

from __future__ import annotations

import math
from datetime import date, datetime

import pandas as pd

from src.storage.db import query

# Columns most tools include when listing projects
ID_COLUMNS = ["contract_number", "project_name", "client", "sector"]


def latest_period() -> str:
    return str(query("SELECT MAX(period) AS p FROM cvr")["p"].iloc[0].date())


def records(df: pd.DataFrame) -> list[dict]:
    """DataFrame -> list of plain dicts with rounded numbers and ISO dates (JSON friendly)."""
    out = []
    for row in df.to_dict(orient="records"):
        clean = {}
        for key, value in row.items():
            if isinstance(value, (pd.Timestamp, datetime, date)):
                clean[key] = value.strftime("%Y-%m-%d")
            elif isinstance(value, float):
                clean[key] = None if math.isnan(value) else round(value, 2)
            else:
                clean[key] = value
        out.append(clean)
    return out


def find_projects(text: str) -> pd.DataFrame:
    """Match a contract number exactly, or a name/client fragment case-insensitively."""
    text = text.strip()
    return query(
        """
        SELECT contract_number, project_name, client, sector
        FROM latest
        WHERE contract_number = ? OR project_name ILIKE ? OR client ILIKE ?
        ORDER BY project_name
        """,
        [text, f"%{text}%", f"%{text}%"],
    )


def resolve_project(text: str) -> tuple[str | None, dict | None]:
    """Return (contract_number, None) for a unique match, else (None, error payload)."""
    matches = find_projects(text)
    if len(matches) == 1:
        return matches["contract_number"].iloc[0], None
    if matches.empty:
        return None, {"error": f"No project matches '{text}'. Try search_projects first."}
    return None, {
        "error": f"'{text}' matches {len(matches)} projects. Ask the user which one, or use a contract number.",
        "candidates": records(matches),
    }
