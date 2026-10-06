"""Single entry point for initiating a coach handoff.

Every coach-handoff path MUST call `initiate_coach_handoff` so the
`voice_survey.handoff_started` marker can never be skipped and the
started/resolved funnel counts stay paired. Owns the common tail
(persist HandoffContext + emit marker + signal Twilio); callers keep their
own pre-handoff logic and their own return value.
"""

from ..session_context import SessionContext
from ...voice_ai.business_event_instrumentation import start_voice_business_span
from ...voice_ai.handoff_state import HandoffContext, set_handoff
from ...voice_ai.twilio_protocol import send_end


async def initiate_coach_handoff(
    ctx: SessionContext,
    *,
    path: str,
    trigger: str,
    handoff_source: str,
    whisper_text: str,
) -> None:
    response_id = (
        str(ctx.call_state_manager.response_id) if ctx.call_state_manager else ""
    )
    if ctx.call_sid:
        set_handoff(
            HandoffContext(
                call_sid=ctx.call_sid,
                whisper_text=whisper_text,
                resume_snapshot=ctx.adapter.snapshot(),
                participant_phone=ctx.participant_phone,
                path=path,
                response_id=response_id,
                trigger=trigger,
            )
        )
    with start_voice_business_span(
        event="handoff_started",
        call_sid=ctx.call_sid or "",
        session_id=ctx.session_id or "",
        correlation_id=ctx.correlation_id or "",
        response_id=response_id,
    ) as span:
        span.set_attribute("voice_survey.path", path)
        span.set_attribute("voice_survey.trigger", trigger)
        span.set_attribute("voice_survey.handoff_source", handoff_source)
        span.set_attribute("voice_survey.last_node_id", ctx.active_big_model_node or "")
        # The coach whisper carries the human-readable reason. Canned whispers are
        # safe; the big-model whisper can contain caller content, so tag it for
        # the collector to scrub before it reaches any downstream sink.
        span.set_attribute("voice_survey.handoff_whisper_text", whisper_text)
        span.set_attribute("voice_survey.contains_user_content", "true")
    await send_end(
        ctx.websocket, handoff_data={"mode": "coach_handoff", "callSid": ctx.call_sid}
    )
