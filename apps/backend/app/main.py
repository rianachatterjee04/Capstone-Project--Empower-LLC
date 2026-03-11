from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import logging

# -----------------------------------------------------------------------------
# Create App
# -----------------------------------------------------------------------------
app = FastAPI(
    title="Foundry People",
    version="1.0.0",
    description="AI-native enterprise HR operating system",
)

# -----------------------------------------------------------------------------
# Allowed Origins
# -----------------------------------------------------------------------------
ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "http://localhost:3001",
    "http://localhost:5173",
    "http://localhost:5174",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:3001",
    "http://127.0.0.1:5173",
    "http://127.0.0.1:5174",
    "http://localhost:8081",
    "http://127.0.0.1:8081",
]

# -----------------------------------------------------------------------------
# Global Exception Handler
# -----------------------------------------------------------------------------
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logging.exception("Global Error")

    origin = request.headers.get("origin")
    if origin not in ALLOWED_ORIGINS:
        origin = ALLOWED_ORIGINS[0]

    return JSONResponse(
        status_code=500,
        content={
            "message": "Internal Server Error",
            "detail": str(exc),
        },
        headers={
            "Access-Control-Allow-Origin": origin,
            "Access-Control-Allow-Credentials": "true",
            "Access-Control-Allow-Methods": "*",
            "Access-Control-Allow-Headers": "*",
        },
    )

# -----------------------------------------------------------------------------
# Middleware
# -----------------------------------------------------------------------------
from app.middleware.view_audit import ViewAuditMiddleware

app.add_middleware(ViewAuditMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)

# -----------------------------------------------------------------------------
# Routers
# -----------------------------------------------------------------------------
from app.api.router import api_router
from app.api.realtime_ws import router as realtime_router
from app.copilot.copilot_router import router as copilot_router
from app.api.routers.intelligence import router as intelligence_router

app.include_router(intelligence_router, prefix="/api")
app.include_router(api_router, prefix="/api")
app.include_router(copilot_router, prefix="/api")
app.include_router(realtime_router)

# -----------------------------------------------------------------------------
# Health Check
# -----------------------------------------------------------------------------
@app.get("/")
async def root():
    return {"status": "Foundry People API running"}

@app.get("/health")
async def health():
    return {"ok": True}
