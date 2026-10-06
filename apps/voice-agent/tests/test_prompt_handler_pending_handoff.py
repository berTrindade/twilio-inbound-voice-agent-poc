import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import voice_agent.api.websocket_handlers.prompt_handler as prompt_handler_module
from voice_agent.api.websocket_handlers.prompt_handler import handle_prompt_message
from voice_agent.voice_ai.pending_handoff_state import request_coach_handoff
from voice_agent.voice_ai.predefined_responses import PredefinedResponses
from voice_agent.voice_ai.handoff_reasons import HandoffReason, HandoffSource


@pytest.mark.asyncio
async def test_pending_signal_routes_to_coach_handover():
    ctx = MagicMock()
    ctx.call_sid = "CA1"
    ctx.active_big_model_node = None
    request_coach_handoff(
        "CA1",
        reason="submission_failed",
        whisper_text="w",
        trigger=HandoffReason.SYSTEM_ERROR,
    )
    with patch(
        "voice_agent.api.websocket_handlers.prompt_handler.handle_coach_handover",
        new=AsyncMock(return_value="HANDOFF_RESULT"),
    ) as mock_handover:
        result = await handle_prompt_message(
            ctx, {"voicePrompt": "ok", "last": True}, MagicMock()
        )
    mock_handover.assert_awaited_once()
    turn = mock_handover.await_args.args[1]
    assert turn.reply == PredefinedResponses.COACH_HANDOVER_FAILURE_MESSAGE
    assert turn.small_resp.get("whisper_text") == "w"
    # Marker attributed to the API failure (system-driven), not a caller request:
    assert mock_handover.await_args.kwargs["trigger"] == HandoffReason.SYSTEM_ERROR
    assert mock_handover.await_args.kwargs["handoff_source"] == HandoffSource.SYSTEM
    assert result == "HANDOFF_RESULT"


@pytest.mark.asyncio
async def test_no_signal_does_not_route_to_handover():
    ctx = MagicMock()
    ctx.call_sid = "CA-none"
    ctx.active_big_model_node = None
    # Return a finished node so the handler takes the ALREADY_DONE short-circuit
    ctx.adapter.current.return_value = {
        "node_id": None,
        "finished": True,
        "question_prompt": "",
    }
    ctx.websocket.send_text = AsyncMock()
    ctx.conversation_log = []
    ctx.metrics_collector = MagicMock()
    ctx.call_state_manager = None

    with patch(
        "voice_agent.api.websocket_handlers.prompt_handler.handle_coach_handover",
        new=AsyncMock(),
    ) as mock_handover:
        with patch(
            "voice_agent.api.websocket_handlers.prompt_handler.send_and_log",
            new=AsyncMock(),
        ):
            await handle_prompt_message(
                ctx, {"voicePrompt": "hi", "last": True}, MagicMock()
            )
    mock_handover.assert_not_awaited()


@pytest.mark.asyncio
async def test_disabled_handoff_logs_error_but_still_routes():
    """When coach_handoff_enabled=False and a pending signal is present,
    handle_coach_handover is still awaited AND an ERROR log fires."""
    ctx = MagicMock()
    ctx.call_sid = "CA2"
    ctx.active_big_model_node = None

    request_coach_handoff(
        "CA2",
        reason="submission_failed",
        whisper_text="whisper2",
        trigger=HandoffReason.SYSTEM_ERROR,
    )

    with patch.object(prompt_handler_module.settings, "coach_handoff_enabled", False):
        with patch(
            "voice_agent.api.websocket_handlers.prompt_handler.handle_coach_handover",
            new=AsyncMock(return_value="HANDOFF_RESULT"),
        ) as mock_handover:
            with patch.object(prompt_handler_module, "logger") as mock_logger:
                result = await handle_prompt_message(
                    ctx, {"voicePrompt": "ok", "last": True}, MagicMock()
                )

    # handoff still happens despite the flag being False
    mock_handover.assert_awaited_once()
    # the explicit trigger passed by the caller survives, source=system
    assert mock_handover.await_args.kwargs["trigger"] == HandoffReason.SYSTEM_ERROR
    assert mock_handover.await_args.kwargs["handoff_source"] == HandoffSource.SYSTEM

    # ERROR log was emitted
    error_calls = mock_logger.error.call_args_list
    assert any(
        "Blocking API failure but coach handoff disabled" in str(call)
        for call in error_calls
    ), f"Expected ERROR log not found. Calls: {error_calls}"

    assert result == "HANDOFF_RESULT"
