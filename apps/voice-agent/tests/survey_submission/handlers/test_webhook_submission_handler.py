"""Tests for WebhookSubmissionHandler."""

from unittest.mock import Mock, patch
from uuid import uuid4

import pytest
import requests

from voice_agent.survey_submission.handlers.webhook_submission_handler import (
    WebhookSubmissionHandler,
)
from voice_agent.survey_submission.types import (
    FailureKind,
    MilestoneEvent,
    SubmissionResult,
)


WEBHOOK_URL = "https://example.test/hook"
MODULE = "voice_agent.survey_submission.handlers.webhook_submission_handler"


def _make_event(**overrides) -> MilestoneEvent:
    defaults = {
        "event_type": "call_ended",
        "question_id": None,
        "source": None,
        "previous_source": None,
        "all_answers": {"Q1": "yes", "Q2": "no"},
        "response_id": uuid4(),
        "call_sid": "CA123",
        "correlation_id": "corr-1",
    }
    defaults.update(overrides)
    return MilestoneEvent(**defaults)


def _make_handler(**overrides) -> WebhookSubmissionHandler:
    kwargs = {
        "webhook_url": WEBHOOK_URL,
        "response_id": uuid4(),
        "repository": Mock(),
        "token": "",
    }
    kwargs.update(overrides)
    return WebhookSubmissionHandler(
        kwargs.pop("webhook_url"),
        response_id=kwargs.pop("response_id"),
        repository=kwargs.pop("repository"),
        **kwargs,
    )


class TestWebhookSubmissionHandlerSubmit:
    @pytest.mark.asyncio
    async def test_submit_posts_expected_json_and_returns_success(self):
        response_id = uuid4()
        handler = _make_handler(response_id=response_id, token="secret-token")
        event = _make_event(response_id=response_id)

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.raise_for_status = Mock()

        with patch(f"{MODULE}.requests.post", return_value=mock_response) as mock_post:
            result = await handler.submit(event)

        assert result.success is True
        assert result.survey_id == "webhook"
        assert result.failure_kind == FailureKind.NONE
        assert result.data["answer_count"] == 2

        mock_post.assert_called_once()
        _, kwargs = mock_post.call_args
        assert mock_post.call_args[0][0] == WEBHOOK_URL
        assert kwargs["timeout"] == 30.0
        assert kwargs["json"] == {
            "event_type": "call_ended",
            "response_id": str(response_id),
            "survey_id": "webhook",
            "answers": {"Q1": "yes", "Q2": "no"},
            "answer_count": 2,
        }
        assert kwargs["headers"]["Authorization"] == "Bearer secret-token"

    @pytest.mark.asyncio
    async def test_submit_omits_authorization_header_without_token(self):
        handler = _make_handler(token="")
        event = _make_event()

        mock_response = Mock()
        mock_response.status_code = 204
        mock_response.raise_for_status = Mock()

        with patch(f"{MODULE}.requests.post", return_value=mock_response) as mock_post:
            result = await handler.submit(event)

        assert result.success is True
        _, kwargs = mock_post.call_args
        assert "Authorization" not in kwargs["headers"]

    @pytest.mark.asyncio
    async def test_submit_returns_failure_on_network_error(self):
        handler = _make_handler()
        event = _make_event()

        with patch(
            f"{MODULE}.requests.post",
            side_effect=requests.exceptions.ConnectionError("boom"),
        ):
            result = await handler.submit(event)

        assert isinstance(result, SubmissionResult)
        assert result.success is False
        assert result.survey_id == "webhook"
        assert result.failure_kind == FailureKind.BLOCKING
        assert result.error

    @pytest.mark.asyncio
    async def test_submit_returns_failure_on_timeout(self):
        handler = _make_handler()
        event = _make_event()

        with patch(
            f"{MODULE}.requests.post",
            side_effect=requests.exceptions.Timeout(),
        ):
            result = await handler.submit(event)

        assert result.success is False
        assert result.error == "timeout"
        assert result.failure_kind == FailureKind.BLOCKING

    @pytest.mark.asyncio
    async def test_submit_returns_failure_on_non_2xx(self):
        handler = _make_handler()
        event = _make_event()

        mock_response = Mock()
        mock_response.status_code = 500
        http_error = requests.exceptions.HTTPError("500 Server Error")
        http_error.response = mock_response
        mock_response.raise_for_status = Mock(side_effect=http_error)

        with patch(f"{MODULE}.requests.post", return_value=mock_response):
            result = await handler.submit(event)

        assert result.success is False
        assert result.failure_kind == FailureKind.BLOCKING
        assert result.status_code == 500


class TestWebhookSubmissionHandlerTrigger:
    def test_should_trigger_only_on_call_ended(self):
        handler = _make_handler()
        assert handler.should_trigger(_make_event(event_type="call_ended")) is True
        assert (
            handler.should_trigger(_make_event(event_type="question_answered")) is False
        )
        assert (
            handler.should_trigger(_make_event(event_type="source_completed")) is False
        )

    def test_survey_id(self):
        handler = _make_handler()
        assert handler.survey_id() == "webhook"


class TestWebhookSubmissionHandlerFromConfig:
    def test_from_config_reads_url_and_token(self):
        settings = Mock()
        settings.submission_webhook_url = WEBHOOK_URL
        settings.submission_webhook_token = "tok"
        response_id = uuid4()
        repo = Mock()

        handler = WebhookSubmissionHandler.from_config(
            settings, response_id=response_id, repository=repo
        )

        assert handler.webhook_url == WEBHOOK_URL
        assert handler.token == "tok"
        assert handler.response_id == response_id
        assert handler.repository is repo
