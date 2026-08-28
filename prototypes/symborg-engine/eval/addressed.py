"""What the person wanted when they turned to it.

The inverse of the salience set. There the number that matters is how often it spoke
when it should not have; here it is how often it did the wrong thing when someone
deliberately asked. Opening a camera for a memory question is merely useless; answering
from memory when someone is pointing at a mushroom is worse, because it will answer
confidently about something it cannot see.

    OPENAI_API_KEY=... PYTHONPATH=src python3 eval/addressed.py
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from symborg_engine.copilot.addressed import understand   # noqa: E402
from symborg_engine.providers import resolve_language_model  # noqa: E402

HERE = Path(__file__).parent


def main() -> int:
    rows = [json.loads(line) for line in
            (HERE / "addressed.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    model = resolve_language_model(None)
    print(f"{len(rows)} requests   provider: {type(model).__name__}\n")

    wrong_kind: Counter = Counter()
    right = 0
    payload_right = payload_total = 0

    for row in rows:
        address = understand(model, row["said"])
        got = address.want.value
        ok = got == row["want"]
        right += ok
        if not ok:
            wrong_kind[f'{row["want"]}→{got}'] += 1

        mark = " · " if ok else " × "
        print(f"{mark}{got:9} {row['said'][:50]}")
        if not ok:
            print(f"      expected {row['want']}")

        # For translation the intent is not enough: what gets read out to a stranger is
        # the query, and a request that carries its own wrapper into the sentence is a
        # different kind of wrong from a misread intent.
        if "query_is" in row:
            payload_total += 1
            clean = _flat(address.query)
            wanted = _flat(row["query_is"])
            hit = wanted in clean and len(clean) < len(wanted) * 1.6
            payload_right += hit
            if not hit:
                print(f"      payload: {address.query!r}")

    print(f"\n  intent      {right}/{len(rows)}   ({right / len(rows):.0%})")
    if payload_total:
        print(f"  payload     {payload_right}/{payload_total}   ← what a stranger hears")
    if wrong_kind:
        print("\n  confusions:")
        for pair, count in wrong_kind.most_common():
            print(f"    {pair:24} {count}")
    print("\n  Hand-authored set, tuned against. A regression harness, not evidence.")
    return 0


def _flat(text: str) -> str:
    return " ".join(text.replace("İ", "i").replace("I", "ı").lower().split()).strip(" .,:;?!")


if __name__ == "__main__":
    raise SystemExit(main())
