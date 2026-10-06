"""Tests for the big-model handover path.

When the big escalation model returns ``action="handover_to_coach"`` it, like
the small interpreter, lumps an explicit "I want a human" request together with
inferred frustration / bot-not-working. The big model now emits the same
``handover_reason`` field, and this path maps it to the right ``trigger`` /
``handoff_source`` so the funnel can tell a caller-initiated handoff from an
agent-inferred one.
"""

import types
from unittest.mock import AsyncMock, patch

import pytest

from voice_agent.api.websocket_handlers.outcomes.big_model_response import (
    handle_big_model_response,
)
from voice_agent.voice_ai.handoff_reasons import HandoffReason, HandoffSource

MODULE = "voice_agent.api.websocket_handlers.outcomes.big_model_response"


def _ctx():
    return types.SimpleNamespace(
        call_state_manager=None,  # skip the persist/add_turn block
        websocket=object(),
        conversation_log=None,
        metrics_collector=None,
        call_sid="CA1",
    )


def _resp(handover_reason=None):
    resp = {
        "action": "handover_to_coach",
        "text": "A coach will take over now.",
        "whisper_text": "Caller wants a human.",
    }
    if handover_reason is not None:
        resp["handover_reason"] = handover_reason
    return resp


async def _run(resp):
    with (
        patch(f"{MODULE}.send_and_log", new=AsyncMock()),
        patch(f"{MODULE}.initiate_coach_handoff", new=AsyncMock()) as init,
        patch(
            f"{MODULE}.settings", new=types.SimpleNamespace(coach_handoff_enabled=True)
        ),
    ):
        await handle_big_model_response(_ctx(), {}, resp)
    init.assert_awaited_once()
    return init.await_args.kwargs


@pytest.mark.parametrize(
    "handover_reason, expected_trigger, expected_source",
    [
        ("explicit_request", HandoffReason.COACH_REQUESTED, HandoffSource.CALLER),
        ("frustration", HandoffReason.USER_FRUSTRATION, HandoffSource.AGENT),
        ("agent_confusion", HandoffReason.AGENT_CONFUSION, HandoffSource.AGENT),
        ("agent_decision", HandoffReason.AGENT_DECISION, HandoffSource.AGENT),
        ("other", HandoffReason.OTHER, HandoffSource.AGENT),
        ("none", HandoffReason.AGENT_DECISION, HandoffSource.AGENT),
        (None, HandoffReason.AGENT_DECISION, HandoffSource.AGENT),
    ],
)
async def test_big_model_handover_maps_reason_to_trigger_and_source(
    handover_reason, expected_trigger, expected_source
):
    kwargs = await _run(_resp(handover_reason))
    assert kwargs["trigger"] == expected_trigger
    assert kwargs["handoff_source"] == expected_source


class TestUnknownAction:
    """The big model's own exception handler returns action="clarify", which is
    not in the action vocabulary, so every big-model failure lands in the
    unknown-action fallback. It must speak the text that handler set rather
    than discarding it for the generic line."""

    async def _spoken(self, resp):
        with patch(f"{MODULE}.send_and_log", new=AsyncMock()) as send:
            await handle_big_model_response(
                _ctx(), {"question_prompt": "What is your name?"}, resp
            )
        return [call.args[1] for call in send.await_args_list]

    @pytest.mark.asyncio
    async def test_clarify_speaks_the_exception_text(self):
        spoken = await self._spoken(
            {
                "action": "clarify",
                "text": "Sorry, I didn't catch that. Could you say it again?",
            }
        )
        assert spoken[0] == "Sorry, I didn't catch that. Could you say it again?"
        assert spoken[1] == "What is your name?"

    @pytest.mark.asyncio
    async def test_unknown_action_without_text_falls_back(self):
        spoken = await self._spoken({"action": "wat"})
        assert spoken[0] == "Could you please say that again?"
        assert spoken[1] == "What is your name?"
