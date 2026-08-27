"""Live microphone run, with enough feedback to tell working from broken.

Everything before this was text. This is where the loop meets real speech, and the
number it exists to produce is the lead: how long before the speaker stopped that
generation began.

    set -a; . ../../.env; set +a
    PYTHONPATH=src python3 bench/live.py

Speak Turkish, then pause for about two seconds. Ctrl+C to stop.

Sends microphone audio to a hosted transcription service and costs API time while it
runs, so do not leave it open. macOS asks for microphone permission on first run.
"""

from __future__ import annotations

import argparse
import array
import math
import statistics
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from symborg_engine import Session, drive  # noqa: E402
from symborg_engine.providers.realtime_stream import (  # noqa: E402
    MicrophoneSource, RealtimeTranscriptStream,
)

DIM, BOLD, GOLD, TEAL, RED, RESET = (
    "\033[2m", "\033[1m", "\033[33m", "\033[36m", "\033[31m", "\033[0m")
CLEAR = "\033[2K\r"


def _rms(block: bytes) -> int:
    samples = array.array("h")
    samples.frombytes(block)
    if not samples:
        return 0
    return int(math.sqrt(sum(v * v for v in samples) / len(samples)))


class Meter:
    """Shows that audio is arriving, so silence reads as silence and not as failure."""

    def __init__(self) -> None:
        self.level = 0
        self.blocks = 0
        self.peak = 0
        self._stop = threading.Event()
        self._line = ""

    def wrap(self, blocks):
        for block in blocks:
            self.level = _rms(block)
            self.peak = max(self.peak, self.level)
            self.blocks += 1
            yield block

    def start(self) -> None:
        threading.Thread(target=self._run, daemon=True).start()

    def stop(self) -> None:
        self._stop.set()
        sys.stdout.write(CLEAR)
        sys.stdout.flush()

    def say(self, text: str) -> None:
        """Print above the meter without the meter overwriting it."""
        sys.stdout.write(CLEAR + text + "\n")
        sys.stdout.flush()

    def _run(self) -> None:
        while not self._stop.wait(0.12):
            bars = min(28, self.level // 40)
            colour = TEAL if self.level > 60 else DIM
            sys.stdout.write(
                f"{CLEAR}{DIM}mic{RESET} {colour}{'▌' * bars}{'·' * (28 - bars)}{RESET} "
                f"{DIM}{self.level:5d}  {self.blocks} blok{RESET}"
            )
            sys.stdout.flush()


def main() -> int:
    ap = argparse.ArgumentParser(description="Live microphone run.")
    ap.add_argument("--device", default=None, help="input device name or index")
    ap.add_argument("--gap", type=int, default=None, help="silence in ms that ends a turn")
    args = ap.parse_args()

    session = Session()
    if type(session.model).__name__ == "OfflineLanguageModel":
        print("Offline provider — candidates would be canned. Set a key first.", file=sys.stderr)
        return 1

    print(f"\n{BOLD}SYMBORG — live{RESET}")
    print(f"{DIM}transcription: gpt-live-transcribe   candidates: {session.model._model}{RESET}")
    print(f"{DIM}Speak Turkish, then pause ~2s. Ctrl+C to stop.{RESET}\n")

    meter = Meter()
    leads: list[int] = []
    started = time.time()

    def on_fragment(fragment, fired: bool) -> None:
        meter.say(f"{DIM}…{RESET} {fragment.text}"
                  + (f"   {GOLD}◀ KAPI AÇILDI{RESET}" if fired else ""))

    def on_turn(turn) -> None:
        meter.say("")
        meter.say(f"{TEAL}duyulan{RESET}  {turn.partial}")
        if turn.anticipated:
            leads.append(turn.lead_ms)
            meter.say(f"{GOLD}önden{RESET}    {turn.lead_ms} ms "
                      f"{DIM}(üretim sen konuşurken başladı){RESET}")
        else:
            meter.say(f"{DIM}önden    — kapı ateşlemedi{RESET}")
        if turn.result.is_empty:
            meter.say(f"{DIM}         aday yok — susuyor{RESET}")
        for i, candidate in enumerate(turn.result.candidates):
            meter.say(f"         [{i}] {candidate.text}")
        meter.say("")

    device = args.device
    if device is not None and device.isdigit():
        device = int(device)

    kwargs = {"turn_gap_ms": args.gap} if args.gap else {}

    try:
        with MicrophoneSource(device=device) as mic:
            meter.start()
            stream = RealtimeTranscriptStream(meter.wrap(mic.blocks()), **kwargs)
            drive(session, stream, on_turn=on_turn, on_fragment=on_fragment)
    except KeyboardInterrupt:
        pass
    except Exception as exc:
        meter.stop()
        print(f"\n{RED}{type(exc).__name__}: {exc}{RESET}", file=sys.stderr)
        return 1
    finally:
        meter.stop()

    elapsed = time.time() - started
    print(f"\n{BOLD}{elapsed:.0f} s{RESET}   {meter.blocks} audio blocks   peak level {meter.peak}")
    if meter.peak < 60:
        print(f"{RED}The microphone never picked up speech (peak {meter.peak}).{RESET}")
        print(f"{DIM}Check System Settings → Privacy → Microphone, and the input level.{RESET}")
    if leads:
        print(f"{BOLD}{len(leads)} anticipated turns{RESET}   "
              f"median lead {statistics.median(leads):.0f} ms")
    else:
        print(f"{DIM}No turn was anticipated.{RESET}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
