"""Routing policy for a classified turn."""

import pytest

from voice_agent.api.websocket_handlers.outcomes.classifier import (
    ConversationTurnOutcome,
    classify_prompt_outcome,
)


@pytest.mark.parametrize(
    "interpretation",
    ["predefined_guardrail", "user_question", "answer", "handover_to_coach", "other"],
)
def test_guardrail_topic_wins_whatever_the_interpretation(interpretation):
    outcome = classify_prompt_outcome(
        interpretation, {"valid": True}, False, "medical_dietary"
    )
    assert outcome is ConversationTurnOutcome.GUARDRAIL_TOPIC


@pytest.mark.parametrize("topic", ["none", "", None, "medical"])
def test_no_topic_falls_through_to_the_interpretation(topic):
    outcome = classify_prompt_outcome("user_question", {"valid": False}, False, topic)
    assert outcome is ConversationTurnOutcome.USER_QUESTION


def test_predefined_guardrail_without_a_topic_is_not_a_guardrail():
    outcome = classify_prompt_outcome(
        "predefined_guardrail", {"valid": False}, False, "none"
    )
    assert outcome is ConversationTurnOutcome.INVALID_RETRY
