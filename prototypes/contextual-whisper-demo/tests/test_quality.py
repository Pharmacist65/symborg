import unittest

from symborg.context import InteractionState
from symborg.delivery_gate import should_deliver
from symborg.heuristic_engine import detect_topic, generate_packets
from symborg.packet import CognitivePacket
from symborg.quality import score_packet


class TestPacketQuality(unittest.TestCase):
    def test_detects_great_expectations(self):
        self.assertEqual(detect_topic("Pip and Estella in Great Expectations"), "great expectations")

    def test_short_question_scores_well(self):
        packet = CognitivePacket(
            packet_type="question",
            cue="Ask if ambition is really self-escape.",
            confidence=0.82,
            topic="Great Expectations",
            delivery="audio_whisper",
            expected_use="ask",
        )
        score = score_packet(packet)
        self.assertGreaterEqual(score["total_score"], 0.70)
        self.assertEqual(score["warnings"], [])

    def test_user_speaking_suppresses_delivery(self):
        packet = CognitivePacket(packet_type="anchor", cue="Pip = shame + class desire.", confidence=0.8)
        state = InteractionState(user_is_speaking=True, pause_ms=1000, delivery="audio_whisper")
        ok, reasons = should_deliver(packet, state)
        self.assertFalse(ok)
        self.assertIn("user_is_speaking", reasons)

    def test_long_audio_cue_warns(self):
        packet = CognitivePacket(
            packet_type="anchor",
            cue="This is a very long audio whisper that should probably not be delivered because it competes with working memory and live attention.",
            confidence=0.9,
            delivery="audio_whisper",
        )
        self.assertIn("audio_cue_too_long", packet.validation_warnings())

    def test_generation_respects_silence(self):
        state = InteractionState(user_signal="long_press", pause_ms=1000, delivery="audio_whisper")
        result = generate_packets("Great Expectations and Pip", state=state)
        self.assertEqual(len(result["delivered"]), 0)
        self.assertGreaterEqual(len(result["suppressed"]), 1)


if __name__ == "__main__":
    unittest.main()
