"""Performance tests for persistence operations."""

import pytest
import asyncio
import time
from uuid import uuid4

from voice_agent.voice_ai.call_state_manager import CallStateManager


@pytest.mark.asyncio
class TestPersistencePerformance:
    """Performance tests to ensure persistence doesn't add significant latency."""

    async def test_call_state_manager_overhead(self):
        """Test that CallStateManager operations are fast (<1ms each)."""
        manager = CallStateManager(
            response_id=uuid4(),
            call_sid="CA123",
            session_id="sess-1",
            correlation_id="corr-1",
        )

        # Test start_question performance
        start = time.perf_counter()
        for _ in range(100):
            manager.start_question("test_q", "Test question?", "yes_no")
        elapsed = (time.perf_counter() - start) * 1000  # ms
        avg_per_call = elapsed / 100

        assert (
            avg_per_call < 1.0
        ), f"start_question took {avg_per_call:.2f}ms (expected <1ms)"

        # Test add_turn performance
        manager.start_question("perf_test", "Performance test?", "yes_no")
        start = time.perf_counter()
        for i in range(100):
            manager.add_turn(
                user_message=f"message {i}",
                assistant_message="response",
                llm_interpretation="answer",
                llm_confidence=0.9,
                validation_result={"valid": True},
                escalated=False,
            )
        elapsed = (time.perf_counter() - start) * 1000
        avg_per_call = elapsed / 100

        assert avg_per_call < 1.0, f"add_turn took {avg_per_call:.2f}ms (expected <1ms)"

        # Test complete_question performance
        manager.start_question("complete_test", "Test?", "yes_no")
        manager.add_turn("yes", "ok", "answer", 0.9, {"valid": True}, False)
        start = time.perf_counter()
        for _ in range(100):
            manager.start_question("test", "Test?", "yes_no")
            manager.add_turn("yes", "ok", "answer", 0.9, {"valid": True}, False)
            manager.complete_question("yes")
        elapsed = (time.perf_counter() - start) * 1000
        avg_per_call = elapsed / 100

        assert (
            avg_per_call < 1.0
        ), f"complete_question took {avg_per_call:.2f}ms (expected <1ms)"

    async def test_build_payloads_performance(self):
        """Test that building payloads for persistence is fast."""
        manager = CallStateManager(
            response_id=uuid4(),
            call_sid="CA123",
            session_id="sess-1",
            correlation_id="corr-1",
        )

        # Add several questions with multiple turns each
        for i in range(10):
            manager.start_question(f"q{i}", f"Question {i}?", "yes_no")
            for j in range(5):
                manager.add_turn(
                    f"answer {j}",
                    "response",
                    "answer",
                    0.9,
                    {"valid": j == 4},
                    False,
                )
            manager.complete_question("yes")

        # Test build_session_metadata performance
        manager.finalize_call("completed")
        start = time.perf_counter()
        for _ in range(100):
            manager.build_session_metadata("completed")
        elapsed = (time.perf_counter() - start) * 1000
        avg_per_call = elapsed / 100

        assert (
            avg_per_call < 5.0
        ), f"build_session_metadata took {avg_per_call:.2f}ms (expected <5ms)"

    async def test_async_persistence_fire_and_forget(self):
        """Test that async persistence task creation doesn't block."""

        # Mock persistence function (doesn't actually persist)
        async def mock_persist():
            await asyncio.sleep(0.01)  # Simulate some async work

        # Measure time to launch the async task (not wait for it)
        start = time.perf_counter()
        task = asyncio.create_task(mock_persist())
        elapsed_ms = (time.perf_counter() - start) * 1000

        # Creating the task should be nearly instant
        assert (
            elapsed_ms < 1.0
        ), f"Creating async task took {elapsed_ms:.2f}ms (expected <1ms)"

        # Wait for it to complete (for test cleanup)
        await task


@pytest.mark.asyncio
class TestMemoryUsage:
    """Test memory efficiency of persistence operations."""

    async def test_call_state_manager_memory_efficiency(self):
        """Test that CallStateManager doesn't consume excessive memory."""
        import sys

        manager = CallStateManager(
            response_id=uuid4(),
            call_sid="CA123",
            session_id="sess-1",
            correlation_id="corr-1",
        )

        initial_size = sys.getsizeof(manager.completed_questions)

        # Add 100 questions with 10 turns each
        for i in range(100):
            manager.start_question(f"q{i}", f"Question {i}?", "yes_no")
            for j in range(10):
                manager.add_turn(
                    f"user message {j}" * 10,  # Make it realistic size
                    f"assistant message {j}" * 10,
                    "answer",
                    0.9,
                    {"valid": True, "normalized": "test"},
                    False,
                )
            manager.complete_question("answer")

        final_size = sys.getsizeof(manager.completed_questions)

        # Size should grow linearly, not exponentially
        # With 100 questions and 10 turns each, we expect reasonable growth
        size_per_question = (final_size - initial_size) / 100

        # Each question with 10 turns should be under 10KB
        assert size_per_question < 10000, (
            f"Memory usage per question: {size_per_question} bytes "
            f"(expected <10KB per question)"
        )


@pytest.mark.asyncio
class TestEndToEndLatency:
    """Test end-to-end latency of the persistence pipeline."""

    async def test_full_question_cycle_latency(self):
        """
        Test the full cycle: start question, add turns, complete, persist.

        Target: <50ms total overhead for the synchronous parts.
        """
        manager = CallStateManager(
            response_id=uuid4(),
            call_sid="CA123",
            session_id="sess-1",
            correlation_id="corr-1",
        )

        # Measure synchronous overhead only (not async persistence)
        start = time.perf_counter()

        # Start question
        manager.start_question("perf_test", "Performance test?", "yes_no")

        # Add a few turns
        for i in range(3):
            manager.add_turn(
                f"user message {i}",
                f"assistant message {i}",
                "answer",
                0.9,
                {"valid": i == 2},
                False,
            )

        # Complete question
        manager.complete_question("yes")

        elapsed_ms = (time.perf_counter() - start) * 1000

        # All synchronous operations should complete in under 50ms
        assert elapsed_ms < 50.0, (
            f"Full question cycle took {elapsed_ms:.2f}ms (expected <50ms). "
            f"This is the synchronous overhead added to the conversation flow."
        )

    async def test_no_blocking_during_conversation(self):
        """
        Simulate a realistic conversation flow to ensure persistence doesn't block.
        """
        manager = CallStateManager(
            response_id=uuid4(),
            call_sid="CA123",
            session_id="sess-1",
            correlation_id="corr-1",
        )

        # Mock persistence function
        async def mock_persist(data):
            await asyncio.sleep(0.001)  # Simulate minimal async work

        # Simulate 5 questions
        persistence_tasks = []
        conversation_overheads = []

        for q_num in range(5):
            start = time.perf_counter()

            # Start question
            manager.start_question(f"q{q_num}", f"Question {q_num}?", "yes_no")

            # Add 2 turns (average case)
            manager.add_turn("unclear", "clarify", "other", 0.6, None, True)
            manager.add_turn("yes", "thanks", "answer", 0.95, {"valid": True}, False)

            # Complete
            question_data = manager.complete_question("yes")

            # Launch persistence (fire and forget)
            task = asyncio.create_task(mock_persist(question_data))
            persistence_tasks.append(task)

            elapsed_ms = (time.perf_counter() - start) * 1000
            conversation_overheads.append(elapsed_ms)

        # Check that conversation overhead was minimal
        max_overhead = max(conversation_overheads)
        avg_overhead = sum(conversation_overheads) / len(conversation_overheads)

        assert (
            max_overhead < 50.0
        ), f"Max conversation overhead: {max_overhead:.2f}ms (expected <50ms)"
        assert (
            avg_overhead < 10.0
        ), f"Average conversation overhead: {avg_overhead:.2f}ms (expected <10ms)"

        # Wait for all persistence to complete (for cleanup)
        await asyncio.gather(*persistence_tasks)

        # Verify all questions were tracked
        assert len(manager.completed_questions) == 5
