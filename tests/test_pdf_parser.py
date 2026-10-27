"""
Tests for step 2: the PDF extractor.

Run from the project root:
    python data/generate_reports.py   # once, to create the PDFs
    pytest -v
"""

from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from src.extraction.pdf_parser import parse_folder, parse_money, parse_percent, parse_report

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "data" / "reports"
TRUTH = ROOT / "data" / "ground_truth.csv"

pytestmark = pytest.mark.skipif(
    not TRUTH.exists(), reason="Run `python data/generate_reports.py` first"
)


# ---- 1. Small helpers -------------------------------------------------------

@pytest.mark.parametrize("text, expected", [
    ("£1,575,767", 1575767.0),
    ("£0", 0.0),
    ("-£485", -485.0),
    (" £12,000 ", 12000.0),
])
def test_parse_money(text, expected):
    assert parse_money(text) == expected


@pytest.mark.parametrize("text, expected", [
    ("29.4%", 29.4),
    ("-12.5%", -12.5),
    ("0.0%", 0.0),
])
def test_parse_percent(text, expected):
    assert parse_percent(text) == expected


# ---- 2. One report ----------------------------------------------------------

@pytest.fixture(scope="module")
def december():
    pdf = next(REPORTS.glob("2025-12*.pdf"))
    return parse_report(pdf)


def test_one_row_per_page(december):
    truth = pd.read_csv(TRUTH)
    assert len(december) == (truth.period == "2025-12-01").sum()


def test_row_has_all_fields(december):
    expected = {
        "contract_number", "project_name", "period", "client", "sector", "location",
        "project_lead", "fee_manager", "reimbursement_mechanism", "contract_value",
        "completion_date", "total_revenue", "total_costs", "gross_margin",
        "gross_margin_percent", "planned_margin_percent", "monthly_movement",
        "cost_contingency", "cost_contingency_movement", "project_admin_cost",
        "wip_due", "wip_overdue", "invoices_paid", "invoices_not_due", "invoices_overdue",
    }
    missing = expected - set(december[0])
    assert not missing, f"missing fields: {sorted(missing)}"


def test_types(december):
    row = december[0]
    assert isinstance(row["contract_number"], str)
    assert isinstance(row["period"], date) and row["period"] == date(2025, 12, 1)
    assert isinstance(row["completion_date"], date)
    assert isinstance(row["total_revenue"], float)
    assert isinstance(row["gross_margin_percent"], float)


# ---- 3. Every report, checked against the answer key ------------------------

@pytest.fixture(scope="module")
def all_rows():
    df = pd.DataFrame(parse_folder(REPORTS))
    df["period"] = pd.to_datetime(df["period"]).dt.strftime("%Y-%m-%d")
    return df


def test_row_count_matches_truth(all_rows):
    assert len(all_rows) == len(pd.read_csv(TRUTH))


@pytest.mark.parametrize("field", [
    "total_revenue", "total_costs", "gross_margin", "cost_contingency",
    "wip_overdue", "invoices_overdue", "project_admin_cost",
])
def test_money_matches_truth(all_rows, field):
    truth = pd.read_csv(TRUTH, dtype={"contract_number": str})
    merged = truth.merge(all_rows, on=["period", "contract_number"], suffixes=("_true", "_pdf"))
    assert len(merged) == len(truth), "some rows did not match on period + contract_number"
    # PDFs show whole pounds, so allow up to £1 of rounding
    diff = (merged[f"{field}_true"] - merged[f"{field}_pdf"]).abs()
    assert diff.max() <= 1.0, f"{field}: worst difference £{diff.max():,.2f}"


def test_margin_percent_matches_truth(all_rows):
    truth = pd.read_csv(TRUTH, dtype={"contract_number": str})
    merged = truth.merge(all_rows, on=["period", "contract_number"], suffixes=("_true", "_pdf"))
    # PDFs show one decimal place
    diff = (merged["gross_margin_percent_true"] - merged["gross_margin_percent_pdf"]).abs()
    assert diff.max() <= 0.051
