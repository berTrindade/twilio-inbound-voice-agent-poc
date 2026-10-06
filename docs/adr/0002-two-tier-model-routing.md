# 2. Two-tier model routing, with escalation as an outcome

Status: accepted

## Context

Everything between the caller finishing a sentence and the agent starting one is on the critical
path. Twilio publish the budget they design against: 375ms for the model, 885ms for everything on
their side of the call, and their dashboard flags a turn that runs long.

Most turns in a structured survey are not hard. "Yeah, a few times" against a yes/no question does
not need a frontier model. A minority are genuinely ambiguous, and those are the ones that decide
whether the call feels competent.

## Options considered

1. **One large model on every turn.** Simplest to reason about, uniformly slow, and pays frontier
   latency for "yes".
2. **A fixed grammar, no model.** Fastest and most predictable. Falls apart on the phrasings people
   actually use, which is the entire problem.
3. **A small model classifies every turn, with escalation available.** Cheap common path, expensive
   path reserved for turns that earn it.

## Decision

Option 3. A small model reads every turn and says what it meant. It does not decide what to do
about it.

Escalating to the larger model is **one outcome among several**, not a fallback. Every turn lands
on exactly one of: record an answer, retry, answer the caller's question, refuse an off-topic one,
escalate, or hand over to a person. Because escalation is a peer of the others and not what
happens when the first attempt fails, the control flow stays readable.

## Consequences

Measured p50 of 1607ms on the local path, which is over Twilio's model budget and holds together
for a survey anyway because the caller expects a beat after answering a question. On Groq the same
code is comfortably inside it.

The routing decision is itself something that can be wrong, which is why the eval battery exists
and why its failures are left failing rather than tuned away. Two cases currently fail, putting
negation and guardrail at 2/3 each, and both are named in the
[eval's README](../../apps/voice-agent/scripts/llm_eval/README.md) rather than hidden.

This is the decision most likely to be reversed. As small models get better the two tiers may
collapse into one, and that is recorded as an open question in
[architecture.md](../architecture.md#open-questions) rather than settled here.
