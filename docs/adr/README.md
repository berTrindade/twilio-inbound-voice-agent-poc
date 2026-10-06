# Decision records

The decisions in this repo that had a real alternative, with what each one cost. Written after the
fact, which is why every one of them has consequences that were measured rather than predicted.

| | Decision | The tradeoff it bought |
|---|---|---|
| [1](0001-telephony-behind-a-port-with-two-implementations.md) | Telephony behind a port, with two implementations | Two code paths to keep working, in exchange for a seam that is proven rather than assumed |
| [2](0002-two-tier-model-routing.md) | Two-tier model routing, with escalation as an outcome | A routing decision that can be wrong, in exchange for not paying frontier latency on "yes" |
| [3](0003-run-the-model-outside-the-container.md) | Run the model outside the container | One box outside Compose while everything else is inside it, in exchange for 1.6s instead of 12.8s per turn |
| [4](0004-validate-extraction-deterministically.md) | Validate extraction deterministically | An extra turn on some questions, in exchange for a wrong classification never reaching the record |
| [5](0005-handover-is-a-terminal-state.md) | Handover to a person is a terminal state | Telephony support and a disabled default, in exchange for a caller who is never trapped |
| [6](0006-instrument-the-turn-not-the-request.md) | Instrument the turn, not the request | Per-call detail confined to traces, in exchange for a metrics backend that stays cheap |

The decisions that are still open, rather than made, are at the end of
[architecture.md](../architecture.md#open-questions).
