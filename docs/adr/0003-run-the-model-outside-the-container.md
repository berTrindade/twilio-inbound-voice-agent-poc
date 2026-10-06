# 3. Run the model outside the container

Status: accepted

## Context

The obvious topology puts every moving part in Compose, model included. One file, one command,
nothing on the host. It is also the version that does not work on a Mac.

A container cannot reach the GPU there. Apple's virtualization framework exposes no GPU compute to
Linux guests, so a model running inside Docker on macOS is on CPU, and no amount of configuration
changes that. This is a platform limit, not a tuning problem.

It was worth measuring rather than assuming. Same model, same quantisation, scored through the same
eval harness:

| Runtime | p50 per turn | Eval score |
|---|---|---|
| Model in a container | 12.8s | 21/24 |
| Docker Model Runner | 1.6s | 21/24 |

Eight times slower, with the same three cases failing. The runtime changed and the model behaviour
did not, which is what makes this a deployment finding rather than a model one. The interpreter
prompt has been reworded since and the battery now scores 22/24 through Model Runner. The
in-container run has not been repeated, so the table is left at the numbers both rows were
actually measured at.

## Options considered

1. **Model in a container.** Cleanest topology, unusable on macOS at 12.8s per turn.
2. **Require a Linux GPU host.** Correct for production, and excludes most people who would clone
   this to look at it.
3. **Docker Model Runner.** Runs the model outside the VM on macOS and in a CUDA container on
   Linux, so one setup is fast on both.

## Decision

Option 3. Model Runner ships with Docker, so there is nothing extra to install, and the same
`make up` is fast on either platform.

## Consequences

The model is not a Compose service, so it is the one box in the deployment diagram sitting outside
the Compose network while everything else sits inside it. That asymmetry is a genuine wrinkle in
the documentation and it is called out: the model runtime shares a host with everything else, which
makes its latency a **deployment property, not an architectural one**. That distinction is the
reason this ADR exists.

It cost something concrete. Model Runner's Ollama-compatible `/api/chat` omits `prompt_eval_count`
and `eval_count`, so `gen_ai.usage.*` reads zero on every span taken locally. Its OpenAI-compatible
`/engines/v1` does return usage but ignores `response_format: json_object`, which the interpreter
depends on. Token counts were the cheaper thing to give up. Real Ollama returns both, and pointing
`OLLAMA_BASE_URL` at one restores them.
