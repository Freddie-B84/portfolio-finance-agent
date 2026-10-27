"""
Store extracted CVR rows in DuckDB so the tools can query them with SQL.

Build the database once (extraction takes a few seconds):
    python -m src.storage.db

Tables and views:
    cvr     one row per project per month (everything the extractor found)
    latest  each project's most recent month
"""

from __future__ import annotations

import os
from pathlib import Path

import duckdb
import pandas as pd

from src.extraction.pdf_parser import parse_folder

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REPORTS = ROOT / "data" / "reports"
DEFAULT_DB = Path(os.getenv("PORTFOLIO_DB", ROOT / "data" / "portfolio.duckdb"))


def build_database(reports_dir: str | Path = DEFAULT_REPORTS, db_path: str | Path = DEFAULT_DB) -> int:
    """Extract every PDF in reports_dir into a fresh DuckDB file. Returns the row count."""
    rows = parse_folder(reports_dir)
    if not rows:
        raise FileNotFoundError(f"No CVR PDFs found in {reports_dir}. Run data/generate_reports.py first.")

    df = pd.DataFrame(rows)
    df["period"] = pd.to_datetime(df["period"])
    df["completion_date"] = pd.to_datetime(df["completion_date"])

    db_path = Path(db_path)
    db_path.unlink(missing_ok=True)
    with duckdb.connect(str(db_path)) as con:
        con.register("df", df)
        con.execute("CREATE TABLE cvr AS SELECT * FROM df ORDER BY period, contract_number")
        con.execute("""
            CREATE VIEW latest AS
            SELECT * FROM cvr
            QUALIFY ROW_NUMBER() OVER (PARTITION BY contract_number ORDER BY period DESC) = 1
        """)
    return len(df)


def connect(db_path: str | Path = DEFAULT_DB, read_only: bool = True) -> duckdb.DuckDBPyConnection:
    """Open the database, building it first if it doesn't exist yet."""
    db_path = Path(db_path)
    if not db_path.exists():
        build_database(db_path=db_path)
    return duckdb.connect(str(db_path), read_only=read_only)


def query(sql: str, params: list | None = None, db_path: str | Path = DEFAULT_DB) -> pd.DataFrame:
    """Run a read-only query and return a DataFrame."""
    with connect(db_path) as con:
        return con.execute(sql, params or []).df()


if __name__ == "__main__":
    n = build_database()
    print(f"Built {DEFAULT_DB} with {n} project-months")
    print(query("SELECT MIN(period) AS first, MAX(period) AS last, COUNT(DISTINCT contract_number) AS projects FROM cvr"))
