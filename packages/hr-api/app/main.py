from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import logging
import re

from app.core.config import settings

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

# SECURITY: with allow_credentials=True, a wildcard or malformed origin must never be
# trusted for credentialed cross-origin reads of employee data. Reject any extra origin
# that is not an explicit http(s):// origin or that contains a wildcard.
def _valid_extra_origin(o: str) -> bool:
    if "*" not in o and (o.startswith("http://") or o.startswith("https://")):
        return True
    logging.warning("Ignoring invalid CORS_EXTRA_ORIGINS entry: %r", o)
    return False


_EXTRA_ORIGINS = [
    o.strip()
    for o in settings.cors_extra_origins.split(",")
    if o.strip() and _valid_extra_origin(o.strip())
]
CORS_ALLOW_ORIGINS = [*ALLOWED_ORIGINS, *_EXTRA_ORIGINS]

# Next.js often binds IPv6 (::1) or uses a free port (3002+); Starlette returns 400 on preflight if Origin is not allowed.
_DEV_LOCAL_ORIGIN_RE = re.compile(r"https?://(localhost|127\.0\.0\.1|\[::1\])(:\d+)?\Z")


def _is_production_env() -> bool:
    return settings.env.lower() in ("prod", "production")


def _cors_reflect_origin(origin: str | None) -> str:
    if not origin:
        return ALLOWED_ORIGINS[0]
    if origin in CORS_ALLOW_ORIGINS:
        return origin
    if not _is_production_env() and _DEV_LOCAL_ORIGIN_RE.match(origin):
        return origin
    return ALLOWED_ORIGINS[0]


# -----------------------------------------------------------------------------
# Global Exception Handler
# -----------------------------------------------------------------------------
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logging.exception("Global Error")

    origin = _cors_reflect_origin(request.headers.get("origin"))

    # SECURITY: never leak raw exception text (SQL fragments, internal paths, etc.) to
    # clients in production. The full detail is logged server-side above; only return it
    # in the response in non-production to aid local debugging.
    content: dict = {"message": "Internal Server Error"}
    if not _is_production_env():
        content["detail"] = str(exc)

    headers = {
        "Access-Control-Allow-Methods": "*",
        "Access-Control-Allow-Headers": "*",
    }
    # SECURITY: only emit credentialed CORS headers when the origin is on the vetted
    # allow-list (or a localhost origin in non-prod). Do NOT reflect an arbitrary origin
    # together with Allow-Credentials: true.
    request_origin = request.headers.get("origin")
    if request_origin and origin == request_origin:
        headers["Access-Control-Allow-Origin"] = origin
        headers["Access-Control-Allow-Credentials"] = "true"

    return JSONResponse(
        status_code=500,
        content=content,
        headers=headers,
    )

# -----------------------------------------------------------------------------
# Database constraint violations
# -----------------------------------------------------------------------------
# A constraint violation is the database refusing a request, and almost always
# the CALLER's to fix: a duplicate name, a missing required column, a reference
# to a row that does not exist. Falling through to the handler above answered
# all of them with 500 "Internal Server Error", which tells an integrator our
# software broke when in fact their request did -- and gives them nothing to act
# on. A sweep of the 143 parameterless write endpoints found six.
#
# 409 for a duplicate, 422 for a bad or missing value, and a sentence naming the
# column or constraint involved. The underlying exception is still logged in
# full server-side; only the useful part is returned.
from sqlalchemy.exc import IntegrityError


def _violation_response(exc: IntegrityError) -> tuple[int, str]:
    # SQLAlchemy's asyncpg dialect wraps the driver error in its own
    # IntegrityError, so the asyncpg exception carrying column_name and
    # constraint_name is one __cause__ deeper. Reading exc.orig alone found a
    # dialect wrapper every time and fell through to the unclassified branch.
    orig = getattr(exc, "orig", None)
    for _ in range(3):
        if type(orig).__module__.startswith("asyncpg"):
            break
        nxt = getattr(orig, "__cause__", None)
        if nxt is None:
            break
        orig = nxt
    kind = type(orig).__name__
    column = getattr(orig, "column_name", None)
    constraint = getattr(orig, "constraint_name", None)
    table = getattr(orig, "table_name", None)

    if kind == "UniqueViolationError":
        where = f" ({constraint})" if constraint else ""
        return 409, f"that record already exists{where}"
    if kind == "NotNullViolationError":
        if column:
            return 422, f"'{column}' is required"
        return 422, "a required field was missing"
    if kind == "ForeignKeyViolationError":
        if column:
            return 422, f"'{column}' refers to a row that does not exist"
        return 422, "a referenced record does not exist"
    if kind == "CheckViolationError":
        where = f" ({constraint})" if constraint else ""
        return 422, f"a value is outside the range this field allows{where}"
    if kind == "ExclusionViolationError":
        return 409, "that record conflicts with an existing one"
    # An integrity error we have not classified. Still the database refusing the
    # write, so still a 4xx -- but say plainly that we could not be specific
    # rather than inventing a reason.
    return 422, f"the database rejected this write{f' on {table}' if table else ''}"


@app.exception_handler(IntegrityError)
async def integrity_error_handler(request: Request, exc: IntegrityError):
    logging.exception("Constraint violation")
    status_code, message = _violation_response(exc)

    content: dict = {"message": message}
    if not _is_production_env():
        content["detail"] = str(exc)

    headers = {
        "Access-Control-Allow-Methods": "*",
        "Access-Control-Allow-Headers": "*",
    }
    origin = _cors_reflect_origin(request.headers.get("origin"))
    request_origin = request.headers.get("origin")
    if request_origin and origin == request_origin:
        headers["Access-Control-Allow-Origin"] = origin
        headers["Access-Control-Allow-Credentials"] = "true"

    return JSONResponse(status_code=status_code, content=content, headers=headers)


# -----------------------------------------------------------------------------
# Tables this deployment has not been given
# -----------------------------------------------------------------------------
# Several routers already hand-roll this: they check for their table and, if it
# is absent, answer 503 "<table> table is not available yet. Run the <x>
# migration first." That is the right answer -- the feature is not provisioned
# here, the operator knows exactly what to run, and nobody is told our software
# broke.
#
# Routers that had not written that check answered the same situation with 500
# "Internal Server Error". Same cause, same remedy, opposite message. The sweep
# of parameterless writes found five endpoints failing this way, on tables
# including ai_decisions and expo_push_tokens.
#
# So make it uniform. This does not paper over the gap -- the response names the
# missing table, and BETA_READINESS.md lists every one of them as work to do.
# It stops us blaming ourselves for an operator-fixable deployment state.
#
# UndefinedColumn is deliberately NOT handled here. A missing table is a feature
# that was never installed; a missing COLUMN means the code and the schema
# disagree about a table that does exist, which is our bug and should stay loud.
from asyncpg.exceptions import UndefinedTableError
from sqlalchemy.exc import ProgrammingError


def _missing_table(exc: ProgrammingError) -> str | None:
    orig = getattr(exc, "orig", None)
    for _ in range(3):
        if isinstance(orig, UndefinedTableError):
            break
        nxt = getattr(orig, "__cause__", None)
        if nxt is None:
            return None
        orig = nxt
    if not isinstance(orig, UndefinedTableError):
        return None
    # asyncpg puts the name in the message: relation "public.ai_decisions" does not exist
    m = re.search(r'relation "([^"]+)" does not exist', str(orig))
    return m.group(1) if m else "a required table"


@app.exception_handler(ProgrammingError)
async def programming_error_handler(request: Request, exc: ProgrammingError):
    table = _missing_table(exc)
    if table is None:
        # Not a missing table -- a genuine bad statement. Let it be a 500.
        return await global_exception_handler(request, exc)

    logging.exception("Missing table")
    content: dict = {
        "message": f"{table} is not available in this deployment. "
                   f"Run the migration that creates it, then retry.",
        "unavailable": True,
    }
    if not _is_production_env():
        content["detail"] = str(exc)

    headers = {
        "Access-Control-Allow-Methods": "*",
        "Access-Control-Allow-Headers": "*",
    }
    origin = _cors_reflect_origin(request.headers.get("origin"))
    request_origin = request.headers.get("origin")
    if request_origin and origin == request_origin:
        headers["Access-Control-Allow-Origin"] = origin
        headers["Access-Control-Allow-Credentials"] = "true"

    return JSONResponse(status_code=503, content=content, headers=headers)


# -----------------------------------------------------------------------------
# Middleware
# -----------------------------------------------------------------------------
from app.middleware.view_audit import ViewAuditMiddleware

app.add_middleware(ViewAuditMiddleware)

_cors_kwargs: dict = {
    "allow_origins": CORS_ALLOW_ORIGINS,
    "allow_credentials": True,
    "allow_methods": ["*"],
    "allow_headers": ["*"],
    "expose_headers": ["*"],
}
# SECURITY: do NOT blanket-trust "*.vercel.app" for credentialed CORS — any
# attacker can deploy at <anything>.vercel.app. Allow only localhost (dev) and
# our own product domain subdomains (*.fintrahub.com). Specific Vercel origins
# must be added explicitly via CORS_EXTRA_ORIGINS.
_cors_kwargs["allow_origin_regex"] = r"https?://(localhost(:\d+)?|127\.0\.0\.1(:\d+)?|([a-z0-9-]+\.)*fintrahub\.com)"

app.add_middleware(CORSMiddleware, **_cors_kwargs)

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
