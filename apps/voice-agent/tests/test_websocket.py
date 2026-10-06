"""Unit tests for WebSocket endpoint."""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import WebSocketDisconnect

from voice_agent.api.websocket import websocket_endpoint, SESSIONS
from voice_agent.api.websocket_types import PromptEndMode


@pytest.fixture
def mock_websocket():
    """Create a mock WebSocket for testing."""
    websocket = AsyncMock()
    websocket.accept = AsyncMock()
    websocket.receive_text = AsyncMock()
    websocket.send_text = AsyncMock()
    websocket.call_sid = None
    return websocket


@pytest.fixture(autouse=True)
def clear_sessions():
    """Clear sessions before each test."""
    SESSIONS.clear()
    yield
    SESSIONS.clear()


@pytest.mark.asyncio
async def test_websocket_setup_message(mock_websocket):
    """Test that setup message initializes session correctly."""
    call_sid = "CA123456789"
    setup_message = json.dumps({"type": "setup", "callSid": call_sid})

    # Mock receive_text to return setup message, then disconnect
    mock_websocket.receive_text.side_effect = [
        setup_message,
        WebSocketDisconnect(),
    ]

    await websocket_endpoint(mock_websocket)

    # Verify call_sid was set on websocket (this proves setup worked)
    assert mock_websocket.call_sid == call_sid
    mock_websocket.accept.assert_called_once()
    # Session is cleaned up on disconnect, but we verify it was created
    # by checking that call_sid was set


@pytest.mark.asyncio
async def test_websocket_prompt_message_echoes_response(mock_websocket):
    """
    Test that a prompt message results in an assistant response
    in valid ConversationRelay text-token format.

    The new voice survey flow no longer echoes the user's text; it sends
    survey questions / clarifications instead. Here we just assert that
    at least one valid text token is sent during the interaction.
    """
    call_sid = "CA123456789"
    voice_prompt = "Hello, this is a test"
    setup_message = json.dumps({"type": "setup", "callSid": call_sid})
    prompt_message = json.dumps({"type": "prompt", "voicePrompt": voice_prompt})

    mock_websocket.receive_text.side_effect = [
        setup_message,
        prompt_message,
        WebSocketDisconnect(),
    ]

    await websocket_endpoint(mock_websocket)

    # We expect at least one outgoing text token (initial question and/or response)
    assert mock_websocket.send_text.call_count >= 2

    # Check that the last message is a valid Twilio ConversationRelay text token
    sent_data = mock_websocket.send_text.call_args[0][0]
    response = json.loads(sent_data)

    assert response["type"] == "text"
    assert isinstance(response["token"], str)
    assert isinstance(response["last"], bool)


@pytest.mark.asyncio
async def test_websocket_interrupt_message(mock_websocket):
    """
    Interrupt messages should NOT trigger an additional response,
    but an initial survey question is always sent at connect time.
    """
    # Clean any leftover side effects
    mock_websocket.send_text.side_effect = None

    call_sid = "CA123456789"
    setup_message = json.dumps({"type": "setup", "callSid": call_sid})
    interrupt_message = json.dumps({"type": "interrupt"})

    mock_websocket.receive_text.side_effect = [
        setup_message,
        interrupt_message,
        WebSocketDisconnect(),
    ]

    await websocket_endpoint(mock_websocket)

    # 1 text token = the initial survey question
    assert mock_websocket.send_text.call_count == 2

    # Verify that the only message is a Twilio text token (not an interrupt reply)
    sent_data = mock_websocket.send_text.call_args_list[0][0][0]
    response = json.loads(sent_data)

    assert response["type"] == "text"
    assert isinstance(response["token"], str)
    assert isinstance(response["last"], bool)


@pytest.mark.asyncio
async def test_websocket_unknown_message_type(mock_websocket):
    """Test that unknown message types are logged but don't crash."""
    call_sid = "CA123456789"
    setup_message = json.dumps({"type": "setup", "callSid": call_sid})
    unknown_message = json.dumps({"type": "unknown_type"})

    mock_websocket.receive_text.side_effect = [
        setup_message,
        unknown_message,
        WebSocketDisconnect(),
    ]

    await websocket_endpoint(mock_websocket)

    # Should handle gracefully without crashing
    # After disconnect, session is cleaned up, but we verify call_sid was set
    assert mock_websocket.call_sid == call_sid
    # Session was cleaned up on disconnect
    assert call_sid not in SESSIONS


@pytest.mark.asyncio
async def test_websocket_disconnect_cleans_up_session(mock_websocket):
    """Test that disconnect properly cleans up session."""
    call_sid = "CA123456789"
    setup_message = json.dumps({"type": "setup", "callSid": call_sid})

    mock_websocket.receive_text.side_effect = [
        setup_message,
        WebSocketDisconnect(),
    ]

    await websocket_endpoint(mock_websocket)

    # Session should be removed after disconnect
    assert call_sid not in SESSIONS


@pytest.mark.asyncio
async def test_websocket_error_handling(mock_websocket):
    """Test that errors are handled gracefully."""
    call_sid = "CA123456789"
    setup_message = json.dumps({"type": "setup", "callSid": call_sid})

    # Simulate an error during processing
    mock_websocket.receive_text.side_effect = [
        setup_message,
        Exception("Test error"),
    ]

    await websocket_endpoint(mock_websocket)

    # Session should be cleaned up even on error
    assert call_sid not in SESSIONS


@pytest.mark.asyncio
async def test_websocket_prompt_without_setup(mock_websocket):
    """Test handling prompt before setup (edge case)."""
    prompt_message = json.dumps({"type": "prompt", "voicePrompt": "test"})

    mock_websocket.receive_text.side_effect = [
        prompt_message,
        WebSocketDisconnect(),
    ]

    await websocket_endpoint(mock_websocket)

    # Should handle gracefully (call_sid will be None)
    assert len(SESSIONS) == 0


@pytest.mark.asyncio
async def test_websocket_multiple_prompts(mock_websocket):
    """
    Test handling multiple prompts in sequence in the new voice survey flow.

    Expectations:
    - An initial survey question is sent after setup.
    - Additional responses are sent for each user prompt.
    - All outbound messages are valid ConversationRelay text tokens.
    """
    # Ensure no leftover side effects from other tests
    mock_websocket.send_text.side_effect = None

    call_sid = "CA123456789"
    setup_message = json.dumps({"type": "setup", "callSid": call_sid})
    prompt1 = json.dumps({"type": "prompt", "voicePrompt": "First message"})
    prompt2 = json.dumps({"type": "prompt", "voicePrompt": "Second message"})

    mock_websocket.receive_text.side_effect = [
        setup_message,
        prompt1,
        prompt2,
        WebSocketDisconnect(),
    ]

    await websocket_endpoint(mock_websocket)

    # We expect at least:
    # 1) initial survey question
    # 2) response to first prompt
    # 3) response to second prompt
    assert mock_websocket.send_text.call_count >= 3

    # Verify every outbound message is a valid Twilio ConversationRelay text token
    for call in mock_websocket.send_text.call_args_list:
        sent_data = call[0][0]
        response = json.loads(sent_data)

        assert response["type"] == "text"
        assert isinstance(response["token"], str)
        assert isinstance(response["last"], bool)


@pytest.mark.asyncio
async def test_websocket_invalid_json(mock_websocket):
    """Test that invalid JSON is handled gracefully."""
    call_sid = "CA123456789"
    setup_message = json.dumps({"type": "setup", "callSid": call_sid})

    mock_websocket.receive_text.side_effect = [
        setup_message,
        "invalid json{",  # Invalid JSON
        WebSocketDisconnect(),
    ]

    await websocket_endpoint(mock_websocket)

    # Should handle gracefully and clean up session
    assert call_sid not in SESSIONS


@pytest.mark.asyncio
async def test_websocket_message_without_type(mock_websocket):
    """Test that message without type field is handled gracefully."""
    call_sid = "CA123456789"
    setup_message = json.dumps({"type": "setup", "callSid": call_sid})
    invalid_message = json.dumps({"no_type": "value"})

    mock_websocket.receive_text.side_effect = [
        setup_message,
        invalid_message,
        WebSocketDisconnect(),
    ]

    await websocket_endpoint(mock_websocket)

    # Should handle gracefully (will raise KeyError but caught by Exception handler)
    assert call_sid not in SESSIONS


@pytest.mark.asyncio
async def test_websocket_setup_without_callsid(mock_websocket):
    """Test that setup message without callSid is handled gracefully."""
    invalid_setup = json.dumps({"type": "setup"})

    mock_websocket.receive_text.side_effect = [
        invalid_setup,
        WebSocketDisconnect(),
    ]

    await websocket_endpoint(mock_websocket)

    # Should handle gracefully (will raise KeyError but caught by Exception handler)
    assert len(SESSIONS) == 0


@pytest.mark.asyncio
async def test_websocket_prompt_without_voiceprompt(mock_websocket):
    """Test that prompt message without voicePrompt is handled gracefully."""
    call_sid = "CA123456789"
    setup_message = json.dumps({"type": "setup", "callSid": call_sid})
    invalid_prompt = json.dumps({"type": "prompt"})

    mock_websocket.receive_text.side_effect = [
        setup_message,
        invalid_prompt,
        WebSocketDisconnect(),
    ]

    await websocket_endpoint(mock_websocket)

    # Should handle gracefully (will raise KeyError but caught by Exception handler)
    assert call_sid not in SESSIONS


@pytest.mark.asyncio
async def test_websocket_send_text_error(mock_websocket):
    """Test that error sending response is handled gracefully."""
    call_sid = "CA123456789"
    setup_message = json.dumps({"type": "setup", "callSid": call_sid})
    prompt_message = json.dumps({"type": "prompt", "voicePrompt": "test"})

    # Simulate error when sending response
    mock_websocket.send_text.side_effect = Exception("Send error")

    mock_websocket.receive_text.side_effect = [
        setup_message,
        prompt_message,
        WebSocketDisconnect(),
    ]

    await websocket_endpoint(mock_websocket)

    # Should handle gracefully and clean up session
    assert call_sid not in SESSIONS


@pytest.mark.asyncio
async def test_websocket_empty_message(mock_websocket):
    """Test that empty message is handled gracefully."""
    call_sid = "CA123456789"
    setup_message = json.dumps({"type": "setup", "callSid": call_sid})

    mock_websocket.receive_text.side_effect = [
        setup_message,
        "",  # Empty message
        WebSocketDisconnect(),
    ]

    await websocket_endpoint(mock_websocket)

    # Should handle gracefully
    assert call_sid not in SESSIONS


@pytest.mark.asyncio
async def test_invalid_retry_captures_previous_assistant_message():
    """
    Test that INVALID_RETRY captures the previous assistant message from conversation_log,
    not the error/clarification message that will be sent next.

    This is a regression test for a bug where the first AI turn was being lost
    when the user gave an invalid response.
    """
    from voice_agent.api.websocket import (
        handle_prompt_message,
    )
    from voice_agent.api.session_context import SessionContext
    from voice_agent.voice_ai.call_state_manager import CallStateManager
    from uuid import uuid4

    # Setup mocks
    mock_websocket = AsyncMock()
    mock_websocket.send_text = AsyncMock()

    mock_adapter = MagicMock()
    mock_adapter.current.return_value = {
        "finished": False,
        "node_id": "test_question",
        "question_prompt": "What is your preferred time?",
    }
    mock_adapter.engine.get_node.return_value = {
        "type": "single_choice",
        "options": [
            {"id": "morning", "value": "morning"},
            {"id": "afternoon", "value": "afternoon"},
            {"id": "evening", "value": "evening"},
        ],
    }
    mock_adapter.merge_user_utterance.return_value = "yes"
    mock_adapter.snapshot.return_value = {"answers": {}}
    mock_adapter.validate.return_value = {
        "valid": False,
        "reason": "not a valid option",
    }
    mock_adapter.should_escalate.return_value = False

    mock_llm_handler = MagicMock()
    mock_llm_handler.call_small_model_async = AsyncMock(
        return_value={
            "interpretation": "other",
            "answer": None,
            "reply": "I'm sorry, I didn't understand. Please choose morning, afternoon, or evening.",
            "confidence": 0.5,
        }
    )
    mock_llm_handler.call_big_model_async = AsyncMock()

    # Conversation log: simulates the initial question was already sent
    # Note: handle_prompt_message will add the user message, so we only pre-populate
    # with the assistant's message
    initial_question = "What is your preferred time? Morning, afternoon, or evening?"
    conversation_log = [
        {"role": "assistant", "text": initial_question},
    ]

    mock_metrics = MagicMock()
    mock_span = MagicMock()

    # Create a real CallStateManager to verify the captured message
    call_state_manager = CallStateManager(
        response_id=uuid4(),
        call_sid="CA123",
        session_id="sess-1",
        correlation_id="corr-1",
    )
    call_state_manager.start_question(
        "test_question", "What is your preferred time?", "single_choice"
    )

    # Execute
    ctx = SessionContext(
        websocket=mock_websocket,
        adapter=mock_adapter,
        llm_handler=mock_llm_handler,
        conversation_log=conversation_log,
        correlation_id="test-corr",
        session_id="sess-1",
        metrics_collector=mock_metrics,
        call_state_manager=call_state_manager,
    )
    result = await handle_prompt_message(
        ctx=ctx,
        msg={"voicePrompt": "yes", "last": True},
        msg_span=mock_span,
    )

    # Verify outcome
    assert result.end_mode == PromptEndMode.CONTINUE
    assert result.active_big_model_node is None

    # Verify the turn was captured with the PREVIOUS assistant message
    # (the initial question), NOT the error reply that was sent after
    assert len(call_state_manager.current_question_data["turns"]) == 1
    captured_turn = call_state_manager.current_question_data["turns"][0]

    # This is the key assertion: assistant_message should be the PREVIOUS message
    # from conversation_log, not the clarification reply
    assert captured_turn["assistant_message"] == initial_question
    assert captured_turn["user_message"] == "yes"
    assert captured_turn["llm_interpretation"] == "other"
    assert captured_turn["escalated"] is False
    assert captured_turn["validation_result"]["valid"] is False


@pytest.mark.asyncio
async def test_classify_prompt_outcome_invalid_retry():
    """Test that classify_prompt_outcome correctly identifies INVALID_RETRY."""
    from voice_agent.api.websocket_handlers.outcomes import (
        classify_prompt_outcome,
        ConversationTurnOutcome,
    )

    # GUARDRAIL_TOPIC: predefined guardrail short-circuits normal flow
    outcome = classify_prompt_outcome(
        interpretation="predefined_guardrail",
        val_res={"valid": False},
        escalate=False,
        guardrail_topic="self_harm",
    )
    assert outcome == ConversationTurnOutcome.GUARDRAIL_TOPIC

    # INVALID_RETRY: not escalate AND not valid
    outcome = classify_prompt_outcome(
        interpretation="other",
        val_res={"valid": False, "reason": "not valid"},
        escalate=False,
        guardrail_topic="none",
    )
    assert outcome == ConversationTurnOutcome.INVALID_RETRY

    # HAPPY_PATH: not escalate AND valid
    outcome = classify_prompt_outcome(
        interpretation="answer",
        val_res={"valid": True, "normalized": "morning"},
        escalate=False,
        guardrail_topic="none",
    )
    assert outcome == ConversationTurnOutcome.HAPPY_PATH

    # ESCALATE: escalate is True
    outcome = classify_prompt_outcome(
        interpretation="other",
        val_res={"valid": False},
        escalate=True,
        guardrail_topic="none",
    )
    assert outcome == ConversationTurnOutcome.ESCALATE


class TestSpeakNextOrFinish:
    """
    Unit tests for the speak_next_or_finish helper.

    Covers:
    - Not-finished path: spoken only, prompt only, both
    - Interruptibility flag preservation (the regression)
    - Finished path: with spoken, with prompt, with neither (GOODBYE fallback), with both
    """

    def _make_nxt(
        self,
        spoken_intro="",
        spoken_intro_interruptible=None,
        spoken_intro_preemptible=None,
        question_prompt="",
        interruptible=None,
        preemptible=None,
        finished=False,
    ):
        return {
            "spoken_intro": spoken_intro,
            "spoken_intro_interruptible": spoken_intro_interruptible,
            "spoken_intro_preemptible": spoken_intro_preemptible,
            "question_prompt": question_prompt,
            "interruptible": interruptible,
            "preemptible": preemptible,
            "finished": finished,
        }

    # ------------------------------------------------------------------
    # Not-finished path
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_only_spoken_intro_is_sent(self):
        from voice_agent.api.websocket_helpers import speak_next_or_finish

        mock_ws = AsyncMock()
        nxt = self._make_nxt(spoken_intro="Welcome to the survey.", finished=False)

        result = await speak_next_or_finish(mock_ws, nxt, [], metrics_collector=None)

        assert result is False
        assert mock_ws.send_text.call_count == 1
        sent = json.loads(mock_ws.send_text.call_args_list[0][0][0])
        assert sent["token"] == "Welcome to the survey."

    @pytest.mark.asyncio
    async def test_only_prompt_is_sent(self):
        from voice_agent.api.websocket_helpers import speak_next_or_finish

        mock_ws = AsyncMock()
        nxt = self._make_nxt(
            question_prompt="How many cigarettes per day?", finished=False
        )

        result = await speak_next_or_finish(mock_ws, nxt, [], metrics_collector=None)

        assert result is False
        assert mock_ws.send_text.call_count == 1
        sent = json.loads(mock_ws.send_text.call_args_list[0][0][0])
        assert sent["token"] == "How many cigarettes per day?"

    @pytest.mark.asyncio
    async def test_spoken_and_prompt_both_sent(self):
        from voice_agent.api.websocket_helpers import speak_next_or_finish

        mock_ws = AsyncMock()
        nxt = self._make_nxt(
            spoken_intro="Great answer!",
            question_prompt="How long have you been using it?",
            finished=False,
        )

        result = await speak_next_or_finish(mock_ws, nxt, [], metrics_collector=None)

        assert result is False
        assert mock_ws.send_text.call_count == 2
        first = json.loads(mock_ws.send_text.call_args_list[0][0][0])
        second = json.loads(mock_ws.send_text.call_args_list[1][0][0])
        assert first["token"] == "Great answer!"
        assert second["token"] == "How long have you been using it?"

    # ------------------------------------------------------------------
    # Interruptibility flag preservation
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_spoken_intro_flags_preserved(self):
        """spoken_intro_interruptible/preemptible must reach the wire, not be silently dropped."""
        from voice_agent.api.websocket_helpers import speak_next_or_finish

        mock_ws = AsyncMock()
        nxt = self._make_nxt(
            spoken_intro="Closing message text.",
            spoken_intro_interruptible=False,
            spoken_intro_preemptible=False,
            finished=True,
        )

        with patch(
            "voice_agent.api.websocket_helpers.asyncio.sleep", new_callable=AsyncMock
        ):
            result = await speak_next_or_finish(
                mock_ws, nxt, [], metrics_collector=None
            )

        assert result is True
        assert mock_ws.send_text.call_count == 1
        sent = json.loads(mock_ws.send_text.call_args_list[0][0][0])
        assert sent["interruptible"] is False
        assert sent["preemptible"] is False
        assert sent["token"] == "Closing message text."

    @pytest.mark.asyncio
    async def test_question_flags_preserved(self):
        """interruptible/preemptible on the question prompt must reach the wire."""
        from voice_agent.api.websocket_helpers import speak_next_or_finish

        mock_ws = AsyncMock()
        nxt = self._make_nxt(
            question_prompt="Would you use it again?",
            interruptible=False,
            preemptible=False,
            finished=False,
        )

        result = await speak_next_or_finish(mock_ws, nxt, [], metrics_collector=None)

        assert result is False
        assert mock_ws.send_text.call_count == 1
        sent = json.loads(mock_ws.send_text.call_args_list[0][0][0])
        assert sent["interruptible"] is False
        assert sent["preemptible"] is False

    @pytest.mark.asyncio
    async def test_spoken_flags_not_bleed_into_prompt(self):
        """spoken_intro flags must not bleed into the subsequent question prompt send."""
        from voice_agent.api.websocket_helpers import speak_next_or_finish

        mock_ws = AsyncMock()
        nxt = self._make_nxt(
            spoken_intro="Narration text.",
            spoken_intro_interruptible=False,
            spoken_intro_preemptible=False,
            question_prompt="Ready to proceed?",
            interruptible=True,
            preemptible=True,
            finished=False,
        )

        result = await speak_next_or_finish(mock_ws, nxt, [], metrics_collector=None)

        assert result is False
        assert mock_ws.send_text.call_count == 2
        narration_msg = json.loads(mock_ws.send_text.call_args_list[0][0][0])
        prompt_msg = json.loads(mock_ws.send_text.call_args_list[1][0][0])
        assert narration_msg["interruptible"] is False
        assert narration_msg["preemptible"] is False
        assert prompt_msg["interruptible"] is True
        assert prompt_msg["preemptible"] is True

    # ------------------------------------------------------------------
    # Finished path
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_finished_with_spoken_returns_true(self):
        """The COACHING_CLOSING_MESSAGE scenario: spoken sent with its flags, no GOODBYE appended."""
        from voice_agent.api.websocket_helpers import speak_next_or_finish

        mock_ws = AsyncMock()
        nxt = self._make_nxt(
            spoken_intro="One of our coaches will be in touch within the next hour.",
            spoken_intro_interruptible=False,
            spoken_intro_preemptible=False,
            finished=True,
        )

        with patch(
            "voice_agent.api.websocket_helpers.asyncio.sleep", new_callable=AsyncMock
        ):
            result = await speak_next_or_finish(
                mock_ws, nxt, [], metrics_collector=None
            )

        assert result is True
        assert mock_ws.send_text.call_count == 1
        sent = json.loads(mock_ws.send_text.call_args_list[0][0][0])
        assert "Thanks for your time!" not in sent["token"]
        assert sent["interruptible"] is False

    @pytest.mark.asyncio
    async def test_finished_with_prompt_returns_true(self):
        """finished=True with a question_prompt: prompt is sent, no GOODBYE."""
        from voice_agent.api.websocket_helpers import speak_next_or_finish

        mock_ws = AsyncMock()
        nxt = self._make_nxt(question_prompt="Final question.", finished=True)

        with patch(
            "voice_agent.api.websocket_helpers.asyncio.sleep", new_callable=AsyncMock
        ):
            result = await speak_next_or_finish(
                mock_ws, nxt, [], metrics_collector=None
            )

        assert result is True
        assert mock_ws.send_text.call_count == 1
        sent = json.loads(mock_ws.send_text.call_args_list[0][0][0])
        assert sent["token"] == "Final question."
        assert "Thanks for your time!" not in sent["token"]

    @pytest.mark.asyncio
    async def test_finished_with_neither_sends_goodbye(self):
        """finished=True with no spoken or prompt: GOODBYE fallback is sent."""
        from voice_agent.api.websocket_helpers import speak_next_or_finish

        mock_ws = AsyncMock()
        nxt = self._make_nxt(finished=True)

        with patch(
            "voice_agent.api.websocket_helpers.asyncio.sleep", new_callable=AsyncMock
        ):
            result = await speak_next_or_finish(
                mock_ws, nxt, [], metrics_collector=None
            )

        assert result is True
        assert mock_ws.send_text.call_count == 1
        sent = json.loads(mock_ws.send_text.call_args_list[0][0][0])
        assert sent["token"] == "Thanks for your time!"
        assert sent["last"] is True

    @pytest.mark.asyncio
    async def test_finished_with_both_skips_goodbye(self):
        """finished=True with both spoken and prompt: two sends, no third GOODBYE."""
        from voice_agent.api.websocket_helpers import speak_next_or_finish

        mock_ws = AsyncMock()
        nxt = self._make_nxt(
            spoken_intro="Narration.",
            question_prompt="Last question.",
            finished=True,
        )

        with patch(
            "voice_agent.api.websocket_helpers.asyncio.sleep", new_callable=AsyncMock
        ):
            result = await speak_next_or_finish(
                mock_ws, nxt, [], metrics_collector=None
            )

        assert result is True
        assert mock_ws.send_text.call_count == 2
        tokens = [
            json.loads(call[0][0])["token"] for call in mock_ws.send_text.call_args_list
        ]
        assert "Thanks for your time!" not in tokens
