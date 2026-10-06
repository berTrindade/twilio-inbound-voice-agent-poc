"""Handler for unknown Twilio message types."""

import logging
from typing import Any, Dict

from ..session_context import SessionContext
from ..websocket_helpers import sanitize_for_log

logger = logging.getLogger(__name__)


def handle_unknown_message(msg: Dict[str, Any], ctx: SessionContext) -> None:
    """Handle an unknown Twilio message type."""
    mtype = msg.get("type", "unknown")
    logger.warning(
        "Unknown message type received",
        extra={
            "correlation_id": sanitize_for_log(ctx.correlation_id),
            "call_sid": sanitize_for_log(ctx.call_sid),
            "message_type": sanitize_for_log(mtype),
        },
    )
