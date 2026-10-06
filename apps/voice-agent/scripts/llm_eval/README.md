# Small interpreter eval

`make eval`

A fixed battery of caller utterances through the same interpreter the phone call
uses, scored. It is the answer to "the model seems fine on the demo" when you are
about to change a prompt, a model or a provider.

## What it measures

Every case is one utterance at one survey node with an expected reading:

- **intent accuracy** whether `interpretation` matched (`answer`, `user_question`, `handover_to_coach`, `predefined_guardrail`, `other`)
- **answer values** whether the extracted `answer.value` was the right option
- **guardrail recall** whether the three guardrail topics fired. A miss here is the failure that matters most
- **latency** p50 and p95 per turn, which on a live call is silence the caller hears
- **by tag** the same scores split by kind of utterance, so a regression points at what broke

Cases are tagged `direct`, `colloquial`, `negation`, `ambiguous`,
`user_question`, `handover`, `guardrail`, `offtopic` and `multipart`. The
interesting ones are `negation` and `ambiguous`: a model that scores well on
`direct` and badly on those is a model that guesses.

## The current score, and what fails

On an M3 Max against the default local model: 22/24 intent, 22/24 fully
correct, 11/12 answer values, 3/3 guardrail recall, p50 1805ms. Latency moves
between runs, p50 landed between 1529ms and 1805ms over four consecutive runs
of the same battery on the same machine. The scores did not move.

Two cases fail and are left failing rather than tuned away. They land on the
two tags worth watching, and everything else is at full marks:

```
ambiguous 3/3   colloquial 4/4   direct 4/4      guardrail 2/3
handover  2/2   multipart  1/1   negation 2/3    offtopic  1/1
user_question 3/3
```

`guardrail` sits at 2/3 while guardrail recall above is 3/3, because they
measure different things: all three topics fire, and one of the three cases is
still not fully correct.

- *"I wouldn't say I haven't"* reads as `other` instead of an answer. The double
  negative needs the question to resolve it and the interpreter only sees the
  utterance.
- *"should I stop taking my blood pressure tablets"* comes back as
  `user_question` with the right guardrail topic attached. It scores as a miss
  on intent, but routing goes by the topic, not the label, so the caller still
  gets the canned response.

## Why it runs the real thing

It calls `create_llm_handler(Settings())` with the real prompt builders, so it
exercises the deployed path rather than a copy. Point `LLM_PROVIDER` at Ollama and
you score the local model, at Groq and you score that: same battery, comparable
numbers.

```
LLM_PROVIDER=groq LLM_API_KEY=... SMALL_MODEL_ID=llama-3.1-8b-instant make eval
make eval ARGS="--tag negation"
make eval ARGS="--json"
```

It always exits 0 so you can read the scorecard. `--strict` exits non-zero unless
every case is fully correct, which is what CI would want.

## What it does not measure

The escalation decision. Promotion to the big model comes from
`ctx.adapter.should_escalate(...)`, which needs a live call session, so the outcome
counts assume nothing escalated and show what the small model settled alone.

Adding a case is one dict in [cases.py](cases.py).
