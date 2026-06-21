import unittest

from symborg_output_router.router import (
    CognitivePacket,
    DeviceCapabilities,
    UserState,
    route_packet,
)


class OutputRouterTests(unittest.TestCase):
    def test_suppresses_when_silence_mode_active(self):
        packet = CognitivePacket(packet_type="anchor", cue="Pip equals shame and class desire.")
        decision = route_packet(packet, UserState(silence_mode=True))
        self.assertTrue(decision.suppressed)
        self.assertEqual(decision.modality, "suppress")

    def test_user_speaking_suppresses_normal_packet(self):
        packet = CognitivePacket(packet_type="question", cue="Ask if Pip wants Estella.")
        decision = route_packet(packet, UserState(user_is_speaking=True))
        self.assertTrue(decision.suppressed)

    def test_assistive_mode_prefers_candidate_ui(self):
        packet = CognitivePacket(packet_type="assistive_candidate", cue="I need help changing my position.")
        decision = route_packet(
            packet,
            UserState(assistive_mode=True),
            DeviceCapabilities(has_assistive_ui=True),
        )
        self.assertEqual(decision.modality, "assistive_candidate")

    def test_assistive_candidate_falls_back_to_confirmable_screen(self):
        packet = CognitivePacket(packet_type="assistive_candidate", cue="I need help changing my position.")
        decision = route_packet(packet, UserState(), DeviceCapabilities(has_screen=True))
        self.assertEqual(decision.modality, "screen_card")
        self.assertIn("confirmable", decision.reason)

    def test_walking_prefers_short_audio(self):
        packet = CognitivePacket(packet_type="anchor", cue="Pip links shame and class desire.")
        decision = route_packet(packet, UserState(walking=True))
        self.assertEqual(decision.modality, "audio_whisper")

    def test_neural_research_mode_returns_glyph(self):
        packet = CognitivePacket(packet_type="question", cue="Ask if Estella represents class.")
        decision = route_packet(
            packet,
            UserState(neural_research_mode=True),
            DeviceCapabilities(has_neural_research_output=True),
        )
        self.assertEqual(decision.modality, "neural_research_glyph")
        self.assertIn("glyph", decision.render_text)


if __name__ == "__main__":
    unittest.main()
