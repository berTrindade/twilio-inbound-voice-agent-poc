"""Unit tests for configuration."""

import pytest
from pathlib import Path

from voice_agent.config import Settings


def test_ws_url_returns_correct_format():
    """Test that ws_url property returns correct WebSocket URL format."""
    settings = Settings()
    # Set twilio_ws_domain directly since Settings reads env during class initialization
    settings.twilio_ws_domain = "test-domain.example.com"
    assert settings.ws_url == "wss://test-domain.example.com/ws"


def test_ws_url_fallback_when_twilio_ws_domain_empty():
    """Test that ws_url uses fallback URL when twilio_ws_domain is empty."""
    settings = Settings()
    settings.twilio_ws_domain = ""
    settings.host = "0.0.0.0"
    settings.port = 8080
    settings.environment = "development"
    # Should use localhost fallback
    assert settings.ws_url == "ws://localhost:8080/ws"


def test_ws_url_fallback_when_twilio_ws_domain_not_set():
    """Test that ws_url uses fallback URL when twilio_ws_domain is not set."""
    settings = Settings()
    settings.twilio_ws_domain = ""
    settings.host = "localhost"
    settings.port = 3000
    settings.environment = "development"
    # Should use configured host and port
    assert settings.ws_url == "ws://localhost:3000/ws"


def test_ws_url_uses_localhost_fallback():
    """Test that ws_url falls back to localhost when no domain is configured."""
    settings = Settings()
    settings.twilio_ws_domain = ""
    settings.host = "0.0.0.0"
    settings.port = 8080
    settings.environment = "nonprod"
    # Should fall back to localhost
    assert settings.ws_url == "ws://localhost:8080/ws"


def test_welcome_greeting_has_default_value():
    """Test that welcome_greeting has a default value."""
    settings = Settings()
    assert isinstance(settings.welcome_greeting, str)
    assert len(settings.welcome_greeting) > 0


def test_ws_url_with_different_domains():
    """Test ws_url with various domain formats."""
    test_cases = [
        "example.ngrok.io",
        "abc123.ngrok-free.app",
        "custom-domain.com",
        "voice-agent.example.com",
    ]

    for domain in test_cases:
        settings = Settings()
        # Set twilio_ws_domain directly since Settings reads env during class initialization
        settings.twilio_ws_domain = domain
        expected = f"wss://{domain}/ws"
        assert settings.ws_url == expected


def test_survey_json_path_default_exists():
    """Test that the default survey JSON path exists and is a file."""
    settings = Settings()
    json_path = Path(settings.survey_json_path)

    # Check that the path is absolute or can be resolved
    assert json_path.exists(), f"Survey JSON file not found at {json_path}"
    assert json_path.is_file(), f"Survey JSON path is not a file: {json_path}"
    assert json_path.suffix == ".json", f"Survey file is not a JSON file: {json_path}"


def test_survey_json_path_is_valid_path():
    """Test that the survey JSON path is a valid Path object."""
    settings = Settings()
    json_path = Path(settings.survey_json_path)

    # Verify the path is properly constructed
    assert json_path.name == "demo_survey.json"
    assert "survey_data" in str(json_path)


def test_twilio_public_base_url_from_domain():
    """Public base derives from twilio_ws_domain over https."""
    settings = Settings()
    settings.twilio_ws_domain = "test-domain.example.com"
    assert settings.twilio_public_base_url == "https://test-domain.example.com"


def test_twilio_validate_signature_defaults_true(monkeypatch):
    """Validation is ON by default."""
    monkeypatch.delenv("TWILIO_VALIDATE_SIGNATURE", raising=False)
    settings = Settings()
    assert settings.twilio_validate_signature is True


def test_twilio_validate_signature_forced_on_outside_development():
    """The flag cannot disable validation outside development."""
    settings = Settings()
    settings.environment = "nonprod"
    settings._twilio_validate_signature_flag = False
    assert settings.twilio_validate_signature is True


def test_twilio_validate_signature_respects_flag_in_development():
    """In development the TWILIO_VALIDATE_SIGNATURE flag is honored."""
    settings = Settings()
    settings.environment = "development"
    settings._twilio_validate_signature_flag = False
    assert settings.twilio_validate_signature is False


def test_warn_if_misconfigured_silent_in_development(caplog):
    """Development never raises and emits no Twilio config warnings."""
    settings = Settings()
    settings.environment = "development"
    settings.twilio_auth_token = ""
    settings.twilio_ws_domain = ""
    with caplog.at_level("WARNING"):
        settings.warn_if_misconfigured()
    assert "TWILIO_AUTH_TOKEN" not in caplog.text


def test_warn_if_misconfigured_silent_in_test_environment():
    """'test' is exempt like development so ENVIRONMENT=test CI can import main."""
    settings = Settings()
    settings.environment = "test"
    settings.twilio_auth_token = ""
    settings.twilio_ws_domain = ""
    settings.warn_if_misconfigured()  # no exception == pass


def test_warn_if_misconfigured_raises_when_domain_missing_in_non_dev():
    """Non-development with no TWILIO_WS_DOMAIN fails loud at startup."""
    settings = Settings()
    settings.environment = "prod"
    settings.twilio_auth_token = "tok"
    settings.twilio_ws_domain = ""
    with pytest.raises(RuntimeError, match="TWILIO_WS_DOMAIN is required"):
        settings.warn_if_misconfigured()


def test_warn_if_misconfigured_warns_on_missing_token_but_does_not_raise(caplog):
    """Missing token (with domain set) warns but does not block startup."""
    settings = Settings()
    settings.environment = "nonprod"
    settings.twilio_auth_token = ""
    settings.twilio_ws_domain = "voice-agent.example.com"
    with caplog.at_level("WARNING"):
        settings.warn_if_misconfigured()  # must not raise
    assert "TWILIO_AUTH_TOKEN" in caplog.text


def test_warn_if_misconfigured_clean_when_fully_configured():
    """Fully configured non-development startup neither warns nor raises."""
    settings = Settings()
    settings.environment = "prod"
    settings.twilio_auth_token = "tok"
    settings.twilio_ws_domain = "voice-agent.example.com"
    settings.warn_if_misconfigured()  # no exception == pass
