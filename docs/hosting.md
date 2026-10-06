# Running it on a real phone number

Two paths. Both need the same Twilio account setup, so start with section 1 either way.

- **Local with ngrok.** Free, five minutes to set up, and the URL changes every restart.
  Fine for testing and for a demo you drive yourself.
- **Always-on hosted.** About $7/mo, stable URLs you can hand to someone else.

## 1. Twilio account setup

**Accept the AI/ML addendum first.** Console, then Voice, Settings, General. Scroll to
**Predictive and Generative AI/ML Features Addendum**, set it to Enabled, then save.

ConversationRelay does not work until you do this, and the failure is not obvious from the
call. This is the step people miss.

Then buy a number under Phone Numbers. On a trial account you can only call numbers you have
verified.

**Cost**, from Twilio's pricing page at the time of writing:

| Item | Price |
|------|-------|
| ConversationRelay | $0.07 / min |
| US local number | $1.15 / mo |
| US inbound voice | $0.0085 / min |

So roughly $0.08 per minute of testing. Twilio's pricing page does not break out ElevenLabs
or Deepgram separately inside ConversationRelay, so treat the $0.07 as all-in and check your
first invoice.

You do not need ElevenLabs or Deepgram accounts. Twilio brokers both. The runner's defaults
(`TTS_PROVIDER=ElevenLabs`, `TRANSCRIPTION_PROVIDER=Deepgram`, `SPEECH_MODEL=nova-3-general`)
are also Twilio's own defaults. `ttsProvider` accepts Google, Amazon or ElevenLabs.
`transcriptionProvider` accepts Google or Deepgram.

## 2. Local, with ngrok

Run `make up` once so the stack exists and a `.env` has been written for you, then open a
tunnel to the runner:

```bash
ngrok http 8080
```

Uncomment the Twilio block in `.env` and fill it in:

```bash
TWILIO_WS_DOMAIN=abc123.ngrok-free.app     # hostname only, no scheme, no path
TWILIO_AUTH_TOKEN=<from the Twilio console>
LLM_PROVIDER=groq                          # omit these four to stay fully local
LLM_API_KEY=<from console.groq.com>
SMALL_MODEL_ID=llama-3.1-8b-instant
BIG_MODEL_ID=llama-3.3-70b-versatile
```

Then `make up` again to pick the changes up.

Point the number at it last. Phone Numbers, your number, Voice, "A call comes in" set to
Webhook, `https://abc123.ngrok-free.app/twiml`, method **POST**.

Free ngrok gives you a new hostname on every restart, so `TWILIO_WS_DOMAIN` and the Twilio
webhook both need updating each time. See [Why the 403](#why-the-403) below.

**The local model works for a call, but Groq is smoother.** A local turn takes about 1.8s
(`make eval` reports p50 and p95), which on a call is an audible pause before the agent
speaks, on top of the time Twilio spends on speech either side. It holds together for a
survey where you ask and the caller answers; it is not conversational. Groq removes the
pause. `LLM_BASE_URL` already defaults to Groq's endpoint, so `LLM_PROVIDER=groq` plus a key
is the whole change. That is why the block above sets it. Leave those four lines out and the
call runs entirely on your own machine.

**Handover is off locally.** The runner's own default for `COACH_HANDOFF_ENABLED` is `true`,
and when the agent decides to hand over it dials `COACH_PHONE_NUMBER`. Unset, that hangs up on
your caller. The Compose file pins it to `false` so a first test cannot trip on it. To test the
bridge itself, set both `COACH_HANDOFF_ENABLED=true` and a real `COACH_PHONE_NUMBER` in `.env`.
If the handover then fails while the rest of the call works, check **Voice, Settings, Geographic
Permissions** in the Console before debugging the code: the bridge places an outbound call, and
which destination countries an account may dial varies.

## 3. Always-on hosted

Stable URLs you can hand to someone else, with the LLM on Groq so the runner fits a small box.

**Stack:** Render for the runner and dashboard, Neon for Postgres, Groq for the LLM, Twilio
for the number.
**Cost:** about $7/mo for the always-on runner, everything else on a free tier.

> The runner must be always-on. Every free tier cold-starts when idle, and a cold start can
> time out Twilio's WebSocket handshake and drop the call. That is what the one paid instance
> buys you.

### Postgres on Neon

neon.tech, new project, copy the pooled connection string. Neon stays warm and does not hard
pause the way some free tiers do.

### LLM on Groq

console.groq.com, API Keys, create a key. Models are pre-set in `render.yaml`, with
`llama-3.1-8b-instant` as the small model and `llama-3.3-70b-versatile` as the big one. The 8b
model has the most free headroom.

### Deploy on Render

1. render.com, New, Blueprint, connect `berTrindade/twilio-inbound-voice-agent-poc`. Render
   reads `render.yaml` and creates the runner on `starter` and the dashboard on `free`.
2. Fill the `sync: false` secrets when prompted:
   - `DATABASE_URL`, the Neon string, shared across both services
   - `LLM_API_KEY`, the Groq key, on the runner
   - `TWILIO_AUTH_TOKEN`, from the Twilio console, on the runner
3. The first deploy gives you two URLs, one for the runner and one for the dashboard.
4. Set the dashboard's `NEXT_PUBLIC_WS_URL` to `wss://<runner-host>/ws` and redeploy it.
   `TWILIO_WS_DOMAIN` on the runner auto-fills with its own hostname.
5. Point the number's voice webhook at `https://<runner-host>/twiml`, method POST. The URL is
   permanent, so no ngrok and no re-pointing.

### Swapping content on a hosted demo

Edit env vars in the Render dashboard and restart the affected service. The Twilio webhook
never changes.

- Voice and survey, on the runner: `SURVEY_JSON_PATH`, `INITIAL_NODE_ID`, `VOICE`.
- Branding, on the dashboard: `APP_NAME`, `BRAND_COLOR`, `BRAND_COLOR_DARK`, `FAVICON_PATH`.

## Recording a call

Twilio can record the call for you, which is the only way to get clean audio off both legs.
`TWILIO_RECORDING_ENABLED=true` makes the TwiML emit `<Start><Recording>` before connecting
ConversationRelay, so capture begins with the call rather than with the first turn.
`POST /twiml/recording_status` receives the lifecycle callbacks and links the `RecordingSid` to
the call record, so the audio files under the same `callSid` as the stored answers and the trace.

| Variable | Default | What it does |
|---|---|---|
| `TWILIO_RECORDING_ENABLED` | `false` | Whether to record at all |
| `TWILIO_RECORDING_TRACK` | `both` | Which legs to capture |
| `TWILIO_RECORDING_CHANNELS` | `dual` | Caller and agent on separate channels |
| `TWILIO_RECORDING_STATUS_CALLBACK_EVENT` | `in-progress completed absent` | Which lifecycle events to receive |

Keep `dual`. Caller and agent land on separate tracks, so a level can be fixed on one side
without touching the other. Download from the Console under **Monitor, Logs, Calls**.

Recording a call has legal consequences that vary by jurisdiction, and several US states require
every party to agree first. Be the caller yourself, give invented answers, and never record a call
carrying anyone's real personal data.

## Why the 403

A genuine Twilio call rejected with HTTP 403 almost always means `TWILIO_WS_DOMAIN` does not
match the hostname Twilio actually called.

The setting does double duty. `Settings.ws_url` builds the `wss://{domain}/ws` that goes into
the TwiML, and `Settings.twilio_public_base_url` builds the `https://{domain}` that signature
verification checks against. Verification reconstructs the signed URL from that setting rather
than from the incoming request, because behind a proxy the request's own host is the internal
one. So a stale ngrok hostname fails the check even though the request is real.

`TWILIO_AUTH_TOKEN` is required. Without it the runner returns 500 rather than skipping the
check. There is a bypass, but it needs both `ENVIRONMENT=development` and
`TWILIO_VALIDATE_SIGNATURE=false`. Leave verification on, since it works once the domain is
right.

## Notes

- Groq's JSON mode needs the word "json" in the prompt. The small-interpreter prompt already
  instructs JSON output. If a model rejects `response_format`, switch `SMALL_MODEL_ID` to
  another Groq model that supports JSON mode.
- Telephony is the one inherently paid piece. Twilio minutes and ConversationRelay are
  pay-as-you-go no matter how the rest is hosted.
- The dashboard has no login. That is fine locally and not fine on a public URL, so either
  leave the dashboard service out of the Blueprint or put it behind the host's access control.
  Only the runner needs to be reachable by Twilio.
- Using your own Ollama instead: the runner only ever sees a base URL, so set `OLLAMA_BASE_URL`
  and the two model ids in [.env.example](../.env.example). On Linux also set
  `OLLAMA_HOST=0.0.0.0:11434`, since Ollama binds `127.0.0.1` and the container cannot otherwise
  reach it.
