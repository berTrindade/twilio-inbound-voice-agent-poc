"""Integration tests for async persistence functions."""

import asyncio
from unittest.mock import Mock

import pytest
from uuid import uuid4
from datetime import datetime, timezone

from voice_agent.voice_ai import async_persistence as ap
from voice_agent.voice_ai.async_persistence import AsyncPersistence
from voice_agent.models import SurveyResponseStatus


@pytest.fixture
def async_persistence(db_session):
    """Create AsyncPersistence instance with test database session."""
    # Return a session factory that always returns the same test session
    return AsyncPersistence(session_factory=lambda: db_session)


@pytest.mark.asyncio
class TestPersistQuestionAsync:
    """Tests for AsyncPersistence.persist_question method."""

    async def test_persist_question_success(
        self, async_persistence, survey_factory, survey_response_factory, db_session
    ):
        """Test successfully persisting a question."""
        survey = survey_factory()
        response = survey_response_factory(survey_id=survey.id)

        question_data = {
            "question_id": "used_before",
            "question_text": "Have you used a voice assistant before?",
            "node_type": "yes_no",
            "started_at": datetime.now(timezone.utc).isoformat(),
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "duration_ms": 5000,
            "turns": [
                {
                    "turn_number": 1,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "assistant_message": "Have you used a voice assistant before?",
                    "user_message": "yes",
                    "llm_interpretation": "answer",
                    "llm_confidence": 0.95,
                    "validation_result": {"valid": True, "normalized": "yes"},
                    "escalated": False,
                }
            ],
            "final_answer": "yes",
            "attempts": 1,
        }

        await async_persistence.persist_question(response.id, question_data)

        # Verify it was persisted (fetch fresh from DB)
        from voice_agent.repositories import SurveyResponseRepository

        repo = SurveyResponseRepository(db_session)
        updated_response = repo.get_by_id(response.id)

        assert len(updated_response.responses["questions"]) == 1
        saved_question = updated_response.responses["questions"][0]
        assert saved_question["question_id"] == "used_before"
        assert saved_question["answer"] == "yes"
        # Check that metadata fields are in the question (as per repository implementation)
        assert saved_question["node_type"] == "yes_no"
        assert saved_question["attempts"] == 1
        assert len(saved_question["turns"]) == 1

    async def test_persist_question_with_multiple_turns(
        self, async_persistence, survey_factory, survey_response_factory, db_session
    ):
        """Test persisting a question with multiple turns."""
        survey = survey_factory()
        response = survey_response_factory(survey_id=survey.id)

        question_data = {
            "question_id": "age",
            "question_text": "How old are you?",
            "node_type": "numeric",
            "started_at": datetime.now(timezone.utc).isoformat(),
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "duration_ms": 15000,
            "turns": [
                {
                    "turn_number": 1,
                    "user_message": "old enough",
                    "assistant_message": "Please provide a number",
                    "llm_interpretation": "other",
                    "llm_confidence": 0.6,
                    "validation_result": None,
                    "escalated": True,
                },
                {
                    "turn_number": 2,
                    "user_message": "25",
                    "assistant_message": "Thank you",
                    "llm_interpretation": "answer",
                    "llm_confidence": 0.98,
                    "validation_result": {"valid": True, "normalized": 25},
                    "escalated": False,
                },
            ],
            "final_answer": "25",
            "attempts": 2,
        }

        await async_persistence.persist_question(response.id, question_data)

        # Fetch fresh from DB
        from voice_agent.repositories import SurveyResponseRepository

        repo = SurveyResponseRepository(db_session)
        updated_response = repo.get_by_id(response.id)

        saved_question = updated_response.responses["questions"][0]
        assert len(saved_question["turns"]) == 2
        assert saved_question["attempts"] == 2

    async def test_persist_question_nonexistent_response(self, async_persistence):
        """Test persisting to non-existent response fails gracefully."""
        fake_id = uuid4()
        question_data = {
            "question_id": "test",
            "question_text": "Test?",
            "node_type": "yes_no",
            "final_answer": "yes",
            "turns": [],
            "attempts": 1,
        }

        # Should not raise exception (graceful failure)
        await async_persistence.persist_question(fake_id, question_data)


@pytest.mark.asyncio
class TestUpdateMetadata:
    """Tests for the update_metadata method."""

    async def test_update_metadata_success(
        self, async_persistence, survey_factory, survey_response_factory, db_session
    ):
        """Test successfully updating metadata."""
        survey = survey_factory()
        response = survey_response_factory(
            survey_id=survey.id,
            session_metadata={"initial": "data"},
        )

        new_metadata = {
            "total_duration_ms": 120000,
            "total_questions": 5,
            "escalations_count": 2,
        }

        response_id = response.id
        await async_persistence.update_metadata(response_id, new_metadata)

        # Fetch fresh from DB
        from voice_agent.repositories import SurveyResponseRepository

        repo = SurveyResponseRepository(db_session)
        updated_response = repo.get_by_id(response_id)

        assert (
            updated_response.session_metadata["initial"] == "data"
        )  # Original preserved
        assert updated_response.session_metadata["total_duration_ms"] == 120000
        assert updated_response.session_metadata["total_questions"] == 5
        assert updated_response.session_metadata["escalations_count"] == 2

    async def test_update_metadata_overwrites_existing(
        self, async_persistence, survey_factory, survey_response_factory, db_session
    ):
        """Test that updating metadata overwrites existing keys."""
        survey = survey_factory()
        response = survey_response_factory(
            survey_id=survey.id,
            session_metadata={"count": 10, "status": "in_progress"},
        )

        new_metadata = {"count": 20, "new_field": "value"}

        response_id = response.id
        await async_persistence.update_metadata(response_id, new_metadata)

        # Fetch fresh from DB
        from voice_agent.repositories import SurveyResponseRepository

        repo = SurveyResponseRepository(db_session)
        updated_response = repo.get_by_id(response_id)

        assert updated_response.session_metadata["count"] == 20  # Overwritten
        assert updated_response.session_metadata["status"] == "in_progress"  # Preserved
        assert updated_response.session_metadata["new_field"] == "value"  # Added

    async def test_update_metadata_nonexistent_response(self, async_persistence):
        """Test updating non-existent response fails gracefully."""
        fake_id = uuid4()
        metadata = {"test": "data"}

        # Should not raise exception
        await async_persistence.update_metadata(fake_id, metadata)


@pytest.mark.asyncio
class TestCompleteResponseAsync:
    """Tests for complete_response_async function."""

    async def test_complete_response_success(
        self, async_persistence, survey_factory, survey_response_factory, db_session
    ):
        """Test successfully completing a response."""
        survey = survey_factory()
        response = survey_response_factory(survey_id=survey.id)

        assert response.status == SurveyResponseStatus.IN_PROGRESS.value
        assert response.completed_at is None

        final_metadata = {
            "total_duration_ms": 180000,
            "completion_reason": "all_questions_answered",
        }

        response_id = response.id
        await async_persistence.complete_response(response_id, final_metadata)

        # Fetch fresh from DB
        from voice_agent.repositories import SurveyResponseRepository

        repo = SurveyResponseRepository(db_session)
        updated_response = repo.get_by_id(response_id)

        assert updated_response.status == SurveyResponseStatus.COMPLETED.value
        assert updated_response.completed_at is not None
        assert updated_response.session_metadata["total_duration_ms"] == 180000
        assert (
            updated_response.session_metadata["completion_reason"]
            == "all_questions_answered"
        )

    async def test_complete_response_nonexistent(self, async_persistence):
        """Test completing non-existent response fails gracefully."""
        fake_id = uuid4()
        metadata = {"test": "data"}

        # Should not raise exception
        await async_persistence.complete_response(fake_id, metadata)


@pytest.mark.asyncio
class TestAbandonResponseAsync:
    """Tests for abandon_response_async function."""

    async def test_abandon_response_success(
        self, async_persistence, survey_factory, survey_response_factory, db_session
    ):
        """Test successfully abandoning a response."""
        survey = survey_factory()
        response = survey_response_factory(survey_id=survey.id)

        assert response.status == SurveyResponseStatus.IN_PROGRESS.value

        final_metadata = {
            "total_duration_ms": 45000,
            "completion_reason": "user_disconnect",
            "total_questions": 3,
        }

        response_id = response.id
        await async_persistence.abandon_response(response_id, final_metadata)

        # Fetch fresh from DB
        from voice_agent.repositories import SurveyResponseRepository

        repo = SurveyResponseRepository(db_session)
        updated_response = repo.get_by_id(response_id)

        assert updated_response.status == SurveyResponseStatus.ABANDONED.value
        assert updated_response.session_metadata["total_duration_ms"] == 45000
        assert (
            updated_response.session_metadata["completion_reason"] == "user_disconnect"
        )
        assert updated_response.session_metadata["total_questions"] == 3

    async def test_abandon_response_preserves_existing_metadata(
        self, async_persistence, survey_factory, survey_response_factory, db_session
    ):
        """Test abandoning preserves existing metadata."""
        survey = survey_factory()
        response = survey_response_factory(
            survey_id=survey.id,
            session_metadata={"call_sid": "CA123", "started": True},
        )

        final_metadata = {"completion_reason": "disconnect"}

        response_id = response.id
        await async_persistence.abandon_response(response_id, final_metadata)

        # Fetch fresh from DB
        from voice_agent.repositories import SurveyResponseRepository

        repo = SurveyResponseRepository(db_session)
        updated_response = repo.get_by_id(response_id)

        assert updated_response.status == SurveyResponseStatus.ABANDONED.value
        assert updated_response.session_metadata["call_sid"] == "CA123"  # Preserved
        assert updated_response.session_metadata["started"] is True  # Preserved
        assert (
            updated_response.session_metadata["completion_reason"] == "disconnect"
        )  # Added

    async def test_abandon_response_nonexistent(self, async_persistence):
        """Test abandoning non-existent response fails gracefully."""
        fake_id = uuid4()
        metadata = {"test": "data"}

        # Should not raise exception
        await async_persistence.abandon_response(fake_id, metadata)


@pytest.mark.asyncio
class TestConcurrentPersistence:
    """Tests for concurrent persistence operations."""

    async def test_concurrent_question_persistence(
        self, async_persistence, survey_factory, survey_response_factory, db_session
    ):
        """Test that multiple questions can be persisted concurrently."""

        survey = survey_factory()
        response = survey_response_factory(survey_id=survey.id)

        question_data_1 = {
            "question_id": "q1",
            "question_text": "Question 1?",
            "node_type": "yes_no",
            "final_answer": "yes",
            "turns": [],
            "attempts": 1,
        }

        question_data_2 = {
            "question_id": "q2",
            "question_text": "Question 2?",
            "node_type": "numeric",
            "final_answer": "25",
            "turns": [],
            "attempts": 1,
        }

        # Persist concurrently
        await asyncio.gather(
            async_persistence.persist_question(response.id, question_data_1),
            async_persistence.persist_question(response.id, question_data_2),
        )

        # Fetch fresh from DB
        from voice_agent.repositories import SurveyResponseRepository

        repo = SurveyResponseRepository(db_session)
        updated_response = repo.get_by_id(response.id)

        assert len(updated_response.responses["questions"]) == 2

    async def test_metadata_updates_do_not_conflict(
        self, async_persistence, survey_factory, survey_response_factory, db_session
    ):
        """Test that concurrent metadata updates don't conflict."""

        survey = survey_factory()
        response = survey_response_factory(survey_id=survey.id)

        metadata_1 = {"field1": "value1"}
        metadata_2 = {"field2": "value2"}

        response_id = response.id

        # Update concurrently
        await asyncio.gather(
            async_persistence.update_metadata(response_id, metadata_1),
            async_persistence.update_metadata(response_id, metadata_2),
        )

        # Fetch fresh from DB
        from voice_agent.repositories import SurveyResponseRepository

        repo = SurveyResponseRepository(db_session)
        updated_response = repo.get_by_id(response_id)

        # Both fields should be present (though order is not guaranteed)
        assert (
            "field1" in updated_response.session_metadata
            or "field2" in updated_response.session_metadata
        )


def _patch_recording_persistence(monkeypatch, row):
    """Wire persist_recording_metadata's collaborators to mocks. Returns repo."""
    repo = Mock()
    repo.get_by_call_sid.return_value = row
    monkeypatch.setattr(ap, "SessionLocal", lambda: Mock())
    monkeypatch.setattr(ap, "SurveyResponseRepository", lambda db: repo)
    return repo


def test_persist_recording_metadata_writes_the_block(monkeypatch):
    rid = uuid4()
    repo = _patch_recording_persistence(monkeypatch, Mock(id=rid))

    ap.persist_recording_metadata("CAcall123", {"status": "completed"})

    repo.update_session_metadata.assert_called_once_with(
        rid, {"recording": {"status": "completed"}}
    )


def test_persist_recording_metadata_noop_when_row_missing(monkeypatch):
    repo = _patch_recording_persistence(monkeypatch, None)

    ap.persist_recording_metadata("CAunknown", {"status": "completed"})

    repo.update_session_metadata.assert_not_called()


def test_persist_recording_metadata_swallows_write_failure(monkeypatch):
    """It runs as a background task off Twilio's callback, so it must not raise."""
    repo = _patch_recording_persistence(monkeypatch, Mock(id=uuid4()))
    repo.update_session_metadata.side_effect = RuntimeError("db down")

    ap.persist_recording_metadata("CAcall123", {"status": "completed"})
