"""The browser's gate and the engine's gate must agree.

They are two descriptions of the same decision — which audio is worth sending — written
in two languages because one runs on the phone and one runs on whatever the phone talks
to. If they drift, the phone and the engine disagree about what was said, and the bug
looks like a transcription problem rather than a threshold problem.

Skipped when node is not installed. That is a real gap rather than a pass, so it says so.
"""

from __future__ import annotations

import json
import math
import shutil
import struct
import subprocess
import tempfile
import unittest
from pathlib import Path

from symborg_engine.providers.vad import Gate

RATE = 24_000
BLOCK = int(RATE * 0.02)
JS_GATE = Path(__file__).resolve().parents[1] / "src" / "symborg_engine" / "ui" / "static" / "vad.js"


def _quiet(seconds: float, level: int = 40) -> list[int]:
    return [int(level * math.sin(i / 7.0)) for i in range(int(RATE * seconds))]


def _loud(seconds: float, level: int = 6000) -> list[int]:
    return [int(level * math.sin(i / 11.0)) for i in range(int(RATE * seconds))]


@unittest.skipUnless(shutil.which("node"), "node is not installed")
class TestBothGatesAgree(unittest.TestCase):
    def test_the_same_audio_gets_the_same_decisions(self):
        stream = (_quiet(3.0) + _loud(1.5) + _quiet(1.2) + _loud(0.8) + _quiet(4.0))
        blocks = [stream[i:i + BLOCK] for i in range(0, len(stream), BLOCK)]

        gate = Gate(sample_rate=RATE)
        expected = []
        for block in blocks:
            raw = b"".join(struct.pack("<h", max(-32768, min(32767, v))) for v in block)
            expected.append(1 if gate.filter(raw) else 0)

        with tempfile.TemporaryDirectory() as tmp:
            blocks_path = Path(tmp) / "blocks.json"
            blocks_path.write_text(json.dumps(blocks), encoding="utf-8")
            script = (
                f"import {{ readFileSync }} from 'fs';"
                f"const {{ Gate }} = await import('file://{JS_GATE}');"
                f"const blocks = JSON.parse(readFileSync({str(blocks_path)!r}));"
                f"const g = new Gate({RATE});"
                f"console.log(JSON.stringify(blocks.map(b => g.filter(Int16Array.from(b)) ? 1 : 0)));"
            )
            out = subprocess.run(["node", "--input-type=module", "-e", script],
                                 capture_output=True, text=True, timeout=60)
        self.assertEqual(out.returncode, 0, out.stderr)
        got = json.loads(out.stdout.strip().splitlines()[-1])

        self.assertEqual(len(got), len(expected))
        drifted = [i for i, (a, b) in enumerate(zip(expected, got)) if a != b]
        self.assertEqual(drifted, [], f"{len(drifted)} blocks disagree, first at {drifted[:5]}")
        self.assertGreater(sum(expected), 0)      # the audio has to exercise both states
        self.assertLess(sum(expected), len(expected))


class TestTheGatesAreDescribedTheSameWay(unittest.TestCase):
    """Cheap check that runs everywhere: the constants have to match, whatever node says.
    Two files that agree on behaviour today and disagree on their numbers will drift the
    moment either is tuned."""

    def test_the_thresholds_are_written_the_same(self):
        js = JS_GATE.read_text(encoding="utf-8")
        from symborg_engine.providers import vad
        for name, value in (("HANGOVER_MS", vad.SPEECH_HANGOVER_MS),
                            ("LEAD_IN_MS", vad.LEAD_IN_MS),
                            ("FRAME_MS", vad.FRAME_MS)):
            with self.subTest(name=name):
                self.assertIn(f"{name} = {value}", js)

    def test_the_ratios_are_written_the_same(self):
        js = JS_GATE.read_text(encoding="utf-8")
        from symborg_engine.providers import vad
        self.assertIn(f"FLOOR_ALPHA = {vad._FLOOR_ALPHA}", js)
        self.assertIn(f"SPEECH_OVER_FLOOR = {vad._SPEECH_OVER_FLOOR}", js)
        self.assertIn(f"MIN_FLOOR = {int(vad._MIN_FLOOR)}", js)


if __name__ == "__main__":
    unittest.main()
