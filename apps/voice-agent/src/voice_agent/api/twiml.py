"""TwiML endpoints for Twilio ConversationRelay and PSTN coach handoff."""

import json
import logging

from fastapi import APIRouter, BackgroundTasks, Depends, Request

from ..config import settings
from .twilio_auth import verify_twilio_signature
from ..voice_ai.async_persistence import persist_recording_metadata
from ..voice_ai.twilio_protocol import (
    build_twiml,
    build_dial_twiml,
    build_hangup_twiml,
    build_say_hangup_twiml,
    build_whisper_twiml,
)
from ..voice_ai.handoff_state import get_handoff, pop_handoff
from ..voice_ai.business_event_instrumentation import start_voice_business_span
from .websocket_handlers.marker_attrs import handoff_outcome_from_dial_status

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(verify_twilio_signature)])


@router.post("/twiml")
async def twiml_endpoint():
    """
    TwiML endpoint that provides instructions to Twilio for ConversationRelay.

    Returns:
        XML response with ConversationRelay configuration
    """
    logger.info("TwiML endpoint")

    xml = build_twiml(
        ws_url=settings.ws_url,
        welcome=settings.welcome_greeting,
        language=settings.language,
        voice=settings.voice,
        tts_provider=settings.tts_provider,
        transcription_provider=settings.transcription_provider,
        welcome_greeting_interruptible=settings.welcome_greeting_interruptible,
        transcription_language=settings.transcription_language,
        speech_model=settings.speech_model,
        hints=settings.transcription_hints,
        deepgram_smart_format=settings.deepgram_smart_format,
        recording_enabled=settings.twilio_recording_enabled,
        recording_status_callback_url=settings.twilio_recording_status_callback_url,
        recording_status_callback_event=settings.twilio_recording_status_callback_event,
        recording_name=settings.twilio_recording_name,
        recording_channels=settings.twilio_recording_channels,
        recording_track=settings.twilio_recording_track,
    )

    logger.info(f"TwiML requested - WS URL: {settings.ws_url}")
    return xml


@router.post("/twiml/session_end")
async def session_end(request: Request):
    """
    Called by Twilio after ConversationRelay ends (via <Connect action=...>).

    Routes to <Dial> for coach handoff or hangs up for normal survey completion.
    """
    form = await request.form()
    call_sid = form.get("CallSid")
    raw = form.get("HandoffData") or form.get("handoffData")

    handoff_data_present = bool(raw)
    handoff_data_parse_error = False

    mode = "complete"
    if raw:
        try:
            parsed = json.loads(raw)
            mode = parsed.get("mode", mode)
        except Exception:
            handoff_data_parse_error = True
            logger.warning(
                "Failed to parse HandoffData in session_end",
                extra={
                    "call_sid": call_sid,
                    "handoff_data_present": handoff_data_present,
                    "handoff_data_length": len(raw) if isinstance(raw, str) else None,
                },
                exc_info=True,
            )

    logger.info(
        "session_end called",
        extra={
            "call_sid": call_sid,
            "mode": mode,
            "handoff_data_present": handoff_data_present,
            "handoff_data_parse_error": handoff_data_parse_error,
            "coach_handoff_enabled": settings.coach_handoff_enabled,
            "coach_phone_configured": bool(settings.coach_phone_number),
            "coach_dial_timeout_seconds": settings.coach_dial_timeout_seconds,
            "session_status": form.get("SessionStatus"),
            "session_duration": form.get("SessionDuration"),
            "call_status": form.get("CallStatus"),
        },
    )

    if mode != "coach_handoff":
        logger.info(
            "session_end returning hangup because mode is not coach_handoff",
            extra={
                "call_sid": call_sid,
                "mode": mode,
                "handoff_data_present": handoff_data_present,
                "handoff_data_parse_error": handoff_data_parse_error,
                "coach_phone_configured": bool(settings.coach_phone_number),
            },
        )
        if call_sid:
            pop_handoff(call_sid)
        return build_hangup_twiml()

    if not settings.coach_phone_number:
        logger.error(
            "Coach handoff requested but COACH_PHONE_NUMBER is not configured",
            extra={
                "call_sid": call_sid,
                "mode": mode,
                "handoff_data_present": handoff_data_present,
            },
        )
        if call_sid:
            pop_handoff(call_sid)
        return build_hangup_twiml()

    ctx = get_handoff(call_sid) if call_sid else None
    participant_phone = ctx.participant_phone if ctx else None

    if not ctx:
        logger.warning(
            "Coach handoff requested but no handoff context was found; dialing with fallback whisper context",
            extra={
                "call_sid": call_sid,
                "mode": mode,
                "handoff_data_present": handoff_data_present,
            },
        )

    logger.info(
        "session_end returning Dial for coach handoff",
        extra={
            "call_sid": call_sid,
            "coach_dial_timeout_seconds": settings.coach_dial_timeout_seconds,
            "coach_phone_configured": bool(settings.coach_phone_number),
            "caller_id_present": bool(participant_phone),
            "handoff_context_present": bool(ctx),
            "handoff_path": getattr(ctx, "path", "") if ctx else "",
            "handoff_trigger": getattr(ctx, "trigger", "") if ctx else "",
        },
    )

    return build_dial_twiml(
        coach_number=settings.coach_phone_number,
        whisper_url="/twiml/coach_whisper",
        dial_action_url="/twiml/handoff_result",
        timeout_seconds=settings.coach_dial_timeout_seconds,
        caller_id=participant_phone or None,
    )


@router.post("/twiml/coach_whisper")
async def coach_whisper(request: Request):
    """
    Coach-only whisper TwiML, played on the coach's leg before the call is bridged.
    The participant never hears this.
    """
    form = await request.form()
    call_sid = form.get("CallSid")
    ctx = get_handoff(call_sid) if call_sid else None
    text = ctx.whisper_text if ctx else "Incoming handoff from the voice agent."

    logger.info("coach_whisper called", extra={"call_sid": call_sid})
    return build_whisper_twiml(text)


@router.post("/twiml/handoff_result")
async def handoff_result(request: Request):
    """
    Called by Twilio after the <Dial> to the coach completes.

    Hangs up on completed dial outcomes. For failed dial outcomes, plays a
    caller-facing fallback message before hanging up.
    """
    form = await request.form()

    call_sid = form.get("CallSid")
    status = (form.get("DialCallStatus") or "").lower()

    dial_call_sid = form.get("DialCallSid")
    dial_call_duration = form.get("DialCallDuration")
    dial_bridged = form.get("DialBridged")
    mapped_outcome = handoff_outcome_from_dial_status(status)

    handoff_ctx = pop_handoff(call_sid) if call_sid else None

    logger.info(
        "handoff_result called",
        extra={
            "call_sid": call_sid,
            "dial_call_status": status,
            "dial_call_sid": dial_call_sid,
            "dial_call_duration": dial_call_duration,
            "dial_bridged": dial_bridged,
            "mapped_handoff_outcome": mapped_outcome,
            "handoff_context_present": bool(handoff_ctx),
            "handoff_path": getattr(handoff_ctx, "path", "") if handoff_ctx else "",
            "handoff_trigger": (
                getattr(handoff_ctx, "trigger", "") if handoff_ctx else ""
            ),
        },
    )

    with start_voice_business_span(
        event="handoff_resolved",
        call_sid=call_sid or "",
        session_id="",
        correlation_id="",
        response_id=(
            str(getattr(handoff_ctx, "response_id", "") or "") if handoff_ctx else ""
        ),
    ) as span:
        span.set_attribute("voice_survey.handoff_outcome", mapped_outcome)
        span.set_attribute(
            "voice_survey.path",
            getattr(handoff_ctx, "path", "") if handoff_ctx else "",
        )
        span.set_attribute(
            "voice_survey.trigger",
            getattr(handoff_ctx, "trigger", "") if handoff_ctx else "",
        )
        span.set_attribute("voice_survey.dial_call_status", status or "")
        span.set_attribute("voice_survey.dial_call_sid", dial_call_sid or "")
        span.set_attribute("voice_survey.dial_call_duration", dial_call_duration or "")
        span.set_attribute("voice_survey.dial_bridged", dial_bridged or "")

    if status == "completed":
        logger.info(
            "handoff_result returning hangup for completed coach dial",
            extra={
                "call_sid": call_sid,
                "dial_call_sid": dial_call_sid,
                "dial_call_duration": dial_call_duration,
                "dial_bridged": dial_bridged,
            },
        )
        return build_hangup_twiml()

    logger.info(
        "handoff_result returning fallback message for unsuccessful coach dial",
        extra={
            "call_sid": call_sid,
            "dial_call_status": status,
            "dial_call_sid": dial_call_sid,
            "dial_call_duration": dial_call_duration,
            "dial_bridged": dial_bridged,
            "mapped_handoff_outcome": mapped_outcome,
        },
    )

    # no-answer / busy / failed / canceled
    return build_say_hangup_twiml(
        "We were unable to reach a coach at this time. "
        "Please call back to continue where you left off."
    )


def _build_recording_metadata(
    *,
    account_sid: str | None,
    recording_sid: str | None,
    status: str | None,
    duration: str | None,
    channels: str | None,
    track: str | None,
    start_time: str | None,
) -> dict:
    """Build the recording block saved to the call and surfaced in the transcript.

    s3_key follows Twilio's external-storage layout "{AccountSid}/{RecordingSid}".
    Fields Twilio did not send are dropped so the block stays clean.
    """
    metadata = {
        "recording_sid": recording_sid,
        "account_sid": account_sid,
        "status": status,
        "duration": duration,
        "channels": channels,
        "track": track,
        "start_time": start_time,
    }
    if account_sid and recording_sid:
        metadata["s3_key"] = f"{account_sid}/{recording_sid}"
    return {k: v for k, v in metadata.items() if v is not None}


@router.post("/twiml/recording_status")
async def recording_status(request: Request, background_tasks: BackgroundTasks):
    """
    Twilio callback for <Start><Recording> lifecycle events.
    Used to link RecordingSid/RecordingUrl/status back to our call/session.
    """
    form = await request.form()

    account_sid = form.get("AccountSid")
    call_sid = form.get("CallSid")
    recording_sid = form.get("RecordingSid")
    recording_event_status = form.get("RecordingStatus")
    recording_duration = form.get("RecordingDuration")
    recording_channels = form.get("RecordingChannels")
    recording_start_time = form.get("RecordingStartTime")
    recording_track = form.get("RecordingTrack")
    # recording_url = form.get("RecordingUrl") - sensitive data, better not to log

    log_extra = {
        "account_sid": account_sid,
        "call_sid": call_sid,
        "recording_sid": recording_sid,
        "recording_event_status": recording_event_status,
        "recording_duration": recording_duration,
        "recording_channels": recording_channels,
        "recording_start_time": recording_start_time,
        "recording_track": recording_track,
    }

    if recording_event_status == "completed":
        logger.info("Twilio recording completed callback", extra=log_extra)
    elif recording_event_status == "absent":
        logger.warning("Twilio recording absent callback", extra=log_extra)
    else:
        logger.debug("Twilio recording status callback", extra=log_extra)

    # Persist off-request so we return 200 to Twilio promptly.
    if call_sid:
        recording = _build_recording_metadata(
            account_sid=account_sid,
            recording_sid=recording_sid,
            status=recording_event_status,
            duration=recording_duration,
            channels=recording_channels,
            track=recording_track,
            start_time=recording_start_time,
        )
        background_tasks.add_task(persist_recording_metadata, call_sid, recording)

    return {"ok": True}
