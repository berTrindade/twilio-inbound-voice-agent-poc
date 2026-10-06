"""Handoff context store for PSTN coach transfers, keyed by Twilio CallSid.

The context has to survive the ConversationRelay -> Dial boundary: it is
written by the websocket process when the agent decides to hand off, and read
back by the /twiml/session_end, /twiml/coach_whisper and /twiml/handoff_result
webhooks so the coach hears why they are being called.

That boundary is the reason this is persisted rather than kept in a module
dict. Twilio addresses the webhooks to the service, not to the process that
held the websocket, so in-process state only works while there is exactly one
process. It is stored on the call's own survey_responses row, found by the
indexed call_sid column, under a "handoff" key in the encrypted
session_metadata blob.

A call with no row (no default survey configured, or setup failed before the
row was created) has nowhere to store this. The handoff still happens: the
TwiML side falls back to a generic whisper, which is the same degraded
behaviour as a context that was never set.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field, fields
from typing import Any, Dict, Optional

from ..database import SessionLocal
from ..repositories import SurveyResponseRepository

logger = logging.getLogger(__name__)

_KEY = "handoff"


@dataclass
class HandoffContext:
    call_sid: str
    whisper_text: str
    resume_snapshot: Dict[str, Any] = field(default_factory=dict)
    attempts: int = 0
    participant_phone: str = ""
    path: str = ""  # "happy" | "escalation"
    response_id: str = ""
    trigger: str = ""  # carried onto handoff_resolved so the resolved span is
    # self-contained for analytics (no started/resolved join required)


def _from_stored(stored: Any) -> Optional[HandoffContext]:
    """Rebuild a context from JSONB, ignoring keys the dataclass no longer has.

    A row can outlive a deploy, so a stored blob may carry fields from an older
    shape. Dropping unknown keys keeps a rename from raising inside a webhook.
    """
    if not isinstance(stored, dict):
        return None
    known = {f.name for f in fields(HandoffContext)}
    return HandoffContext(**{k: v for k, v in stored.items() if k in known})


def set_handoff(ctx: HandoffContext) -> None:
    """Persist the context for `ctx.call_sid`. Never raises into the caller."""
    _write(ctx.call_sid, asdict(ctx))


def get_handoff(call_sid: str) -> Optional[HandoffContext]:
    """Read the context without clearing it."""
    db = None
    try:
        db = SessionLocal()
        row = SurveyResponseRepository(db).get_by_call_sid(call_sid)
        if row is None:
            return None
        from ..utils.encryption import decrypt_json

        return _from_stored(decrypt_json(row.session_metadata).get(_KEY))
    except Exception:
        logger.error(
            "Failed to read handoff context (non-fatal)",
            extra={"call_sid": call_sid},
            exc_info=True,
        )
        return None
    finally:
        if db is not None:
            db.close()


def pop_handoff(call_sid: str) -> Optional[HandoffContext]:
    """Read the context and clear it, so a retried webhook cannot reuse it."""
    ctx = get_handoff(call_sid)
    if ctx is not None:
        _write(call_sid, None)
    return ctx


def _write(call_sid: str, value: Optional[dict]) -> None:
    if not call_sid:
        return
    db = None
    try:
        db = SessionLocal()
        repo = SurveyResponseRepository(db)
        row = repo.get_by_call_sid(call_sid)
        if row is None:
            logger.warning(
                "No survey response for call_sid; handoff context not stored",
                extra={"call_sid": call_sid},
            )
            return
        repo.update_session_metadata(row.id, {_KEY: value})
    except Exception:
        logger.error(
            "Failed to store handoff context (non-fatal)",
            extra={"call_sid": call_sid},
            exc_info=True,
        )
    finally:
        if db is not None:
            db.close()
