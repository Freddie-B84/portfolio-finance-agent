from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
TRUTH = ROOT / "data" / "ground_truth.csv"


@pytest.fixture(scope="session")
def database():
    """Rebuild the DuckDB file from the current PDFs once per test run."""
    if not TRUTH.exists():
        pytest.skip("Run `python data/generate_reports.py` first")
    from src.storage.db import build_database

    build_database()


@pytest.fixture(scope="session")
def planted(database) -> dict[str, set[str]]:
    """scenario -> set of contract numbers, from the generator's answer key."""
    truth = pd.read_csv(TRUTH, dtype={"contract_number": str})
    return truth.groupby("scenario")["contract_number"].apply(set).to_dict()
