"""Tests for SurveyMilestoneDispatcher."""

from uuid import uuid4

import pytest

from voice_agent.survey_submission.dispatcher import SurveyMilestoneDispatcher
from voice_agent.survey_submission.handler import SurveySubmissionHandler
from voice_agent.survey_submission.types import (
    FailureKind,
    MilestoneEvent,
    SubmissionResult,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_event(**overrides) -> MilestoneEvent:
    defaults = {
        "event_type": "question_answered",
        "question_id": "Q1",
        "source": "section_a",
        "previous_source": None,
        "all_answers": {"Q1": "yes"},
        "response_id": uuid4(),
        "call_sid": "CA123",
        "correlation_id": "corr-1",
    }
    defaults.update(overrides)
    return MilestoneEvent(**defaults)


class StubHandler(SurveySubmissionHandler):
    """Configurable stub handler for testing."""

    def __init__(
        self,
        sid: str = "test_survey",
        trigger: bool = True,
        result: SubmissionResult | None = None,
        raise_on_submit: Exception | None = None,
        raise_on_trigger: Exception | None = None,
    ):
        self._sid = sid
        self._trigger = trigger
        self._result = result or SubmissionResult(success=True, survey_id=sid)
        self._raise_on_submit = raise_on_submit
        self._raise_on_trigger = raise_on_trigger
        self.submit_called_count = 0
        self.last_event: MilestoneEvent | None = None

    def survey_id(self) -> str:
        return self._sid

    def should_trigger(self, event: MilestoneEvent) -> bool:
        if self._raise_on_trigger:
            raise self._raise_on_trigger
        return self._trigger

    async def submit(self, event: MilestoneEvent) -> SubmissionResult:
        self.submit_called_count += 1
        self.last_event = event
        if self._raise_on_submit:
            raise self._raise_on_submit
        return self._result


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestRegistration:
    def test_register_handler(self):
        d = SurveyMilestoneDispatcher()
        h = StubHandler(sid="survey_a")
        d.register(h)
        assert len(d._handlers) == 1

    def test_register_duplicate_is_ignored(self):
        d = SurveyMilestoneDispatcher()
        h1 = StubHandler(sid="survey_a")
        h2 = StubHandler(sid="survey_a")
        d.register(h1)
        d.register(h2)
        assert len(d._handlers) == 1

    def test_register_different_ids(self):
        d = SurveyMilestoneDispatcher()
        d.register(StubHandler(sid="a"))
        d.register(StubHandler(sid="b"))
        assert len(d._handlers) == 2


class TestDispatch:
    @pytest.mark.asyncio
    async def test_handler_triggered_and_called(self):
        d = SurveyMilestoneDispatcher()
        h = StubHandler(sid="section_a", trigger=True)
        d.register(h)

        event = _make_event()
        results = await d.on_milestone(event)

        assert len(results) == 1
        assert results[0].success is True
        assert h.submit_called_count == 1
        assert h.last_event is event

    @pytest.mark.asyncio
    async def test_handler_not_triggered(self):
        d = SurveyMilestoneDispatcher()
        h = StubHandler(sid="section_a", trigger=False)
        d.register(h)

        results = await d.on_milestone(_make_event())

        assert len(results) == 0
        assert h.submit_called_count == 0

    @pytest.mark.asyncio
    async def test_multiple_handlers_some_trigger(self):
        d = SurveyMilestoneDispatcher()
        h1 = StubHandler(sid="a", trigger=True)
        h2 = StubHandler(sid="b", trigger=False)
        h3 = StubHandler(sid="c", trigger=True)
        d.register(h1)
        d.register(h2)
        d.register(h3)

        results = await d.on_milestone(_make_event())

        assert len(results) == 2
        assert h1.submit_called_count == 1
        assert h2.submit_called_count == 0
        assert h3.submit_called_count == 1


class TestDeduplication:
    @pytest.mark.asyncio
    async def test_successful_handler_not_called_twice(self):
        d = SurveyMilestoneDispatcher()
        h = StubHandler(sid="section_a", trigger=True)
        d.register(h)

        await d.on_milestone(_make_event())
        await d.on_milestone(_make_event())

        assert h.submit_called_count == 1

    @pytest.mark.asyncio
    async def test_failed_handler_can_retry(self):
        d = SurveyMilestoneDispatcher()
        fail_result = SubmissionResult(
            success=False, survey_id="section_a", error="timeout"
        )
        h = StubHandler(sid="section_a", trigger=True, result=fail_result)
        d.register(h)

        await d.on_milestone(_make_event())
        assert h.submit_called_count == 1

        # Failed -> not in _submitted -> can retry
        await d.on_milestone(_make_event())
        assert h.submit_called_count == 2


class TestErrorHandling:
    @pytest.mark.asyncio
    async def test_submit_exception_returns_error_result(self):
        d = SurveyMilestoneDispatcher()
        h = StubHandler(
            sid="section_a",
            trigger=True,
            raise_on_submit=RuntimeError("API down"),
        )
        d.register(h)

        results = await d.on_milestone(_make_event())

        assert len(results) == 1
        assert results[0].success is False
        assert "RuntimeError" in results[0].error

    @pytest.mark.asyncio
    async def test_should_trigger_exception_is_swallowed(self):
        d = SurveyMilestoneDispatcher()
        h = StubHandler(
            sid="section_a",
            trigger=True,
            raise_on_trigger=ValueError("bad config"),
        )
        d.register(h)

        results = await d.on_milestone(_make_event())

        assert len(results) == 0
        assert h.submit_called_count == 0

    @pytest.mark.asyncio
    async def test_one_handler_error_does_not_block_others(self):
        d = SurveyMilestoneDispatcher()
        h_fail = StubHandler(
            sid="a", trigger=True, raise_on_submit=RuntimeError("boom")
        )
        h_ok = StubHandler(sid="b", trigger=True)
        d.register(h_fail)
        d.register(h_ok)

        results = await d.on_milestone(_make_event())

        assert len(results) == 2
        assert h_ok.submit_called_count == 1
        assert any(r.success is False for r in results)
        assert any(r.success is True for r in results)


class _RecordingRepository:
    def __init__(self):
        self.calls = []

    def update_integration_event(self, *, response_id, integration_type, data):
        self.calls.append((response_id, integration_type, data))


class TestFailureRecording:
    """A failed submission must leave an integration event behind.

    Handlers only write their own record on the happy path, so without this the
    dashboard cannot distinguish a submission that never ran from one that ran
    and failed.
    """

    def _handler(self, repo, result=None, raise_on_submit=None):
        h = StubHandler(
            sid="section_a",
            trigger=True,
            result=result,
            raise_on_submit=raise_on_submit,
        )
        h.repository = repo
        h.response_id = uuid4()
        h.INTEGRATION_TYPE = "webhook_submission"
        return h

    @pytest.mark.asyncio
    async def test_failed_result_is_persisted(self):
        repo = _RecordingRepository()
        d = SurveyMilestoneDispatcher()
        d.register(
            self._handler(
                repo,
                result=SubmissionResult(
                    success=False,
                    survey_id="section_a",
                    error="timeout",
                    failure_kind=FailureKind.BLOCKING,
                    status_code=504,
                ),
            )
        )

        await d.on_milestone(_make_event())

        assert len(repo.calls) == 1
        _, integration_type, data = repo.calls[0]
        assert integration_type == "webhook_submission"
        assert data["response"] == {
            "success": False,
            "error": "timeout",
            "blocking": True,
            "status_code": 504,
        }

    @pytest.mark.asyncio
    async def test_raised_exception_is_persisted_as_blocking(self):
        repo = _RecordingRepository()
        d = SurveyMilestoneDispatcher()
        d.register(self._handler(repo, raise_on_submit=RuntimeError("boom")))

        await d.on_milestone(_make_event())

        assert len(repo.calls) == 1
        response = repo.calls[0][2]["response"]
        assert response["success"] is False
        assert response["blocking"] is True
        assert "RuntimeError" in response["error"]

    @pytest.mark.asyncio
    async def test_success_is_left_to_the_handler(self):
        repo = _RecordingRepository()
        d = SurveyMilestoneDispatcher()
        d.register(self._handler(repo))

        await d.on_milestone(_make_event())

        assert repo.calls == []

    @pytest.mark.asyncio
    async def test_skipped_result_is_not_a_failure(self):
        repo = _RecordingRepository()
        d = SurveyMilestoneDispatcher()
        d.register(
            self._handler(
                repo,
                result=SubmissionResult(
                    success=False,
                    survey_id="section_a",
                    error="Skipped: no webhook configured",
                ),
            )
        )

        await d.on_milestone(_make_event())

        assert repo.calls == []

    @pytest.mark.asyncio
    async def test_handler_without_a_repository_is_skipped(self):
        d = SurveyMilestoneDispatcher()
        h = StubHandler(
            sid="section_a",
            trigger=True,
            result=SubmissionResult(
                success=False, survey_id="section_a", error="timeout"
            ),
        )
        d.register(h)

        results = await d.on_milestone(_make_event())

        assert results[0].success is False
