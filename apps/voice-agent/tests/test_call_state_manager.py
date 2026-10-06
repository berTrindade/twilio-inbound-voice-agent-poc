"""Unit tests for CallStateManager."""

import pytest
from uuid import uuid4

from voice_agent.voice_ai.call_state_manager import CallStateManager


class TestCallStateManagerInitialization:
    """Tests for CallStateManager initialization."""

    def test_initialization(self):
        """Test basic initialization of CallStateManager."""
        response_id = uuid4()
        call_sid = "CA1234567890"
        session_id = "session-123"
        correlation_id = "corr-123"

        manager = CallStateManager(
            response_id=response_id,
            call_sid=call_sid,
            session_id=session_id,
            correlation_id=correlation_id,
        )

        assert manager.response_id == response_id
        assert manager.call_sid == call_sid
        assert manager.session_id == session_id
        assert manager.correlation_id == correlation_id
        assert manager.call_start_time is not None
        assert manager.call_end_time is None
        assert manager.current_question_data is None
        assert manager.completed_questions == []
        assert manager.escalation_count == 0
        assert manager.interruption_count == 0
        assert manager.nodes_visited == []


class TestQuestionTracking:
    """Tests for question tracking functionality."""

    @pytest.fixture
    def manager(self):
        """Create a CallStateManager instance for testing."""
        return CallStateManager(
            response_id=uuid4(),
            call_sid="CA1234",
            session_id="sess-1",
            correlation_id="corr-1",
        )

    def test_start_question(self, manager):
        """Test starting a new question."""
        manager.start_question(
            node_id="used_before",
            question_text="Have you used a voice assistant before?",
            node_type="yes_no",
        )

        assert manager.current_question_data is not None
        assert manager.current_question_data["question_id"] == "used_before"
        assert (
            manager.current_question_data["question_text"]
            == "Have you used a voice assistant before?"
        )
        assert manager.current_question_data["node_type"] == "yes_no"
        assert manager.current_question_data["turns"] == []
        assert manager.current_question_data["attempts"] == 0
        assert "used_before" in manager.nodes_visited

    def test_add_turn(self, manager):
        """Test adding a turn to current question."""
        manager.start_question("test_q", "Test question?", "yes_no")

        manager.add_turn(
            user_message="yes",
            assistant_message="Thank you",
            llm_interpretation="answer",
            llm_confidence=0.95,
            validation_result={"valid": True, "normalized": "yes"},
            escalated=False,
        )

        assert len(manager.current_question_data["turns"]) == 1
        turn = manager.current_question_data["turns"][0]
        assert turn["turn_number"] == 1
        assert turn["user_message"] == "yes"
        assert turn["assistant_message"] == "Thank you"
        assert turn["llm_interpretation"] == "answer"
        assert turn["llm_confidence"] == 0.95
        assert turn["validation_result"]["valid"] is True
        assert turn["escalated"] is False
        assert manager.current_question_data["attempts"] == 1

    def test_add_turn_with_none_confidence(self, manager):
        """Test adding a turn with None confidence (system prompts)."""
        manager.start_question("test_q", "Test question?", "yes_no")

        manager.add_turn(
            user_message="what?",
            assistant_message="Let me clarify: have you used a voice assistant before?",
            llm_interpretation="user_question",
            llm_confidence=None,  # No LLM confidence for system prompts
            validation_result=None,
            escalated=False,
        )

        assert len(manager.current_question_data["turns"]) == 1
        turn = manager.current_question_data["turns"][0]
        assert turn["llm_confidence"] is None
        assert turn["user_message"] == "what?"
        assert (
            turn["assistant_message"]
            == "Let me clarify: have you used a voice assistant before?"
        )

    def test_add_multiple_turns(self, manager):
        """Test adding multiple turns accumulates correctly."""
        manager.start_question("test_q", "Test?", "yes_no")

        manager.add_turn("unclear", "Let me ask again", "other", 0.6, None, True)
        manager.add_turn("yes", "Thank you", "answer", 0.95, {"valid": True}, False)

        assert len(manager.current_question_data["turns"]) == 2
        assert manager.current_question_data["attempts"] == 2
        assert manager.escalation_count == 1  # First turn was escalated

    def test_complete_question(self, manager):
        """Test completing a question."""
        manager.start_question("test_q", "Test?", "yes_no")
        manager.add_turn("yes", "Thank you", "answer", 0.95, {"valid": True}, False)

        result = manager.complete_question("yes")

        assert result is not None
        assert result["question_id"] == "test_q"
        assert result["final_answer"] == "yes"
        assert result["completed_at"] is not None
        assert result["duration_ms"] is not None
        assert result["duration_ms"] >= 0  # Can be 0 in fast unit tests
        assert len(manager.completed_questions) == 1
        assert manager.current_question_data is None

    def test_complete_question_without_active_question(self, manager):
        """Test completing when no question is active."""
        result = manager.complete_question("answer")
        assert result is None
        assert len(manager.completed_questions) == 0

    def test_add_turn_without_active_question(self, manager):
        """Test adding turn when no question is active."""
        # Should not crash, just log warning
        manager.add_turn("test", "test", "answer", 0.9, None, False)
        assert len(manager.completed_questions) == 0


class TestSessionMetadata:
    """Tests for session-level metadata and tracking."""

    @pytest.fixture
    def manager(self):
        """Create a CallStateManager with some data."""
        mgr = CallStateManager(
            response_id=uuid4(),
            call_sid="CA123",
            session_id="sess-1",
            correlation_id="corr-1",
        )

        # Add some questions
        mgr.start_question("q1", "Question 1?", "yes_no")
        mgr.add_turn("yes", "Thanks", "answer", 0.9, {"valid": True}, False)
        mgr.complete_question("yes")

        mgr.start_question("q2", "Question 2?", "single_choice")
        mgr.add_turn("unclear", "Please clarify", "other", 0.5, None, True)
        mgr.add_turn("option_a", "Great", "answer", 0.95, {"valid": True}, False)
        mgr.complete_question("option_a")

        return mgr

    def test_build_session_metadata(self, manager):
        """Test building session metadata."""
        manager.record_interruption()
        manager.record_interruption()
        manager.finalize_call("all_questions_answered")

        metadata = manager.build_session_metadata("all_questions_answered")

        assert metadata["call_sid"] == "CA123"
        assert metadata["session_id"] == "sess-1"
        assert metadata["correlation_id"] == "corr-1"
        assert metadata["total_questions"] == 2
        assert metadata["total_turns"] == 3  # 1 + 2 turns
        assert metadata["escalations_count"] == 1  # One escalated turn
        assert metadata["interruptions_count"] == 2
        assert metadata["completion_reason"] == "all_questions_answered"
        assert "q1" in metadata["nodes_visited"]
        assert "q2" in metadata["nodes_visited"]
        assert metadata["total_duration_ms"] is not None

    def test_record_interruption(self, manager):
        """Test recording interruptions."""
        assert manager.interruption_count == 0

        manager.record_interruption()
        assert manager.interruption_count == 1

        manager.record_interruption()
        manager.record_interruption()
        assert manager.interruption_count == 3

    def test_finalize_call(self, manager):
        """Test finalizing a call."""
        assert manager.call_end_time is None

        manager.finalize_call("user_disconnect")

        assert manager.call_end_time is not None
        assert manager.get_total_duration_ms() is not None
        assert manager.get_total_duration_ms() >= 0  # Can be 0 in fast unit tests

    def test_get_current_question_id(self, manager):
        """Test getting current question ID."""
        # After setup, no current question (last one was completed)
        assert manager.get_current_question_id() is None

        manager.start_question("q3", "Question 3?", "numeric")
        assert manager.get_current_question_id() == "q3"

        manager.complete_question("42")
        assert manager.get_current_question_id() is None


class TestEscalationTracking:
    """Tests for escalation tracking."""

    def test_escalation_count_increments(self):
        """Test that escalation count increments correctly."""
        manager = CallStateManager(uuid4(), "CA123", "sess-1", "corr-1")

        manager.start_question("q1", "Question?", "yes_no")

        # Non-escalated turn
        manager.add_turn("yes", "Thanks", "answer", 0.9, {"valid": True}, False)
        assert manager.escalation_count == 0

        # Escalated turn
        manager.add_turn("unclear", "Clarify", "other", 0.5, None, True)
        assert manager.escalation_count == 1

        # Another escalated turn
        manager.add_turn("still unclear", "Let me explain", "other", 0.4, None, True)
        assert manager.escalation_count == 2


class TestTimingCalculations:
    """Tests for timing calculations."""

    def test_question_duration_calculation(self):
        """Test that question duration is calculated correctly."""
        manager = CallStateManager(uuid4(), "CA123", "sess-1", "corr-1")

        manager.start_question("q1", "Question?", "yes_no")
        # Simulate some time passing (in real scenario)
        manager.add_turn("yes", "Thanks", "answer", 0.9, {"valid": True}, False)

        result = manager.complete_question("yes")

        assert result["duration_ms"] is not None
        assert result["duration_ms"] >= 0
        assert result["started_at"] is not None
        assert result["completed_at"] is not None

    def test_total_duration_before_finalize(self):
        """Test total duration before call is finalized."""
        manager = CallStateManager(uuid4(), "CA123", "sess-1", "corr-1")
        assert manager.get_total_duration_ms() is None

    def test_total_duration_after_finalize(self):
        """Test total duration after call is finalized."""
        manager = CallStateManager(uuid4(), "CA123", "sess-1", "corr-1")

        manager.finalize_call("completed")
        duration = manager.get_total_duration_ms()

        assert duration is not None
        assert duration >= 0


class TestNodeVisitation:
    """Tests for node visitation tracking."""

    def test_nodes_visited_tracking(self):
        """Test that visited nodes are tracked correctly."""
        manager = CallStateManager(uuid4(), "CA123", "sess-1", "corr-1")

        assert manager.nodes_visited == []

        manager.start_question("welcome", "Welcome", "narration")
        assert "welcome" in manager.nodes_visited

        manager.complete_question(None)
        manager.start_question(
            "used_before", "Have you used a voice assistant before?", "yes_no"
        )
        assert "used_before" in manager.nodes_visited
        assert len(manager.nodes_visited) == 2

    def test_duplicate_node_not_added_twice(self):
        """Test that visiting the same node doesn't add it twice."""
        manager = CallStateManager(uuid4(), "CA123", "sess-1", "corr-1")

        manager.start_question("q1", "Question 1?", "yes_no")
        manager.complete_question("yes")

        # Start same node again (shouldn't happen in practice, but test resilience)
        manager.start_question("q1", "Question 1 again?", "yes_no")

        # Should only appear once
        assert manager.nodes_visited.count("q1") == 1


class TestComplexScenario:
    """Test a complex multi-question scenario."""

    def test_full_conversation_flow(self):
        """Test a complete conversation with multiple questions and turns."""
        manager = CallStateManager(uuid4(), "CA123", "sess-1", "corr-1")

        # Question 1: Simple yes/no answered immediately
        manager.start_question(
            "q1", "Have you used a voice assistant before?", "yes_no"
        )
        manager.add_turn("yes", "Thank you", "answer", 0.95, {"valid": True}, False)
        q1_data = manager.complete_question("yes")

        assert q1_data["attempts"] == 1
        assert len(q1_data["turns"]) == 1

        # Question 2: Multiple attempts with escalation
        manager.start_question("q2", "How old are you?", "numeric")
        manager.add_turn("old enough", "Please provide age", "other", 0.6, None, True)
        manager.add_turn(
            "I said old enough!", "I need a number", "other", 0.5, None, True
        )
        manager.add_turn("25", "Great", "answer", 0.98, {"valid": True}, False)
        q2_data = manager.complete_question("25")

        assert q2_data["attempts"] == 3
        assert len(q2_data["turns"]) == 3

        # Finalize
        manager.finalize_call("all_questions_answered")
        metadata = manager.build_session_metadata("all_questions_answered")

        assert metadata["total_questions"] == 2
        assert metadata["total_turns"] == 4
        assert metadata["escalations_count"] == 2
        assert len(manager.completed_questions) == 2
