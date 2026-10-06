"""Unit tests for SurveyResponse model."""

import pytest
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from voice_agent.database import Base
from voice_agent.models import Survey, SurveyResponse, SurveyResponseStatus


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


class TestSurveyResponseModel:
    """Tests for SurveyResponse model."""

    def test_create_survey_response(self, db_session, sample_survey):
        """Test creating a survey response with required fields."""
        response = SurveyResponse(
            survey_id=sample_survey.id,
            participant_phone="+1234567890",
            status=SurveyResponseStatus.IN_PROGRESS.value,
            responses={"questions": []},
        )

        db_session.add(response)
        db_session.commit()
        db_session.refresh(response)

        assert response.id is not None
        assert response.survey_id == sample_survey.id
        assert response.participant_phone == "+1234567890"
        assert response.status == SurveyResponseStatus.IN_PROGRESS.value
        assert response.responses == {"questions": []}
        assert response.session_metadata == {}
        assert response.started_at is not None
        assert response.created_at is not None
        assert response.completed_at is None

    def test_survey_response_with_all_fields(self, db_session, sample_survey):
        """Test creating a survey response with all optional fields."""
        now = datetime.now(timezone.utc)
        responses_data = {
            "questions": [
                {
                    "question_id": "q1",
                    "question_text": "How are you?",
                    "answer": "Great!",
                    "answered_at": now.isoformat(),
                }
            ]
        }
        session_metadata = {"device": "mobile", "app_version": "1.0.0"}

        response = SurveyResponse(
            survey_id=sample_survey.id,
            participant_phone="+1234567890",
            status=SurveyResponseStatus.COMPLETED.value,
            responses=responses_data,
            session_metadata=session_metadata,
            started_at=now,
            completed_at=now,
        )

        db_session.add(response)
        db_session.commit()
        db_session.refresh(response)

        assert response.responses == responses_data
        assert response.session_metadata == session_metadata
        assert response.status == SurveyResponseStatus.COMPLETED.value
        assert response.completed_at is not None

    def test_survey_response_enum_values(self):
        """Test SurveyResponseStatus enum values."""
        assert SurveyResponseStatus.IN_PROGRESS.value == "in_progress"
        assert SurveyResponseStatus.COMPLETED.value == "completed"
        assert SurveyResponseStatus.ABANDONED.value == "abandoned"

    def test_survey_response_relationship(self, db_session, sample_survey):
        """Test relationship between SurveyResponse and Survey."""
        response = SurveyResponse(
            survey_id=sample_survey.id,
            participant_phone="+1234567890",
            status=SurveyResponseStatus.IN_PROGRESS.value,
            responses={"questions": []},
        )

        db_session.add(response)
        db_session.commit()
        db_session.refresh(response)

        # Test relationship
        assert response.survey is not None
        assert response.survey.id == sample_survey.id
        assert response.survey.title == sample_survey.title

    def test_survey_response_repr(self, db_session, sample_survey):
        """Test string representation of SurveyResponse."""
        response = SurveyResponse(
            survey_id=sample_survey.id,
            participant_phone="+1234567890",
            status=SurveyResponseStatus.IN_PROGRESS.value,
            responses={"questions": []},
        )

        db_session.add(response)
        db_session.commit()
        db_session.refresh(response)

        repr_str = repr(response)
        assert "SurveyResponse" in repr_str
        assert str(response.id) in repr_str
        assert str(response.survey_id) in repr_str
        assert response.status in repr_str

    def test_survey_response_jsonb_flexibility(self, db_session, sample_survey):
        """Test that JSONB fields can store flexible data structures."""
        # Test complex responses structure
        complex_responses = {
            "questions": [
                {
                    "question_id": "q1",
                    "question_text": "How are you?",
                    "answer": "Great!",
                    "answered_at": datetime.now(timezone.utc).isoformat(),
                    "metadata": {
                        "confidence": 0.95,
                        "audio_duration": 2.5,
                        "retry_count": 0,
                    },
                }
            ],
            "custom_field": "custom_value",
            "nested": {"deep": {"structure": "works"}},
        }

        complex_session_metadata = {
            "device": "mobile",
            "os": "iOS",
            "version": "15.0",
            "location": {"lat": 40.7128, "lon": -74.0060},
            "network": {"type": "wifi", "speed": "high"},
        }

        response = SurveyResponse(
            survey_id=sample_survey.id,
            participant_phone="+1234567890",
            status=SurveyResponseStatus.IN_PROGRESS.value,
            responses=complex_responses,
            session_metadata=complex_session_metadata,
        )

        db_session.add(response)
        db_session.commit()
        db_session.refresh(response)

        # Verify complex structures are preserved
        assert response.responses == complex_responses
        assert response.session_metadata == complex_session_metadata
        assert response.responses["nested"]["deep"]["structure"] == "works"
        assert response.session_metadata["location"]["lat"] == 40.7128

    def test_foreign_key_constraint(self, db_session):
        """Test that foreign key constraint is enforced."""
        # Try to create response with non-existent survey
        response = SurveyResponse(
            survey_id=uuid4(),  # Non-existent survey
            participant_phone="+1234567890",
            status=SurveyResponseStatus.IN_PROGRESS.value,
            responses={"questions": []},
        )

        db_session.add(response)

        with pytest.raises(Exception):  # Should raise integrity error
            db_session.commit()

    def test_multiple_responses_per_survey(self, db_session, sample_survey):
        """Test that multiple responses can be created for the same survey."""
        responses = []
        for i in range(5):
            response = SurveyResponse(
                survey_id=sample_survey.id,
                participant_phone=f"+123456789{i}",
                status=SurveyResponseStatus.IN_PROGRESS.value,
                responses={"questions": []},
            )
            db_session.add(response)
            responses.append(response)

        db_session.commit()

        # Verify all were created
        for response in responses:
            db_session.refresh(response)
            assert response.id is not None

    def test_multiple_responses_per_participant(self, db_session, sample_survey):
        """Test that a participant can have multiple responses to the same survey."""
        phone = "+1234567890"

        responses = []
        for _ in range(3):
            response = SurveyResponse(
                survey_id=sample_survey.id,
                participant_phone=phone,
                status=SurveyResponseStatus.IN_PROGRESS.value,
                responses={"questions": []},
            )
            db_session.add(response)
            responses.append(response)

        db_session.commit()

        # Verify all were created
        for response in responses:
            db_session.refresh(response)
            assert response.id is not None
            assert response.participant_phone == phone
