"""Tests for survey submission result types and failure categorization."""

from voice_agent.survey_submission.types import SubmissionResult, FailureKind


def test_failure_kind_defaults_to_none():
    r = SubmissionResult(success=True, survey_id="section_a")
    assert r.failure_kind == FailureKind.NONE


def test_failure_kind_explicit_blocking():
    r = SubmissionResult(
        success=False,
        survey_id="section_a",
        error="boom",
        failure_kind=FailureKind.BLOCKING,
    )
    assert r.failure_kind == FailureKind.BLOCKING


def test_failure_kind_members_are_exhaustive():
    assert {k.value for k in FailureKind} == {"none", "blocking"}
