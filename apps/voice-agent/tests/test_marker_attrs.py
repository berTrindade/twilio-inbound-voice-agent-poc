from voice_agent.api.websocket_types import PromptEndMode
from voice_agent.api.websocket_handlers.marker_attrs import (
    completion_type_from_end_mode,
    handoff_outcome_from_dial_status,
)


def test_finished():
    assert completion_type_from_end_mode(PromptEndMode.SURVEY_COMPLETED) == "finished"


def test_escalation():
    assert (
        completion_type_from_end_mode(PromptEndMode.COACH_HANDOFF_STARTED)
        == "escalation"
    )


def test_abandoned_user_ended():
    assert (
        completion_type_from_end_mode(PromptEndMode.USER_ENDED_SESSION) == "abandoned"
    )


def test_abandoned_already_terminal():
    assert completion_type_from_end_mode(PromptEndMode.ALREADY_TERMINAL) == "abandoned"


def test_handoff_succeeded():
    assert handoff_outcome_from_dial_status("completed") == "succeeded"


def test_handoff_succeeded_caps():
    assert handoff_outcome_from_dial_status("Completed") == "succeeded"


def test_handoff_no_answer():
    assert handoff_outcome_from_dial_status("no-answer") == "no_answer"


def test_handoff_busy():
    assert handoff_outcome_from_dial_status("busy") == "busy"


def test_handoff_failed():
    assert handoff_outcome_from_dial_status("failed") == "failed"


def test_handoff_canceled():
    assert handoff_outcome_from_dial_status("canceled") == "canceled"


def test_handoff_unknown_is_failed():
    assert handoff_outcome_from_dial_status("") == "failed"
    assert handoff_outcome_from_dial_status("weird") == "failed"
