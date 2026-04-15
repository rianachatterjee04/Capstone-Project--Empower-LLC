from fastapi import APIRouter

from app.api.routers.ai_internal import router as ai_internal
from app.api.routers.health import router as health
from app.api.routers.employees import router as employees
from app.api.routers.onboarding import router as onboarding
from app.api.routers.recruiting import router as recruiting
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
from app.api.routers.policies_v2 import router as policies2
from app.api.routers.ai_system import router as ai_system
from app.api.routers.audit_views import router as audit_views
from app.api.routers.market import router as market
from app.api.routers.bonuses import router as bonuses
from app.api.routers.benefits import router as benefits
from app.api.routers.ats import router as ats
from app.api.routers.decisions import router as decisions

from app.api.routers.pto import router as pto

from app.api.routers.screening import router as screening

# Optional router: only include if file exists
try:
    from app.api.routers.doc_verification import router as verification
except Exception:
    verification = None

api_router = APIRouter()

api_router.include_router(ai_internal)
api_router.include_router(health)
api_router.include_router(employees)
api_router.include_router(onboarding)
api_router.include_router(recruiting)
api_router.include_router(cases)
api_router.include_router(policies)
api_router.include_router(escalations)
api_router.include_router(ai_memory)
api_router.include_router(documents)
api_router.include_router(legal)
api_router.include_router(push)
api_router.include_router(approvals)
api_router.include_router(cfo)
api_router.include_router(integrations)
api_router.include_router(policies2)
api_router.include_router(ai_system)

if verification is not None:
    api_router.include_router(verification)

api_router.include_router(audit_views)
api_router.include_router(market)
api_router.include_router(bonuses)
api_router.include_router(benefits)
api_router.include_router(ats)
api_router.include_router(decisions)

api_router.include_router(pto)

api_router.include_router(screening)
