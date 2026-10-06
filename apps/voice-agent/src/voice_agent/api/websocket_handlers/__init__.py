"""WebSocket message handlers package."""

from typing import Any, Callable, Dict

from .setup import handle_setup_message
from .interrupt import handle_interrupt_message
from .error import handle_error_message
from .unknown import handle_unknown_message
from ..session_context import SessionContext

HANDLER_REGISTRY: Dict[str, Callable[[Dict[str, Any], SessionContext], None]] = {
    "interrupt": handle_interrupt_message,
    "error": handle_error_message,
}

__all__ = [
    "handle_setup_message",
    "handle_interrupt_message",
    "handle_error_message",
    "handle_unknown_message",
    "HANDLER_REGISTRY",
    "SessionContext",
]
