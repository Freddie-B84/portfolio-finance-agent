"""
Turn the monthly CVR PDFs into structured rows.

Each PDF has one page per project. Each page has:
  - header text:  "Contract: 40100 Larkspur Clean Room Fit-Out"
                  "CVR: 12 December 2025"
  - three 2-column tables (label | value): Project Details,
    Financial Summary, and WIP & Invoicing

parse_folder("data/reports") returns one dict per project per month.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from pathlib import Path

import pdfplumber

# Label printed in the PDF (lower case) -> field name in our data
LABELS = {
    # Project Details
    "client": "client",
    "sector": "sector",
    "location": "location",
    "project lead": "project_lead",
    "fee manager": "fee_manager",
    "reimbursement mechanism": "reimbursement_mechanism",
    "contract value": "contract_value",
    "current completion date": "completion_date",
    # Financial Summary
    "total revenue": "total_revenue",
    "total costs": "total_costs",
    "gross margin": "gross_margin",
    "gross margin %": "gross_margin_percent",
    "planned margin %": "planned_margin_percent",
    "monthly movement": "monthly_movement",
    "cost contingency": "cost_contingency",
    "cost contingency movement": "cost_contingency_movement",
    "project admin cost": "project_admin_cost",
    # WIP & Invoicing
    "wip due": "wip_due",
    "wip overdue": "wip_overdue",
    "invoices raised - paid": "invoices_paid",
    "invoices raised - not due": "invoices_not_due",
    "invoices raised - overdue": "invoices_overdue",
}

TEXT_FIELDS = {"client", "sector", "location", "project_lead", "fee_manager", "reimbursement_mechanism"}
DATE_FIELDS = {"completion_date"}

CONTRACT_RE = re.compile(r"Contract:\s*(\d+)\s+(.+)")
PERIOD_RE = re.compile(r"CVR:\s*\d+\s+([A-Za-z]+ \d{4})")


class ExtractionError(ValueError):
    """Raised when a page doesn't look like a CVR page."""


def parse_money(text: str) -> float:
    """'£1,575,767' -> 1575767.0 and '-£485' -> -485.0"""
    cleaned = text.strip()
    negative = cleaned.startswith("-")
    number = float(cleaned.replace("-", "").replace("£", "").replace(",", ""))
    return -number if negative else number


def parse_percent(text: str) -> float:
    """'29.4%' -> 29.4"""
    return float(text.strip().rstrip("%"))


def _convert(field: str, value: str):
    if field in TEXT_FIELDS:
        return value.strip()
    if field in DATE_FIELDS:
        return datetime.strptime(value.strip(), "%d/%m/%Y").date()
    if field.endswith("_percent"):
        return parse_percent(value)
    return parse_money(value)


def parse_page(page) -> dict:
    """Extract one project's figures from one PDF page."""
    text = page.extract_text() or ""

    contract = CONTRACT_RE.search(text)
    period = PERIOD_RE.search(text)
    if not contract or not period:
        raise ExtractionError(f"page {page.page_number}: no Contract/CVR header found")

    row: dict = {
        "contract_number": contract.group(1),
        "project_name": contract.group(2).strip(),
        "period": datetime.strptime(period.group(1), "%B %Y").date(),
    }

    for table in page.extract_tables():
        for cells in table[1:]:  # first row is the table header
            if not cells or len(cells) < 2 or cells[0] is None or cells[1] is None:
                continue
            field = LABELS.get(cells[0].strip().lower())
            if field:
                row[field] = _convert(field, cells[1])

    return row


def parse_report(path: str | Path) -> list[dict]:
    """All pages of one PDF."""
    with pdfplumber.open(path) as pdf:
        return [parse_page(page) for page in pdf.pages]


def parse_folder(folder: str | Path) -> list[dict]:
    """All PDFs in a folder, oldest first (file names start with YYYY-MM)."""
    rows: list[dict] = []
    for pdf_path in sorted(Path(folder).glob("*.pdf")):
        rows.extend(parse_report(pdf_path))
    return rows


if __name__ == "__main__":
    import sys

    folder = sys.argv[1] if len(sys.argv) > 1 else "data/reports"
    rows = parse_folder(folder)
    print(f"Extracted {len(rows)} project-months from {folder}")
    if rows:
        print(rows[-1])
