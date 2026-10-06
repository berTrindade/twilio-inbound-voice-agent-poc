"""Metrics collection for the call runner: WebSocket connections and system health."""

import os
import psutil
import logging
from opentelemetry import metrics
from typing import Optional

logger = logging.getLogger(__name__)


def sanitize_for_log(value):
    """Sanitize any value to prevent log injection attacks.

    Removes carriage returns, newlines, tabs, and unicode line/paragraph
    separators that could be used to inject fake log entries into log
    aggregation systems. Also handles None values safely.
    """
    if value is None:
        return "<null>"
    val_str = str(value)
    return (
        val_str.replace("\r", "")
        .replace("\n", "")
        .replace("\t", "")
        .replace("\u2028", "")
        .replace("\u2029", "")
    )


def _sanitize_dict_strings(d):
    """Sanitize all string values in a dictionary using sanitize_for_log.

    This helps prevent log injection attacks when dict values are logged.
    """
    if not isinstance(d, dict):
        return d
    return {k: (sanitize_for_log(v) if isinstance(v, str) else v) for k, v in d.items()}


class MetricsCollector:
    """Collects and exports metrics for the call runner."""

    def __init__(self):
        """Initialize metrics collector."""
        self.meter = metrics.get_meter("voice-agent")

        # WebSocket metrics
        # UpDownCounter, not Counter: concurrency goes down as well as up, and a
        # Counter can only ever climb.
        self.active_websocket_connections = self.meter.create_up_down_counter(
            "survey.websocket.connections.active",
            description="Number of active WebSocket connections",
            unit="1",
        )

        self.websocket_connection_total = self.meter.create_counter(
            "survey.websocket.connections.total",
            description="Total WebSocket connections established",
            unit="1",
        )

        self.websocket_disconnections_total = self.meter.create_counter(
            "survey.websocket.disconnections.total",
            description="Total WebSocket disconnections",
            unit="1",
        )

        # Message metrics
        self.websocket_messages_received = self.meter.create_counter(
            "survey.websocket.messages.received",
            description="Total WebSocket messages received",
            unit="1",
        )

        self.websocket_messages_sent = self.meter.create_counter(
            "survey.websocket.messages.sent",
            description="Total WebSocket messages sent",
            unit="1",
        )

        # Error metrics
        self.websocket_errors_total = self.meter.create_counter(
            "survey.websocket.errors.total",
            description="Total WebSocket errors",
            unit="1",
        )

        # Processing time
        self.message_processing_time = self.meter.create_histogram(
            "survey.message.processing.duration",
            description="Time taken to process WebSocket messages",
            unit="ms",
        )

        # System metrics
        self.cpu_usage = self.meter.create_gauge(
            "survey.system.cpu.usage",
            description="CPU usage percentage",
            unit="%",
        )

        self.memory_usage = self.meter.create_gauge(
            "survey.system.memory.usage",
            description="Memory usage percentage",
            unit="%",
        )

        self.process_memory_rss = self.meter.create_gauge(
            "survey.process.memory.rss",
            description="Process resident set size",
            unit="bytes",
        )

    def record_connection_opened(self, attributes: dict = None):
        """Record a WebSocket connection opened."""
        self.websocket_connection_total.add(1, attributes or {})
        self.active_websocket_connections.add(1, attributes or {})
        safe_attributes = _sanitize_dict_strings(attributes or {})
        logger.debug(
            "WebSocket connection opened", extra={"attributes": safe_attributes}
        )

    def record_connection_closed(self, attributes: dict = None):
        """Record a WebSocket connection closed."""
        self.websocket_disconnections_total.add(1, attributes or {})
        self.active_websocket_connections.add(-1, attributes or {})
        safe_attributes = _sanitize_dict_strings(attributes or {})
        logger.debug(
            "WebSocket connection closed", extra={"attributes": safe_attributes}
        )

    def record_message_received(self, attributes: dict = None):
        """Record a WebSocket message received."""
        self.websocket_messages_received.add(1, attributes or {})

    def record_message_sent(self, attributes: dict = None):
        """Record a WebSocket message sent."""
        self.websocket_messages_sent.add(1, attributes or {})

    def record_message_processing_time(
        self, duration_ms: float, attributes: dict = None
    ):
        """Record message processing time."""
        self.message_processing_time.record(duration_ms, attributes or {})

    def record_error(self, error_type: str, attributes: dict = None):
        """Record a WebSocket error."""
        attrs = attributes or {}
        attrs["error_type"] = error_type
        self.websocket_errors_total.add(1, attrs)
        safe_error_type = sanitize_for_log(str(error_type)[:100]) if error_type else ""
        safe_attrs = _sanitize_dict_strings(attrs)
        logger.warning(
            "WebSocket error recorded",
            extra={"error_type": safe_error_type, "attributes": safe_attrs},
        )

    def update_system_metrics(self):
        """Update system resource metrics."""
        try:
            cpu_percent = psutil.cpu_percent(interval=0.1)
            memory_percent = psutil.virtual_memory().percent
            process = psutil.Process(os.getpid())
            process_memory_rss = process.memory_info().rss

            self.cpu_usage.set(cpu_percent)
            self.memory_usage.set(memory_percent)
            self.process_memory_rss.set(process_memory_rss)

            logger.debug(
                "System metrics updated",
                extra={
                    "cpu_percent": cpu_percent,
                    "memory_percent": memory_percent,
                    "process_memory_rss": process_memory_rss,
                },
            )
        except Exception as e:
            logger.error(f"Failed to update system metrics: {e}", exc_info=True)


# Global metrics collector instance
_metrics_collector: Optional[MetricsCollector] = None


def get_metrics_collector() -> MetricsCollector:
    """Get the global metrics collector instance."""
    global _metrics_collector
    if _metrics_collector is None:
        _metrics_collector = MetricsCollector()
    return _metrics_collector
