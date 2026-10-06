"""Health check endpoints."""

import logging
import urllib.error
import urllib.request

from fastapi import APIRouter
from sqlalchemy import text

from ..config import settings
from ..database import SessionLocal

logger = logging.getLogger(__name__)

router = APIRouter()


def _check_database() -> dict:
    try:
        db = SessionLocal()
        try:
            db.execute(text("SELECT 1"))
        finally:
            db.close()
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "detail": str(e)}


def _check_model() -> dict:
    """Can the runner actually reach a model right now?

    Every model failure is caught downstream and turned into "Sorry, I didn't
    catch that", which is indistinguishable from a bad answer. This is the only
    place that says out loud that the runtime is missing rather than wrong.
    """
    if settings.llm_provider != "ollama":
        if not settings.llm_api_key:
            return {
                "ok": False,
                "detail": f"LLM_PROVIDER is {settings.llm_provider} but LLM_API_KEY is empty",
            }
        return {
            "ok": True,
            "detail": f"{settings.llm_provider}, key present (not called)",
        }

    url = f"{settings.ollama_base_url.rstrip('/')}/api/tags"
    try:
        with urllib.request.urlopen(url, timeout=3):
            return {"ok": True, "detail": settings.ollama_base_url}
    except (urllib.error.URLError, OSError) as e:
        return {
            "ok": False,
            "detail": f"no model runtime at {settings.ollama_base_url} ({e})",
        }


@router.get("/health")
async def health():
    """Liveness. Deliberately shallow: the container healthcheck reads this, and
    a dependency being down should not stop the process serving."""
    # Import here to avoid circular dependency
    from .websocket import SESSIONS

    return {
        "service": "voice-agent",
        "status": "healthy",
        "active_connections": len(SESSIONS),
    }


@router.get("/health/ready")
async def ready():
    """Readiness: can this actually take a call? Always 200, so nothing restarts
    on the back of it. `make up` reads this to report a stack that started but
    cannot answer."""
    checks = {"database": _check_database(), "model": _check_model()}
    return {
        "service": "voice-agent",
        "ready": all(c["ok"] for c in checks.values()),
        "checks": checks,
    }
