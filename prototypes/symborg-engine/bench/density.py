"""How much of a day is actually somebody speaking.

Every cost estimate for this product scales linearly off one number nobody has measured:
what fraction of the hours it is switched on contains speech. At 30% the bill is one
thing; at 60% only an on-device architecture survives. Guessing it wrong means building
the wrong product, so this measures it instead — from a real microphone, in a real room,
with nothing leaving the machine.

    PYTHONPATH=src python3 bench/density.py --minutes 60

No network, no API key, no audio written to disk. It counts seconds and prints numbers.

    PYTHONPATH=src python3 bench/density.py --minutes 60 --log ~/density.jsonl

With --log it appends one line per minute, so a day can be run in pieces and added up.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from symborg_engine.providers.vad import Gate                    # noqa: E402
from symborg_engine.providers.realtime_stream import MicrophoneSource  # noqa: E402

# What the numbers become. Rates are entered here rather than inline so a stale figure
# is one line to change and obvious when it is wrong.
REALTIME_USD_PER_MIN = 0.06
"""Live transcription, streamed. The expensive tier — checked against the provider's
pricing page on 28 August 2026; verify before quoting it to anyone."""

BATCH_USD_PER_MIN = 0.003
"""Batch transcription of gated segments. Roughly twenty times cheaper, and the whole
reason the gate exists."""

BYTES_PER_SECOND = 24_000 * 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Measure how much of a day is speech.")
    parser.add_argument("--minutes", type=float, default=10.0)
    parser.add_argument("--log", default=None, help="Append one line per minute")
    parser.add_argument("--device", default=None)
    args = parser.parse_args(argv)

    gate = Gate()
    started = time.monotonic()
    deadline = started + args.minutes * 60
    log_path = Path(args.log).expanduser() if args.log else None
    minute_mark = started + 60

    print(f"\n  Listening for {args.minutes:g} minutes. Nothing leaves this machine.")
    print("  Carry on with your day; Ctrl-C to stop early.\n")
    print("   elapsed   speech   passed   what it would cost per 8h day")

    try:
        with MicrophoneSource(device=args.device) as mic:
            for block in mic.blocks():
                gate.filter(block)
                now = time.monotonic()
                if now >= minute_mark:
                    _report(gate, now - started)
                    if log_path is not None:
                        _append(log_path, gate, now - started)
                    minute_mark += 60
                if now >= deadline:
                    break
    except KeyboardInterrupt:
        print("\n  stopped early.")
    except ImportError as exc:
        print(f"\n  {exc}")
        return 1

    elapsed = time.monotonic() - started
    if elapsed < 5:
        print("\n  Too short to mean anything.")
        return 1

    _summary(gate, elapsed)
    return 0


def _report(gate: Gate, elapsed: float) -> None:
    passed = gate.passed_fraction
    per_day = passed * 8 * 60
    print(f"   {elapsed / 60:5.0f}m    {passed:5.0%}   "
          f"{passed * elapsed / 60:5.1f}m   "
          f"${per_day * REALTIME_USD_PER_MIN:6.2f} live   "
          f"${per_day * BATCH_USD_PER_MIN:5.2f} batch")


def _append(path: Path, gate: Gate, elapsed: float) -> None:
    row = {"elapsed_s": round(elapsed, 1), "speech_fraction": round(gate.passed_fraction, 4)}
    try:
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row) + "\n")
    except OSError:
        pass          # a log that cannot be written must not stop the measurement


def _summary(gate: Gate, elapsed: float) -> None:
    passed = gate.passed_fraction
    day_minutes = passed * 8 * 60
    ungated_day = 8 * 60

    print(f"\n  measured over {elapsed / 60:.1f} minutes")
    print(f"  speech        {passed:.0%} of the time")
    print(f"  \n  over an 8-hour day, that is {day_minutes:.0f} minutes of audio,")
    print(f"  against {ungated_day:.0f} without the gate.\n")

    for label, rate in (("live tier ", REALTIME_USD_PER_MIN), ("batch tier", BATCH_USD_PER_MIN)):
        gated = day_minutes * rate * 30
        raw = ungated_day * rate * 30
        print(f"  {label}   ${gated:7.2f}/month gated    ${raw:8.2f}/month ungated")

    data_mb = day_minutes * 60 * BYTES_PER_SECOND / 1e6
    print(f"\n  raw PCM upload  {data_mb:.0f} MB/day  ({data_mb * 30 / 1000:.1f} GB/month)")
    print(f"  as Opus at 24 kbps  {day_minutes * 60 * 3_000 / 1e6:.0f} MB/day"
          f"  ({day_minutes * 60 * 3_000 * 30 / 1e9:.1f} GB/month)")

    print("\n  One room, one part of one day. Run it in a pharmacy, in a meeting, at")
    print("  dinner and in a car before believing any of it.")


if __name__ == "__main__":
    raise SystemExit(main())
