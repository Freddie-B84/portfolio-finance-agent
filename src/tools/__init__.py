"""All analysis tools the agent can call. Each is a plain Python function returning a dict."""

from src.tools.margins import declining_margin_projects, highest_margin_projects, lowest_margin_projects
from src.tools.portfolio import portfolio_summary, portfolio_trend
from src.tools.projects import project_details, project_history, search_projects
from src.tools.risk import admin_cost_outliers, contingency_erosion_projects, risk_overview
from src.tools.wip_invoices import overdue_invoice_projects, overdue_wip_projects, unbilled_revenue_projects

ALL_TOOLS = [
    portfolio_summary,
    portfolio_trend,
    lowest_margin_projects,
    highest_margin_projects,
    declining_margin_projects,
    overdue_invoice_projects,
    overdue_wip_projects,
    unbilled_revenue_projects,
    contingency_erosion_projects,
    admin_cost_outliers,
    risk_overview,
    search_projects,
    project_details,
    project_history,
]

TOOLS_BY_NAME = {tool.__name__: tool for tool in ALL_TOOLS}
