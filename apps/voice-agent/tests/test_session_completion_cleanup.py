import pytest
from unittest.mock import AsyncMock, MagicMock
from voice_agent.api.websocket_handlers.session_completion import (
    handle_session_completion,
)
from voice_agent.api.websocket_types import PromptHandlingResult, PromptEndMode
from voice_agent.voice_ai.pending_handoff_state import (
    request_coach_handoff,
    pop_pending_handoff,
)


@pytest.mark.asyncio
async def test_call_end_clears_pending_handoff():
    request_coach_handoff(
        "CA-end", reason="r", whisper_text="w", trigger="system_error"
    )
    ctx = MagicMock()
    ctx.call_sid = "CA-end"
    ctx.call_state_manager = None
    ctx.milestone_dispatcher = None
    ctx.websocket = AsyncMock()
    result = PromptHandlingResult(
        end_mode=PromptEndMode.USER_ENDED_SESSION, active_big_model_node=None
    )
    await handle_session_completion(result, ctx)
    assert pop_pending_handoff("CA-end") is None  # cleared


@pytest.mark.asyncio
async def test_pending_handoff_cleared_even_if_milestone_dispatch_raises():
    request_coach_handoff(
        "CA-boom", reason="r", whisper_text="w", trigger="system_error"
    )
    ctx = MagicMock()
    ctx.call_sid = "CA-boom"
    ctx.call_state_manager = None
    ctx.websocket = AsyncMock()
    # call_ended milestone dispatch raises — cleanup must still run (finally)
    ctx.milestone_dispatcher.on_milestone = AsyncMock(side_effect=RuntimeError("boom"))
    ctx.adapter.engine.answers = {}
    result = PromptHandlingResult(
        end_mode=PromptEndMode.USER_ENDED_SESSION, active_big_model_node=None
    )
    with pytest.raises(RuntimeError):
        await handle_session_completion(result, ctx)
    assert pop_pending_handoff("CA-boom") is None  # cleared despite the raise
