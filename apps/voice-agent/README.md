# Call runner

FastAPI + WebSocket service that runs voice surveys over Twilio ConversationRelay.

It walks a caller through a JSON survey graph on a live call. A small model
interprets each answer and escalates to a big model when it cannot, the graph
decides every branch deterministically, answers are submitted in the background as
each section completes, and the agent can hand the call to a person over PSTN as a
terminal state. Defaults use no paid services.

Why the seams sit where they do: [docs/architecture.md](../../docs/architecture.md)
and the [ADRs](../../docs/adr/README.md).

## Running it

`make up` from the repository root; [the root README](../../README.md#running-it)
has the rest. Two things specific to this service: migrations run before uvicorn
starts, and the survey named by `SURVEY_JSON_PATH` loads on application startup.
The API is on `http://localhost:8080`.

Without Docker, needing Python 3.13+, Poetry, Postgres 16+ and
[Ollama](https://ollama.com/):

```bash
poetry install
cp env.example .env                                        # every value is already the code default
docker compose -f ../../infra/docker-compose.yml up postgres -d
ollama pull qwen2.5:7b-instruct && ollama pull llama3.1:8b
poetry run alembic upgrade head
poetry run uvicorn voice_agent.main:app --reload --port 8080
```

## Layout

| Path | What is in it |
|------|---------------|
| [api/](src/voice_agent/api/) | HTTP and WebSocket endpoints, Twilio webhooks, signature verification |
| [voice_ai/](src/voice_agent/voice_ai/) | Survey engine, guardrails, LLM handlers, call state, handover |
| [survey_submission/](src/voice_agent/survey_submission/) | Milestone dispatcher and its handlers |
| [models/](src/voice_agent/models/), [repositories/](src/voice_agent/repositories/) | ORM models and data access |
| [alembic/](alembic/) | Migrations |
| [scripts/llm_eval/](scripts/llm_eval/) | Interpreter eval battery, run with `make eval` |

## API

| Route | Notes |
|-------|-------|
| `GET /health` | Health check with active connection count |
| `WS /ws` | One socket per call. `setup`, then `prompt` turns in and `text` out; `interrupt` and `error` share it; `end` closes |
| `POST /twiml` | Returns the TwiML pointing ConversationRelay at `WS /ws` |
| `POST /twiml/session_end` | ConversationRelay session end callback |
| `POST /twiml/coach_whisper` | Whisper played to the coach before bridging |
| `POST /twiml/handoff_result` | Outcome of the PSTN dial |
| `POST /twiml/recording_status` | Recording lifecycle callback |

Every `/twiml` route is behind signature verification, see
[twilio_auth.py](src/voice_agent/api/twilio_auth.py).

## LLM provider

`LLM_PROVIDER` picks the handler in
[llm_handler_factory.py](src/voice_agent/voice_ai/llm_handler_factory.py); an
unrecognised value falls back to `ollama` with a warning. `ollama` calls an
Ollama-compatible API at `OLLAMA_BASE_URL`, which under Compose is Docker Model
Runner rather than Ollama itself. `groq` and `openai` call any OpenAI-compatible API
at `LLM_BASE_URL`. Models come from `SMALL_MODEL_ID` and `BIG_MODEL_ID`.

## Survey submission

Crossing a survey section boundary emits a `MilestoneEvent`, which
`SurveyMilestoneDispatcher` fans out to handlers as fire-and-forget tasks so they
never block the conversation. `LocalSubmissionHandler` records answers to Postgres
when the call ends; `WebhookSubmissionHandler` also POSTs to
`SUBMISSION_WEBHOOK_URL`, and is off by default.

## Database

Two tables. The call runner owns the schema; the dashboard only reads it.

```mermaid
erDiagram
    surveys ||--o{ survey_responses : "answered by"

    surveys {
        uuid        id         PK
        string      title
        string      type       "lookup key, newest version wins"
        jsonb       data       "the question graph, as authored"
        timestamptz created_at
    }

    survey_responses {
        uuid        id                   PK
        uuid        survey_id            FK
        string      participant_phone    "encrypted"
        jsonb       responses            "encrypted, every answer given"
        jsonb       session_metadata     "encrypted, call and handoff state"
        jsonb       integrations         "encrypted, submission payloads"
        string      status               "in_progress, completed or abandoned"
        jsonb       integration_outcomes "plaintext, success per handler"
        int         escalations_count    "plaintext"
        string      last_question_id     "plaintext, drives the drop-off chart"
        string      last_question_text   "plaintext"
        string      call_sid             "indexed, Twilio CallSid"
        timestamptz started_at           "indexed"
        timestamptz completed_at
        timestamptz created_at
    }
```

Three things there are deliberate:

- **Answers are JSONB, not an answers table.** The question graph changes between
  versions, and normalising it would mean a migration per question. The trade is
  that answers cannot be queried in SQL.
- **The plaintext columns are projections of the encrypted ones.** Everything
  carrying what a caller said is AES-256-GCM with a per-row nonce, so no index over
  it could ever serve a lookup. The dashboard still has to count and group, so the
  few non-identifying facts it aggregates on are written alongside in the clear.
- **Six indexes, each with a query behind it.** `idx_sr_started_at` carries every
  dashboard list and chart, `ix_survey_responses_call_sid` serves the
  recording-status callback, `ix_survey_responses_survey_id` keeps the foreign key
  indexed, `idx_survey_type_created` finds the current survey, plus two primary
  keys. Five more were dropped after a measured dashboard pass at 200k rows showed
  they were never scanned, see
  [`f6a7b8c9d0e1`](alembic/versions/f6a7b8c9d0e1_drop_unused_columns_and_indexes.py).

```bash
poetry run alembic revision --autogenerate -m "description"   # create
poetry run alembic upgrade head                               # apply
poetry run alembic downgrade -1                               # roll back
```

Example calls are optional and separate from the survey itself.
[`scripts/demo_data.py`](src/voice_agent/scripts/demo_data.py) writes 400 across the
last 45 days through the same encryption helpers and JSONB shapes a live call
produces. It is deterministic and idempotent, and every row carries a `CAdemo` call
SID where a real call carries a Twilio one, which is how the dashboard labels them
and how `--clear` finds them. `make seed` and `make unseed` are the manual
equivalents; `make up` seeds automatically.

## Testing

```bash
poetry run pytest                                          # or `make test` from the root
poetry run pytest --cov=voice_agent --cov-report=term-missing
poetry run pytest -m live                                  # excluded by default, hits real services
poetry run black .
```

## Environment variables

Defaults are the ones in [config.py](src/voice_agent/config.py), which is what you
get outside Docker.

| Variable | Description | Default |
|----------|-------------|---------|
| `DATABASE_URL` | PostgreSQL connection string | `postgresql://survey_user:survey_pass@localhost:5432/survey_db` |
| `VOICE_AGENT_HOST` | Server host | `0.0.0.0` |
| `VOICE_AGENT_PORT` | Server port | `8080` |
| `ENVIRONMENT` | Environment name | `development` |
| `LOG_LEVEL` | Log level (debug, info, warning, error) | `info` |
| `LOG_STYLE` | Log format (`text` or `json`) | `text` in development, `json` elsewhere |
| `SENSITIVE_LOGGING_ENABLED` | Gates log lines carrying personal data and caller content (user and assistant text, survey answers). Set to `true` only for local debugging | `false` |
| `ENCRYPTION_KEY` | Optional base64 key for encrypting stored personal data at rest. Unset means pass-through | empty |
| `LLM_PROVIDER` | LLM provider (`ollama`, `groq` or `openai`) | `ollama` |
| `OLLAMA_BASE_URL` | Ollama-compatible server URL, used when `LLM_PROVIDER=ollama` | `http://localhost:11434` |
| `OLLAMA_TIMEOUT_SECONDS` | Timeout for a single model call | `60` |
| `SMALL_MODEL_ID` | Small (interpreter) model id | `qwen2.5:7b-instruct` |
| `BIG_MODEL_ID` | Big (escalation) model id | `llama3.1:8b` |
| `LLM_BASE_URL` | OpenAI-compatible endpoint, used when the provider is `groq` or `openai` | `https://api.groq.com/openai/v1` |
| `LLM_API_KEY` | Key for that endpoint. `GROQ_API_KEY` is read as a fallback | empty |
| `SURVEY_JSON_PATH` | Path to a survey JSON graph. A bare filename resolves inside `src/voice_agent/survey_data/` | `src/voice_agent/survey_data/demo_survey.json` |
| `INITIAL_NODE_ID` | First node in the survey graph | `WELCOME_V1` |
| `TWILIO_WS_DOMAIN` | Public hostname Twilio reaches. Hostname only, no scheme and no path. Required outside development | empty |
| `TWILIO_AUTH_TOKEN` | Twilio auth token, used to verify webhook signatures | empty |
| `COACH_HANDOFF_ENABLED` | Whether a handover dials the coach over PSTN. When false the handover message is spoken and the survey continues | `true` |
| `COACH_PHONE_NUMBER` | Number dialled on handover | empty |
| `OTEL_SERVICE_NAME` | OpenTelemetry service name | `voice-agent` |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | OTLP collector endpoint. Empty turns trace, metric and log export off | empty |

Under Compose the defaults differ, and Compose wins because it sets the variables in
the container: `OLLAMA_BASE_URL=http://model-runner.docker.internal`,
`OLLAMA_TIMEOUT_SECONDS=120`, `SMALL_MODEL_ID=ai/qwen2.5:7B-Q4_K_M`,
`BIG_MODEL_ID=ai/llama3.1:8B-Q4_K_M`, `COACH_HANDOFF_ENABLED=false`. The root `.env`
overrides those in turn.
