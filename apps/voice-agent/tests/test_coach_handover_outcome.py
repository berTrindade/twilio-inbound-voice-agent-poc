"""Tests for the COACH_HANDOVER outcome strategy.

The COACH_HANDOVER outcome fires when the *small model* returns
``interpretation="handover_to_coach"``. That single interpretation lumps two
distinct cases together: the caller explicitly asking for a human, and the
agent inferring frustration / that the bot isn't working. The small model now
disambiguates them via a ``handover_reason`` field, and this strategy maps that
to the right ``trigger`` / ``handoff_source`` so the handoff funnel can tell a
genuine caller request apart from an agent-inferred handoff.
"""

import types
from unittest.mock import AsyncMock, patch

import pytest

from voice_agent.api.websocket_handlers.outcomes.coach_handover import (
    handle_coach_handover,
)
from voice_agent.voice_ai.handoff_reasons import HandoffReason, HandoffSource

MODULE = "voice_agent.api.websocket_handlers.outcomes.coach_handover"


def _ctx():
    return types.SimpleNamespace(
        call_state_manager=None,  # skip the persist/add_turn block
        websocket=object(),
        conversation_log=None,
        metrics_collector=None,
        active_big_model_node="node_7",
        call_sid="CA1",
    )


def _turn(handover_reason=None):
    small_resp = {"whisper_text": "Caller wants a human; please assist."}
    if handover_reason is not None:
        small_resp["handover_reason"] = handover_reason
    return types.SimpleNamespace(
        reply="Let me connect you with a coach.",
        combined_user_text="i want to talk to a person",
        interpretation="handover_to_coach",
        small_conf=0.9,
        small_resp=small_resp,
    )


async def _run(turn):
    with (
        patch(f"{MODULE}.send_and_log", new=AsyncMock()),
        patch(f"{MODULE}.initiate_coach_handoff", new=AsyncMock()) as init,
        patch(
            f"{MODULE}.settings", new=types.SimpleNamespace(coach_handoff_enabled=True)
        ),
    ):
        await handle_coach_handover(_ctx(), turn)
    init.assert_awaited_once()
    return init.await_args.kwargs


@pytest.mark.parametrize(
    "handover_reason, expected_trigger, expected_source",
    [
        # Caller explicitly asked for a human -> caller-initiated.
        ("explicit_request", HandoffReason.COACH_REQUESTED, HandoffSource.CALLER),
        # Agent inferred frustration / bot-not-working -> agent-inferred.
        ("frustration", HandoffReason.USER_FRUSTRATION, HandoffSource.AGENT),
        # Agent couldn't interpret the caller after attempts -> agent-inferred.
        ("agent_confusion", HandoffReason.AGENT_CONFUSION, HandoffSource.AGENT),
        # Agent judged a human is better for another reason -> agent-inferred.
        ("agent_decision", HandoffReason.AGENT_DECISION, HandoffSource.AGENT),
        # Explicit catch-all bucket -> agent-inferred.
        ("other", HandoffReason.OTHER, HandoffSource.AGENT),
        # Model omitted the field or sent "none" -> safe agent-decision default.
        ("none", HandoffReason.AGENT_DECISION, HandoffSource.AGENT),
        (None, HandoffReason.AGENT_DECISION, HandoffSource.AGENT),
    ],
)
async def test_coach_handover_maps_reason_to_trigger_and_source(
    handover_reason, expected_trigger, expected_source
):
    kwargs = await _run(_turn(handover_reason))
    assert kwargs["trigger"] == expected_trigger
    assert kwargs["handoff_source"] == expected_source
