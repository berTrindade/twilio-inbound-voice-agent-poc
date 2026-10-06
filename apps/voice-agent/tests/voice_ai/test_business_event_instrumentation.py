import pytest
from opentelemetry import trace

from voice_agent.voice_ai.business_event_instrumentation import (
    start_voice_business_span,
)


def test_emits_span_with_common_attributes(business_span_exporter):
    with start_voice_business_span(
        event="call_started",
        call_sid="CA123",
        session_id="sess-1",
        correlation_id="corr-1",
        response_id="resp-1",
    ) as span:
        span.set_attribute("voice_survey.phone_hash", "abc123")

    spans = business_span_exporter.get_finished_spans()
    assert len(spans) == 1
    s = spans[0]
    assert s.name == "voice_survey.business_event"
    assert s.attributes["voice_survey.event"] == "call_started"
    assert s.attributes["call_sid"] == "CA123"
    assert s.attributes["session_id"] == "sess-1"
    assert s.attributes["correlation_id"] == "corr-1"
    assert s.attributes["response_id"] == "resp-1"
    assert s.attributes["voice_survey.phone_hash"] == "abc123"


def test_nests_under_the_active_span(business_span_exporter):
    """One call is one trace: the marker shares the operational span's trace and
    parents to it, rather than starting a root of its own."""
    tracer = trace.get_tracer("test")
    with tracer.start_as_current_span("parent_op") as parent:
        parent_ctx = parent.get_span_context()
        with start_voice_business_span(event="milestone", call_sid="CA1") as biz:
            biz_ctx = biz.get_span_context()
    assert biz_ctx.trace_id == parent_ctx.trace_id
    biz_span = [
        s
        for s in business_span_exporter.get_finished_spans()
        if s.name == "voice_survey.business_event"
    ][0]
    assert biz_span.parent.span_id == parent_ctx.span_id


def test_is_its_own_root_when_no_active_span(business_span_exporter):
    with start_voice_business_span(event="call_started", call_sid="CA1"):
        pass
    biz = [
        s
        for s in business_span_exporter.get_finished_spans()
        if s.name == "voice_survey.business_event"
    ]
    assert len(biz) == 1
    assert biz[0].parent is None


def test_records_exception_and_sets_error_status(business_span_exporter):
    with pytest.raises(ValueError):
        with start_voice_business_span(event="call_started", call_sid="CA1"):
            raise ValueError("boom")
    biz = [
        s
        for s in business_span_exporter.get_finished_spans()
        if s.name == "voice_survey.business_event"
    ]
    assert len(biz) == 1
    assert biz[0].status.status_code.name == "ERROR"
    assert any(ev.name == "exception" for ev in biz[0].events)
