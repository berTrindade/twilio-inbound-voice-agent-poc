"""Unit tests for Twilio webhook signature validation."""

import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient
from twilio.request_validator import RequestValidator

from voice_agent.main import app

TOKEN = "test_auth_token_123"
BASE = "https://test-domain.example.com"


@pytest.fixture
def auth_client():
    """TestClient with NO dependency override — real validation runs."""
    # Ensure no stale override from other test modules leaks in.
    app.dependency_overrides.clear()
    yield TestClient(app)
    app.dependency_overrides.clear()


def _patch_settings(*, token=TOKEN, validate=True, environment="nonprod", base=BASE):
    """Patch the settings object the dependency reads."""
    p = patch("voice_agent.api.twilio_auth.settings")
    mock = p.start()
    mock.twilio_auth_token = token
    mock.twilio_validate_signature = validate
    mock.environment = environment
    mock.twilio_public_base_url = base
    return p, mock


def _sign(path, params):
    return RequestValidator(TOKEN).compute_signature(f"{BASE}{path}", params)


def test_valid_signature_passes_all_endpoints(auth_client):
    """A correctly-signed request reaches every TwiML endpoint."""
    p, _ = _patch_settings()
    try:
        cases = [
            ("/twiml", {}),
            ("/twiml/session_end", {"CallSid": "CA1"}),
            ("/twiml/coach_whisper", {"CallSid": "CA1"}),
            (
                "/twiml/handoff_result",
                {"CallSid": "CA1", "DialCallStatus": "completed"},
            ),
        ]
        for path, params in cases:
            sig = _sign(path, params)
            r = auth_client.post(path, data=params, headers={"X-Twilio-Signature": sig})
            assert r.status_code == 200, f"{path} -> {r.status_code}"
    finally:
        p.stop()


def test_missing_signature_header_rejected(auth_client):
    """No X-Twilio-Signature header → 403."""
    p, _ = _patch_settings()
    try:
        r = auth_client.post("/twiml/session_end", data={"CallSid": "CA1"})
        assert r.status_code == 403
    finally:
        p.stop()


def test_wrong_token_signature_rejected(auth_client):
    """Signature computed with a different token → 403."""
    p, _ = _patch_settings()
    try:
        bad_sig = RequestValidator("some_other_token").compute_signature(
            f"{BASE}/twiml/session_end", {"CallSid": "CA1"}
        )
        r = auth_client.post(
            "/twiml/session_end",
            data={"CallSid": "CA1"},
            headers={"X-Twilio-Signature": bad_sig},
        )
        assert r.status_code == 403
    finally:
        p.stop()


def test_tampered_params_rejected(auth_client):
    """Params changed after signing → 403."""
    p, _ = _patch_settings()
    try:
        sig = _sign("/twiml/session_end", {"CallSid": "CA1"})
        r = auth_client.post(
            "/twiml/session_end",
            data={"CallSid": "CA_TAMPERED"},
            headers={"X-Twilio-Signature": sig},
        )
        assert r.status_code == 403
    finally:
        p.stop()


def test_signature_against_internal_host_rejected_then_public_passes(auth_client):
    """Regression guard for the ingress-host bug.

    A signature computed against the internal host fails; the same request
    signed against the configured public base succeeds.
    """
    p, _ = _patch_settings()
    try:
        params = {"CallSid": "CA1"}
        internal_sig = RequestValidator(TOKEN).compute_signature(
            "http://internal-svc:8080/twiml/session_end", params
        )
        r1 = auth_client.post(
            "/twiml/session_end",
            data=params,
            headers={"X-Twilio-Signature": internal_sig},
        )
        assert r1.status_code == 403

        public_sig = _sign("/twiml/session_end", params)
        r2 = auth_client.post(
            "/twiml/session_end",
            data=params,
            headers={"X-Twilio-Signature": public_sig},
        )
        assert r2.status_code == 200
    finally:
        p.stop()


def test_dev_bypass_allows_unsigned(auth_client):
    """validate=false + development → unsigned request passes."""
    p, _ = _patch_settings(validate=False, environment="development")
    try:
        r = auth_client.post("/twiml/session_end", data={"CallSid": "CA1"})
        assert r.status_code == 200
    finally:
        p.stop()


def test_bypass_flag_ignored_outside_development(auth_client):
    """validate=false + staging → flag ignored, unsigned request still 403."""
    p, _ = _patch_settings(validate=False, environment="staging")
    try:
        r = auth_client.post("/twiml/session_end", data={"CallSid": "CA1"})
        assert r.status_code == 403
    finally:
        p.stop()


def test_missing_token_while_required_returns_500(auth_client):
    """Token unset while validation required → 500 (cannot validate)."""
    p, _ = _patch_settings(token="", validate=True, environment="nonprod")
    try:
        r = auth_client.post("/twiml/session_end", data={"CallSid": "CA1"})
        assert r.status_code == 500
    finally:
        p.stop()
