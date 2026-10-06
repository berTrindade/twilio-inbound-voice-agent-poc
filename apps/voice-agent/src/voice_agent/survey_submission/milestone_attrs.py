"""Pure helpers mapping handler `survey_id` + `SubmissionResult` to the
`voice_survey.milestone` span vocabulary."""

from .types import SubmissionResult


def milestone_type_from_survey_id(survey_id: str) -> str:
    """Return the public milestone_type for a handler's SURVEY_ID."""
    return survey_id


def milestone_outcome_from_result(result: SubmissionResult) -> str:
    """Normalise a SubmissionResult to one public outcome value.

    Handlers signal "did not run, non-error" with success=False + error string
    starting "Skipped:", which is how a handler reports that a prerequisite it
    depends on was absent.
    """
    if not result.success:
        if result.error and result.error.startswith("Skipped:"):
            return "skipped"
        return "failed"
    return "success"
