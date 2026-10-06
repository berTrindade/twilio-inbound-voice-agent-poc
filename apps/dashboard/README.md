# Voice agent dashboard

Next.js 16 dashboard for the voice agent. Survey responses, completion stats,
conversation transcripts and integration health.

Normally you do not run this on its own. `make up` from the repository root starts
it along with everything it talks to; see [running it](../../README.md#running-it).

## Running it on its own

```bash
npm install
npm run dev
```

It needs a Postgres with the call runner's migrations already applied. The dashboard
only reads that database and never migrates it.

## Where everything is documented

| Topic | Where |
|-------|-------|
| Routes, components, data flow, deployment | [ARCHITECTURE.md](ARCHITECTURE.md) |
| Environment variables | [ARCHITECTURE.md](ARCHITECTURE.md#environment-variables) |
| End to end tests | [ARCHITECTURE.md](ARCHITECTURE.md#testing) |
| Database schema and entity diagram | [call runner README](../voice-agent/README.md#database) |
