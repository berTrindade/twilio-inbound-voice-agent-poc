"""Structured logging with JSON format for Datadog integration."""

import os
import json
import logging
from datetime import datetime, UTC

from ..config import settings


SENSITIVE_KEYS = frozenset(
    {
        # Free-form user/assistant text
        "user_text",
        "user_message",
        "assistant_message",
        "combined_user_text",
        "voice_prompt",
        "assistant_text",
        # Survey answers and model output
        "big_model_raw_value",
        "raw_llm_response",
        "normalized",
        "small_resp",
        "big_resp",
        "val_res",
        "answers",
        "answer_value",
        "question_text",
        # Address and identity
        "address",
        "street",
        "city",
        "address_state",
        "postal_code",
        "first_name",
        "last_name",
        "raw_dob",
        "dob",
        "phone",
        "email",
        # Misc fields that can carry personal data
        "raw_weekday",
        "raw_weekend",
        "response_body_preview",
        "address_partial",
    }
)

REDACTED = "<redacted>"


class SensitiveLoggingFilter(logging.Filter):
    """Replaces known personal-data keys with '<redacted>' unless SENSITIVE_LOGGING_ENABLED is true.

    Centralises redaction so call sites can pass personal data through `extra={...}` without
    inline flag checks. New sensitive fields are added once to SENSITIVE_KEYS.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        if settings.sensitive_logging_enabled:
            return True
        for key in SENSITIVE_KEYS:
            if hasattr(record, key):
                setattr(record, key, REDACTED)
        return True


class JsonFormatter(logging.Formatter):
    """JSON formatter for structured logging compatible with Datadog."""

    def format(self, record):
        """Format log record as JSON."""
        log_record = {
            "timestamp": datetime.now(UTC).isoformat() + "Z",
            "level": record.levelname,
            "message": record.getMessage(),
            "name": record.name,
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        if record.exc_info:
            log_record["exc_info"] = self.formatException(record.exc_info)

        # Include any extra fields passed via the 'extra' parameter
        # Exclude reserved logging attributes to avoid duplicates
        reserved_attrs = {
            "name",
            "msg",
            "args",
            "created",
            "filename",
            "funcName",
            "levelname",
            "levelno",
            "lineno",
            "module",
            "msecs",
            "message",
            "pathname",
            "process",
            "processName",
            "relativeCreated",
            "thread",
            "threadName",
            "exc_info",
            "exc_text",
            "stack_info",
            "asctime",
        }

        for key, value in record.__dict__.items():
            if key not in reserved_attrs:
                log_record[key] = value

        return json.dumps(log_record)


# Global flag to ensure logging is only configured once
_logging_configured = False


def setup_logging(level: str = None, fmt: str = None, datefmt: str = None):
    """
    Configure logging with JSON format for production and text format for development.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        fmt: Format string (unused for JSON format)
        datefmt: Date format (unused for JSON format)

    Returns:
        Root logger instance
    """
    global _logging_configured

    # Only configure logging once globally
    if _logging_configured:
        return logging.getLogger()

    level_str = level or os.getenv("LOG_LEVEL", "INFO")
    environment = os.getenv("ENVIRONMENT", "local")

    logger = logging.getLogger()
    for noisy in [
        "urllib3",
        "s3transfer",
        "python_multipart",
        "python_multipart.multipart",
        "voice_agent.voice_ai.call_state_manager",  # Temporarily silenced for the demo
    ]:
        logging.getLogger(noisy).setLevel(logging.WARNING)
    logger.setLevel(level_str.upper())

    # Prevent duplicate handlers - only add if no handlers exist
    if not logger.handlers:
        log_handler = logging.StreamHandler()

        log_style = os.getenv(
            "LOG_STYLE", "text" if environment == "local" else "json"
        ).lower()

        if log_style == "json":
            log_format = JsonFormatter()
        elif log_style == "text":
            log_format = logging.Formatter(
                fmt="%(asctime)s %(name)s %(levelname)s %(message)s",
                datefmt=datefmt or "%Y-%m-%d %H:%M:%S",
            )
        else:
            raise ValueError(f"Invalid log style: {log_style}")

        log_handler.setFormatter(log_format)
        # Attach filter to the handler so it runs on every record routed
        # to it, including records propagated from child loggers.
        log_handler.addFilter(SensitiveLoggingFilter())
        logger.addHandler(log_handler)

        _logging_configured = True

    return logger
