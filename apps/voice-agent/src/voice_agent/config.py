"""Configuration for the voice-agent application."""

import os
import logging
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
# Look for .env file in the app root directory (2 levels up from this file)
env_path = Path(__file__).parent.parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

logger = logging.getLogger(__name__)


def _resolve_survey_path(value: str) -> str:
    """Demo seam: allow a profile to name a survey by bare filename.

    A value with no path separator (e.g. ``acme.json``) resolves to the bundled
    ``survey_data`` directory so demo profiles stay portable across machines and
    containers. Full paths are returned unchanged for backward compatibility.
    """
    if "/" in value or "\\" in value:
        return value
    return str(Path(__file__).parent / "survey_data" / value)


class Settings:
    """Application settings."""

    # Server Configuration
    host: str = os.getenv("VOICE_AGENT_HOST", "0.0.0.0")
    port: int = int(os.getenv("VOICE_AGENT_PORT", "8080"))
    ai_voice_agent_log_level: str = os.getenv("VOICE_AGENT_LOG_LEVEL", "info").lower()
    sql_echo: bool = os.getenv("SQL_ECHO", "false").lower() == "true"

    # Application Environment
    environment: str = os.getenv("ENVIRONMENT", "development")

    # Gates personal-data log lines (user/assistant text, survey answers).
    sensitive_logging_enabled: bool = (
        os.getenv("SENSITIVE_LOGGING_ENABLED", "false").lower() == "true"
    )

    # Database Configuration
    database_url: str = os.getenv(
        "DATABASE_URL", "postgresql://survey_user:survey_pass@localhost:5432/survey_db"
    )

    # -------------------------
    # Twilio / Voice Configuration
    # -------------------------
    # Existing ConversationRelay domain + welcome text
    twilio_ws_domain: str = os.getenv("TWILIO_WS_DOMAIN", "")
    # Twilio webhook signature validation
    twilio_auth_token: str = os.getenv("TWILIO_AUTH_TOKEN", "")
    # Raw TWILIO_VALIDATE_SIGNATURE flag (default ON). Read via the
    # twilio_validate_signature property, which forces validation on outside
    # development so it cannot be disabled in staging/prod.
    _twilio_validate_signature_flag: bool = (
        os.getenv("TWILIO_VALIDATE_SIGNATURE", "true").lower() == "true"
    )
    welcome_greeting: str = os.getenv(
        "WELCOME_GREETING",
        "Hi, I'm your assistant. Let's get started.",
    )
    welcome_greeting_interruptible: str = "none"

    # New: TTS/STT voice + language for ConversationRelay
    voice: str = os.getenv("VOICE", "XrExE9yKIg1WjnnlVkGX")
    language: str = os.getenv("LANGUAGE", "en-US")
    tts_provider: str = os.getenv("TTS_PROVIDER", "ElevenLabs")
    transcription_provider: str = os.getenv("TRANSCRIPTION_PROVIDER", "Deepgram")
    transcription_language: str = os.getenv("TRANSCRIPTION_LANGUAGE", "en-US")
    speech_model: str = os.getenv("SPEECH_MODEL", "nova-3-general")
    transcription_hints: str = os.getenv(
        "TRANSCRIPTION_HINTS",
        "yes,no,phone,web,A,B,C,D,E,F,G,I,email,address,mornings,afternoons,evenings",
    )
    # Deepgram Smart Format (ConversationRelay)
    deepgram_smart_format: bool = (
        os.getenv("DEEPGRAM_SMART_FORMAT", "false").lower() == "true"
    )

    # -------------------------
    # Twilio Voice Recording Configuration
    # -------------------------
    # Controls whether TwiML should start call audio recording before
    # connecting the call to ConversationRelay.
    #
    # Note: Twilio Console external S3 storage controls where recordings are stored.
    # This flag controls whether recordings are actually started for calls.
    twilio_recording_enabled: bool = (
        os.getenv("TWILIO_RECORDING_ENABLED", "false").lower() == "true"
    )

    # Space-separated callback events. Twilio sends only "completed" by default
    # if this is omitted, but including these helps with observability/testing.
    # Supported values include: in-progress, completed, absent
    twilio_recording_status_callback_event: str = os.getenv(
        "TWILIO_RECORDING_STATUS_CALLBACK_EVENT",
        "in-progress completed absent",
    )

    # Recording name only needs to be unique per call. This is mainly useful
    # if we later want to stop the recording explicitly via <Stop><Recording>.
    twilio_recording_name: str = os.getenv(
        "TWILIO_RECORDING_NAME",
        "voice_ai_recording",
    )

    # Record both sides of the call. Twilio defaults are usually "both" and
    # "dual", but we keep these configurable for clarity and QA/prod tuning.
    twilio_recording_track: str = os.getenv("TWILIO_RECORDING_TRACK", "both")
    twilio_recording_channels: str = os.getenv("TWILIO_RECORDING_CHANNELS", "dual")

    # -------------------------
    # LLM Configuration
    # -------------------------
    # Which LLM backend to use: "ollama" (default, free/local) or "groq"/"openai"
    # (any OpenAI-compatible API, e.g. Groq's free tier — best for hosted demos
    # since it needs no GPU).
    llm_provider: str = os.getenv("LLM_PROVIDER", "ollama")
    # Local Ollama server (OpenAI-free). Run `ollama serve` + pull the models.
    ollama_base_url: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    ollama_timeout_seconds: float = float(os.getenv("OLLAMA_TIMEOUT_SECONDS", "60"))
    # OpenAI-compatible provider (used when llm_provider in {"groq", "openai"}).
    # Defaults to Groq's endpoint; set LLM_API_KEY (or GROQ_API_KEY) + Groq model
    # ids via SMALL_MODEL_ID / BIG_MODEL_ID.
    llm_base_url: str = os.getenv("LLM_BASE_URL", "https://api.groq.com/openai/v1")
    llm_api_key: str = os.getenv("LLM_API_KEY", "") or os.getenv("GROQ_API_KEY", "")
    # -------------------------
    # Optional generic webhook target for completed surveys. When
    # SUBMISSION_WEBHOOK_URL is set, the local build also POSTs a JSON envelope
    # of the collected answers here when the call ends. Empty by default
    # (local-only, no external calls).
    submission_webhook_url: str = os.getenv("SUBMISSION_WEBHOOK_URL", "")
    submission_webhook_token: str = os.getenv("SUBMISSION_WEBHOOK_TOKEN", "")

    # Defaults target local Ollama models. Override per provider via env.
    small_model_id: str = os.getenv(
        "SMALL_MODEL_ID",
        "qwen2.5:7b-instruct",
    )
    big_model_id: str = os.getenv(
        "BIG_MODEL_ID",
        "llama3.1:8b",
    )

    # -------------------------
    # Survey configuration
    # -------------------------
    survey_json_path: str = _resolve_survey_path(
        os.getenv(
            "SURVEY_JSON_PATH",
            str(Path(__file__).parent / "survey_data" / "demo_survey.json"),
        )
    )
    initial_node_id: str = os.getenv(
        "INITIAL_NODE_ID",
        "WELCOME_V1",
    )

    # Adjustment applied to estimated final TTS playback time (seconds).
    # Can be positive or negative.
    tts_estimate_adjustment_seconds: float = float(
        os.getenv("TTS_ESTIMATE_ADJUSTMENT_SECONDS", "0")
    )

    # -------------------------
    # PSTN Coach Handoff Configuration
    # -------------------------
    coach_phone_number: str = os.getenv("COACH_PHONE_NUMBER") or ""
    coach_dial_timeout_seconds: int = int(os.getenv("COACH_DIAL_TIMEOUT_SECONDS", "70"))
    # Off by default, and Compose pins it off too. When false the handover
    # message is spoken but the PSTN dial is skipped and the survey continues.
    # Defaulting it on would hang up on the caller whenever no number is set.
    coach_handoff_enabled: bool = (
        os.getenv("COACH_HANDOFF_ENABLED", "false").lower() == "true"
    )

    # -------------------------
    @property
    def ws_url(self) -> str:
        """Get WebSocket URL for Twilio ConversationRelay."""
        if self.twilio_ws_domain:
            return f"wss://{self.twilio_ws_domain}/ws"
        # Fallback to public URL for non-prod environment
        # For local development, use localhost
        if self.environment == "development" and self.host in (
            "0.0.0.0",
            "localhost",
            "127.0.0.1",
        ):
            host = "localhost"
            return f"ws://{host}:{self.port}/ws"
        # Default to localhost when no domain is configured
        return f"ws://localhost:{self.port}/ws"

    @property
    def twilio_validate_signature(self) -> bool:
        """Whether Twilio X-Twilio-Signature validation is active.

        Forced on outside development so the TWILIO_VALIDATE_SIGNATURE bypass
        can never disable validation in staging/prod. In development it follows
        the flag (default on). verify_twilio_signature also re-checks the
        environment as defense in depth.
        """
        if self.environment != "development":
            return True
        return self._twilio_validate_signature_flag

    @property
    def twilio_public_base_url(self) -> str:
        """Public HTTPS base that Twilio signed against (scheme + host, no path)."""
        # Twilio-signed requests are always signed with a real Twilio URL, so
        # there is no need for a fallback URL. The public host comes from
        # TWILIO_WS_DOMAIN, which warn_if_misconfigured() requires in non-dev.
        return f"https://{self.twilio_ws_domain}"

    @property
    def twilio_recording_status_callback_url(self) -> str:
        """Public callback URL for Twilio recording lifecycle events."""
        if not self.twilio_ws_domain:
            return ""
        return f"{self.twilio_public_base_url}/twiml/recording_status"

    def warn_if_misconfigured(self) -> None:
        """Validate Twilio signature-validation config at app startup.

        Call AFTER logging is configured so messages route through the
        structured logger. Outside development/test the signature check is
        always active (the bypass flag is ignored), so its inputs must be present:

        - Missing TWILIO_AUTH_TOKEN -> every webhook is rejected with HTTP 500.
          Warn so the gap is visible at boot (per-request 500 still applies).
        - Missing TWILIO_WS_DOMAIN -> twilio_public_base_url has no host, so the
          reconstructed URL never matches and genuine Twilio requests are
          rejected with HTTP 403. Fail loud at startup instead of shipping a
          silent outage.

        "test" is exempt alongside "development" (CI may set ENVIRONMENT=test,
        and warn_if_misconfigured runs at import time via main.py), matching the
        non-production set.
        """
        if self.environment in ("development", "test"):
            return

        if not self.twilio_auth_token:
            logger.warning(
                "TWILIO_AUTH_TOKEN not set - Twilio webhook requests will be "
                "rejected with HTTP 500 until it is configured",
                extra={"environment": self.environment},
            )

        if not self.twilio_ws_domain:
            raise RuntimeError(
                f"TWILIO_WS_DOMAIN is required when environment={self.environment!r} "
                "but is not set. Twilio signature validation reconstructs the signed "
                "URL from this host; without it the host is empty, so every genuine "
                "webhook is rejected with HTTP 403. Set TWILIO_WS_DOMAIN to the public "
                "ingress host for this environment."
            )


settings = Settings()
