"""Outcome strategy registry for conversation turn outcomes."""

from typing import Callable, Dict

from .base import TurnContext
from .classifier import ConversationTurnOutcome, classify_prompt_outcome
from .big_model_response import handle_big_model_response
from .user_question import handle_user_question
from .happy_path import handle_happy_path
from .invalid_retry import handle_invalid_retry
from .escalation import handle_escalation
from .coach_handover import handle_coach_handover
from .guardrail_topic import handle_guardrail_topic

OUTCOME_STRATEGIES: Dict[ConversationTurnOutcome, Callable] = {
    ConversationTurnOutcome.USER_QUESTION: handle_user_question,
    ConversationTurnOutcome.HAPPY_PATH: handle_happy_path,
    ConversationTurnOutcome.INVALID_RETRY: handle_invalid_retry,
    ConversationTurnOutcome.ESCALATE: handle_escalation,
    ConversationTurnOutcome.COACH_HANDOVER: handle_coach_handover,
    ConversationTurnOutcome.GUARDRAIL_TOPIC: handle_guardrail_topic,
}

__all__ = [
    "TurnContext",
    "ConversationTurnOutcome",
    "classify_prompt_outcome",
    "OUTCOME_STRATEGIES",
    "handle_big_model_response",
    "handle_user_question",
    "handle_happy_path",
    "handle_invalid_retry",
    "handle_escalation",
    "handle_coach_handover",
    "handle_guardrail_topic",
]
