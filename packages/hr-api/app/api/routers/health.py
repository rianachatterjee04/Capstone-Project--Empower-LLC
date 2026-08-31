from __future__ import annotations

from fastapi import APIRouter
from fastapi import Depends
from app.db.deps import get_db
from app.core.json_utils import json_safe
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.deps import get_db

router = APIRouter(tags=["health"])


# ---------------------------------------------------------
# Liveness — is API process alive
# Used by container orchestrators (fast check)
# ---------------------------------------------------------
@router.get("/health")
async def health():
    return {"status": "alive"}


# ---------------------------------------------------------
# Build identity — WHICH CODE is this process actually running?
#
# Every "it works on my machine" and every "I fixed that already" argument in
# this repo has eventually come down to a long-running dev server holding an
# older import of the tree. A browser cannot tell, a screenshot cannot tell,
# and a passing unit test says nothing about the process answering on :8000.
#
# So the process reports its own provenance. `dirty` matters as much as the
# SHA: a clean SHA with uncommitted edits on disk is a different program from
# the one that SHA names.
#
# NO CREDENTIALS. The database is reported by NAME only -- a DSN carries a
# password and this endpoint is unauthenticated on purpose, because something
# you have to authenticate to is no use when you are debugging why you cannot
# authenticate.
# ---------------------------------------------------------
def _effective_media_root() -> dict:
    """Where this process will actually read and write media."""
    import os
    import pathlib
    try:
        from app.interview import media as MED
        root = MED.storage_root()
    except Exception:
        return {"path": None, "source": "unavailable", "exists": False}
    return {
        "path": str(root),
        "source": ("FINTRA_MEDIA_ROOT" if os.environ.get("FINTRA_MEDIA_ROOT")
                   else "default"),
        "exists": pathlib.Path(root).is_dir(),
        "kind": MED.storage_kind(),
    }


@router.get("/health/build")
async def build_identity():
    import os
    import pathlib
    import subprocess
    import sys
    import time

    root = pathlib.Path(__file__).resolve().parents[3]

    def _git(*args: str) -> str | None:
        try:
            out = subprocess.run(["git", *args], cwd=str(root), timeout=5,
                                 capture_output=True, text=True)
            return out.stdout.strip() if out.returncode == 0 else None
        except Exception:
            return None

    sha = _git("rev-parse", "HEAD")
    status = _git("status", "--porcelain")
    branch = _git("rev-parse", "--abbrev-ref", "HEAD")
    subject = _git("log", "-1", "--pretty=%s")

    dsn = (os.environ.get("FINTRA_INTERVIEW_PG_DSN")
           or os.environ.get("FINTRA_HR_PG_DSN") or "")
    db_name = dsn.rsplit("/", 1)[-1].split("?")[0] if dsn else None

    return json_safe({
        "service": "fintra-hr-api",
        "git": {
            "sha": sha,
            "short": (sha or "")[:8] or None,
            "branch": branch,
            "subject": subject,
            # A clean SHA with edits on disk is not the program that SHA names.
            "dirty": bool(status),
            "dirty_files": len([l for l in (status or "").splitlines() if l]),
        },
        "process": {
            "cwd": os.getcwd(),
            "source_root": str(root),
            "python": sys.version.split()[0],
            "pid": os.getpid(),
            "started_unix": int(getattr(build_identity, "_t0", time.time())),
        },
        # Name only. Never the DSN.
        "database": db_name,
        # The EFFECTIVE root, not the environment variable. Reporting the raw
        # variable says "None" on a correctly configured server that is using
        # the default, which is useless in the one situation this field exists
        # for: the seeder wrote media to one place and the server is serving
        # from another, so every part 404s and the player looks empty.
        "media_root": _effective_media_root(),
        "note": ("If the sha here is not the sha you just committed, the server "
                 "is running older code and everything you are looking at is "
                 "stale. Restart it."),
    })


# ---------------------------------------------------------
# Readiness — can system actually serve requests
# Checks database connectivity
# ---------------------------------------------------------
@router.get("/health/ready")
async def readiness(db: AsyncSession = Depends(get_db)):
    try:
        await db.execute(text("select 1"))
        return {"status": "ready"}
    except Exception as e:
        return {"status": "not_ready", "reason": str(e)}


# ---------------------------------------------------------
# Deep system check — enterprise diagnostics
# Used by admins / monitoring dashboards
# ---------------------------------------------------------
@router.get("/health/system")
async def system_health(db: AsyncSession = Depends(get_db)):
    report = {
        "api": "ok",
        "database": "unknown",
        "migrations": "unknown",
        "workers": "unknown",
        "storage": "unknown"
    }

    # DB check
    try:
        await db.execute(text("select 1"))
        report["database"] = "ok"
    except Exception:
        report["database"] = "down"

    # schema check (critical tables exist)
    try:
        await db.execute(text("select count(*) from public.employees"))
        report["migrations"] = "ok"
    except Exception:
        report["migrations"] = "missing_tables"

    # workers placeholder (Temporal/queue heartbeat later)
    report["workers"] = "unknown"

    # storage placeholder (Supabase/S3 later)
    report["storage"] = "unknown"

    overall = "ok"
    if "down" in report.values() or "missing_tables" in report.values():
        overall = "degraded"

    return {"overall": overall, "services": report}

