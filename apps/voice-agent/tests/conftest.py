"""Pytest configuration."""

import pytest
from opentelemetry import trace as _otel_trace
from opentelemetry.sdk.trace import TracerProvider as _TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor as _SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter as _InMemorySpanExporter,
)
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from voice_agent.database import Base
from voice_agent.models.survey import Survey
from voice_agent.models.survey_response import SurveyResponse, SurveyResponseStatus
from uuid import uuid4

# Configure pytest-asyncio
pytest_plugins = ("pytest_asyncio",)


@pytest.fixture(scope="function")
def db_session():
    """Create a test database session."""
    # Use in-memory SQLite database for tests
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()

    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)


@pytest.fixture
def survey_factory(db_session: Session):
    """Factory for creating test surveys."""

    def _create_survey(title="Test Survey", survey_type="test", data=None):
        survey = Survey(id=uuid4(), title=title, type=survey_type, data=data or {})
        db_session.add(survey)
        db_session.commit()
        db_session.refresh(survey)
        return survey

    return _create_survey


@pytest.fixture
def survey_response_factory(db_session: Session):
    """Factory for creating test survey responses."""

    def _create_response(
        survey_id,
        participant_phone="+1234567890",
        status=SurveyResponseStatus.IN_PROGRESS.value,
        responses=None,
        session_metadata=None,
    ):
        response = SurveyResponse(
            id=uuid4(),
            survey_id=survey_id,
            participant_phone=participant_phone,
            status=status,
            responses=responses or {"questions": []},
            session_metadata=session_metadata or {},
        )
        db_session.add(response)
        db_session.commit()
        db_session.refresh(response)
        return response

    return _create_response


@pytest.fixture
def handoff_store(monkeypatch):
    """Point the handoff context store at a throwaway database.

    The store persists onto the call's own survey_responses row rather than a
    module dict, because the TwiML webhooks that read it do not run in the
    process that wrote it. So a test that sets a handoff needs a row carrying
    that CallSid; the returned factory creates one.

    StaticPool keeps every session on the same in-memory database, since the
    store opens its own sessions rather than taking one.
    """
    from sqlalchemy.pool import StaticPool
    from voice_agent.voice_ai import handoff_state

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    monkeypatch.setattr(handoff_state, "SessionLocal", session_factory)

    survey_id = uuid4()
    session = session_factory()
    session.add(Survey(id=survey_id, title="T", type="test", data={}))
    session.commit()
    session.close()

    def _row_for(call_sid: str):
        session = session_factory()
        try:
            row = SurveyResponse(
                id=uuid4(),
                survey_id=survey_id,
                participant_phone=call_sid,
                status=SurveyResponseStatus.IN_PROGRESS.value,
                responses={"questions": []},
                session_metadata={},
                call_sid=call_sid,
            )
            session.add(row)
            session.commit()
            return row.id
        finally:
            session.close()

    yield _row_for
    Base.metadata.drop_all(engine)


# ---------------------------------------------------------------------------
# OTel business-event span fixture
# ---------------------------------------------------------------------------

_BUSINESS_EXPORTER = _InMemorySpanExporter()
_BUSINESS_PROCESSOR_INSTALLED = False


@pytest.fixture
def business_span_exporter():
    """In-memory exporter for `voice_survey.*` business-event spans.

    `set_tracer_provider` is one-shot, so attach a processor to whatever
    provider is already global (install an SDK provider only if the global is
    still the no-op default). Cleared before and after each test.
    """
    global _BUSINESS_PROCESSOR_INSTALLED
    current = _otel_trace.get_tracer_provider()
    if not isinstance(current, _TracerProvider):
        current = _TracerProvider()
        _otel_trace.set_tracer_provider(current)
    if not _BUSINESS_PROCESSOR_INSTALLED:
        current.add_span_processor(_SimpleSpanProcessor(_BUSINESS_EXPORTER))
        _BUSINESS_PROCESSOR_INSTALLED = True
    _BUSINESS_EXPORTER.clear()
    yield _BUSINESS_EXPORTER
    _BUSINESS_EXPORTER.clear()
