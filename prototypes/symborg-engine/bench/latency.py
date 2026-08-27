"""Latency benchmark for candidate generation.

Run it before changing a model, a token budget or a prompt. The number this reports is
a product property, not an implementation detail: natural conversation leaves roughly
200 ms between turns, and a candidate arriving after the conversation has moved on has
failed even when the sentence was right.

    set -a; . ../../.env; set +a
    PYTHONPATH=src python3 bench/latency.py

Costs a small number of API calls.
"""

from __future__ import annotations

import argparse
import statistics
import sys
import time

from symborg_engine.generate.candidates import CANDIDATE_SCHEMA, parse_candidates
from symborg_engine.generate.prompts import CANDIDATE_SYSTEM, build_candidate_prompt
from symborg_engine.providers import resolve_language_model
from symborg_engine.providers.base import Prompt, ProviderError

TURN = "Partner: Ağrın var mı? Doktoru çağırmamı ister misin?"

BUDGET_MS = 500
"""Above this a delay starts being socially noticed; ~200 ms is the natural gap."""


def run(model, label: str, tokens: int, schema: dict | None, n: int) -> None:
    prompt = Prompt(
        system=CANDIDATE_SYSTEM,
        user=build_candidate_prompt(TURN, "", 3),
        max_tokens=tokens, temperature=0.5, json_schema=schema,
    )
    times: list[float] = []
    parsed = 0
    for _ in range(n):
        started = time.perf_counter()
        try:
            raw = model.complete(prompt)
        except ProviderError as exc:
            print(f"  {label:34} FAILED: {exc}")
            return
        times.append((time.perf_counter() - started) * 1000)
        parsed = len(parse_candidates(raw))

    median = statistics.median(times)
    over = median / BUDGET_MS
    print(f"  {label:34} median {median:6.0f} ms   min {min(times):5.0f}   "
          f"{over:4.1f}x budget   parsed {parsed}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("-n", type=int, default=4, help="calls per configuration")
    args = ap.parse_args()

    model = resolve_language_model()
    name = type(model).__name__
    if name == "OfflineLanguageModel":
        print("Offline provider — nothing to measure. Set a key first.", file=sys.stderr)
        return 1

    print(f"\nprovider: {name}   budget: {BUDGET_MS} ms (natural turn gap ~200 ms)\n")
    run(model, "current defaults", 160, CANDIDATE_SCHEMA, args.n)
    run(model, "no schema", 160, None, args.n)
    run(model, "larger budget (400 tokens)", 400, CANDIDATE_SCHEMA, args.n)
    print("\nA hosted call cannot reach the budget by tuning. Closing the gap means")
    print("starting earlier — generating before the turn ends — not answering faster.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
