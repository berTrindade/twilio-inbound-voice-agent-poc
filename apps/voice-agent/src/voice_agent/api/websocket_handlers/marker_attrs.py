"""Pure helpers mapping internal end-of-call / Twilio-callback enums to the
public vocabulary for `voice_survey.call_completed` and `voice_survey.handoff_resolved`.
"""

from ..websocket_types import PromptEndMode


def completion_type_from_end_mode(end_mode: PromptEndMode) -> str:
    """PromptEndMode -> completion_type in {finished, escalation, abandoned}."""
    if end_mode == PromptEndMode.SURVEY_COMPLETED:
        return "finished"
    if end_mode == PromptEndMode.COACH_HANDOFF_STARTED:
        return "escalation"
    return "abandoned"  # USER_ENDED_SESSION + ALREADY_TERMINAL: did not complete


def handoff_outcome_from_dial_status(dial_call_status: str) -> str:
    """Twilio DialCallStatus -> handoff_outcome in
    {succeeded, no_answer, busy, failed, canceled}."""
    s = (dial_call_status or "").lower()
    if s == "completed":
        return "succeeded"
    if s == "no-answer":
        return "no_answer"
    if s == "busy":
        return "busy"
    if s == "canceled":
        return "canceled"
    if s == "failed":
        return "failed"
    return "failed"  # unknown/missing -> failed (never silently drop or mark success)
