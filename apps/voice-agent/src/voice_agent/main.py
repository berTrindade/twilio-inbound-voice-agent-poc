"""FastAPI application initialization."""

import json
import hashlib
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .config import settings

# Initialize logging FIRST (before any imports that log)
from .utils.logger import setup_logging

logger = setup_logging(level=settings.ai_voice_agent_log_level.upper())

# Initialize OpenTelemetry instrumentation
from .instrumentation import initialize_opentelemetry

try:
    initialize_opentelemetry()
    logger.info("✅ OpenTelemetry instrumentation initialized")
except Exception as e:
    logger.error(f"Failed to initialize OpenTelemetry: {e}", exc_info=True)

from .config import settings
from .api import (
    health_router,
    websocket_router,
    twiml_router,
)
from .metrics import get_metrics_collector

# Get metrics collector instance
metrics_collector = get_metrics_collector()

logger.info(
    "🚀 Starting call runner",
    extra={
        "environment": settings.environment,
        "host": settings.host,
        "port": settings.port,
        "log_level": settings.ai_voice_agent_log_level,
    },
)

# Fail loud at startup if Twilio webhook signature validation is misconfigured,
# rather than letting it surface as silent per-request 500s/403s mid-call.
settings.warn_if_misconfigured()

# Initialize FastAPI app
app = FastAPI(
    title="Call runner",
    description="Runs a voice survey over a Twilio ConversationRelay WebSocket",
    version="0.1.0",
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(health_router)
app.include_router(websocket_router)
app.include_router(twiml_router)


# Startup event for metrics collection and survey initialization
@app.on_event("startup")
async def startup_event():
    """Initialize metrics and the survey on startup."""
    logger.info("📊 Application startup - metrics collection started")
    metrics_collector.update_system_metrics()

    # COACH_PHONE_NUMBER is only used for the PSTN coach handoff, which a
    # browser session never reaches, so it stays optional.
    if not settings.coach_phone_number or not settings.coach_phone_number.strip():
        logger.warning(
            "COACH_PHONE_NUMBER not set - PSTN coach handoff disabled (web-chat only)"
        )
    else:
        masked_phone = settings.coach_phone_number[:4] + "***"
        logger.info(
            "Coach phone number configured: %s",
            masked_phone,
            extra={"coach_phone": masked_phone},
        )

    # Initialize survey in database
    await initialize_default_survey()


async def initialize_default_survey():
    """
    Initialize the default survey in the database on startup.

    This ensures a Survey record exists for the configured survey JSON file,
    creating it if necessary. The survey_id is stored in app.state for use
    by websocket connections.
    """
    from .database import SessionLocal
    from .repositories import SurveyRepository

    db = None
    try:
        # Load survey JSON
        survey_path = Path(settings.survey_json_path)
        if not survey_path.exists():
            logger.error(
                f"Survey JSON file not found: {settings.survey_json_path}",
                extra={"survey_path": str(survey_path)},
            )
            return

        with open(survey_path, "r", encoding="utf-8") as f:
            survey_data = json.load(f)

        # Generate deterministic survey type/identifier
        # Use filename without extension as the base type
        survey_type = survey_path.stem  # e.g., "demo_survey"

        # Create a hash of the survey data for versioning
        survey_json_str = json.dumps(survey_data, sort_keys=True)
        survey_hash = hashlib.sha256(survey_json_str.encode()).hexdigest()[:16]

        # Survey title
        survey_title = f"Voice Survey - {survey_type}"

        db = SessionLocal()
        repo = SurveyRepository(db)

        # Check if survey already exists for this type
        existing_survey = repo.get_latest_by_type(survey_type)

        if existing_survey:
            # Use existing survey
            survey = existing_survey
            logger.info(
                "Using existing survey from database",
                extra={
                    "survey_id": str(survey.id),
                    "survey_type": survey_type,
                    "survey_title": survey.title,
                },
            )
        else:
            # Create new survey
            survey = repo.create(
                title=survey_title,
                survey_type=survey_type,
                data=survey_data,
            )
            logger.info(
                "Created new survey in database",
                extra={
                    "survey_id": str(survey.id),
                    "survey_type": survey_type,
                    "survey_title": survey_title,
                    "data_hash": survey_hash,
                },
            )

        # Store survey_id in app state for use by websocket connections
        app.state.default_survey_id = survey.id
        logger.info(
            "✅ Default survey initialized",
            extra={"survey_id": str(survey.id)},
        )

    except Exception as e:
        logger.error(
            "Failed to initialize default survey",
            extra={"error": str(e), "error_type": type(e).__name__},
            exc_info=True,
        )
        # Don't fail startup, but log prominently
        app.state.default_survey_id = None
    finally:
        if db is not None:
            db.close()


# Shutdown event
@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown."""
    logger.info("🛑 Application shutdown")
    # Close any remaining WebSocket connections
    from .api.websocket import SESSIONS

    for call_sid, session in list(SESSIONS.items()):
        try:
            await session["websocket"].close()
            logger.info(f"Closed WebSocket for session: {call_sid}")
        except Exception as e:
            logger.error(f"Error closing WebSocket for {call_sid}: {e}")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "voice_agent.main:app",
        host=settings.host,
        port=settings.port,
        log_level=settings.ai_voice_agent_log_level,
        reload=True,
    )
