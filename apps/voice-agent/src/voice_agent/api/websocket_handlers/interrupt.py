"""Handler for the Twilio 'interrupt' message."""

import logging
from typing import Any, Dict

from ..session_context import SessionContext
from ..websocket_helpers import sanitize_for_log

logger = logging.getLogger(__name__)


def handle_interrupt_message(msg: Dict[str, Any], ctx: SessionContext) -> None:
    """Handle a Twilio 'interrupt' message (barge-in)."""
    if ctx.call_state_manager:
        try:
            ctx.call_state_manager.record_interruption()
        except Exception as e:
            logger.error(f"Error recording interruption: {e}", exc_info=True)

    logger.info(
        "Interruption received for call",
        extra={
            "correlation_id": sanitize_for_log(ctx.correlation_id),
            "call_sid": sanitize_for_log(ctx.call_sid),
            "message_type": "interrupt",
        },
    )
