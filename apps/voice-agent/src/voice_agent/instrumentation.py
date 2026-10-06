"""
OpenTelemetry instrumentation setup for the call runner.
This module must be imported before other modules to ensure proper instrumentation.
"""

import logging
import os

from opentelemetry import metrics, trace
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import (
    ConsoleMetricExporter,
    PeriodicExportingMetricReader,
)
from opentelemetry._logs import set_logger_provider
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from opentelemetry.sdk.resources import SERVICE_NAME, SERVICE_VERSION, Resource
from opentelemetry.semconv.resource import ResourceAttributes

# Import logging setup
from voice_agent.utils.logger import setup_logging

# Configure logging - respect LOG_LEVEL environment variable
log_level = os.getenv("LOG_LEVEL", "INFO").upper()
logger = setup_logging(level=log_level)

# Try to import OTLP exporters
try:
    from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import (
        OTLPMetricExporter,
    )
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter

    OTLP_AVAILABLE = True
except ImportError:
    logger.warning(
        "⚠️  OTLP exporters not available - telemetry will use console export"
    )
    OTLP_AVAILABLE = False

# Import instrumentation libraries
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.asyncio import AsyncioInstrumentor
from opentelemetry.instrumentation.requests import RequestsInstrumentor
from opentelemetry.instrumentation.urllib3 import URLLib3Instrumentor


def initialize_opentelemetry():
    """Initialize OpenTelemetry instrumentation for the call runner."""
    # Check if providers are already initialized
    tracer_provider = trace.get_tracer_provider()
    meter_provider = metrics.get_meter_provider()

    # Check if SDK providers are already set
    if hasattr(tracer_provider, "shutdown") and hasattr(meter_provider, "shutdown"):
        logger.info("🔭 OpenTelemetry already initialized")
        return tracer_provider, meter_provider

    # Create resource with service information
    resource = Resource.create(
        {
            SERVICE_NAME: os.getenv("OTEL_SERVICE_NAME", "voice-agent"),
            SERVICE_VERSION: os.getenv("OTEL_SERVICE_VERSION", "0.1.0"),
            ResourceAttributes.SERVICE_NAMESPACE: "voice_agent",
            ResourceAttributes.DEPLOYMENT_ENVIRONMENT: os.getenv(
                "ENVIRONMENT", "development"
            ),
        }
    )

    # Configure trace provider
    trace_provider = TracerProvider(resource=resource)

    # Configure trace exporters based on environment variables
    traces_console = os.getenv("OTEL_TRACES_CONSOLE", "false").lower() == "true"
    otlp_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
    span_processors = []

    # Add console trace exporter if enabled
    if traces_console:
        console_trace_exporter = ConsoleSpanExporter()
        console_span_processor = BatchSpanProcessor(console_trace_exporter)
        span_processors.append(console_span_processor)
        logger.info("🔭 Using console trace exporter")

    # Add OTLP trace exporter if endpoint is set (for Datadog in production)
    if OTLP_AVAILABLE and otlp_endpoint:
        try:
            otlp_trace_exporter = OTLPSpanExporter(
                endpoint=otlp_endpoint, insecure=True
            )
            otlp_span_processor = BatchSpanProcessor(otlp_trace_exporter)
            span_processors.append(otlp_span_processor)
            logger.info(f"🔭 Using OTLP trace exporter: {otlp_endpoint}")
        except Exception as e:
            logger.warning(f"⚠️  Failed to setup OTLP trace exporter: {e}")

    # Add all span processors to trace provider
    for span_processor in span_processors:
        trace_provider.add_span_processor(span_processor)

    if not span_processors:
        logger.info(
            "🔭 Traces export disabled (set OTEL_TRACES_CONSOLE=true or OTEL_EXPORTER_OTLP_ENDPOINT to enable)"
        )

    trace.set_tracer_provider(trace_provider)

    # Configure metrics provider
    metrics_console = os.getenv("OTEL_METRICS_CONSOLE", "false").lower() == "true"
    metric_readers = []

    # Add console metrics exporter if enabled
    if metrics_console:
        console_metrics_exporter = ConsoleMetricExporter()
        console_metrics_reader = PeriodicExportingMetricReader(console_metrics_exporter)
        metric_readers.append(console_metrics_reader)
        logger.info("🔭 Using console metrics exporter")

    # Add OTLP metrics exporter if endpoint is set (for Datadog in production)
    if OTLP_AVAILABLE and otlp_endpoint:
        try:
            otlp_metrics_exporter = OTLPMetricExporter(
                endpoint=otlp_endpoint, insecure=True
            )
            otlp_metrics_reader = PeriodicExportingMetricReader(otlp_metrics_exporter)
            metric_readers.append(otlp_metrics_reader)
            logger.info(f"🔭 Using OTLP metrics exporter: {otlp_endpoint}")
        except Exception as e:
            logger.warning(f"⚠️  Failed to setup OTLP metrics exporter: {e}")

    meter_provider = MeterProvider(
        resource=resource,
        metric_readers=metric_readers,
    )

    if not metric_readers:
        logger.info(
            "🔭 Metrics export disabled (set OTEL_METRICS_CONSOLE=true or OTEL_EXPORTER_OTLP_ENDPOINT to enable)"
        )

    metrics.set_meter_provider(meter_provider)

    # Configure logs provider. Without this the Loki pipeline receives nothing,
    # because the app only ever wrote to stdout.
    if OTLP_AVAILABLE and otlp_endpoint:
        try:
            logger_provider = LoggerProvider(resource=resource)
            logger_provider.add_log_record_processor(
                BatchLogRecordProcessor(
                    OTLPLogExporter(endpoint=otlp_endpoint, insecure=True)
                )
            )
            set_logger_provider(logger_provider)
            # On the root logger so every module exports. A record emitted inside
            # a span carries that span's trace_id, which is what lets you pivot
            # from a slow turn to the log lines it produced.
            logging.getLogger().addHandler(
                LoggingHandler(
                    level=getattr(logging, log_level, logging.INFO),
                    logger_provider=logger_provider,
                )
            )
            logger.info(f"🔭 Using OTLP log exporter: {otlp_endpoint}")
        except Exception as e:
            logger.warning(f"⚠️  Failed to setup OTLP log exporter: {e}")
    else:
        logger.info(
            "🔭 Logs export disabled (set OTEL_EXPORTER_OTLP_ENDPOINT to enable)"
        )

    # Instrument libraries
    try:
        FastAPIInstrumentor().instrument()
        logger.info("🔭 FastAPI instrumentation enabled")
    except Exception as e:
        logger.warning(f"⚠️  Failed to instrument FastAPI: {e}")

    try:
        AsyncioInstrumentor().instrument()
        logger.info("🔭 AsyncIO instrumentation enabled")
    except Exception as e:
        logger.warning(f"⚠️  Failed to instrument AsyncIO: {e}")

    try:
        RequestsInstrumentor().instrument()
        logger.info("🔭 Requests instrumentation enabled")
    except Exception as e:
        logger.warning(f"⚠️  Failed to instrument Requests: {e}")

    try:
        URLLib3Instrumentor().instrument()
        logger.info("🔭 URLLib3 instrumentation enabled")
    except Exception as e:
        logger.warning(f"⚠️  Failed to instrument URLLib3: {e}")

    logger.info("✅ OpenTelemetry initialized successfully")

    return trace_provider, meter_provider
