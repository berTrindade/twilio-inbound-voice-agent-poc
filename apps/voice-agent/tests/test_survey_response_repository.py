"""Unit tests for SurveyResponseRepository."""

import pytest
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from voice_agent.database import Base
from voice_agent.models import Survey, SurveyResponseStatus
from voice_agent.repositories import SurveyResponseRepository


@pytest.fixture
def db_session():
    """Create a test database session."""
    engine = create_engine("sqlite:///:memory:")
    with engine.connect() as conn:
        conn.execute(text("PRAGMA foreign_keys=ON"))
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture
def sample_survey(db_session):
    """Create a sample survey for testing."""
    survey = Survey(
        title="Test Survey",
        type="test",
        data={"questions": [{"id": "q1", "text": "How are you?"}]},
    )
    db_session.add(survey)
    db_session.commit()
    db_session.refresh(survey)
    return survey


@pytest.fixture
def survey_response_repo(db_session):
    """Create a SurveyResponseRepository instance."""
    return SurveyResponseRepository(db_session)


class TestSurveyResponseRepositoryCreate:
    """Tests for creating survey responses."""

    def test_create_basic_response(self, survey_response_repo, sample_survey):
        """Test creating a basic survey response."""
        response = survey_response_repo.create(
            survey_id=sample_survey.id,
            participant_phone="+1234567890",
        )

        assert response.id is not None
        assert response.survey_id == sample_survey.id
        assert response.participant_phone == "+1234567890"
        assert response.status == SurveyResponseStatus.IN_PROGRESS.value
        assert response.responses == {"questions": []}
        assert response.session_metadata == {}
        assert response.started_at is not None
        assert response.completed_at is None
        assert response.created_at is not None

    def test_create_stores_call_sid(self, survey_response_repo, sample_survey):
        """call_sid is mirrored into the indexed column for callback lookups."""
        response = survey_response_repo.create(
            survey_id=sample_survey.id,
            participant_phone="CAcall123",
            call_sid="CAcall123",
        )

        assert response.call_sid == "CAcall123"

    def test_create_response_with_initial_data(
        self, survey_response_repo, sample_survey
    ):
        """Test creating a survey response with initial responses."""
        initial_responses = {
            "questions": [
                {
                    "question_id": "q1",
                    "question_text": "How are you?",
                    "answer": "Great!",
                    "answered_at": datetime.now(timezone.utc).isoformat(),
                }
            ]
        }
        initial_session_metadata = {"device": "mobile", "app_version": "1.0.0"}

        response = survey_response_repo.create(
            survey_id=sample_survey.id,
            participant_phone="+1234567890",
            responses=initial_responses,
            session_metadata=initial_session_metadata,
        )

        assert response.responses == initial_responses
        assert response.session_metadata == initial_session_metadata

    def test_create_response_with_invalid_survey(self, survey_response_repo):
        """Test creating a response with invalid survey ID."""
        with pytest.raises(Exception):
            survey_response_repo.create(
                survey_id=uuid4(),
                participant_phone="+1234567890",
            )


class TestSurveyResponseRepositoryGetByCallSid:
    """Tests for looking up survey responses by Twilio CallSid."""

    def test_get_by_call_sid_returns_matching_row(
        self, survey_response_repo, sample_survey
    ):
        created = survey_response_repo.create(
            survey_id=sample_survey.id,
            participant_phone="CAcall123",
            call_sid="CAcall123",
        )

        found = survey_response_repo.get_by_call_sid("CAcall123")

        assert found is not None
        assert found.id == created.id

    def test_get_by_call_sid_returns_none_when_absent(self, survey_response_repo):
        assert survey_response_repo.get_by_call_sid("CAunknown") is None


class TestSurveyResponseRepositoryGetById:
    """Tests for getting survey responses by ID."""

    def test_get_existing_response(self, survey_response_repo, sample_survey):
        """Test getting an existing response."""
        created = survey_response_repo.create(
            survey_id=sample_survey.id,
            participant_phone="+1234567890",
        )

        retrieved = survey_response_repo.get_by_id(created.id)

        assert retrieved is not None
        assert retrieved.id == created.id
        assert retrieved.survey_id == created.survey_id

    def test_get_nonexistent_response(self, survey_response_repo):
        """Test getting a non-existent response."""
        result = survey_response_repo.get_by_id(uuid4())
        assert result is None


class TestSurveyResponseRepositoryAddQuestionResponse:
    """Tests for adding incremental question responses."""

    def test_add_single_question_response(self, survey_response_repo, sample_survey):
        """Test adding a single question response."""
        response = survey_response_repo.create(
            survey_id=sample_survey.id,
            participant_phone="+1234567890",
        )

        updated = survey_response_repo.add_question_response(
            response_id=response.id,
            question_id="q1",
            question_text="How are you?",
            answer="Great!",
        )

        assert len(updated.responses["questions"]) == 1
        question = updated.responses["questions"][0]
        assert question["question_id"] == "q1"
        assert question["question_text"] == "How are you?"
        assert question["answer"] == "Great!"
        assert "answered_at" in question

    def test_add_multiple_question_responses(self, survey_response_repo, sample_survey):
        """Test adding multiple question responses incrementally."""
        response = survey_response_repo.create(
            survey_id=sample_survey.id,
            participant_phone="+1234567890",
        )

        # Add first question
        survey_response_repo.add_question_response(
            response_id=response.id,
            question_id="q1",
            question_text="How are you?",
            answer="Great!",
        )

        # Add second question
        updated = survey_response_repo.add_question_response(
            response_id=response.id,
            question_id="q2",
            question_text="What's your age?",
            answer="30",
        )

        assert len(updated.responses["questions"]) == 2

    def test_add_question_response_with_metadata(
        self, survey_response_repo, sample_survey
    ):
        """Test adding a question response with metadata."""
        response = survey_response_repo.create(
            survey_id=sample_survey.id,
            participant_phone="+1234567890",
        )

        metadata = {"confidence": 0.95, "audio_duration": 2.5}

        updated = survey_response_repo.add_question_response(
            response_id=response.id,
            question_id="q1",
            question_text="How are you?",
            answer="Great!",
            metadata=metadata,
        )

        question = updated.responses["questions"][0]
        # Metadata fields are merged into the question object
        assert question["confidence"] == 0.95
        assert question["audio_duration"] == 2.5

    def test_add_question_to_completed_response(
        self, survey_response_repo, sample_survey
    ):
        """Test that adding a question to a completed response raises an error."""
        response = survey_response_repo.create(
            survey_id=sample_survey.id,
            participant_phone="+1234567890",
        )

        # Complete the response
        survey_response_repo.complete_response(response.id)

        # Try to add a question
        with pytest.raises(ValueError, match="already completed"):
            survey_response_repo.add_question_response(
                response_id=response.id,
                question_id="q1",
                question_text="How are you?",
                answer="Great!",
            )

    def test_add_question_to_nonexistent_response(self, survey_response_repo):
        """Test adding a question to a non-existent response."""
        with pytest.raises(ValueError, match="not found"):
            survey_response_repo.add_question_response(
                response_id=uuid4(),
                question_id="q1",
                question_text="How are you?",
                answer="Great!",
            )


class TestSurveyResponseRepositoryCompleteAndAbandon:
    """Tests for completing and abandoning responses."""

    def test_complete_response(self, survey_response_repo, sample_survey):
        """Test completing a survey response."""
        response = survey_response_repo.create(
            survey_id=sample_survey.id,
            participant_phone="+1234567890",
        )

        completed = survey_response_repo.complete_response(response.id)

        assert completed.status == SurveyResponseStatus.COMPLETED.value
        assert completed.completed_at is not None

    def test_complete_nonexistent_response(self, survey_response_repo):
        """Test completing a non-existent response."""
        with pytest.raises(ValueError, match="not found"):
            survey_response_repo.complete_response(uuid4())

    def test_abandon_response(self, survey_response_repo, sample_survey):
        """Test abandoning a survey response."""
        response = survey_response_repo.create(
            survey_id=sample_survey.id,
            participant_phone="+1234567890",
        )

        abandoned = survey_response_repo.abandon_response(response.id)

        assert abandoned.status == SurveyResponseStatus.ABANDONED.value

    def test_abandon_nonexistent_response(self, survey_response_repo):
        """Test abandoning a non-existent response."""
        with pytest.raises(ValueError, match="not found"):
            survey_response_repo.abandon_response(uuid4())


class TestUpdateIntegrationEvent:
    """Integration events are encrypted; only the success flag is denormalised.

    The denormalised copy is what the dashboard aggregates over, so an
    integration type missing from the allowlist is invisible there even though
    the encrypted record exists.
    """

    def _response(self, repo, survey):
        return repo.create(survey_id=survey.id, participant_phone="+1234567890")

    def test_webhook_failure_is_denormalised(self, survey_response_repo, sample_survey):
        response = self._response(survey_response_repo, sample_survey)

        survey_response_repo.update_integration_event(
            response_id=response.id,
            integration_type="webhook_submission",
            data={"response": {"success": False, "error": "timeout"}},
        )

        stored = survey_response_repo.get_by_id(response.id)
        assert stored.integration_outcomes["webhook_submission"] == {"success": False}

    def test_local_submission_is_denormalised(
        self, survey_response_repo, sample_survey
    ):
        response = self._response(survey_response_repo, sample_survey)

        survey_response_repo.update_integration_event(
            response_id=response.id,
            integration_type="local_submission",
            data={"response": {"success": True, "answer_count": 3}},
        )

        stored = survey_response_repo.get_by_id(response.id)
        assert stored.integration_outcomes["local_submission"] == {"success": True}

    def test_unknown_integration_type_is_not_denormalised(
        self, survey_response_repo, sample_survey
    ):
        response = self._response(survey_response_repo, sample_survey)

        survey_response_repo.update_integration_event(
            response_id=response.id,
            integration_type="something_else",
            data={"response": {"success": False, "participant_phone": "+1555"}},
        )

        stored = survey_response_repo.get_by_id(response.id)
        assert not (stored.integration_outcomes or {})
