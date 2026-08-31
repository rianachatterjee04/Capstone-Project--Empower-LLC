# Fintra People / HR API (`packages/hr-api`)

FastAPI + SQLAlchemy backend for the **People / HR** module of the Fintra platform
("Foundry People"). It runs the full employee lifecycle — recruiting and AI interviews,
onboarding, goals and reviews, compensation cycles, equity, time off, and the bridges
that carry people data into payroll and finance.

Backend: FastAPI + SQLAlchemy (Postgres in prod, SQLite for local dev), pgvector for AI
memory, optional Temporal workflows. Routers live under `app/api/routers/`; domain logic
under `app/comp/`, `app/equity/`, `app/performance/`, `app/onboarding/`, `app/benefits/`,
`app/intelligence/`, and friends.

## Run

```bash
cd packages/hr-api
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8002
# or from the repo root:
npm run dev:hr-api
```

Interactive API docs: http://127.0.0.1:8002/docs

## Module map (what shipped)

The router set (`app/api/routers/`) covers the whole people lifecycle. The load-bearing
groups:

| Area | Routers | What it does |
|---|---|---|
| **Recruiting & hiring** | `recruiting.py`, `recruiting_pipeline.py`, `recruiting_cockpit.py`, `ats.py`, `interviews.py`, `interview_ai.py`, `interview_loop.py`, `screening.py`, `resume_ai.py`, `reference_check.py`, `referrals.py`, `talent_marketplace.py` | Requisition → screen → AI interview → offer. The pipeline hands an accepted offer to `employees.create_employee`. |
| **Onboarding** | `onboarding.py`, `onboarding_flow.py`, `checklists.py`, `setup_wizard.py` | New-hire checklists and guided setup; feeds the payroll-employee sync. |
| **Employee records** | `employees.py`, `employee_records.py`, `org_chart.py`, `org_graph.py`, `public_profile.py`, `people_crm.py`, `people_calendar.py` | The system of record for people; org chart and directory. |
| **Performance** | `goals.py`, `reviews.py`, `performance.py`, `calibration.py`, `recognition.py`, `ombudsman.py` | Goals, review cycles, calibration, recognition, and the ombudsman channel (`app/performance/cycles.py`). |
| **Compensation** | `total_comp.py`, `comp_cycle.py`, `comp_planning.py`, `comp_ai.py`, `bonuses.py` | Comp cycles and planning; `total_comp.py` aggregates the five streams — base + bonus + commission + payroll actuals + equity — target vs actual (`app/comp/cycle.py`). |
| **Equity** | `equity.py` | Cap table, vesting schedules, 83(b) tracking, and scenario modeling (`app/equity/engine.py`). Feeds the employee equity portal. |
| **Time & benefits** | `pto.py`, `timeoff.py`, `benefits.py`, `wellness.py` | PTO/time-off requests and balances; benefits enrollment. |
| **Bridges** | `payroll_sync.py`, `workforce_finance.py` | `payroll_sync.upsert` mirrors a hire into a payroll employee; `workforce_finance.py` carries headcount/labor cost into finance. |
| **AI & intelligence** | `agents.py`, `ai_*`, `digital_twin.py`, `intelligence.py`, `narrative_analytics.py`, `skills_graph.py`, `attrition.py`, `workforce_risk.py` | AI helpdesk, interview AI, per-employee digital twins, attrition and workforce-risk models, skills graph. |
| **Exec & manager** | `cfo.py`, `cpo.py`, `exec_brief.py`, `exec_copilot.py`, `manager_brief.py`, `decisions.py` | Executive/manager briefs and copilots. |
| **Governance** | `approvals*.py`, `policies*.py`, `security.py`, `audit_views.py`, `investigations.py`, `escalations.py`, `cases.py`, `legal.py`, `doc_verification.py` | Approvals center, policy engine, security views, investigations, document verification. |
| **Platform** | `orgs.py`, `settings_hub.py`, `integrations.py`, `notifications.py`, `push.py`, `realtime_ws.py`, `memory.py`, `ai_memory.py` | Org/tenant setup, settings, integrations, notifications, realtime, and pgvector AI memory. |

## Cross-module seams (verified — see `docs/E2E_FLOW_AUDIT.md`, Flow 3)

- **Hire → payroll employee**: `payroll_sync.upsert` bridges an accepted offer into a
  payroll employee record.
- **Total Comp aggregation**: `total_comp` pulls all five streams. The commission stream
  reads `quota × commission_pct` from the finance side (`packages/api/routes/sales_commission.py`).
- **Payroll actuals → GL**: payroll runs post back to the Finance-OS ledger via the
  code-keyed ingest bridge (`packages/api/routes/internal_journal.py`).
- **Equity 409A** feeds the equity portal's vesting/scenario views.

## Safety framing

- People data is tenant-scoped; every backend enforces `fintra_entitlements` context
  after resolving identity (see `docs/PLATFORM.md`).
- Sensitive identifiers are handled by the payroll service (SSN/bank encrypted at rest,
  hash-only credentials) — HR holds references, not the plaintext secrets.

## Local dev DB

For local dev, tables are created via the init scripts (`init_db_fixed.py`,
`add_indexes.py`) against the configured database URL. Prod runs Postgres; SQLite is fine
for a single-developer local loop.

> **Cross-references.** Paths under `packages/api`, `packages/payroll`, `packages/sentri-api`
> and similar refer to services in the wider Fintra platform that are **not part of this
> build**. They are named so the seam is visible, not because the code ships here.
