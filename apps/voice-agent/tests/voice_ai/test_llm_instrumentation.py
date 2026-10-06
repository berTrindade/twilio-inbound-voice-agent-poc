"""Tests for OTel `gen_ai.*` instrumentation on voice-ai LLM and guardrail calls."""

import json
from unittest.mock import MagicMock, patch

import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from voice_agent.voice_ai.ollama_llm_handler import OllamaLLMHandler
from voice_agent.voice_ai.llm_instrumentation import start_voice_llm_span


_EXPORTER = InMemorySpanExporter()


@pytest.fixture(scope="module", autouse=True)
def _install_test_tracer_provider():
    """Attach an in-memory exporter to the live TracerProvider.

    OTel's `set_tracer_provider` is one-shot — subsequent calls are silently
    rejected. So we install a SDK-backed provider only when the global is still
    the no-op default; otherwise we just register our exporter on whatever is
    already there. Either way, the exporter is shared across tests in this
    module and cleared between them.
    """
    current = trace.get_tracer_provider()
    if not isinstance(current, TracerProvider):
        provider = TracerProvider()
        trace.set_tracer_provider(provider)
        current = provider
    current.add_span_processor(SimpleSpanProcessor(_EXPORTER))
    yield


@pytest.fixture
def span_exporter():
    _EXPORTER.clear()
    yield _EXPORTER
    _EXPORTER.clear()


def _attrs(span):
    return dict(span.attributes)


def _llm_handler():
    settings = MagicMock()
    settings.ollama_base_url = "http://localhost:11434"
    settings.ollama_timeout_seconds = 60
    settings.small_model_id = "test-small-model"
    settings.big_model_id = "test-big-model"
    return OllamaLLMHandler(settings)


def _ollama_response(payload):
    """Build a fake requests.Response carrying an Ollama /api/chat payload."""
    resp = MagicMock()
    resp.raise_for_status.return_value = None
    resp.json.return_value = payload
    return resp


# ---------------------------------------------------------------------------
# start_voice_llm_span
# ---------------------------------------------------------------------------


class TestStartVoiceLLMSpan:
    def test_sets_gen_ai_attributes_on_entry(self, span_exporter):
        with start_voice_llm_span(
            "voice_ai.llm.test",
            model="claude-haiku",
            call_sid="CA123",
            correlation_id="corr-1",
            session_id="sess-1",
        ):
            pass

        finished = span_exporter.get_finished_spans()
        assert len(finished) == 1
        attrs = _attrs(finished[0])
        assert attrs["gen_ai.operation.name"] == "chat"
        assert attrs["gen_ai.provider.name"] == "ollama"
        assert attrs["gen_ai.request.model"] == "claude-haiku"
        assert attrs["call_sid"] == "CA123"
        assert attrs["correlation_id"] == "corr-1"
        assert attrs["session_id"] == "sess-1"
        assert attrs["voice_survey.contains_user_content"] == "true"

    def test_nests_under_active_parent(self, span_exporter):
        outer_tracer = trace.get_tracer("test.outer")
        with outer_tracer.start_as_current_span("invoke_agent voice_survey") as parent:
            parent_trace = parent.get_span_context().trace_id
            with start_voice_llm_span("voice_ai.llm.test", model="m") as inner:
                inner_trace = inner.get_span_context().trace_id
        assert inner_trace == parent_trace, "LLM span must nest under the turn parent"

    def test_is_valid_span_when_no_active_parent(self, span_exporter):
        with start_voice_llm_span("voice_ai.llm.test", model="m") as inner:
            assert inner.get_span_context().is_valid

    def test_records_exception_and_sets_error_status(self, span_exporter):
        with pytest.raises(ValueError):
            with start_voice_llm_span("voice_ai.llm.test", model="m"):
                raise ValueError("boom")
        llm_span = span_exporter.get_finished_spans()[0]
        assert llm_span.status.status_code.name == "ERROR"
        assert any(ev.name == "exception" for ev in llm_span.events)


# ---------------------------------------------------------------------------
# OllamaLLMHandler async wrappers — gen_ai.usage.* attributes
# ---------------------------------------------------------------------------


class TestAsyncWrapperSpanAttributes:
    @pytest.mark.asyncio
    async def test_small_model_async_sets_usage_from_chat_response(self, span_exporter):
        handler = _llm_handler()
        chat_payload = {
            "message": {
                "content": json.dumps(
                    {
                        "interpretation": "answer",
                        "answer": "yes",
                        "reply": "OK",
                        "confidence": 0.9,
                    }
                )
            },
            "prompt_eval_count": 17,
            "eval_count": 23,
            "done_reason": "end_turn",
        }

        with patch(
            "voice_agent.voice_ai.ollama_llm_handler.requests.post",
            return_value=_ollama_response(chat_payload),
        ):
            await handler.call_small_model_async(
                "system",
                "user",
                call_sid="CA1",
                correlation_id="c1",
                session_id="s1",
            )

        spans = span_exporter.get_finished_spans()
        llm = next(s for s in spans if s.name == "voice_ai.llm.small_model")
        attrs = _attrs(llm)
        assert attrs["gen_ai.usage.input_tokens"] == 17
        assert attrs["gen_ai.usage.output_tokens"] == 23
        assert attrs["gen_ai.response.finish_reasons"] == ("end_turn",)
        assert attrs["call_sid"] == "CA1"
        assert "input.value" in attrs
        assert "output.value" in attrs

    @pytest.mark.asyncio
    async def test_big_model_async_sets_usage_from_chat_response(self, span_exporter):
        handler = _llm_handler()
        chat_payload = {
            "message": {"content": json.dumps({"action": "say", "text": "hi"})},
            "prompt_eval_count": 42,
            "eval_count": 7,
            "done_reason": "stop_sequence",
        }

        with patch(
            "voice_agent.voice_ai.ollama_llm_handler.requests.post",
            return_value=_ollama_response(chat_payload),
        ):
            await handler.call_big_model_async("system", "user", call_sid="CA2")

        spans = span_exporter.get_finished_spans()
        llm = next(s for s in spans if s.name == "voice_ai.llm.big_model")
        attrs = _attrs(llm)
        assert attrs["gen_ai.usage.input_tokens"] == 42
        assert attrs["gen_ai.usage.output_tokens"] == 7
        assert attrs["gen_ai.response.finish_reasons"] == ("stop_sequence",)
        assert attrs["call_sid"] == "CA2"

    @pytest.mark.asyncio
    async def test_async_wrapper_returns_dict_unchanged_when_called_with_defaults(
        self, span_exporter
    ):
        handler = _llm_handler()
        chat_payload = {
            "message": {"content": json.dumps({"action": "clarify"})},
            "prompt_eval_count": 1,
            "eval_count": 2,
            "done_reason": "end_turn",
        }

        with patch(
            "voice_agent.voice_ai.ollama_llm_handler.requests.post",
            return_value=_ollama_response(chat_payload),
        ):
            result = await handler.call_big_model_async("system", "user")
        # The dict result still has the existing public keys.
        assert result["action"] == "clarify"
        # And carries instrumentation-only keys for downstream span use.
        assert result["_usage"] == {"inputTokens": 1, "outputTokens": 2}
        assert result["_stop_reason"] == "end_turn"


def test_gen_ai_provider_tracks_the_configured_provider(monkeypatch):
    """The span must never claim a provider the call did not use."""
    from voice_agent.config import settings
    from voice_agent.voice_ai.llm_instrumentation import gen_ai_provider_attrs

    for provider, expected in [
        ("ollama", "ollama"),
        ("groq", "groq"),
        ("openai", "openai"),
        ("GROQ", "groq"),
        # create_llm_handler falls back to ollama, so the span must agree.
        ("wat", "ollama"),
    ]:
        monkeypatch.setattr(settings, "llm_provider", provider)
        attrs = gen_ai_provider_attrs()
        # semconv v1.37.0 name and the deprecated one must never disagree.
        assert attrs == {"gen_ai.provider.name": expected, "gen_ai.system": expected}
