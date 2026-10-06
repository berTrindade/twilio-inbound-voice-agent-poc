from voice_agent.survey_submission.dispatcher import SurveyMilestoneDispatcher
from voice_agent.survey_submission.handler import SurveySubmissionHandler
from voice_agent.survey_submission.types import MilestoneEvent, SubmissionResult


class _FakeHandler(SurveySubmissionHandler):
    def __init__(self, sid, result, triggers=True):
        self._sid, self._result, self._triggers = sid, result, triggers

    def survey_id(self):
        return self._sid

    def should_trigger(self, event):
        return self._triggers

    async def submit(self, event):
        return self._result


def _evt():
    return MilestoneEvent(
        event_type="question_answered",
        question_id="q1",
        source="section_a",
        previous_source=None,
        all_answers={},
        response_id=None,
        call_sid="CA1",
        correlation_id="c1",
    )


def _milestones(exp):
    return [
        s
        for s in exp.get_finished_spans()
        if s.attributes.get("voice_survey.event") == "milestone"
    ]


async def test_marker_on_success(business_span_exporter):
    d = SurveyMilestoneDispatcher()
    d.register(
        _FakeHandler(
            "section_a",
            SubmissionResult(
                success=True,
                survey_id="section_a",
                data={"answered": True},
            ),
        )
    )
    await d.on_milestone(_evt())
    spans = _milestones(business_span_exporter)
    assert len(spans) == 1
    a = spans[0].attributes
    assert a["voice_survey.milestone_type"] == "section_a"
    assert a["voice_survey.outcome"] == "success"
    assert a["call_sid"] == "CA1"


async def test_marker_on_failure(business_span_exporter):
    d = SurveyMilestoneDispatcher()
    d.register(
        _FakeHandler(
            "section_a",
            SubmissionResult(
                success=False,
                survey_id="section_a",
                error="start_survey failed: timeout",
            ),
        )
    )
    await d.on_milestone(_evt())
    assert (
        _milestones(business_span_exporter)[0].attributes["voice_survey.outcome"]
        == "failed"
    )


async def test_no_marker_when_handler_not_triggered(business_span_exporter):
    d = SurveyMilestoneDispatcher()
    d.register(
        _FakeHandler(
            "section_a",
            SubmissionResult(
                success=True,
                survey_id="section_a",
                data={"answered": True},
            ),
            triggers=False,
        )
    )
    await d.on_milestone(_evt())
    assert _milestones(business_span_exporter) == []
