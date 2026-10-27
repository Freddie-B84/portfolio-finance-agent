"""
Generate fake monthly Cost Value Reconciliation (CVR) reports for a fictional
engineering consultancy, "Acme Engineering".

Every name, client and number here is invented. The data is simulated so that
specific projects develop specific problems over time (collapsing margin,
overdue invoices, contingency erosion...). Those problems are written to
`ground_truth.csv`, which the tests and the evaluation script use to check
that the extractor and the agent find the right projects.

Usage:
    python data/generate_reports.py                 # 12 months, 25 projects
    python data/generate_reports.py --months 6 --projects 10 --seed 7
"""

from __future__ import annotations

import argparse
import csv
import random
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

# --------------------------------------------------------------------------
# Fictional reference data
# --------------------------------------------------------------------------

CLIENT_SECTORS = {
    "Northgate Water Ltd": "Water",
    "Harbourline Rail": "Rail",
    "Crestview Energy": "Energy",
    "Silverbrook Council": "Public Sector",
    "Meridian Pharma": "Life Sciences",
    "Oakridge Housing Trust": "Public Sector",
    "Bluewater Ports": "Maritime",
    "Kestrel Aerospace": "Defence",
    "Fenwick Highways Agency": "Highways",
    "Larkspur Nuclear Services": "Nuclear",
}
CLIENTS = list(CLIENT_SECTORS)
LOCATIONS = ["Leeds", "Bristol", "Glasgow", "Manchester", "Cardiff", "Birmingham", "Newcastle", "London"]
PEOPLE = [
    "A. Morgan", "J. Patel", "S. Okafor", "L. Fraser", "R. Kowalski", "E. Nakamura",
    "D. Byrne", "H. Ahmed", "C. Lindqvist", "M. Rossi", "T. Adeyemi", "K. Walsh",
]
MECHANISMS = ["Lump Sum", "Time & Materials", "Target Cost", "Cost Reimbursable"]
PROJECT_TYPES = [
    "Treatment Works Upgrade", "Signalling Renewal", "Substation Design", "Depot Redevelopment",
    "Clean Room Fit-Out", "Bridge Strengthening", "Flood Defence Scheme", "Pipeline Diversion",
    "Control Room Upgrade", "Station Accessibility", "Battery Storage Site", "Lab Expansion",
]

# Problems a project can develop. "healthy" means none.
SCENARIOS = [
    "margin_collapse",       # forecast margin falls steadily month after month
    "overdue_invoices",      # invoices raised but not paid, overdue balance grows
    "contingency_erosion",   # cost contingency is consumed quickly
    "wip_no_invoicing",      # revenue recognised but nothing invoiced, WIP goes overdue
    "admin_overrun",         # project admin cost far above the norm
]


@dataclass
class Project:
    contract_number: str
    name: str
    client: str
    sector: str
    location: str
    project_lead: str
    fee_manager: str
    mechanism: str
    contract_value: float
    planned_margin: float          # e.g. 0.22 for 22%
    start_month: int               # index of the first month with activity
    duration_months: int
    completion_date: date
    scenario: str = "healthy"
    # running state
    revenue: float = 0.0
    costs: float = 0.0
    contingency: float = 0.0
    invoiced_paid: float = 0.0
    invoiced_not_due: float = 0.0
    invoiced_overdue: float = 0.0
    admin_cost: float = 0.0
    history: list[dict] = field(default_factory=list)


def month_start(base: date, offset: int) -> date:
    year = base.year + (base.month - 1 + offset) // 12
    month = (base.month - 1 + offset) % 12 + 1
    return date(year, month, 1)


def build_projects(n: int, n_months: int, start: date, rng: random.Random) -> list[Project]:
    projects = []
    # Roughly a third of projects get a problem; each scenario appears at least once.
    scenario_pool = SCENARIOS + [rng.choice(SCENARIOS) for _ in range(max(0, n // 3 - len(SCENARIOS)))]
    scenario_pool += ["healthy"] * (n - len(scenario_pool))
    rng.shuffle(scenario_pool)

    used_names = set()
    for i in range(n):
        client = rng.choice(CLIENTS)
        while True:
            name = f"{client.split()[0]} {rng.choice(PROJECT_TYPES)}"
            if name not in used_names:
                used_names.add(name)
                break
        start_month = rng.randint(0, max(0, n_months // 3))
        duration = rng.randint(n_months, n_months + 12)
        value = round(rng.uniform(250_000, 4_000_000), -3)
        projects.append(Project(
            contract_number=str(40100 + i * 7),
            name=name,
            client=client,
            sector=CLIENT_SECTORS[client],
            location=rng.choice(LOCATIONS),
            project_lead=rng.choice(PEOPLE),
            fee_manager=rng.choice(PEOPLE),
            mechanism=rng.choice(MECHANISMS),
            contract_value=value,
            planned_margin=rng.uniform(0.16, 0.30),
            start_month=start_month,
            duration_months=duration,
            completion_date=month_start(start, start_month + duration),
            scenario=scenario_pool[i],
            contingency=value * rng.uniform(0.04, 0.08),
        ))
    return projects


def simulate_month(p: Project, m: int, rng: random.Random) -> dict | None:
    """Advance one project by one month and return that month's CVR figures."""
    if m < p.start_month:
        return None
    active = m - p.start_month  # months since the project started

    # Revenue earned this month (S-curve-ish progress with noise)
    monthly_revenue = p.contract_value / p.duration_months * rng.uniform(0.7, 1.3)
    if active == 0:
        monthly_revenue *= 0.5

    # Margin this month depends on the scenario
    margin = p.planned_margin + rng.uniform(-0.03, 0.03)
    if p.scenario == "margin_collapse":
        margin = p.planned_margin - 0.06 * active  # drops ~6 points a month
    monthly_costs = monthly_revenue * (1 - margin)

    p.revenue += monthly_revenue
    p.costs += monthly_costs

    # Contingency use
    contingency_before = p.contingency
    use = p.contingency * rng.uniform(0.0, 0.05)
    if p.scenario == "contingency_erosion":
        use = p.contingency * rng.uniform(0.25, 0.40)
    elif rng.random() < 0.1:  # occasionally a healthy project adds contingency
        use = -p.contract_value * rng.uniform(0.002, 0.006)
    p.contingency = max(0.0, p.contingency - use)

    # Invoicing: last month's "not due" becomes paid or overdue
    if p.scenario == "overdue_invoices":
        p.invoiced_overdue += p.invoiced_not_due * 0.85
        p.invoiced_paid += p.invoiced_not_due * 0.15
    else:
        late = p.invoiced_not_due * rng.uniform(0.0, 0.08)
        p.invoiced_overdue = p.invoiced_overdue * 0.5 + late  # old overdue gets chased and paid
        p.invoiced_paid += p.invoiced_not_due - late
    invoice_now = 0.0 if p.scenario == "wip_no_invoicing" else monthly_revenue * rng.uniform(0.85, 1.05)
    p.invoiced_not_due = invoice_now

    invoiced_total = p.invoiced_paid + p.invoiced_not_due + p.invoiced_overdue
    wip = max(0.0, p.revenue - invoiced_total)
    if p.scenario == "wip_no_invoicing":
        wip_overdue = wip * min(0.9, 0.3 + 0.15 * active)
        wip_due = wip - wip_overdue
    else:
        wip_overdue = wip * rng.uniform(0.0, 0.15)
        wip_due = wip - wip_overdue

    # Admin cost: normally ~2-4% of monthly revenue
    admin_rate = rng.uniform(0.02, 0.04) if p.scenario != "admin_overrun" else rng.uniform(0.12, 0.18)
    p.admin_cost += monthly_revenue * admin_rate

    gross_margin = p.revenue - p.costs
    forecast_gm_pct = (gross_margin / p.revenue * 100) if p.revenue else 0.0
    previous_gm = p.history[-1]["gross_margin"] if p.history else 0.0

    row = {
        "monthly_revenue": monthly_revenue,
        "total_revenue": p.revenue,
        "total_costs": p.costs,
        "gross_margin": gross_margin,
        "gross_margin_percent": forecast_gm_pct,
        "planned_margin_percent": p.planned_margin * 100,
        "monthly_movement": gross_margin - previous_gm,
        "cost_contingency": p.contingency,
        "cost_contingency_movement": p.contingency - contingency_before,
        "wip_due": wip_due,
        "wip_overdue": wip_overdue,
        "invoices_paid": p.invoiced_paid,
        "invoices_not_due": p.invoiced_not_due,
        "invoices_overdue": p.invoiced_overdue,
        "project_admin_cost": p.admin_cost,
    }
    p.history.append(row)
    return row


# --------------------------------------------------------------------------
# PDF rendering
# --------------------------------------------------------------------------

def money(x: float) -> str:
    return f"£{x:,.0f}" if x >= 0 else f"-£{abs(x):,.0f}"


def project_page(p: Project, period: date, cvr_no: int, row: dict, styles) -> list:
    header = [
        Paragraph("<b>ACME ENGINEERING LTD</b> &nbsp;&nbsp; Cost Value Reconciliation", styles["Title"]),
        Paragraph(f"Contract: {p.contract_number} {p.name}", styles["Heading2"]),
        Paragraph(f"CVR: {cvr_no} {period.strftime('%B %Y')}", styles["Normal"]),
        Spacer(1, 4 * mm),
    ]

    details = Table([
        ["Project Details", ""],
        ["Client", p.client],
        ["Sector", p.sector],
        ["Location", p.location],
        ["Project Lead", p.project_lead],
        ["Fee Manager", p.fee_manager],
        ["Reimbursement Mechanism", p.mechanism],
        ["Contract Value", money(p.contract_value)],
        ["Current Completion Date", p.completion_date.strftime("%d/%m/%Y")],
    ], colWidths=[70 * mm, 100 * mm])

    finance = Table([
        ["Financial Summary (cumulative)", "Value"],
        ["Total Revenue", money(row["total_revenue"])],
        ["Total Costs", money(row["total_costs"])],
        ["Gross Margin", money(row["gross_margin"])],
        ["Gross Margin %", f"{row['gross_margin_percent']:.1f}%"],
        ["Planned Margin %", f"{row['planned_margin_percent']:.1f}%"],
        ["Monthly Movement", money(row["monthly_movement"])],
        ["Cost Contingency", money(row["cost_contingency"])],
        ["Cost Contingency Movement", money(row["cost_contingency_movement"])],
        ["Project Admin Cost", money(row["project_admin_cost"])],
    ], colWidths=[70 * mm, 100 * mm])

    cash = Table([
        ["WIP & Invoicing", "Value"],
        ["WIP Due", money(row["wip_due"])],
        ["WIP Overdue", money(row["wip_overdue"])],
        ["Invoices Raised - Paid", money(row["invoices_paid"])],
        ["Invoices Raised - Not Due", money(row["invoices_not_due"])],
        ["Invoices Raised - Overdue", money(row["invoices_overdue"])],
    ], colWidths=[70 * mm, 100 * mm])

    style = TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1F3864")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ALIGN", (1, 1), (1, -1), "RIGHT"),
    ])
    for t in (details, finance, cash):
        t.setStyle(style)

    return header + [details, Spacer(1, 5 * mm), finance, Spacer(1, 5 * mm), cash, PageBreak()]


def render_month(path: Path, period: date, cvr_no: int, rows: list[tuple[Project, dict]]) -> None:
    styles = getSampleStyleSheet()
    doc = SimpleDocTemplate(str(path), pagesize=A4, title=f"Acme CVR {period:%B %Y}",
                            leftMargin=18 * mm, rightMargin=18 * mm, topMargin=15 * mm, bottomMargin=15 * mm)
    story = []
    for p, row in rows:
        story += project_page(p, period, cvr_no, row, styles)
    doc.build(story)


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--months", type=int, default=12)
    ap.add_argument("--projects", type=int, default=25)
    ap.add_argument("--start", default="2025-01", help="first report month, YYYY-MM")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", default=str(Path(__file__).parent / "reports"))
    args = ap.parse_args()

    rng = random.Random(args.seed)
    start = date(int(args.start[:4]), int(args.start[5:7]), 1)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    projects = build_projects(args.projects, args.months, start, rng)
    truth_rows = []

    for m in range(args.months):
        period = month_start(start, m)
        month_rows = []
        for p in projects:
            row = simulate_month(p, m, rng)
            if row is None:
                continue
            month_rows.append((p, row))
            truth_rows.append({
                "period": period.isoformat(), "contract_number": p.contract_number,
                "project_name": p.name, "client": p.client, "sector": p.sector,
                "scenario": p.scenario, **{k: round(v, 2) for k, v in row.items()},
            })
        filename = out / f"{period:%Y-%m} - Acme - CVR - {period:%B %Y}.pdf"
        render_month(filename, period, m + 1, month_rows)
        print(f"wrote {filename.name} ({len(month_rows)} projects)")

    truth_path = out.parent / "ground_truth.csv"
    with truth_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(truth_rows[0].keys()))
        writer.writeheader()
        writer.writerows(truth_rows)
    problems = {p.name: p.scenario for p in projects if p.scenario != "healthy"}
    print(f"wrote {truth_path.name}; {len(problems)} projects with planted problems:")
    for name, scenario in sorted(problems.items(), key=lambda kv: kv[1]):
        print(f"  {scenario:<22} {name}")


if __name__ == "__main__":
    main()
