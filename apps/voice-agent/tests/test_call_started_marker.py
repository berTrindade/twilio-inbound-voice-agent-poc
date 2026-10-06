"""Tests for voice_survey.call_started business event marker."""

import base64
import os
from unittest.mock import patch

import pytest

from voice_agent.api.websocket_handlers.setup import emit_call_started_marker
from voice_agent.utils.encryption import _reset_key, hmac_hash

# Deterministic 32-byte key shared with test_encryption.py
TEST_KEY = base64.b64encode(b"0123456789abcdef0123456789abcdef").decode()

TEST_PHONE = "+15551234567"


@pytest.fixture(autouse=True)
def configure_encryption_key():
    """Set a known ENCRYPTION_KEY so hmac_hash produces keyed HMAC output."""
    _reset_key()
    with patch.dict(os.environ, {"ENCRYPTION_KEY": TEST_KEY}):
        yield
    _reset_key()


def test_call_started_marker_attributes(business_span_exporter):
    emit_call_started_marker(
        call_sid="CA1",
        session_id="sess-1",
        correlation_id="corr-1",
        response_id="resp-1",
        participant_phone=TEST_PHONE,
    )
    spans = [
        s
        for s in business_span_exporter.get_finished_spans()
        if s.attributes.get("voice_survey.event") == "call_started"
    ]
    assert len(spans) == 1
    a = spans[0].attributes
    assert a["call_sid"] == "CA1"
    assert a["response_id"] == "resp-1"
    phone_hash = a["voice_survey.phone_hash"]
    # keyed HMAC-SHA256 → 64-char hex
    assert isinstance(phone_hash, str) and len(phone_hash) == 64
    # raw phone and its digits must not appear in the hash
    assert "+1555" not in phone_hash
    assert "5551234567" not in phone_hash
    # must delegate to hmac_hash (same key → same digest)
    assert phone_hash == hmac_hash(TEST_PHONE)


def test_call_started_marker_hashes_consistently(business_span_exporter):
    emit_call_started_marker(
        call_sid="CA1",
        session_id="s1",
        correlation_id="c1",
        response_id="r1",
        participant_phone=TEST_PHONE,
    )
    emit_call_started_marker(
        call_sid="CA2",
        session_id="s2",
        correlation_id="c2",
        response_id="r2",
        participant_phone=TEST_PHONE,
    )
    spans = [
        s
        for s in business_span_exporter.get_finished_spans()
        if s.attributes.get("voice_survey.event") == "call_started"
    ]
    assert (
        spans[0].attributes["voice_survey.phone_hash"]
        == spans[1].attributes["voice_survey.phone_hash"]
    )


def test_call_started_marker_empty_phone_yields_empty_hash(business_span_exporter):
    emit_call_started_marker(
        call_sid="CA1",
        session_id="s1",
        correlation_id="c1",
        response_id="r1",
        participant_phone="",
    )
    spans = [
        s
        for s in business_span_exporter.get_finished_spans()
        if s.attributes.get("voice_survey.event") == "call_started"
    ]
    assert spans[0].attributes["voice_survey.phone_hash"] == ""
