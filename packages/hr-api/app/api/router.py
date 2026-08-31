from fastapi import APIRouter

from app.api.routers.ai_internal import router as ai_internal
from app.api.routers.health import router as health
from app.api.routers.employees import router as employees
from app.api.routers.reports import router as reports
from app.api.routers.onboarding import router as onboarding
from app.api.routers.recruiting import router as recruiting
from app.api.routers.interview_v2 import router as interview_v2
from app.api.routers.commercial import router as commercial
from app.api.routers.trucking import router as trucking
from app.api.routers.cases import router as cases
from app.api.routers.policies import router as policies
from app.api.routers.escalations import router as escalations
from app.api.routers.ai_memory import router as ai_memory
from app.api.routers.documents import router as documents
from app.api.routers.legal import router as legal
from app.api.routers.push import router as push
from app.api.routers.approvals import router as approvals
from app.api.routers.cfo import router as cfo
from app.api.routers.integrations import router as integrations
from app.api.routers.payroll_sync import router as payroll_sync
from app.api.routers.policies_v2 import router as policies2
from app.api.routers.ai_system import router as ai_system
from app.api.routers.audit_views import router as audit_views
from app.api.routers.market import router as market
from app.api.routers.bonuses import router as bonuses
from app.api.routers.benefits import router as benefits
from app.api.routers.ats import router as ats
from app.api.routers.decisions import router as decisions

from app.api.routers.pto import router as pto

# --- SMB HR core (BambooHR-parity): time-off engine, checklists,
#     effective-dated records, org chart
from app.api.routers.timeoff import router as timeoff
from app.api.routers.checklists import router as checklists
from app.api.routers.employee_records import router as employee_records
from app.api.routers.org_chart import router as org_chart

from app.api.routers.screening import router as screening
from app.api.routers.performance import router as performance
from app.api.routers.reviews import router as reviews

# --- Foundry People AI extensions (resume AI, interviews, comp AI, learning, ombudsman, helpdesk, attrition)
from app.api.routers.resume_ai import router as resume_ai
from app.api.routers.ai_interview import router as ai_interview
from app.api.routers.reference_check import router as reference_check
from app.api.routers.recruiting_cockpit import router as recruiting_cockpit
from app.api.routers.referrals import router as referrals
from app.api.routers.interview_loop import router as interview_loop
from app.api.routers.skills_graph import router as skills_graph
from app.api.routers.calibration import router as calibration
from app.api.routers.automations import router as automations
from app.api.routers.interviews import router as interviews
from app.api.routers.interview_ai import router as interview_ai_assist
from app.api.routers.comp_ai import router as comp_ai
# --- NET-NEW P0 differentiators: pay equity + candidate integrity
from app.api.routers.pay_equity import router as pay_equity
from app.api.routers.candidate_integrity import router as candidate_integrity
from app.api.routers.learning import router as learning
from app.api.routers.ombudsman import router as ombudsman
from app.api.routers.ai_helpdesk import router as ai_helpdesk
from app.api.routers.attrition import router as attrition

# --- Foundry People agentic OS layer
from app.api.routers.cpo import router as cpo
from app.api.routers.agents import router as agents
from app.api.routers.workforce_risk import router as workforce_risk
from app.api.routers.talent_marketplace import router as marketplace
from app.api.routers.org_design import router as org_design
from app.api.routers.digital_twin import router as digital_twin
from app.api.routers.exec_copilot import router as exec_copilot
from app.api.routers.content_gen import router as content_gen

# --- Foundry People work operating system layer
from app.api.routers.tasks import router as tasks
from app.api.routers.manager_brief import router as manager_brief
from app.api.routers.team_workspace import router as team_workspace
from app.api.routers.exec_brief import router as exec_brief

# --- Foundry People knowledge + CRM + finance + graph
from app.api.routers.memory import router as memory
from app.api.routers.people_crm import router as people_crm
from app.api.routers.workforce_finance import router as workforce_finance
from app.api.routers.org_graph import router as org_graph

# --- Workforce Intelligence: the OS for the entire workforce (humans + AI agents
#     + contractors + bots) — Workforce Graph + Workforce Financial Intelligence
from app.api.routers.workforce_graph import router as workforce_graph

# --- Foundry People operations layer (approvals, activity, notifications, goals, recognition, calendar, narrative analytics)
from app.api.routers.approvals_center import router as approvals_center
from app.api.routers.activity import router as activity_feed
from app.api.routers.notifications import router as notifications
from app.api.routers.goals import router as goals
from app.api.routers.recognition import router as recognition
from app.api.routers.people_calendar import router as people_calendar
from app.api.routers.narrative_analytics import router as narrative_analytics

# --- Lattice-parity gap closers: 1:1s, Engagement/eNPS pulse, Grow (career ladders)
from app.api.routers.one_on_ones import router as one_on_ones
from app.api.routers.engagement import router as engagement
from app.api.routers.grow import router as grow

# --- Foundry People configuration + experience layers (settings, setup, public profile, wellness)
from app.api.routers.settings_hub import router as settings_hub
from app.api.routers.setup_wizard import router as setup_wizard
from app.api.routers.public_profile import router as public_profile
from app.api.routers.wellness import router as wellness

# --- AI-Workforce live-data dashboards
from app.api.ai_workforce import router as ai_workforce


# --- HR investigations (workplace cases: witnesses, evidence, findings,
#     disciplinary action) and HR security posture (SSO/SCIM/login records).
#     Previously built but never mounted; prefixes /investigations and /security
#     do not collide with any mounted router.
from app.api.routers.investigations import router as investigations
from app.api.routers.security import router as security

# --- Cross-domain governance seam for Fintra Trust CORTEX: exposes HR pending
#     governance decisions normalized to the cross-domain contract.
from app.api.routers.governance import router as governance

# --- Company bootstrap + amount-tier approvals + comp cycle
#     (backing tables in migrations/20260709_orgs_approval_comp.sql)
from app.api.routers.orgs import router as orgs
from app.api.routers.comp_cycle import router as comp_cycle

# --- Total Compensation Unification (base+bonus+benefits+commission+payroll+equity)
from app.api.routers.total_comp import router as total_comp

# Optional router: only include if file exists
try:
    from app.api.routers.doc_verification import router as verification
except Exception:
    verification = None

api_router = APIRouter()

# --- Module entitlement gate (Fintra control plane) -------------------------
# require_hr_access composes the existing require_org auth, publishes the Fintra
# context and — when FINTRA_ENFORCE is on (default) — returns 402 (module not
# licensed) / 403 (no seat) if the org's `hr` subscription is not active. It
# fail-opens on control-plane unreachability (see app/api/entitlements.py).
# Applied to the core HR data routers. NOT applied to health (public) or
# ai_internal (service-to-service auth via require_internal_ai).
from fastapi import Depends
from app.api.entitlements import require_hr_access

HR_GATE = [Depends(require_hr_access)]

api_router.include_router(ai_internal)
api_router.include_router(health)
api_router.include_router(employees, dependencies=HR_GATE)
api_router.include_router(reports, dependencies=HR_GATE)
api_router.include_router(onboarding, dependencies=HR_GATE)
api_router.include_router(recruiting, dependencies=HR_GATE)
api_router.include_router(cases, dependencies=HR_GATE)
api_router.include_router(policies, dependencies=HR_GATE)
api_router.include_router(escalations)
api_router.include_router(ai_memory)
api_router.include_router(documents, dependencies=HR_GATE)
api_router.include_router(legal)
api_router.include_router(push)
api_router.include_router(approvals)
# Company bootstrap + comp cycle (previously unmounted; tables now migrated)
api_router.include_router(orgs)
api_router.include_router(comp_cycle)
api_router.include_router(total_comp)
api_router.include_router(cfo)
api_router.include_router(integrations)
api_router.include_router(payroll_sync)
api_router.include_router(policies2)
api_router.include_router(ai_system)

if verification is not None:
    api_router.include_router(verification)

api_router.include_router(audit_views)
api_router.include_router(market)
api_router.include_router(bonuses, dependencies=HR_GATE)
api_router.include_router(benefits, dependencies=HR_GATE)
api_router.include_router(ats)
api_router.include_router(decisions)

api_router.include_router(pto, dependencies=HR_GATE)

# SMB HR core (time-off engine, checklists, effective-dated records, org chart)
api_router.include_router(timeoff, dependencies=HR_GATE)
api_router.include_router(checklists, dependencies=HR_GATE)
api_router.include_router(employee_records, dependencies=HR_GATE)
api_router.include_router(org_chart, dependencies=HR_GATE)

api_router.include_router(screening)
api_router.include_router(performance, dependencies=HR_GATE)
api_router.include_router(reviews, dependencies=HR_GATE)

# Foundry People AI extensions
api_router.include_router(resume_ai)
api_router.include_router(ai_interview)
api_router.include_router(reference_check)
api_router.include_router(recruiting_cockpit)
api_router.include_router(referrals)
api_router.include_router(interview_loop)
api_router.include_router(skills_graph)
api_router.include_router(calibration)
api_router.include_router(automations)
api_router.include_router(interviews)
api_router.include_router(interview_ai_assist)
api_router.include_router(comp_ai)
# NET-NEW P0 differentiators
api_router.include_router(pay_equity)
api_router.include_router(candidate_integrity)
api_router.include_router(learning)
api_router.include_router(ombudsman)
api_router.include_router(ai_helpdesk)
api_router.include_router(attrition)

# Foundry People agentic OS layer
api_router.include_router(cpo)
api_router.include_router(agents)
api_router.include_router(workforce_risk)
api_router.include_router(marketplace)
api_router.include_router(org_design)
api_router.include_router(digital_twin)
api_router.include_router(exec_copilot)
api_router.include_router(content_gen)

# Foundry People Work Operating System
api_router.include_router(tasks)
api_router.include_router(manager_brief)
api_router.include_router(team_workspace)
api_router.include_router(exec_brief)

# Foundry People knowledge + CRM + finance + graph
api_router.include_router(memory)
api_router.include_router(people_crm)
api_router.include_router(workforce_finance)
api_router.include_router(org_graph)
api_router.include_router(workforce_graph)

# Foundry People operations layer
api_router.include_router(approvals_center)
api_router.include_router(activity_feed)
api_router.include_router(notifications)
api_router.include_router(goals, dependencies=HR_GATE)
api_router.include_router(recognition)
api_router.include_router(people_calendar)
api_router.include_router(narrative_analytics)

# Lattice-parity gap closers: 1:1s, Engagement/eNPS pulse, Grow (career ladders)
api_router.include_router(one_on_ones)
api_router.include_router(engagement)
api_router.include_router(grow)

# Foundry People configuration + experience
api_router.include_router(settings_hub)
api_router.include_router(setup_wizard)
api_router.include_router(public_profile)
api_router.include_router(wellness)

# AI-Workforce live-data dashboards
api_router.include_router(ai_workforce)

# Equity / cap-table module

# HR investigations + HR security posture (built-but-unmounted; no prefix collision)
api_router.include_router(investigations)
api_router.include_router(security)

# Cross-domain governance seam for Fintra Trust CORTEX (org-scoped by the token)
api_router.include_router(governance)
api_router.include_router(interview_v2)

api_router.include_router(trucking)
api_router.include_router(commercial)