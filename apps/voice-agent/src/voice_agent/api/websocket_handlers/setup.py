"""Handler for the Twilio 'setup' message."""

import logging
from typing import Any, Dict, Optional

from fastapi import WebSocket

from ...config import settings
from ...utils.encryption import hmac_hash
from ...database import SessionLocal
from ...repositories import SurveyResponseRepository
from ...voice_ai.call_state_manager import CallStateManager
from ...voice_ai.llm_handler_factory import LLMHandler
from ...survey_submission import (
    SurveyMilestoneDispatcher,
    LocalSubmissionHandler,
    WebhookSubmissionHandler,
)
from ...voice_ai.business_event_instrumentation import start_voice_business_span
from ..websocket_helpers import sanitize_for_log

logger = logging.getLogger(__name__)


def emit_call_started_marker(
    *,
    call_sid: str,
    session_id: str,
    correlation_id: str,
    response_id: str,
    participant_phone: str,
) -> None:
    """Emit `voice_survey.call_started` at the end of call setup.

    Phone is hashed with a keyed HMAC (HMAC-SHA256 via hmac_hash) so the raw
    E.164 string never reaches a span.
    """
    phone_hash = hmac_hash(participant_phone) if participant_phone else ""
    with start_voice_business_span(
        event="call_started",
        call_sid=call_sid,
        session_id=session_id,
        correlation_id=correlation_id,
        response_id=response_id,
    ) as span:
        span.set_attribute("voice_survey.phone_hash", phone_hash)


async def handle_setup_message(
    websocket: WebSocket,
    msg: Dict[str, Any],
    session_id: str,
    correlation_id: str,
    llm_handler: LLMHandler,
    sessions: Dict[str, Dict[str, Any]],
) -> tuple[
    Optional[str],
    Optional[CallStateManager],
    Optional[SurveyMilestoneDispatcher],
    str,
]:
    """
    Handle Twilio's initial "setup" message and register the session.

    Phase A: Creates SurveyResponse record and initializes CallStateManager.

    Returns:
        Tuple of (call_sid, call_state_manager, milestone_dispatcher, participant_phone)
    """
    call_sid = sanitize_for_log(msg.get("callSid"))
    participant_phone = msg.get("from", "")
    websocket.call_sid = call_sid  # type: ignore[attr-defined]
    sessions[call_sid] = {
        "websocket": websocket,
        "session_id": session_id,
        "correlation_id": correlation_id,
    }

    logger.info(
        "Session initialized for call",
        extra={
            "correlation_id": sanitize_for_log(correlation_id),
            "session_id": sanitize_for_log(session_id),
            "call_sid": sanitize_for_log(call_sid),
            "message_type": "setup",
        },
    )

    # Phase A: Initialize persistence
    call_state_manager = None
    try:
        # Get survey_id from app state (set during startup)
        survey_id = getattr(websocket.app.state, "default_survey_id", None)

        if survey_id is None:
            logger.error(
                "No default survey_id available in app state",
                extra={"call_sid": call_sid},
            )
            return call_sid, None, None, participant_phone

        # Create SurveyResponse record
        db = SessionLocal()
        try:
            repo = SurveyResponseRepository(db)

            # Use call_sid as participant identifier (as per user requirements)
            survey_response = repo.create(
                survey_id=survey_id,
                participant_phone=call_sid,
                session_metadata={
                    "call_sid": call_sid,
                    "session_id": session_id,
                    "correlation_id": correlation_id,
                },
                call_sid=call_sid,
            )

            # Initialize CallStateManager
            call_state_manager = CallStateManager(
                response_id=survey_response.id,
                call_sid=call_sid,
                session_id=session_id,
                correlation_id=correlation_id,
            )

            # Initialize survey submission dispatcher and register the local
            # handler, which records milestones to the local database and calls
            # no external service.
            dispatcher = SurveyMilestoneDispatcher()
            dispatcher.register(
                LocalSubmissionHandler.from_config(
                    settings,
                    response_id=survey_response.id,
                    repository=repo,
                )
            )
            # When a webhook target is configured, also forward completed
            # surveys to it. Unset URL -> local-only, behaviour unchanged.
            if settings.submission_webhook_url:
                dispatcher.register(
                    WebhookSubmissionHandler.from_config(
                        settings,
                        response_id=survey_response.id,
                        repository=repo,
                    )
                )

            logger.info(
                "Initialized call state manager and milestone dispatcher",
                extra={
                    "call_sid": call_sid,
                    "response_id": str(survey_response.id),
                    "survey_id": str(survey_id),
                },
            )

            emit_call_started_marker(
                call_sid=call_sid,
                session_id=session_id,
                correlation_id=correlation_id,
                response_id=str(survey_response.id),
                participant_phone=participant_phone,
            )

        finally:
            db.close()

    except Exception as e:
        logger.error(
            "Failed to initialize call state manager (non-fatal)",
            extra={
                "call_sid": call_sid,
                "error": str(e),
                "error_type": type(e).__name__,
            },
            exc_info=True,
        )
        # Continue without persistence rather than fail the call
        call_state_manager = None
        dispatcher = None

    return call_sid, call_state_manager, dispatcher, participant_phone
