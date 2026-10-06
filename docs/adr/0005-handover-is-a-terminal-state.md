# 5. Handover to a person is a terminal state

Status: accepted

## Context

An agent that cannot give up traps the caller. The failure mode is familiar from the outside: the
third rephrasing of a question you have already answered, with no way out except hanging up.

Giving up well is a product requirement, and where it sits in the design is what it gets built
like. Modelled as an error path it collects the usual treatment of error paths, which is to say it
gets tested last and reasoned about least. Modelled as a terminal state in the question graph, it
gets tested like every other way a call can end.

## Options considered

1. **Retry until the caller succeeds or hangs up.** No new machinery. Produces the trapped caller.
2. **An error path.** Honest about failure, wrong about what kind of thing it is. Handing a call to
   a person who can finish it is a good outcome, not a fault.
3. **A first-class terminal state in the question graph.** Handover is somewhere the graph can
   legitimately end.

## Decision

Option 3. The question graph can terminate in handover the same way it terminates in completion.
The reason for the handover is classified and recorded, so the call can be reviewed afterwards
against what actually caused it.

Handover is also one of the six outcomes a turn can land on, which is the same decision seen from
[ADR 2](0002-two-tier-model-routing.md): escalating to a bigger model and escalating to a human are
peers, chosen for different reasons.

## Consequences

Every terminal state is reachable and testable, and the handover reason is a dimension you can
count rather than a log line you grep.

It needs telephony support, because bridging a live call is not something this system can do by
itself. On the Twilio path it is TwiML `Dial` with a whisper so the person picking up knows what
they are joining. On the browser path there is nothing to bridge to, which is a real limit of the
second implementation from [ADR 1](0001-telephony-behind-a-port-with-two-implementations.md).

It ships disabled. With handover enabled and no number configured, a handover would hang up on the
caller, which is worse than the behaviour it replaces. Defaulting it off means the failure of an
unconfigured install is a survey that completes, not a call that drops.
