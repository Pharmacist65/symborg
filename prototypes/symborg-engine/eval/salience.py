"""Evaluate whether the copilot knows when to stay quiet.

No benchmark exists for this, so this is ours. The two errors are not symmetric and
must not be scored as though they were:

  SPOKE WHEN IT SHOULD NOT   an interruption. Costs trust, and trust does not recover
                             at the rate it is spent. This is what emptied the category.
  STAYED QUIET WHEN IT       a missed moment. Costs an opportunity. The person is no
  SHOULD HAVE SPOKEN         worse off than with no device at all.

So a false alarm is worse than a miss, and the headline number is the false-alarm rate
rather than accuracy. A system that never speaks scores perfectly on the first and
uselessly on the second — both are reported, and neither alone is the score.

    set -a; . ../../.env; set +a
    PYTHONPATH=src python3 eval/salience.py

Costs one API call per moment.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from symborg_engine.copilot import decide  # noqa: E402
from symborg_engine.providers import resolve_language_model  # noqa: E402

SET = Path(__file__).with_name("salience.jsonl")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("-v", "--verbose", action="store_true", help="show every failure")
    args = ap.parse_args()

    model = resolve_language_model()
    if type(model).__name__ == "OfflineLanguageModel":
        print("Offline provider — nothing to measure. Set a key first.", file=sys.stderr)
        return 1

    rows = [json.loads(line) for line in SET.read_text(encoding="utf-8").splitlines() if line.strip()]

    false_alarms: list[dict] = []
    misses: list[dict] = []
    by_tag: dict[str, list[bool]] = defaultdict(list)

    print(f"\n{len(rows)} moments   provider: {type(model).__name__}\n")

    for row in rows:
        judgement = decide(model, row["transcript"], row.get("memory", ""))
        spoke = judgement.worth_it
        should = bool(row["speak"])
        by_tag[row["tag"]].append(spoke == should)

        if spoke and not should:
            false_alarms.append({**row, "said": judgement.say})
        elif should and not spoke:
            misses.append(row)

        mark = "·" if spoke == should else ("!" if spoke else "×")
        print(f"  {mark} {'speak' if spoke else 'quiet':5}  {row['transcript'][:52]}")
        if spoke:
            print(f"        → {judgement.say}")

    should_speak = sum(1 for r in rows if r["speak"])
    should_quiet = len(rows) - should_speak

    print(f"\n  false alarms   {len(false_alarms):2}/{should_quiet}   "
          f"({len(false_alarms)/should_quiet:.0%})   ← the number that matters")
    print(f"  missed         {len(misses):2}/{should_speak}   "
          f"({len(misses)/should_speak:.0%})")
    print(f"  silence rate   {sum(1 for r in rows if r['speak'] == 0) - len(false_alarms) + len(misses):2}/{len(rows)} judged quiet")

    failing = {tag: results for tag, results in by_tag.items() if not all(results)}
    if failing:
        print("\n  by class:")
        for tag, results in sorted(failing.items(), key=lambda kv: sum(kv[1]) - len(kv[1])):
            print(f"    {tag:16} {sum(results)}/{len(results)}")

    if args.verbose:
        for row in false_alarms:
            print(f"\n  INTERRUPTED ({row['tag']}): {row['transcript']}")
            print(f"    said: {row['said']}")
        for row in misses:
            print(f"\n  MISSED ({row['tag']}): {row['transcript']}")

    print("\n  Hand-authored set, tuned against. A regression harness, not evidence.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
