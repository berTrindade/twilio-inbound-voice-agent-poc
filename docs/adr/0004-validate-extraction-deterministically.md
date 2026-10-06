# 4. Validate extraction deterministically

Status: accepted

## Context

A call produces structured records, not a transcript to be mined afterwards. Every answer ends up
attributed to a question and read by something downstream that cannot tell a confident model from a
correct one.

The tempting shape is to ask the model for the answer in the schema you want and store what comes
back. It works most of the time, and the failures are silent, arrive as data, and are found later
by whoever trusts the table.

## Options considered

1. **Trust the model's structured output.** Least code. Puts an unbounded generator directly
   upstream of the system of record.
2. **Model proposes, code validates.** The model says what a turn meant; deterministic code decides
   whether that is a legal answer to this particular question and what to do next.

## Decision

Option 2, and the split is enforced by where the code lives. The turn classifier reads a turn and
reports an interpretation. It has no authority to record anything. The outcome handlers and the
question engine decide, and the question engine owns validation and terminal states.

## Consequences

A wrong classification produces a retry or a confirmation, not a corrupt record. Guardrail recall
scores 3/3 in the eval battery, and the one guardrail case that fails does so by returning its
topic in a field where that value is not part of the enum, which the validation catches rather than
stores.

The cost is real: an answer that fails validation needs a retry, which is another turn, and
turns are the thing the latency budget is spent on. Asking a caller again is slower
than believing the first transcription. It is also the only version that can be defended to whoever
owns the downstream system.
