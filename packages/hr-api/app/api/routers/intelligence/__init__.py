"""Intelligence routers package - aggregates all intel sub-routers."""
from fastapi import APIRouter

from app.api.routers.intelligence.core import router as core_router
from app.api.routers.intelligence.education import router as education_router
from app.api.routers.intelligence.equity import router as equity_router
from app.api.routers.intelligence.narratives import router as narratives_router
from app.api.routers.intelligence.reconciliation import router as reconciliation_router

router = APIRouter()
router.include_router(core_router)
router.include_router(education_router)
router.include_router(equity_router)
router.include_router(narratives_router)
router.include_router(reconciliation_router)

__all__ = ["router"]
