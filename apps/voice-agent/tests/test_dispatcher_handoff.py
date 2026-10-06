# tests/test_dispatcher_handoff.py
import pytest
from unittest.mock import patch
from voice_agent.survey_submission.dispatcher import SurveyMilestoneDispatcher
from voice_agent.survey_submission.handler import SurveySubmissionHandler
from voice_agent.survey_submission.types import (
    MilestoneEvent,
    SubmissionResult,
    FailureKind,
)
from voice_agent.voice_ai.handoff_reasons import HandoffReason


class _Handler(SurveySubmissionHandler):
    def __init__(self, sid, result=None, raise_exc=False):
        self._sid, self._result, self._raise = sid, result, raise_exc

    def survey_id(self):
        return self._sid

    def should_trigger(self, event):
        return True

    async def submit(self, event):
        if self._raise:
            raise RuntimeError("kaboom")
        return self._result


def _event():
    return MilestoneEvent(
        event_type="source_completed",
        question_id=None,
        source="x",
        previous_source="section_a",
        all_answers={},
        response_id=None,
        call_sid="CA9",
        correlation_id="c1",
    )


@pytest.mark.asyncio
async def test_blocking_result_requests_handoff():
    d = SurveyMilestoneDispatcher()
    d.register(
        _Handler(
            "section_a",
            SubmissionResult(
                success=False,
                survey_id="section_a",
                error="500",
                failure_kind=FailureKind.BLOCKING,
            ),
        )
    )
    with patch("voice_agent.survey_submission.dispatcher.request_coach_handoff") as req:
        await d.on_milestone(_event())
    req.assert_called_once()
    assert req.call_args.args[0] == "CA9"  # call_sid
    # A blocking failure escalates with the generic system_error trigger
    assert req.call_args.kwargs["trigger"] == HandoffReason.SYSTEM_ERROR


@pytest.mark.asyncio
async def test_non_blocking_failure_does_not_request_handoff():
    d = SurveyMilestoneDispatcher()
    d.register(
        _Handler(
            "section_b",
            SubmissionResult(
                success=False,
                survey_id="section_b",
                failure_kind=FailureKind.NONE,
            ),
        )
    )
    with patch("voice_agent.survey_submission.dispatcher.request_coach_handoff") as req:
        await d.on_milestone(_event())
    req.assert_not_called()


@pytest.mark.asyncio
async def test_unhandled_exception_is_blocking_and_requests_handoff():
    d = SurveyMilestoneDispatcher()
    d.register(_Handler("section_b", raise_exc=True))
    with patch("voice_agent.survey_submission.dispatcher.request_coach_handoff") as req:
        results = await d.on_milestone(_event())
    assert results[0].failure_kind == FailureKind.BLOCKING
    req.assert_called_once()
