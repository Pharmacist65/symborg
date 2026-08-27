"""Live microphone run: watch the gate fire while someone is still speaking.

Everything before this has been text — replayed fragments and sentences I wrote. This
is the first time the loop meets real speech, and the number it exists to produce is
the lead: how long before the speaker stopped that generation began.

    set -a; . ../../.env; set +a
    PYTHONPATH=src python3 bench/live.py

Speak in Turkish, pause, and watch. Ctrl+C to stop.

This sends microphone audio to a hosted transcription service and costs API time while
it runs, so do not leave it open. macOS will ask for microphone permission on the first
run.
"""

from __future__ import annotations

import argparse
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from symborg_engine import Session, drive  # noqa: E402
from symborg_engine.providers.realtime_stream import (  # noqa: E402
    MicrophoneSource, RealtimeTranscriptStream,
)

DIM, BOLD, GOLD, TEAL, RESET = "\033[2m", "\033[1m", "\033[33m", "\033[36m", "\033[0m"


def main() -> int:
    ap = argparse.ArgumentParser(description="Live microphone run.")
    ap.add_argument("--device", default=None, help="input device name or index")
    ap.add_argument("--eagerness", default="high", choices=["low", "medium", "high", "auto"])
    args = ap.parse_args()

    session = Session()
    provider = type(session.model).__name__
    if provider == "OfflineLanguageModel":
        print("Offline provider — candidates would be canned. Set a key first.", file=sys.stderr)
        return 1

    print(f"\n{BOLD}SYMBORG — live{RESET}")
    print(f"{DIM}transcription: gpt-live-transcribe   candidates: {session.model._model}{RESET}")
    print(f"{DIM}Speak Turkish, then pause. Ctrl+C to stop.{RESET}\n")

    leads: list[int] = []

    def on_turn(turn) -> None:
        print(f"\n{TEAL}heard{RESET}  {turn.partial}")
        if turn.anticipated:
            leads.append(turn.lead_ms)
            print(f"{GOLD}gate{RESET}   fired {turn.lead_ms} ms before you stopped "
                  f"{DIM}(generation overlapped your last words){RESET}")
        else:
            print(f"{DIM}gate   did not fire — generation began after silence{RESET}")
        if turn.result.is_empty:
            print(f"{DIM}       no candidates — staying silent{RESET}")
        for i, candidate in enumerate(turn.result.candidates):
            print(f"       [{i}] {candidate.text}")

    device = args.device
    if device is not None and device.isdigit():
        device = int(device)

    try:
        with MicrophoneSource(device=device) as mic:
            drive(session, RealtimeTranscriptStream(mic.blocks(), eagerness=args.eagerness),
                  on_turn=on_turn)
    except KeyboardInterrupt:
        pass
    except Exception as exc:
        print(f"\n{exc}", file=sys.stderr)
        return 1

    if leads:
        print(f"\n{BOLD}{len(leads)} anticipated turns{RESET}   "
              f"median lead {statistics.median(leads):.0f} ms   max {max(leads)} ms")
    else:
        print(f"\n{DIM}No turn was anticipated.{RESET}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
