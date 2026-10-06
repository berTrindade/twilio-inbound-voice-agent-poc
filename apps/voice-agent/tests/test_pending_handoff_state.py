from voice_agent.voice_ai.pending_handoff_state import (
    request_coach_handoff,
    pop_pending_handoff,
    clear_pending_handoff,
)


def test_request_then_pop_returns_once():
    request_coach_handoff(
        "CA1", reason="submission_failed", whisper_text="w", trigger="system_error"
    )
    got = pop_pending_handoff("CA1")
    assert (
        got is not None
        and got.reason == "submission_failed"
        and got.whisper_text == "w"
        and got.trigger == "system_error"
    )
    assert pop_pending_handoff("CA1") is None  # consumed


def test_clear_removes_entry():
    request_coach_handoff("CA2", reason="r", whisper_text="w", trigger="system_error")
    clear_pending_handoff("CA2")
    assert pop_pending_handoff("CA2") is None


def test_request_with_no_call_sid_is_noop():
    request_coach_handoff(
        None, reason="r", whisper_text="w", trigger="system_error"
    )  # must not raise
    assert pop_pending_handoff(None) is None
