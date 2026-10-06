"""Span helper for voice-ai business-event marker spans.

Short marker spans nested under the active operational span, same topology as
`start_voice_llm_span`. Common attributes are set here; per-marker payload
attributes are set by the caller.
"""

from contextlib import contextmanager

from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode

_tracer = trace.get_tracer("voice_agent.voice_ai.business_event")


@contextmanager
def start_voice_business_span(
    *,
    event: str,
    call_sid: str = "",
    session_id: str = "",
    correlation_id: str = "",
    response_id: str = "",
):
    """Open a marker span for a voice-ai business event.

    Args:
        event: discriminator — call_started | milestone | handoff_started |
            handoff_resolved | call_completed.
    """
    attributes = {
        "voice_survey.event": event,
        "call_sid": call_sid,
        "session_id": session_id,
        "correlation_id": correlation_id,
        "response_id": response_id,
    }

    with _tracer.start_as_current_span(
        "voice_survey.business_event",
        attributes=attributes,
    ) as span:
        try:
            yield span
        except Exception as exc:
            span.record_exception(exc)
            span.set_status(Status(StatusCode.ERROR, str(exc)))
            raise
