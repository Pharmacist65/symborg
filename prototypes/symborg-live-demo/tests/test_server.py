from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest


SERVER_PATH = Path(__file__).resolve().parents[1] / "server.py"
SPEC = importlib.util.spec_from_file_location("symborg_live_demo_server", SERVER_PATH)
assert SPEC and SPEC.loader
server = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(server)


class LiveDemoServerTests(unittest.TestCase):
    def test_dickens_pipeline_returns_screen_routed_packet(self) -> None:
        result = server.analyze({
            "scenario": "dickens",
            "pause_ms": 900,
            "delivery": "screen",
            "has_audio": False,
            "has_ar": False,
            "has_haptics": False,
            "has_screen": True,
        })

        self.assertEqual(result["topic"], "great expectations")
        self.assertGreaterEqual(len(result["delivered"]), 1)
        self.assertEqual(result["delivered"][0]["route"]["modality"], "screen_card")

    def test_assistive_scenario_prefers_sentence_candidate_ui(self) -> None:
        result = server.analyze({
            "scenario": "clinical",
            "pause_ms": 900,
            "delivery": "assistive",
            "assistive_mode": True,
            "has_assistive_ui": True,
            "has_screen": True,
        })

        self.assertEqual(result["topic"], "clinical pain")
        self.assertGreaterEqual(len(result["delivered"]), 1)
        self.assertEqual(result["delivered"][0]["route"]["modality"], "assistive_candidate")

    def test_gate_suppresses_output_while_user_is_speaking(self) -> None:
        result = server.analyze({
            "scenario": "meeting",
            "pause_ms": 900,
            "delivery": "audio_whisper",
            "user_is_speaking": True,
        })

        self.assertEqual(result["delivered"], [])
        self.assertTrue(result["suppressed"])
        self.assertIn("user_is_speaking", result["suppressed"][0]["reasons"])


if __name__ == "__main__":
    unittest.main()
