# Evaluation results (LLM agent)

| Metric | Score |
|---|---|
| Questions | 12 |
| Tool choice accuracy | 100% |
| Project recall (planted problems found) | 100% |
| Answers with no invented numbers | 100% |
| Correctly refused unknown project | 1/1 |
| Total time | 262s |

| Question | Tools called | Tool OK | Recall | Grounded |
|---|---|---|---|---|
| Which projects are losing money? | lowest_margin_projects | ✅ | 100% | ✅ |
| Where has margin been slipping over the last three months? | declining_margin_projects | ✅ | 100% | ✅ |
| Which clients haven't paid their invoices? | overdue_invoice_projects | ✅ | 100% | ✅ |
| Are there projects where we've done the work but not billed the client? | unbilled_revenue_projects | ✅ | 100% | ✅ |
| Which projects have burned through their contingency? | contingency_erosion_projects | ✅ | 100% | ✅ |
| Are any projects spending far too much on admin? | admin_cost_outliers | ✅ | 100% | ✅ |
| What should I be worried about in the portfolio? | risk_overview | ✅ | 100% | ✅ |
| What's our overall gross margin this month? | portfolio_summary | ✅ | - | ✅ |
| How has the portfolio's margin changed over the year? | portfolio_trend | ✅ | - | ✅ |
| Tell me how Fenwick Depot Redevelopment is doing. | search_projects, project_details | ✅ | 100% | ✅ |
| How has contingency changed month by month on Harbourline Station Accessibility? | search_projects, project_history, project_history | ✅ | 100% | ✅ |
| What's the gross margin on the Thames Tunnel Ventilation project? | search_projects | ✅ | - | ✅ |
