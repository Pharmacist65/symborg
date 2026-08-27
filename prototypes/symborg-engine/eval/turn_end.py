"""Evaluate a turn-end predictor.

There is no standard benchmark for deciding when a system should start speaking, so
this is ours. It scores the two errors that actually cost something, and they are not
symmetric:

  MISS       the predictor never fired, so generation begins only after silence and
             the person waits the full call — the turn is effectively lost.
  EARLY FIRE the predictor fired mid-turn and the speaker carried on, so a generation
             was wasted and the candidates may be stale.

A miss costs a turn. An early fire costs one API call. The threshold should sit where
that asymmetry puts it, not where balanced accuracy would.

    PYTHONPATH=src python3 eval/turn_end.py

IMPORTANT LIMITATION. The set in ``turns.jsonl`` is hand-authored, not transcribed from
recorded speech. It is a regression harness: it catches breakage and exposes known
failure classes. It is not evidence of real-world performance, and no published claim
should rest on it. Real evaluation needs recorded two-party Turkish conversation with
timing, which is a separate piece of work.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from symborg_engine.turntaking import (  # noqa: E402
    DEFAULT_THRESHOLD, SilencePredictor, TurkishHeuristicPredictor, TurnMonitor,
)

SET = Path(__file__).with_name("turns.jsonl")


@dataclass(slots=True)
class Outcome:
    tag: str
    fired_at: int | None
    end_at: int
    fragments: list[str]

    @property
    def missed(self) -> bool:
        return self.fired_at is None

    @property
    def early(self) -> bool:
        return self.fired_at is not None and self.fired_at < self.end_at

    @property
    def on_time(self) -> bool:
        return self.fired_at == self.end_at

    @property
    def lead_fragments(self) -> int:
        """Fragments of head start. Zero means it fired exactly at the end."""
        return 0 if self.fired_at is None else self.end_at - self.fired_at


def evaluate(predictor, threshold: float, rows: list[dict]) -> list[Outcome]:
    out: list[Outcome] = []
    for row in rows:
        monitor = TurnMonitor(predictor=predictor, threshold=threshold)
        fired_at = None
        for i, fragment in enumerate(row["fragments"]):
            if monitor.observe(fragment).fired:
                fired_at = i
                break
        out.append(Outcome(row["tag"], fired_at, row["end_at"], row["fragments"]))
    return out


def report(name: str, outcomes: list[Outcome], verbose: bool) -> None:
    n = len(outcomes)
    missed = [o for o in outcomes if o.missed]
    early = [o for o in outcomes if o.early]
    on_time = [o for o in outcomes if o.on_time]

    print(f"\n{name}")
    print(f"  fired at the turn end : {len(on_time):2}/{n}  ({len(on_time)/n:.0%})")
    print(f"  fired early           : {len(early):2}/{n}  ({len(early)/n:.0%})   one wasted call each")
    print(f"  missed entirely       : {len(missed):2}/{n}  ({len(missed)/n:.0%})   full latency, turn lost")

    by_tag: dict[str, list[Outcome]] = defaultdict(list)
    for o in outcomes:
        if not o.on_time:
            by_tag[o.tag].append(o)
    if by_tag:
        print("  failures by class:")
        for tag, group in sorted(by_tag.items(), key=lambda kv: -len(kv[1])):
            kinds = "".join("M" if o.missed else "E" for o in group)
            print(f"    {tag:16} {len(group):2}  [{kinds}]")

    if verbose:
        for o in outcomes:
            if o.on_time:
                continue
            where = "MISS " if o.missed else f"EARLY@{o.fired_at}"
            print(f"    {where}  ({o.tag}) " + " | ".join(o.fragments))


def main() -> int:
    ap = argparse.ArgumentParser(description="Evaluate turn-end prediction.")
    ap.add_argument("-t", "--threshold", type=float, default=DEFAULT_THRESHOLD)
    ap.add_argument("-v", "--verbose", action="store_true", help="list every failure")
    ap.add_argument("--sweep", action="store_true", help="try a range of thresholds")
    args = ap.parse_args()

    rows = [json.loads(line) for line in SET.read_text(encoding="utf-8").splitlines() if line.strip()]
    print(f"{len(rows)} hand-authored turns — a regression harness, not evidence")

    report("silence baseline (what systems do today)",
           evaluate(SilencePredictor(), args.threshold, rows), args.verbose)
    report(f"Turkish morphology (threshold {args.threshold})",
           evaluate(TurkishHeuristicPredictor(), args.threshold, rows), args.verbose)

    if args.sweep:
        print("\nthreshold sweep")
        print(f"  {'thr':>5}  {'on time':>8}  {'early':>6}  {'missed':>7}")
        for t in (0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9):
            o = evaluate(TurkishHeuristicPredictor(), t, rows)
            print(f"  {t:5.1f}  {sum(x.on_time for x in o):8}  "
                  f"{sum(x.early for x in o):6}  {sum(x.missed for x in o):7}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
