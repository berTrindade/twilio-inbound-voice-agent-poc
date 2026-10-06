# 6. Instrument the turn, not the request

Status: accepted

## Context

Default HTTP instrumentation measures requests. This system has one request at the start of a call
and then a socket that stays open for minutes. A dashboard built on request metrics would show one
event per call and nothing about the thing that decides whether the call was any good.

The unit of work here is the turn. It is what the caller experiences, what the latency budget is
spent on, and what has to be compared against a threshold.

Getting this wrong is cheap to do and expensive to notice. The first version of the turn histogram
started its timer before awaiting the next frame, so it measured how long the caller took to speak
and reported 6667ms p50 against 1.3 to 1.7 seconds actually spent in the handler. The number was
wrong for weeks and looked plausible throughout.

## Options considered

1. **Request-level metrics from the framework instrumentation.** Free, and answers no useful
   question about a long-lived socket.
2. **A managed APM.** What the commercial version of this would use, and ruled out by the
   self-hosting constraint.
3. **Model the turn explicitly.** A trace per call, a span per turn, and RED measured on turns.

## Decision

Option 3, with three commitments.

**The turn is the unit.** One trace per call, and one child span per websocket message, measuring
handler time from the frame arriving to the reply going out. The span and the histogram are
message-shaped because the frame is what arrives; a turn is the `prompt` message, and every latency
panel on the dashboard filters to it. Setup, interrupt and error are instrumented the same
way and read separately.

**The threshold comes from the platform, not from us.** The dashboard draws the same published
Twilio budget that [ADR 2](0002-two-tier-model-routing.md) routes against. Using their numbers is
more honest than inventing an SLO, and it means the dashboard and their dashboard agree about what
"slow" means.

**All three pillars, correlated.** Traces to Tempo, metrics to Prometheus, logs to Loki, with
`trace_id` on every log record and links wired in both directions. A pillar you cannot pivot from
is a pillar you will not use during an incident.

## Consequences

The dashboard answers the question the system is actually judged on: how long a caller waited,
how often the agent failed, how many calls are live.

Per-call identifiers stay on spans and off metrics. `call_sid` on a histogram gives every call its
own time series, which is the standard way to make a metrics backend expensive; the trace is where
a per-call identifier belongs, and the correlation makes that enough.

What is deliberately not here: alerting, exemplars from metrics into traces, and any sampling
strategy beyond keeping everything. All three are listed in
[what this is not](../../README.md#what-this-is-not) rather than quietly omitted.
