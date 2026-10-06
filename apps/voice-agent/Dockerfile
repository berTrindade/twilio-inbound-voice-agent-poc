# Multi-stage Dockerfile for voice-agent

# Stage 1: Builder
FROM python:3.14.3-slim AS builder

WORKDIR /build

# Install poetry
RUN pip install --no-cache-dir poetry==1.8.3

# Copy project files
COPY apps/voice-agent/pyproject.toml apps/voice-agent/poetry.lock /build/

# Export requirements and install into system Python
RUN poetry export -f requirements.txt --only main --without-hashes -o /requirements.txt && \
    pip install --no-cache-dir -r /requirements.txt

# Stage 2: Runtime
FROM python:3.14.3-slim

WORKDIR /app

# Copy installed packages from builder's system Python
COPY --from=builder /usr/local/lib/python3.14/site-packages /usr/local/lib/python3.14/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application code
COPY apps/voice-agent/src/voice_agent /app/voice_agent

# Copy Alembic configuration and migrations
COPY apps/voice-agent/alembic.ini /app/alembic.ini
COPY apps/voice-agent/alembic /app/alembic

# Create non-root user
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

# Expose port
EXPOSE 8080

# Health check, over urllib so the image needs no curl
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/health')" || exit 1

CMD ["python", "-m", "uvicorn", "voice_agent.main:app", "--host", "0.0.0.0", "--port", "8080"]
