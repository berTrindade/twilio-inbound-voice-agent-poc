import json
import logging
from typing import Any, Dict, Optional

from fastapi import WebSocket
from fastapi.responses import Response
from twilio.twiml.voice_response import VoiceResponse, Connect, Dial

logger = logging.getLogger(__name__)


async def send_text_token(
    ws: WebSocket,
    text: str,
    last: bool = False,
    interruptible: Optional[bool] = None,
    preemptible: Optional[bool] = None,
    lang: Optional[str] = None,
):
    """
    Send a Text Token to Twilio ConversationRelay (TTS request).
    Spec: { type: "text", token, last, interruptible?, preemptible? }
    """
    try:
        msg = {"type": "text", "token": text, "last": last}
        if interruptible is not None:
            msg["interruptible"] = bool(interruptible)
        if preemptible is not None:
            msg["preemptible"] = bool(preemptible)
        if lang:
            msg["lang"] = lang
        await ws.send_text(json.dumps(msg))
    except Exception:
        logger.exception("Failed to send the websocket message to Twilio")
        return


async def send_end(ws: WebSocket, handoff_data: Optional[Dict[str, Any]] = None):
    """
    Send ConversationRelay {type:end} to cleanly terminate the relay session.
    Twilio will then invoke the <Connect action="..."> callback URL.
    handoffData is serialized as a JSON string as Twilio expects.
    """
    try:
        msg: Dict[str, Any] = {"type": "end"}
        if handoff_data is not None:
            msg["handoffData"] = json.dumps(handoff_data)
        await ws.send_text(json.dumps(msg))
    except Exception:
        logger.exception("Failed to send the end websocket message to Twilio")
        return


def build_twiml(
    ws_url: str,
    welcome: str,
    language: str,
    voice: str,
    transcription_provider: str = "Deepgram",
    tts_provider: str = "Amazon",
    # Twilio ConversationRelay parameter controlling whether the welcome greeting
    # can be interrupted. Valid values: "none", "speech", "dtmf", "any".
    welcome_greeting_interruptible: str = "none",
    transcription_language: str | None = None,
    tts_language: str | None = None,
    speech_model: str | None = None,
    hints: str | None = None,
    deepgram_smart_format: bool | None = None,
    recording_enabled: bool = False,
    recording_status_callback_url: str | None = None,
    recording_channels: str = "dual",
    recording_track: str = "both",
    recording_status_callback_event: str = "in-progress completed absent",
    recording_name: str = "voice_ai_recording",
) -> Response:
    """
    Build Twilio ConversationRelay TwiML.
    The action on <Connect> routes Twilio's control flow after the relay session ends.
    Optionally starts call recording before connecting to ConversationRelay.
    """
    response = VoiceResponse()

    if recording_enabled:
        start = response.start()
        recording_kwargs = {
            "name": recording_name,
            "channels": recording_channels,
            "track": recording_track,
        }

        if recording_status_callback_url:
            recording_kwargs["recording_status_callback"] = (
                recording_status_callback_url
            )
            recording_kwargs["recording_status_callback_method"] = "POST"

            if recording_status_callback_event:
                recording_kwargs["recording_status_callback_event"] = (
                    recording_status_callback_event
                )

        start.recording(**recording_kwargs)

    connect = Connect(action="/twiml/session_end", method="POST")
    connect.conversation_relay(
        url=ws_url,
        welcome_greeting=welcome,
        welcome_greeting_interruptible=welcome_greeting_interruptible,
        language=language,
        voice=voice,
        transcription_provider=transcription_provider,
        tts_provider=tts_provider,
        transcription_language=transcription_language,
        tts_language=tts_language,
        speech_model=speech_model,
        hints=hints,
        deepgram_smart_format=deepgram_smart_format,
    )
    response.append(connect)
    return Response(content=str(response), media_type="text/xml")


def build_dial_twiml(
    coach_number: str,
    whisper_url: str,
    dial_action_url: str,
    timeout_seconds: int = 70,
    caller_id: Optional[str] = None,
) -> Response:
    """Build <Dial> TwiML for cold PSTN transfer to a coach with whisper."""
    response = VoiceResponse()
    dial_kwargs: dict = {
        "timeout": timeout_seconds,
        "action": dial_action_url,
        "method": "POST",
    }
    if caller_id:
        dial_kwargs["caller_id"] = caller_id
    dial = Dial(**dial_kwargs)
    dial.number(coach_number, url=whisper_url)
    response.append(dial)
    return Response(content=str(response), media_type="text/xml")


def build_hangup_twiml() -> Response:
    """Build a TwiML response that immediately hangs up."""
    response = VoiceResponse()
    response.hangup()
    return Response(content=str(response), media_type="text/xml")


def build_say_hangup_twiml(message: str) -> Response:
    """Build a TwiML response that says a message then hangs up."""
    response = VoiceResponse()
    response.say(message)
    response.hangup()
    return Response(content=str(response), media_type="text/xml")


def build_whisper_twiml(whisper_text: str) -> Response:
    """Build coach-only whisper TwiML (played on the coach's leg before bridging)."""
    response = VoiceResponse()
    response.say(whisper_text)
    return Response(content=str(response), media_type="text/xml")
