"""Tests for the handoff reason vocabulary and node->reason map."""

from voice_agent.voice_ai.handoff_reasons import (
    HANDOVER_NODE_REASONS,
    HandoffReason,
    HandoffSource,
    reason_for_handover_request,
    reason_for_node,
)


def test_reason_for_node_defaults_to_survey_routed():
    # The shipped demo survey defines no handover nodes, so every survey-routed
    # handoff lands on the default.
    assert reason_for_node("SOME_UNMAPPED_NODE") == HandoffReason.SURVEY_ROUTED
    assert reason_for_node("") == HandoffReason.SURVEY_ROUTED


def test_mapped_nodes_resolve_to_their_reason():
    # Empty today. Guards a survey that adds handover nodes: whatever it maps
    # must come back from reason_for_node rather than the default.
    for node_id, reason in HANDOVER_NODE_REASONS.items():
        assert reason_for_node(node_id) == reason


def test_reason_for_handover_request_explicit_request_is_caller():
    # Caller explicitly asked for a human -> COACH_REQUESTED / CALLER.
    assert reason_for_handover_request("explicit_request") == (
        HandoffReason.COACH_REQUESTED,
        HandoffSource.CALLER,
    )


def test_reason_for_handover_request_frustration_is_agent():
    # Agent inferred frustration / bot-not-working -> USER_FRUSTRATION / AGENT.
    assert reason_for_handover_request("frustration") == (
        HandoffReason.USER_FRUSTRATION,
        HandoffSource.AGENT,
    )


def test_reason_for_handover_request_agent_codes():
    # The remaining whisper-classification codes the models can emit. All are
    # AGENT-sourced — only an explicit request is attributed to the caller.
    assert reason_for_handover_request("agent_confusion") == (
        HandoffReason.AGENT_CONFUSION,
        HandoffSource.AGENT,
    )
    assert reason_for_handover_request("agent_decision") == (
        HandoffReason.AGENT_DECISION,
        HandoffSource.AGENT,
    )
    assert reason_for_handover_request("other") == (
        HandoffReason.OTHER,
        HandoffSource.AGENT,
    )


def test_reason_for_handover_request_defaults_to_agent_decision():
    # Missing / "none" / unknown -> the model decided but didn't say why.
    for value in ("none", "", "something_unexpected"):
        assert reason_for_handover_request(value) == (
            HandoffReason.AGENT_DECISION,
            HandoffSource.AGENT,
        )
