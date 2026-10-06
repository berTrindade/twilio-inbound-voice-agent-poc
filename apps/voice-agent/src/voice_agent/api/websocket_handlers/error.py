"""Handler for the Twilio 'error' message."""

import logging
from typing import Any, Dict

from ..session_context import SessionContext
from ..websocket_helpers import sanitize_for_log

logger = logging.getLogger(__name__)


def handle_error_message(msg: Dict[str, Any], ctx: SessionContext) -> None:
    """Handle a Twilio 'error' message."""
    logger.warning(
        "Twilio error",
        extra={
            "correlation_id": sanitize_for_log(ctx.correlation_id),
            "call_sid": sanitize_for_log(ctx.call_sid),
            "message_type": "error",
            "description": sanitize_for_log(msg.get("description")),
        },
    )
