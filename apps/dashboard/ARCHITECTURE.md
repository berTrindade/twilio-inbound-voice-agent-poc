# Dashboard architecture

> A walkthrough of how the dashboard is built and how its pieces fit together.

---

## What this is

The dashboard shows what happened on voice survey calls, and lets you drive a call
yourself from the browser. It connects directly to the same PostgreSQL database the
call runner writes to, reads the JSONB columns, and presents them as stats, charts,
conversation transcripts and integration health.

It is built with Next.js 16 (App Router) and uses server components for almost
everything. There is no API layer between the dashboard and the database: server
components query PostgreSQL directly through the `postgres` npm package.

---

## Routes

| Route | Component type | Description |
|-------|---------------|-------------|
| `/` | Server | Stats cards (today against yesterday, this week against last, completion rate, average duration, active calls, escalation rate, integration health) and a paginated, sortable response list with status, date range and duration filters |
| `/responses/[id]` | Server | Call overview, integration status cards with the request and response payloads, and the full conversation transcript with per-turn LLM interpretation and confidence |
| `/analytics` | Server | Five charts (volume by day, completion trend, dropoff by question, average confidence by question, integration health) with a 7 / 14 / 30 / 90 day window selector |
| `/chat` | Client | Browser client that runs a whole call against the call runner without a phone. See below |

There is no authentication. This is a POC and the dashboard is meant to be run
locally. Anything hosted publicly should sit behind whatever access control the
host provides.

---

## Browser chat client (`/chat`)

This is the quickest way to exercise the system end to end, and the fastest thing to
reach for when reviewing it. It opens a WebSocket straight to the call runner's `/ws`
endpoint, the same endpoint Twilio ConversationRelay connects to, and speaks the same
message protocol. No phone number, no tunnel, no Twilio account.

On connect it sends `{"type": "setup", "callSid": "web-client-<timestamp>"}`. The
runner treats that exactly as it treats a real call: it creates the survey response
row, initialises call state, and speaks the welcome plus the first question back as
`{"type": "text", "token": ...}` frames. Each thing you type goes back as
`{"type": "prompt", "voicePrompt": "...", "last": true}`, which is the ConversationRelay
shape for a finished caller utterance.

That means a browser session goes through the real turn pipeline: the small model
classifies the turn, the outcome handlers run, the question engine walks the graph
and branches, answers are validated and persisted, and the submission dispatcher fires
at the end. The call then shows up at `/` and `/responses/[id]` like any other, which
is why the same route backs the end to end test.

The client is in [app/chat/page.tsx](app/chat/page.tsx) and
[components/VoiceChat.tsx](components/VoiceChat.tsx). It also uses the browser's own
Web Speech API for input and output, so in Chrome or Edge you can speak answers and
hear the replies, with no paid speech services involved. Both are optional: the mic
button only appears when the browser supports recognition, and spoken replies can be
toggled off. Connection state, the session id and the WebSocket URL in use are shown
in the header.

### Which WebSocket URL it uses

[app/chat/WsConfig.ts](app/chat/WsConfig.ts) decides, based on whether the page URL
carries a query string at all. The value of the query string is not inspected.

| Condition | WebSocket URL |
|-----------|---------------|
| The page URL has any query string | `ws://localhost:8080/ws`, ignoring `NEXT_PUBLIC_WS_URL` |
| No query string | `NEXT_PUBLIC_WS_URL` if set, otherwise `ws://localhost:8080/ws` |

The two only differ once `NEXT_PUBLIC_WS_URL` points somewhere other than localhost,
which is the case the query string escape hatch exists for.

Under Docker Compose, `NEXT_PUBLIC_WS_URL` is set to `ws://localhost:8080/ws` in
[infra/docker-compose.yml](../../infra/docker-compose.yml), because the browser
reaches the runner on the host rather than over the compose network.

### Visibility

`SHOW_CHAT=true` shows the `/chat` link in the navigation
([components/DashboardHeader.tsx](components/DashboardHeader.tsx)). The route itself
is always reachable.

---

## Data flow

The dashboard has no API layer of its own. Server components call query functions
directly, which execute SQL against PostgreSQL.

```mermaid
flowchart LR
    Page["Page (Server Component)"] --> Query["database/queries.ts"]
    Query --> Pool["database/db.ts<br/>(postgres connection pool)"]
    Pool --> DB[("PostgreSQL")]
    DB --> Pool
    Pool --> Query
    Query --> Page
    Page --> Component["Client Component<br/>(charts, filters, accordions)"]
```

### Query files

| File | What it holds |
|------|----------------|
| [database/queries.ts](database/queries.ts) | Stats, paginated list, detail by id, and the five analytics queries |
| [database/db.ts](database/db.ts) | Connection pool setup (`max: 10`, `idle_timeout: 20`, `connect_timeout: 10`) and the row types that mirror the database schema |

### Safety guards

Every exported function in [database/queries.ts](database/queries.ts) is wrapped in
try/catch and returns a safe empty value on failure (`[]`, `0`, `null`, or a zeroed
stats object). Errors are logged with a `[DB]` prefix. This exists because the
dashboard has to survive environments where the database is not reachable, such as
the Docker image build, which builds against a dummy `DATABASE_URL`. Do not remove
these guards. They are what keeps `next build` and Playwright from crashing.

### Analytics queries

[`getAnalyticsData`](database/queries.ts) fires five queries through `Promise.all()`:

1. Volume by day. Counts by status (completed, abandoned, in_progress) grouped by date.
2. Completion rate trend. Completion percentage per day.
3. Dropoff by question. Last question answered before abandonment.
4. Average confidence by question. Average of `llm_confidence` across turns.
5. Integration success rates. Success and failure counts read from the
   `integration_outcomes` column for the `local_submission` key.

---

## Key components

| Component | What it does |
|-----------|-------------|
| [StatsCards](components/StatsCards.tsx) | KPI cards on the main dashboard, with week on week deltas |
| [ResponsesList](components/ResponsesList.tsx) and [ResponsesTable](components/ResponsesTable.tsx) | Paginated table with sort controls |
| [FilterSection](components/FilterSection.tsx) | Status, date range and duration filters |
| [QuestionAccordion](components/QuestionAccordion.tsx) | Expandable question and answer blocks on the response detail page |
| [IntegrationsSection](components/IntegrationsSection.tsx) | Integration status cards, with a modal showing the payload sent and the raw response, and copy to clipboard |
| [CallOverview](components/CallOverview.tsx) | Call metadata (masked phone, status, duration, timestamps) on the detail page |
| [VolumeChart](components/charts/VolumeChart.tsx), [CompletionTrendChart](components/charts/CompletionTrendChart.tsx), [DropoffChart](components/charts/DropoffChart.tsx), [ConfidenceChart](components/charts/ConfidenceChart.tsx), [IntegrationHealthChart](components/charts/IntegrationHealthChart.tsx) | Recharts analytics visualisations |
| [VoiceChat](components/VoiceChat.tsx) | The WebSocket chat client described above |

---

## Encryption at rest

The call runner can encrypt personal data before it is stored. The dashboard decrypts
it on read in [utils/encryption.ts](utils/encryption.ts): AES-256-GCM, wire format
`enc:v1:<base64(nonce || ciphertext || tag)>`.

`ENCRYPTION_KEY` must be the same 32 byte base64 key the runner uses. When it is not
set, or is not a valid 32 byte base64 value, the helpers pass values through unchanged
so plain text data still renders. Phone numbers are masked to the first four
characters before they leave the query layer, encrypted or not.

Nothing in the dashboard looks a caller up by phone number. The filters are status,
date range and duration, all of which read plaintext columns, so none of them needs
the key.

---

## Environment variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DATABASE_URL` | No | `postgresql://survey_user:survey_pass@localhost:5432/survey_db` | PostgreSQL connection string. The default only suits a local stack |
| `DATABASE_SSL` | No | TLS required | Set to `disable` for a local Postgres that has no TLS |
| `ENCRYPTION_KEY` | No | unset | 32 byte base64 key, must match the call runner. Unset means passthrough |
| `SHOW_CHAT` | No | `false` | Set to `"true"` to show the `/chat` link in the nav |
| `NEXT_PUBLIC_WS_URL` | No | `ws://localhost:8080/ws` | WebSocket URL for the chat client |
| `APP_NAME` | No | `Voice agent` | Application name shown in the header and chat client |
| `BRAND_COLOR` | No | `#1b6df1` | Accent colour |
| `BRAND_COLOR_DARK` | No | `#1a6ad0` | Hover and active accent colour |
| `FAVICON_PATH` | No | `/ico.png` | Favicon path |
| `NODE_ENV` | No | `development` | Set to `production` in the Dockerfile for the production build |
| `PORT` | No | `3000` | Server port, set in the Dockerfile |
| `HOSTNAME` | No | `0.0.0.0` | Server hostname, set in the Dockerfile |

Branding is read from the environment per request in
[utils/branding.ts](utils/branding.ts), so changing it is a restart rather than a
rebuild.

Under Docker Compose these come from the root `.env` and
[infra/docker-compose.yml](../../infra/docker-compose.yml). Running the dashboard on
its own, they come from a local `.env` file, for which
[env.example](env.example) is the template.

---

## Deployment

### Docker build, three stages

```mermaid
flowchart LR
    A["Stage 1: deps<br/>npm ci"] --> B["Stage 2: builder<br/>npm run build<br/>(standalone output)"]
    B --> C["Stage 3: runner<br/>node server.js"]
```

1. **deps**. Installs npm dependencies from the lockfile on `node:24-alpine`.
2. **builder**. Copies the dependencies and builds Next.js in standalone mode
   (`output: 'standalone'` in [next.config.ts](next.config.ts)). It builds against a
   dummy `DATABASE_URL` build argument, which is why the query guards matter.
3. **runner**. Copies the standalone output, `public/` and `.next/static`, and runs as
   the non-root user `nextjs:nodejs` (uid and gid 1001) on port 3000.

### Where it runs

A standalone Next.js container, so anywhere a Node container runs, alongside the call
runner and PostgreSQL. Locally that is Docker Compose, started with `make up` from the
repository root.

---

## Types

TypeScript types live in two places:

- [utils/types.ts](utils/types.ts). Question, turn and survey node shapes for the UI,
  the analytics row types, and `IntegrationsData`, which is the one that has to stay in
  sync with the backend.
- [database/db.ts](database/db.ts). `SurveyResponse`, `Question`, `Turn`,
  `ValidationResult` and `SessionMetadata`, mirroring the database schema as it comes
  back from a query.

`IntegrationsData` in [utils/types.ts](utils/types.ts) describes the `integrations`
JSONB column. Today it has one key, `local_submission`, written by the runner's
`LocalSubmissionHandler`. Adding an integration type in the backend means updating that
interface, [components/IntegrationsSection.tsx](components/IntegrationsSection.tsx),
and `getIntegrationSuccessRates` in [database/queries.ts](database/queries.ts), which
reads the separate `integration_outcomes` column.

---

## Testing

One end to end test, [e2e/survey-demo.spec.ts](e2e/survey-demo.spec.ts), drives `/chat`
through the first two turns of the demo survey against a running stack.

```bash
# From apps/dashboard
npm run test:e2e
```

That is `playwright test`. There is no Makefile target for it. The root Makefile's
`make test` runs the call runner's pytest suite, not this.

[playwright.config.ts](playwright.config.ts) targets Chromium only, with generous
timeouts because the turns go through a real local LLM. Against a local `E2E_BASE_URL`
it starts `npm run dev` itself and reuses an already running server outside CI. Set
`E2E_BASE_URL` to an `https://` origin to point the same test at a deployed instance,
in which case it starts no server.

### Known pitfalls

- `page.goto('/')` ignores any path in `baseURL`. Use explicit paths such as
  `page.goto('/chat')`.
- `window is not defined` during the build. Client components that touch `window` need
  a `useState` lazy initialiser, as [app/chat/page.tsx](app/chat/page.tsx) does.
- Database queries fail gracefully. The guards in
  [database/queries.ts](database/queries.ts) keep the server up without a database, so
  a page that renders empty may mean no connection rather than no data. Check the
  server log for `[DB]`.
