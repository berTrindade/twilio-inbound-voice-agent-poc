"""Run the golden battery through the real small interpreter and score it.

Deliberately calls the same handler the phone call uses (`create_llm_handler`),
with the same prompts, so the numbers describe the deployed path rather than a
parallel one. Whatever LLM_PROVIDER is set to is what gets measured.

    make eval

Outcome counts reuse `classify_prompt_outcome` with escalate=False, because the
real escalate flag comes from `ctx.adapter.should_escalate(...)` and needs a
live call session. They show what the small model alone would have settled.
"""

import argparse
import json
import statistics
import sys
import time
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from voice_agent.api.websocket_handlers.outcomes.classifier import (  # noqa: E402
    classify_prompt_outcome,
)
from voice_agent.config import Settings  # noqa: E402
from voice_agent.voice_ai.llm_handler_factory import create_llm_handler  # noqa: E402
from voice_agent.voice_ai.prompts import (  # noqa: E402
    build_small_interpreter_system_prompt,
    build_small_model_user_prompt,
)

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cases import CASES  # noqa: E402


def load_nodes(settings):
    with open(settings.survey_json_path) as f:
        return {n["id"]: n for n in json.load(f)}


def answer_value(result):
    answer = result.get("answer")
    if not isinstance(answer, dict):
        return None
    return answer.get("value")


def score(case, result):
    """full = interpretation, answer and guardrail topic all correct."""
    checks = [result.get("interpretation") == case["expect"]]

    if "expect_answer" in case:
        got = answer_value(result)
        checks.append(
            isinstance(got, str)
            and got.strip().lower() == case["expect_answer"].lower()
        )

    topic = result.get("guardrail_topic") or "none"
    checks.append(topic == case.get("expect_topic", "none"))

    if all(checks):
        return "full"
    return "partial" if checks[0] else "fail"


VERDICT_MARK = {"full": "pass", "partial": "part", "fail": "FAIL"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", help="only run cases with this tag")
    parser.add_argument("--json", action="store_true", help="emit raw results as JSON")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="exit non-zero unless every case is correct",
    )
    args = parser.parse_args()

    settings = Settings()
    nodes = load_nodes(settings)
    handler = create_llm_handler(settings)
    system_prompt = build_small_interpreter_system_prompt()

    cases = [c for c in CASES if not args.tag or c["tag"] == args.tag]

    print(f"provider {settings.llm_provider}  small model {settings.small_model_id}")
    print(f"{len(cases)} cases\n")

    rows = []
    for case in cases:
        node = nodes[case["node"]]
        user_prompt = build_small_model_user_prompt(node, case["text"])

        started = time.perf_counter()
        result = handler.call_small_model(system_prompt, user_prompt)
        elapsed_ms = (time.perf_counter() - started) * 1000

        verdict = score(case, result)
        outcome = classify_prompt_outcome(
            result.get("interpretation"),
            {"valid": True},
            False,
            result.get("guardrail_topic") or "none",
        )
        rows.append(
            {
                "tag": case["tag"],
                "text": case["text"],
                "expect": case["expect"],
                "got": result.get("interpretation"),
                "expect_answer": case.get("expect_answer"),
                "got_answer": answer_value(result),
                "expect_topic": case.get("expect_topic", "none"),
                "got_topic": result.get("guardrail_topic") or "none",
                "confidence": result.get("confidence"),
                "verdict": verdict,
                "outcome": outcome.name,
                "ms": round(elapsed_ms),
            }
        )

        detail = f"{case['expect']} -> {result.get('interpretation')}"
        if verdict != "full" and case.get("expect_answer"):
            detail += f" | answer {case['expect_answer']!r} -> {answer_value(result)!r}"
        if verdict != "full" and case.get("expect_topic"):
            detail += f" | topic {case['expect_topic']} -> {rows[-1]['got_topic']}"
        print(
            f"  {VERDICT_MARK[verdict]:>4}  {case['tag']:<13} {rows[-1]['ms']:>5}ms  "
            f"{case['text'][:44]:<44}  {detail}"
        )

    if args.json:
        print(json.dumps(rows, indent=2))
        return 0

    report(rows)
    if args.strict:
        return 0 if all(r["verdict"] == "full" for r in rows) else 1
    return 0


def report(rows):
    total = len(rows)
    full = sum(1 for r in rows if r["verdict"] == "full")
    intent_ok = sum(1 for r in rows if r["expect"] == r["got"])

    print(f"\n{'-' * 72}\n")
    print(f"  intent accuracy     {pct(intent_ok, total)}")
    print(f"  fully correct       {pct(full, total)}")

    answered = [r for r in rows if r["expect_answer"]]
    if answered:
        ok = sum(
            1
            for r in answered
            if isinstance(r["got_answer"], str)
            and r["got_answer"].strip().lower() == r["expect_answer"].lower()
        )
        print(f"  answer values       {pct(ok, len(answered))}")

    guardrails = [r for r in rows if r["expect_topic"] != "none"]
    if guardrails:
        caught = sum(1 for r in guardrails if r["got_topic"] == r["expect_topic"])
        print(f"  guardrail recall    {pct(caught, len(guardrails))}")

    latencies = sorted(r["ms"] for r in rows)
    print(
        f"  latency p50 / p95   {percentile(latencies, 50)}ms / {percentile(latencies, 95)}ms"
    )
    print(f"  latency mean        {round(statistics.mean(latencies))}ms")

    print("\n  by tag")
    by_tag = defaultdict(list)
    for r in rows:
        by_tag[r["tag"]].append(r)
    for tag, tag_rows in sorted(by_tag.items()):
        ok = sum(1 for r in tag_rows if r["verdict"] == "full")
        print(f"    {tag:<15} {pct(ok, len(tag_rows))}")

    print("\n  outcomes if nothing escalated")
    by_outcome = defaultdict(int)
    for r in rows:
        by_outcome[r["outcome"]] += 1
    for outcome, count in sorted(by_outcome.items(), key=lambda kv: -kv[1]):
        print(f"    {outcome:<15} {count}")
    print()


def pct(n, d):
    return f"{n}/{d}  {100 * n / d:5.1f}%"


def percentile(sorted_values, p):
    if not sorted_values:
        return 0
    i = min(len(sorted_values) - 1, int(round(p / 100 * len(sorted_values) + 0.5)) - 1)
    return sorted_values[i]


if __name__ == "__main__":
    raise SystemExit(main())
