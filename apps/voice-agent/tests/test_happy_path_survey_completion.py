"""Tests for the survey-completion persistence path in handle_happy_path.

When advance() returns finished=True (no handover_to_coach node), the closing
interstitial text spoken via speak_next_or_finish was never persisted to
responses.questions, causing the last node to be missing from the dashboard.

The fix calls _persist_survey_completion with the final spoken text so it
appears in the Questions & Conversations history.
"""

import types
from unittest.mock import AsyncMock, Mock, patch

import pytest

MODULE = "voice_agent.api.websocket_handlers.outcomes.happy_path"


def _ctx(with_csm=True):
    csm = Mock()
    csm.response_id = "resp-1"
    csm.get_current_question_id.return_value = "q_optin"
    csm.complete_question.return_value = {"question_id": "q_optin", "turns": []}
    csm.completed_questions = [
        {"question_id": "q_optin", "turns": [{"user_message": "yes"}]}
    ]

    adapter = Mock()
    adapter.engine = Mock()
    adapter.engine.answers = {}
    adapter.validate.return_value = {"valid": True, "normalized": "yes"}
    adapter.should_escalate.return_value = False
    adapter.record.return_value = None

    return types.SimpleNamespace(
        call_state_manager=csm if with_csm else None,
        websocket=object(),
        conversation_log=[
            {"role": "assistant", "text": "Do you want to opt in?"},
            {"role": "user", "text": "yes"},
        ],
        metrics_collector=Mock(),
        active_big_model_node=None,
        call_sid="CA1",
        milestone_dispatcher=None,
        adapter=adapter,
        correlation_id="corr-1",
    )


def _turn(node_id="q_optin"):
    from voice_agent.api.websocket_handlers.outcomes.base import TurnContext

    return TurnContext(
        cur={"node_id": node_id, "question_prompt": "Do you want to opt in?"},
        node={"id": node_id, "type": "single_choice"},
        node_id=node_id,
        combined_user_text="yes",
        user_text="yes",
        interpretation="answer",
        reply="Got it.",
        small_conf=0.95,
        val_res={"valid": True, "normalized": "yes"},
        small_resp={
            "interpretation": "answer",
            "answer": {"type": "single_choice", "value": "yes"},
            "reply": "Got it.",
            "confidence": 0.95,
            "guardrail_topic": "none",
        },
    )


def _finished_nxt(spoken_intro="", question_prompt=""):
    return {
        "node_id": None,
        "question_prompt": question_prompt,
        "spoken_intro": spoken_intro,
        "spoken_intro_interruptible": None,
        "spoken_intro_preemptible": None,
        "finished": True,
        "handover_to_coach": False,
        "handover_context": None,
        "interruptible": None,
        "preemptible": None,
        "state": {},
    }


@pytest.mark.asyncio
async def test_persist_survey_completion_called_with_spoken_text():
    """`_persist_survey_completion` receives the spoken_intro when finished=True."""
    from voice_agent.api.websocket_handlers.outcomes.happy_path import (
        handle_happy_path,
    )

    ctx = _ctx()
    ctx.adapter.advance.return_value = _finished_nxt(
        spoken_intro="Thank you, you're all set! Please hold as we connect you."
    )

    with (
        patch(
            f"{MODULE}.speak_next_or_finish", new_callable=AsyncMock, return_value=True
        ),
        patch(f"{MODULE}._emit_milestone_events", new_callable=AsyncMock),
        patch(
            f"{MODULE}._persist_survey_completion", new_callable=AsyncMock
        ) as mock_persist,
    ):
        from voice_agent.api.websocket_types import PromptEndMode

        result = await handle_happy_path(ctx, _turn())

    assert result.end_mode == PromptEndMode.SURVEY_COMPLETED
    mock_persist.assert_awaited_once()
    _, call_text = mock_persist.await_args.args
    assert "Thank you, you're all set" in call_text


@pytest.mark.asyncio
async def test_persist_survey_completion_uses_goodbye_fallback_when_no_text():
    """`_persist_survey_completion` falls back to GOODBYE when nxt has no text."""
    from voice_agent.api.websocket_handlers.outcomes.happy_path import (
        handle_happy_path,
    )
    from voice_agent.voice_ai.predefined_responses import PredefinedResponses

    ctx = _ctx()
    ctx.adapter.advance.return_value = _finished_nxt(
        spoken_intro="", question_prompt=""
    )

    with (
        patch(
            f"{MODULE}.speak_next_or_finish", new_callable=AsyncMock, return_value=True
        ),
        patch(f"{MODULE}._emit_milestone_events", new_callable=AsyncMock),
        patch(
            f"{MODULE}._persist_survey_completion", new_callable=AsyncMock
        ) as mock_persist,
    ):
        await handle_happy_path(ctx, _turn())

    mock_persist.assert_awaited_once()
    _, call_text = mock_persist.await_args.args
    assert call_text == PredefinedResponses.GOODBYE


@pytest.mark.asyncio
async def test_persist_survey_completion_not_called_when_no_csm():
    """When call_state_manager is None, _persist_survey_completion is not called."""
    from voice_agent.api.websocket_handlers.outcomes.happy_path import (
        handle_happy_path,
    )

    ctx = _ctx(with_csm=False)
    ctx.adapter.advance.return_value = _finished_nxt(spoken_intro="Goodbye!")

    with (
        patch(
            f"{MODULE}.speak_next_or_finish", new_callable=AsyncMock, return_value=True
        ),
        patch(f"{MODULE}._emit_milestone_events", new_callable=AsyncMock),
        patch(
            f"{MODULE}._persist_survey_completion", new_callable=AsyncMock
        ) as mock_persist,
    ):
        from voice_agent.api.websocket_types import PromptEndMode

        result = await handle_happy_path(ctx, _turn())

    assert result.end_mode == PromptEndMode.SURVEY_COMPLETED
    mock_persist.assert_not_awaited()


@pytest.mark.asyncio
async def test_persist_survey_completion_not_called_on_handover_path():
    """When nxt has handover_to_coach=True, _persist_survey_completion is not called."""
    from voice_agent.api.websocket_handlers.outcomes.happy_path import (
        handle_happy_path,
    )

    ctx = _ctx()
    ctx.adapter.advance.return_value = {
        "node_id": None,
        "question_prompt": "",
        "spoken_intro": "Connecting you to a coach.",
        "spoken_intro_interruptible": None,
        "spoken_intro_preemptible": None,
        "finished": True,
        "handover_to_coach": True,
        "handover_context": types.SimpleNamespace(
            node_id="TRANSFER_TO_COACH_V1", whisper_text="whisper"
        ),
        "interruptible": None,
        "preemptible": None,
        "state": {},
    }

    with (
        patch(f"{MODULE}.send_and_log", new_callable=AsyncMock),
        patch(f"{MODULE}._persist_coach_handoff", new_callable=AsyncMock),
        patch(f"{MODULE}._emit_milestone_events", new_callable=AsyncMock),
        patch(f"{MODULE}.initiate_coach_handoff", new_callable=AsyncMock),
        patch(
            f"{MODULE}.settings", new=types.SimpleNamespace(coach_handoff_enabled=True)
        ),
        patch(
            f"{MODULE}._persist_survey_completion", new_callable=AsyncMock
        ) as mock_persist,
    ):
        await handle_happy_path(ctx, _turn())

    mock_persist.assert_not_awaited()
