"""In-memory pending coach-handoff signal, keyed by Twilio CallSid.

A background submission handler (or a side-effect call) records that a blocking
API failure occurred; the websocket turn loop consumes the signal on the
caller's next utterance and routes to the existing coach-handoff outcome.
Mirrors handoff_state.py. Always cleared on call end to avoid leaks.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Dict, Optional

logger = logging.getLogger(__name__)


@dataclass
class PendingHandoff:
    call_sid: str
    reason: str  # e.g. "validation_failed" — for logs/whisper, not user-facing
    whisper_text: str  # coach whisper context
    trigger: str  # HandoffReason code for the voice_survey.handoff_started marker


_PENDING: Dict[str, PendingHandoff] = {}


def request_coach_handoff(
    call_sid: Optional[str], reason: str, whisper_text: str, trigger: str
) -> None:
    if not call_sid:
        logger.warning(
            "request_coach_handoff called without call_sid", extra={"reason": reason}
        )
        return
    _PENDING[call_sid] = PendingHandoff(
        call_sid=call_sid, reason=reason, whisper_text=whisper_text, trigger=trigger
    )
    logger.info(
        "Pending coach handoff recorded",
        extra={"call_sid": call_sid, "reason": reason, "trigger": trigger},
    )


def pop_pending_handoff(call_sid: Optional[str]) -> Optional[PendingHandoff]:
    if not call_sid:
        return None
    return _PENDING.pop(call_sid, None)


def clear_pending_handoff(call_sid: Optional[str]) -> None:
    if call_sid:
        _PENDING.pop(call_sid, None)
