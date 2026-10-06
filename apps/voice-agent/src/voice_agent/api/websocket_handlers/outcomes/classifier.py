"""Classification logic for conversation turn outcomes."""

from enum import Enum, auto
from typing import Any, Dict

from ....voice_ai.guardrails.guardrails_response_manager import (
    GUARDRAIL_TOPIC_RESPONSES,
)


class ConversationTurnOutcome(Enum):
    USER_QUESTION = auto()
    HAPPY_PATH = auto()
    INVALID_RETRY = auto()
    ESCALATE = auto()
    COACH_HANDOVER = auto()
    GUARDRAIL_TOPIC = auto()


def classify_prompt_outcome(
    interpretation: str,
    val_res: Dict[str, Any],
    escalate: bool,
    guardrail_topic: str,
) -> ConversationTurnOutcome:
    """
    Small pure function that decides which path prompt handling should take.
    This isolates policy from side-effects and makes the logic testable.
    """
    # --- GUARDRAIL (highest priority) ---
    # The topic decides, not the label: the small model can tag a medical
    # question correctly and still call it a user_question. Only topics with a
    # canned response count, so an invented one cannot route a turn to silence.
    if guardrail_topic in GUARDRAIL_TOPIC_RESPONSES:
        return ConversationTurnOutcome.GUARDRAIL_TOPIC

    if interpretation == "handover_to_coach":
        return ConversationTurnOutcome.COACH_HANDOVER

    if interpretation == "user_question":
        return ConversationTurnOutcome.USER_QUESTION

    if not escalate and val_res.get("valid"):
        return ConversationTurnOutcome.HAPPY_PATH

    if not escalate and not val_res.get("valid"):
        return ConversationTurnOutcome.INVALID_RETRY

    return ConversationTurnOutcome.ESCALATE
