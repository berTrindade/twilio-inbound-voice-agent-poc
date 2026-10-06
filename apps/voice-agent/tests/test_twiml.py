"""Unit tests for TwiML endpoints."""

import json
import pytest
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient

from voice_agent.main import app
from voice_agent.voice_ai.handoff_state import (
    HandoffContext,
    get_handoff,
    set_handoff,
)


@pytest.fixture
def client():
    """Create a test client.

    These tests exercise endpoint behavior, not Twilio auth; bypass signature
    validation via FastAPI dependency override (auth is covered in
    tests/test_twilio_auth.py).
    """
    from voice_agent.api.twilio_auth import verify_twilio_signature

    app.dependency_overrides[verify_twilio_signature] = lambda: None
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def mock_settings_with_domain():
    """Mock settings with twilio_ws_domain configured."""
    with patch("voice_agent.api.twiml.settings") as mock_settings:
        mock_settings.twilio_ws_domain = "test-domain.example.com"
        mock_settings.welcome_greeting = "Test greeting"
        mock_settings.language = "en-US"
        mock_settings.voice = "Ruth-Neural"
        mock_settings.coach_phone_number = ""
        mock_settings.coach_dial_timeout_seconds = 20
        type(mock_settings).ws_url = property(
            lambda self: "wss://test-domain.example.com/ws"
        )
        yield mock_settings


@pytest.fixture
def mock_settings_without_domain():
    """Mock settings without twilio_ws_domain configured."""
    with patch("voice_agent.api.twiml.settings") as mock_settings:
        mock_settings.twilio_ws_domain = ""
        mock_settings.welcome_greeting = "Test greeting"
        mock_settings.language = "en-US"
        mock_settings.voice = "Ruth-Neural"
        mock_settings.host = "localhost"
        mock_settings.port = 8080
        mock_settings.environment = "development"
        mock_settings.coach_phone_number = ""
        mock_settings.coach_dial_timeout_seconds = 20
        type(mock_settings).ws_url = property(lambda self: "ws://localhost:8080/ws")
        yield mock_settings


@pytest.fixture
def mock_settings_with_coach_phone():
    """Mock settings with coach phone number configured."""
    with patch("voice_agent.api.twiml.settings") as mock_settings:
        mock_settings.twilio_ws_domain = "test-domain.example.com"
        mock_settings.welcome_greeting = "Test greeting"
        mock_settings.language = "en-US"
        mock_settings.voice = "Ruth-Neural"
        mock_settings.coach_phone_number = "+15551234567"
        mock_settings.coach_dial_timeout_seconds = 20
        type(mock_settings).ws_url = property(
            lambda self: "wss://test-domain.example.com/ws"
        )
        yield mock_settings


# ---------------------------------------------------------------------------
# /twiml — ConversationRelay
# ---------------------------------------------------------------------------


def test_twiml_endpoint_returns_valid_xml(client, mock_settings_with_domain):
    """Test that TwiML endpoint returns valid XML with correct format."""
    response = client.post("/twiml")

    assert response.status_code == 200
    assert response.headers["content-type"] == "text/xml; charset=utf-8"

    content = response.text
    assert '<?xml version="1.0" encoding="UTF-8"?>' in content
    assert "<Response>" in content
    assert "<Connect" in content
    assert "<ConversationRelay" in content
    assert 'url="wss://test-domain.example.com/ws"' in content
    assert 'welcomeGreeting="Test greeting"' in content


def test_twiml_endpoint_includes_correct_ws_url(client, mock_settings_with_domain):
    """Test that TwiML includes the correct WebSocket URL."""
    response = client.post("/twiml")

    assert response.status_code == 200
    assert "wss://test-domain.example.com/ws" in response.text


def test_twiml_endpoint_includes_welcome_greeting(client, mock_settings_with_domain):
    """Test that TwiML includes the welcome greeting."""
    response = client.post("/twiml")

    assert response.status_code == 200
    assert 'welcomeGreeting="Test greeting"' in response.text


def test_twiml_endpoint_works_without_domain(client, mock_settings_without_domain):
    """Test that TwiML endpoint works without TWILIO_WS_DOMAIN using fallback URL."""
    response = client.post("/twiml")

    assert response.status_code == 200
    assert response.headers["content-type"] == "text/xml; charset=utf-8"
    content = response.text
    assert "<Response>" in content
    assert "<ConversationRelay" in content
    assert 'url="ws://localhost:8080/ws"' in content


def test_twiml_includes_action_on_connect(client, mock_settings_with_domain):
    """Test that <Connect> includes action pointing to session_end (not ConversationRelay)."""
    response = client.post("/twiml")

    assert response.status_code == 200
    content = response.text
    assert 'action="/twiml/session_end"' in content
    # action must be on <Connect>, not on <ConversationRelay>
    connect_index = content.index("<Connect")
    relay_index = content.index("<ConversationRelay")
    action_index = content.index('action="/twiml/session_end"')
    assert connect_index < action_index < relay_index


def test_twiml_endpoint_xml_structure(client, mock_settings_with_domain):
    """Test that TwiML has correct XML structure."""
    response = client.post("/twiml")

    assert response.status_code == 200
    content = response.text

    assert content.startswith('<?xml version="1.0" encoding="UTF-8"?>')
    assert "<Response>" in content
    assert "</Response>" in content
    assert "<Connect" in content
    assert "</Connect>" in content
    assert "<ConversationRelay" in content


# ---------------------------------------------------------------------------
# /twiml/session_end
# ---------------------------------------------------------------------------


def test_session_end_hangs_up_on_normal_completion(client, mock_settings_with_domain):
    """Normal survey completion (no HandoffData) → <Hangup/>."""
    response = client.post("/twiml/session_end", data={"CallSid": "CA123"})

    assert response.status_code == 200
    assert "<Hangup" in response.text
    assert "<Dial" not in response.text


def test_session_end_returns_dial_on_coach_handoff(
    client, mock_settings_with_coach_phone
):
    """Coach handoff with phone configured → <Dial> with <Number>."""
    handoff_data = json.dumps({"mode": "coach_handoff", "callSid": "CA123"})
    response = client.post(
        "/twiml/session_end",
        data={"CallSid": "CA123", "HandoffData": handoff_data},
    )

    assert response.status_code == 200
    content = response.text
    assert "<Dial" in content
    assert "<Number" in content
    assert "+15551234567" in content
    assert 'url="/twiml/coach_whisper"' in content
    assert 'action="/twiml/handoff_result"' in content
    assert "timeout" in content


def test_session_end_hangs_up_when_phone_not_configured(
    client, mock_settings_with_domain
):
    """Coach handoff requested but COACH_PHONE_NUMBER not set → <Hangup/>."""
    mock_settings_with_domain.coach_phone_number = ""
    handoff_data = json.dumps({"mode": "coach_handoff"})
    response = client.post(
        "/twiml/session_end",
        data={"CallSid": "CA123", "HandoffData": handoff_data},
    )

    assert response.status_code == 200
    assert "<Hangup" in response.text
    assert "<Dial" not in response.text


def test_session_end_handles_malformed_handoff_data(client, mock_settings_with_domain):
    """Malformed HandoffData → treated as normal completion → <Hangup/>."""
    response = client.post(
        "/twiml/session_end",
        data={"CallSid": "CA123", "HandoffData": "not-valid-json"},
    )

    assert response.status_code == 200
    assert "<Hangup" in response.text


def test_session_end_cleans_up_handoff_context(
    client, mock_settings_with_domain, handoff_store
):
    """session_end pops handoff context from store on normal completion."""
    handoff_store("CA123")
    set_handoff(
        HandoffContext(
            call_sid="CA123",
            whisper_text="test",
            resume_snapshot={},
        )
    )
    assert get_handoff("CA123") is not None

    client.post("/twiml/session_end", data={"CallSid": "CA123"})

    assert get_handoff("CA123") is None


# ---------------------------------------------------------------------------
# /twiml/coach_whisper
# ---------------------------------------------------------------------------


def test_coach_whisper_returns_say_twiml(
    client, mock_settings_with_domain, handoff_store
):
    """coach_whisper returns <Say> TwiML with the stored whisper text."""
    handoff_store("CA456")
    set_handoff(
        HandoffContext(
            call_sid="CA456",
            whisper_text="Please verify name and email.",
            resume_snapshot={},
        )
    )

    response = client.post("/twiml/coach_whisper", data={"CallSid": "CA456"})

    assert response.status_code == 200
    content = response.text
    assert "<Say>" in content
    assert "Please verify name and email." in content
    assert "<Dial" not in content


def test_coach_whisper_uses_generic_text_when_no_context(
    client, mock_settings_with_domain
):
    """coach_whisper falls back to generic message when no context is stored."""
    response = client.post("/twiml/coach_whisper", data={"CallSid": "CA_UNKNOWN"})

    assert response.status_code == 200
    content = response.text
    assert "<Say>" in content
    assert "handoff" in content.lower()


def test_coach_whisper_does_not_bridge_audio_to_caller(
    client, mock_settings_with_domain
):
    """coach_whisper returns only <Say>, never <Dial> (user must not hear it)."""
    response = client.post("/twiml/coach_whisper", data={"CallSid": "CA456"})

    assert "<Dial" not in response.text
    assert "<Connect" not in response.text


# ---------------------------------------------------------------------------
# /twiml/handoff_result
# ---------------------------------------------------------------------------


def test_handoff_result_hangs_up_on_completed(client, mock_settings_with_domain):
    """Successful bridge (DialCallStatus=completed) → clean hangup."""
    response = client.post(
        "/twiml/handoff_result",
        data={"CallSid": "CA789", "DialCallStatus": "completed"},
    )

    assert response.status_code == 200
    assert "<Hangup" in response.text
    assert "<Say>" not in response.text


def test_handoff_result_says_message_on_no_answer(client, mock_settings_with_domain):
    """Coach no-answer → <Say> + <Hangup/>."""
    response = client.post(
        "/twiml/handoff_result",
        data={"CallSid": "CA789", "DialCallStatus": "no-answer"},
    )

    assert response.status_code == 200
    content = response.text
    assert "<Say>" in content
    assert "<Hangup" in content
    assert "coach" in content.lower() or "unable" in content.lower()


def test_handoff_result_says_message_on_busy(client, mock_settings_with_domain):
    """Coach busy → <Say> + <Hangup/>."""
    response = client.post(
        "/twiml/handoff_result",
        data={"CallSid": "CA789", "DialCallStatus": "busy"},
    )

    assert response.status_code == 200
    assert "<Say>" in response.text
    assert "<Hangup" in response.text


def test_handoff_result_says_message_on_failed(client, mock_settings_with_domain):
    """Coach call failed → <Say> + <Hangup/>."""
    response = client.post(
        "/twiml/handoff_result",
        data={"CallSid": "CA789", "DialCallStatus": "failed"},
    )

    assert response.status_code == 200
    assert "<Say>" in response.text
    assert "<Hangup" in response.text


def test_handoff_result_cleans_up_handoff_context(
    client, mock_settings_with_domain, handoff_store
):
    """handoff_result always pops the handoff context from store."""
    handoff_store("CA789")
    set_handoff(
        HandoffContext(
            call_sid="CA789",
            whisper_text="test",
            resume_snapshot={},
        )
    )
    assert get_handoff("CA789") is not None

    client.post(
        "/twiml/handoff_result",
        data={"CallSid": "CA789", "DialCallStatus": "completed"},
    )

    assert get_handoff("CA789") is None


# ---------------------------------------------------------------------------
# send_end() unit tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_send_end_sends_end_type():
    """send_end sends {type: 'end'} without handoff_data."""
    from voice_agent.voice_ai.twilio_protocol import send_end

    mock_ws = AsyncMock()
    await send_end(mock_ws)

    mock_ws.send_text.assert_called_once()
    sent = json.loads(mock_ws.send_text.call_args[0][0])
    assert sent == {"type": "end"}


@pytest.mark.asyncio
async def test_send_end_serializes_handoff_data_as_json_string():
    """send_end serializes handoff_data as a JSON string (Twilio requirement)."""
    from voice_agent.voice_ai.twilio_protocol import send_end

    mock_ws = AsyncMock()
    await send_end(mock_ws, handoff_data={"mode": "coach_handoff", "callSid": "CA123"})

    mock_ws.send_text.assert_called_once()
    outer = json.loads(mock_ws.send_text.call_args[0][0])
    assert outer["type"] == "end"
    # handoffData must be a JSON string, not a dict
    assert isinstance(outer["handoffData"], str)
    inner = json.loads(outer["handoffData"])
    assert inner["mode"] == "coach_handoff"
    assert inner["callSid"] == "CA123"


@pytest.mark.asyncio
async def test_send_end_does_not_raise_on_ws_error():
    """send_end swallows WebSocket exceptions gracefully."""
    from voice_agent.voice_ai.twilio_protocol import send_end

    mock_ws = AsyncMock()
    mock_ws.send_text.side_effect = RuntimeError("connection lost")

    # Should not raise
    await send_end(mock_ws, handoff_data={"mode": "coach_handoff"})


# ---------------------------------------------------------------------------
# build_dial_twiml — callerId
# ---------------------------------------------------------------------------


def test_build_dial_twiml_includes_caller_id_when_provided():
    """<Dial> contains callerId attribute when caller_id is passed."""
    from voice_agent.voice_ai.twilio_protocol import build_dial_twiml

    response = build_dial_twiml(
        coach_number="+15559990000",
        whisper_url="/twiml/coach_whisper",
        dial_action_url="/twiml/handoff_result",
        caller_id="+15551112222",
    )

    assert 'callerId="+15551112222"' in response.body.decode()


def test_build_dial_twiml_omits_caller_id_when_not_provided():
    """<Dial> does NOT contain callerId when caller_id is omitted."""
    from voice_agent.voice_ai.twilio_protocol import build_dial_twiml

    response = build_dial_twiml(
        coach_number="+15559990000",
        whisper_url="/twiml/coach_whisper",
        dial_action_url="/twiml/handoff_result",
    )

    assert "callerId" not in response.body.decode()


def test_session_end_passes_caller_id_from_handoff_context(
    client, mock_settings_with_coach_phone, handoff_store
):
    """session_end includes callerId in <Dial> when participant_phone is stored."""
    handoff_store("CA_PHONE_TEST")
    set_handoff(
        HandoffContext(
            call_sid="CA_PHONE_TEST",
            whisper_text="Hello coach",
            resume_snapshot={},
            participant_phone="+15558887777",
        )
    )
    handoff_data = json.dumps({"mode": "coach_handoff", "callSid": "CA_PHONE_TEST"})
    response = client.post(
        "/twiml/session_end",
        data={"CallSid": "CA_PHONE_TEST", "HandoffData": handoff_data},
    )

    assert response.status_code == 200
    assert 'callerId="+15558887777"' in response.text


def test_session_end_dial_has_no_caller_id_without_handoff_context(
    client, mock_settings_with_coach_phone
):
    """session_end omits callerId when no handoff context is stored."""
    handoff_data = json.dumps({"mode": "coach_handoff", "callSid": "CA_NO_CTX"})
    response = client.post(
        "/twiml/session_end",
        data={"CallSid": "CA_NO_CTX", "HandoffData": handoff_data},
    )

    assert response.status_code == 200
    assert "<Dial" in response.text
    assert "callerId" not in response.text
