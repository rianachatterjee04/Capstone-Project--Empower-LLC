from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import asyncio

# -----------------------------------------------------------------------------
# Create App FIRST
# -----------------------------------------------------------------------------
app = FastAPI(
    title="Foundry People",
    version="1.0.0",
    description="AI-native enterprise HR operating system"
)

# -----------------------------------------------------------------------------
# Start Org Guardian (autonomous AI supervisor)
# -----------------------------------------------------------------------------
from app.org_guardian.guardian import guardian_loop

@app.on_event("startup")
async def start_guardian():
    asyncio.create_task(guardian_loop())

# -----------------------------------------------------------------------------
# Routers (import AFTER app exists to avoid circular startup issues)
# -----------------------------------------------------------------------------
from app.api.router import api_router
from app.api.realtime_ws import router as realtime_router
from app.copilot.copilot_router import router as copilot_router

# Intelligence routers
from app.api.routers.intelligence import router as intelligence_router
app.include_router(intelligence_router)

# Middleware
from app.middleware.view_audit import ViewAuditMiddleware

# -----------------------------------------------------------------------------
# Middleware
# -----------------------------------------------------------------------------
app.add_middleware(ViewAuditMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # ⚠️ restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -----------------------------------------------------------------------------
# Core API
# -----------------------------------------------------------------------------
app.include_router(api_router, prefix="/api")

# -----------------------------------------------------------------------------
# Copilot (Employee AI Assistant)
# -----------------------------------------------------------------------------
app.include_router(copilot_router, prefix="/api")

# -----------------------------------------------------------------------------
# Realtime Behavioral Events (WebSocket)
# -----------------------------------------------------------------------------
app.include_router(realtime_router)

# Intelligence Layer routers are included via intelligence_router above

# -----------------------------------------------------------------------------
# Health
# -----------------------------------------------------------------------------
@app.get("/")
async def root():
    return {"status": "Foundry People API running"}

@app.get("/health")
async def health():
    return {"ok": True}

