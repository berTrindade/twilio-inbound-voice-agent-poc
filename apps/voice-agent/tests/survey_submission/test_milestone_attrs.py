from voice_agent.survey_submission.types import SubmissionResult
from voice_agent.survey_submission.milestone_attrs import (
    milestone_type_from_survey_id,
    milestone_outcome_from_result,
)


def test_milestone_type_is_the_survey_id():
    assert milestone_type_from_survey_id("section_a") == "section_a"
    assert milestone_type_from_survey_id("") == ""


def test_outcome_generic_success():
    r = SubmissionResult(success=True, survey_id="section_a", data={"track": "high"})
    assert milestone_outcome_from_result(r) == "success"


def test_outcome_skipped_when_error_prefixed_skipped():
    r = SubmissionResult(
        success=False,
        survey_id="section_b",
        error="Skipped: section_a did not run",
    )
    assert milestone_outcome_from_result(r) == "skipped"


def test_outcome_failed_on_real_error():
    r = SubmissionResult(
        success=False,
        survey_id="section_b",
        error="submit_response failed for q1: 500",
    )
    assert milestone_outcome_from_result(r) == "failed"
