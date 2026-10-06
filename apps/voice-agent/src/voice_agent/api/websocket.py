"""WebSocket endpoint for Twilio ConversationRelay with metrics and tracing."""

import json
import logging
import time
import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from opentelemetry import trace

from ..config import settings
from ..metrics import get_metrics_collector
from ..voice_ai.llm_handler_factory import create_llm_handler
from ..voice_ai.call_state_manager import CallStateManager
from ..voice_ai.async_persistence import abandon_response_async
from ..survey_submission import SurveyMilestoneDispatcher
from .websocket_types import PromptEndMode
from .session_context import SessionContext
from .websocket_helpers import (
    sanitize_for_log,
)  # noqa: F401 (speak_next_or_finish re-exported for tests)
from .websocket_handlers import (
    handle_setup_message,
    handle_unknown_message,
    HANDLER_REGISTRY,
)
from .websocket_handlers.session_init import initialize_survey_session
from .websocket_handlers.session_completion import (
    handle_session_completion,
    emit_call_completed_marker,
)
from .websocket_handlers.prompt_handler import (
    handle_prompt_message,
)  # noqa: F401 (re-exported for tests)

logger = logging.getLogger(__name__)

router = APIRouter()

# Store active sessions by callSid
SESSIONS: Dict[str, Dict[str, Any]] = {}

# OpenTelemetry tracer
tracer = trace.get_tracer(__name__)


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for Twilio ConversationRelay."""
    metrics_collector = get_metrics_collector()

    await websocket.accept()
    call_sid: Optional[str] = None
    correlation_id = str(uuid.uuid4())
    session_id = str(uuid.uuid4())
    conversation_log: List[Dict[str, str]] = []
    call_state_manager: Optional[CallStateManager] = None
    milestone_dispatcher: Optional[SurveyMilestoneDispatcher] = None

    llm_handler = create_llm_handler(settings)

    # No client address: it carries an ephemeral port, so every connection
    # minted a new time series and the up-down counter never cancelled.
    metrics_collector.record_connection_opened({"endpoint": "websocket"})

    adapter = await initialize_survey_session(
        websocket=websocket,
        metrics_collector=metrics_collector,
        conversation_log=conversation_log,
    )
    if adapter is None:
        return

    ctx = SessionContext(
        websocket=websocket,
        adapter=adapter,
        llm_handler=llm_handler,
        conversation_log=conversation_log,
        correlation_id=correlation_id,
        session_id=session_id,
        metrics_collector=metrics_collector,
    )

    try:
        with tracer.start_as_current_span("websocket.session") as session_span:
            session_span.set_attribute("session_id", session_id)
            session_span.set_attribute("correlation_id", correlation_id)

            while True:
                data = await websocket.receive_text()
                # Start the clock after the await. Before it, this measured how
                # long the caller took to speak, so every turn read seconds slow.
                receive_start = time.time()
                msg = json.loads(data)
                mtype = msg.get("type", "unknown")
                metrics_collector.record_message_received({"message_type": mtype})

                with tracer.start_as_current_span(
                    f"websocket.message.{mtype}"
                ) as msg_span:
                    msg_span.set_attribute("message_type", mtype)
                    msg_span.set_attribute("call_sid", call_sid or "unknown")
                    msg_span.set_attribute("correlation_id", correlation_id)

                    if mtype == "setup":
                        msg_span.set_attribute("action", "setup")
                        (
                            call_sid,
                            call_state_manager,
                            milestone_dispatcher,
                            participant_phone,
                        ) = await handle_setup_message(
                            websocket=websocket,
                            msg=msg,
                            session_id=session_id,
                            correlation_id=correlation_id,
                            llm_handler=llm_handler,
                            sessions=SESSIONS,
                        )
                        ctx.call_sid = call_sid
                        ctx.call_state_manager = call_state_manager
                        ctx.milestone_dispatcher = milestone_dispatcher
                        ctx.participant_phone = participant_phone
                        msg_span.set_attribute("call_sid", call_sid or "unknown")
                        # Backfill call_sid onto the session-root span (now known
                        # post-setup) so the whole call trace is correlatable by it.
                        session_span.set_attribute("call_sid", call_sid or "unknown")

                    elif mtype == "prompt":
                        result = await handle_prompt_message(
                            ctx=ctx, msg=msg, msg_span=msg_span
                        )
                        ctx.active_big_model_node = result.active_big_model_node
                        if result.end_mode != PromptEndMode.CONTINUE:
                            await handle_session_completion(result, ctx)
                            break

                    else:
                        msg_span.set_attribute("action", mtype)
                        handler = HANDLER_REGISTRY.get(mtype, handle_unknown_message)
                        handler(msg, ctx)

                    processing_time_ms = (time.time() - receive_start) * 1000
                    metrics_collector.record_message_processing_time(
                        processing_time_ms,
                        {"message_type": mtype},
                    )
                    msg_span.set_attribute("response_duration_ms", processing_time_ms)

    except WebSocketDisconnect:
        logger.info(
            "WebSocket disconnected for call",
            extra={
                "correlation_id": sanitize_for_log(correlation_id),
                "session_id": sanitize_for_log(session_id),
                "call_sid": sanitize_for_log(call_sid),
                "event": "websocket_disconnect",
            },
        )
        if call_state_manager:
            try:
                call_state_manager.finalize_call("user_disconnect")
                final_metadata = call_state_manager.build_session_metadata(
                    "user_disconnect"
                )
                await abandon_response_async(
                    call_state_manager.response_id, final_metadata
                )
            except Exception as e:
                logger.error(f"Error finalizing call on disconnect: {e}", exc_info=True)
            try:
                emit_call_completed_marker(ctx, completion_type="disconnected")
            except Exception as e:
                logger.error(
                    f"Error emitting call_completed on disconnect: {e}", exc_info=True
                )

    except Exception as e:
        logger.error(
            "WebSocket error occurred",
            extra={
                "correlation_id": sanitize_for_log(correlation_id),
                "session_id": sanitize_for_log(session_id),
                "call_sid": sanitize_for_log(call_sid),
                "error": sanitize_for_log(str(e)),
                "error_type": type(e).__name__,
            },
            exc_info=True,
        )
        metrics_collector.record_error(
            type(e).__name__,
            {"endpoint": "websocket"},
        )
        try:
            emit_call_completed_marker(ctx, completion_type="error")
        except Exception as emit_err:
            logger.error(
                f"Error emitting call_completed on error path: {emit_err}",
                exc_info=True,
            )

    finally:
        # A completed survey breaks out of the loop and raises nothing, so
        # without this neither the close metric nor the session cleanup ran on
        # the happy path, and SESSIONS grew by one entry per successful call.
        metrics_collector.record_connection_closed({"endpoint": "websocket"})
        SESSIONS.pop(call_sid, None)
