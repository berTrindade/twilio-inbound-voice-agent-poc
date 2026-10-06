import logging

from ..session_context import SessionContext
from ..websocket_types import PromptEndMode, PromptHandlingResult
from ...config import settings
from ...voice_ai.async_persistence import complete_response_async
from ...voice_ai.business_event_instrumentation import start_voice_business_span
from ...voice_ai.handoff_reasons import HandoffReason, HandoffSource
from ...voice_ai.pending_handoff_state import clear_pending_handoff
from ..websocket_helpers import survey_completed_coach_whisper
from .handoff_initiation import initiate_coach_handoff
from ...survey_submission import MilestoneEvent
from .marker_attrs import completion_type_from_end_mode

logger = logging.getLogger(__name__)


def emit_call_completed_marker(ctx: SessionContext, *, completion_type: str) -> None:
    """Emit `voice_survey.call_completed` for any call termination.

    `completion_type` is the caller's classification: graceful ends pass the
    `PromptEndMode` mapping (finished/escalation/abandoned); the websocket
    disconnect/error paths pass "disconnected"/"error" directly. Turn/duration
    metrics are derived from the call-state manager; no-ops when there is none
    (e.g. the call ended before setup completed).
    """
    csm = ctx.call_state_manager
    if not csm:
        return
    completed = getattr(csm, "completed_questions", []) or []
    with start_voice_business_span(
        event="call_completed",
        call_sid=ctx.call_sid or "",
        session_id=ctx.session_id or "",
        correlation_id=ctx.correlation_id or "",
        response_id=str(csm.response_id),
    ) as span:
        span.set_attribute("voice_survey.completion_type", completion_type)
        span.set_attribute(
            "voice_survey.final_node_id", ctx.active_big_model_node or ""
        )
        span.set_attribute(
            "voice_survey.turn_count",
            sum(len(q.get("turns", [])) for q in completed),
        )
        span.set_attribute("voice_survey.duration_ms", csm.get_total_duration_ms() or 0)


async def handle_session_completion(
    result: PromptHandlingResult,
    ctx: SessionContext,
) -> None:
    """Finalize call state, trigger post-completion actions, emit call_ended milestone."""
    completion_reason = result.end_mode.completion_reason

    if ctx.call_state_manager:
        try:
            ctx.call_state_manager.finalize_call(completion_reason)
            final_metadata = ctx.call_state_manager.build_session_metadata(
                completion_reason
            )
            await complete_response_async(
                ctx.call_state_manager.response_id,
                final_metadata,
            )
        except Exception as e:
            logger.error(f"Error finalizing call on completion: {e}", exc_info=True)

    if ctx.call_state_manager:
        emit_call_completed_marker(
            ctx, completion_type=completion_type_from_end_mode(result.end_mode)
        )

    if (
        result.end_mode == PromptEndMode.SURVEY_COMPLETED
        and settings.coach_handoff_enabled
    ):
        await initiate_coach_handoff(
            ctx,
            path="happy",
            trigger=HandoffReason.COMPLETED_SURVEY,
            handoff_source=HandoffSource.SURVEY,
            whisper_text=survey_completed_coach_whisper(),
        )
    elif result.end_mode == PromptEndMode.SURVEY_COMPLETED:
        logger.info(
            "Survey completed but coach handoff disabled — ending session without PSTN transfer",
            extra={"call_sid": ctx.call_sid},
        )

    try:
        if ctx.milestone_dispatcher:
            call_ended_event = MilestoneEvent(
                event_type="call_ended",
                question_id=None,
                source=None,
                previous_source=None,
                all_answers=dict(ctx.adapter.engine.answers),
                response_id=(
                    ctx.call_state_manager.response_id
                    if ctx.call_state_manager
                    else None
                ),
                call_sid=ctx.call_sid,
                correlation_id=ctx.correlation_id,
            )
            await ctx.milestone_dispatcher.on_milestone(call_ended_event)
    finally:
        # never leak a pending-handoff entry for a call that has ended,
        # even if the call_ended milestone dispatch raises.
        clear_pending_handoff(ctx.call_sid)
