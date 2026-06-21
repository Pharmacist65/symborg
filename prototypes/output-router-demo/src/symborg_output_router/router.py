from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, asdict
from typing import Any, Literal

Modality = Literal[
    "suppress",
    "haptic",
    "audio_whisper",
    "ar_card",
    "screen_card",
    "assistive_candidate",
    "neural_research_glyph",
]


@dataclass(frozen=True)
class CognitivePacket:
    packet_type: str
    cue: str
    confidence: float = 0.75
    topic: str = "unknown"
    expected_use: str = "think"
    cognitive_load: int = 2
    interruption_risk: str = "medium"

    @property
    def word_count(self) -> int:
        return len([w for w in self.cue.split() if w.strip()])


@dataclass(frozen=True)
class UserState:
    user_is_speaking: bool = False
    pause_ms: int = 900
    walking: bool = False
    driving: bool = False
    high_stress: bool = False
    silence_mode: bool = False
    assistive_mode: bool = False
    neural_research_mode: bool = False


@dataclass(frozen=True)
class DeviceCapabilities:
    has_audio: bool = True
    has_ar: bool = True
    has_haptics: bool = True
    has_screen: bool = True
    has_assistive_ui: bool = False
    has_neural_research_output: bool = False


@dataclass(frozen=True)
class RouteDecision:
    modality: Modality
    render_text: str
    reason: str
    suppressed: bool = False


def packet_from_dict(data: dict[str, Any]) -> CognitivePacket:
    return CognitivePacket(
        packet_type=str(data.get("packet_type", data.get("type", "anchor"))),
        cue=str(data.get("cue", "")),
        confidence=float(data.get("confidence", 0.75)),
        topic=str(data.get("topic", "unknown")),
        expected_use=str(data.get("expected_use", "think")),
        cognitive_load=int(data.get("cognitive_load", 2)),
        interruption_risk=str(data.get("interruption_risk", "medium")),
    )


def route_packet(
    packet: CognitivePacket,
    state: UserState | None = None,
    devices: DeviceCapabilities | None = None,
) -> RouteDecision:
    """Choose the safest and most useful output modality for a cognitive packet."""
    state = state or UserState()
    devices = devices or DeviceCapabilities()

    if not packet.cue.strip():
        return RouteDecision("suppress", "", "empty cue", True)

    if state.silence_mode:
        return RouteDecision("suppress", "", "silence mode is active", True)

    if state.driving:
        if devices.has_haptics and packet.packet_type in {"warning", "navigation"}:
            return RouteDecision("haptic", "urgent haptic pulse", "driving mode allows only minimal haptic alerts")
        return RouteDecision("suppress", "", "driving mode suppresses cognitive output", True)

    if packet.confidence < 0.55:
        return RouteDecision("suppress", "", "confidence below threshold", True)

    if state.user_is_speaking:
        if devices.has_haptics and packet.packet_type in {"warning", "assistive_candidate"}:
            return RouteDecision("haptic", "soft haptic pulse", "user is speaking; haptic status only")
        return RouteDecision("suppress", "", "user is speaking", True)

    if state.pause_ms < 350 and packet.packet_type != "warning":
        return RouteDecision("suppress", "", "pause too short for safe delivery", True)

    if packet.word_count > 25 and packet.packet_type != "assistive_candidate":
        return RouteDecision("suppress", "", "cue too long for live delivery", True)

    if packet.packet_type == "assistive_candidate":
        if state.assistive_mode and devices.has_assistive_ui:
            return RouteDecision("assistive_candidate", packet.cue, "assistive mode prefers selectable sentence candidates")
        if devices.has_screen:
            return RouteDecision("screen_card", packet.cue, "assistive candidates require a confirmable UI")
        return RouteDecision("suppress", "", "assistive candidate has no confirmable output surface", True)

    if state.assistive_mode and devices.has_assistive_ui:
        return RouteDecision("assistive_candidate", packet.cue, "assistive mode prefers selectable sentence candidates")

    if state.neural_research_mode and devices.has_neural_research_output:
        glyph = neural_glyph_for(packet)
        return RouteDecision("neural_research_glyph", glyph, "research mode maps packet to symbolic perceptual glyph")

    if state.walking:
        if devices.has_audio and packet.word_count <= 14:
            return RouteDecision("audio_whisper", packet.cue, "walking prefers audio over visual attention")
        if devices.has_haptics:
            return RouteDecision("haptic", "packet-ready pulse", "walking with long cue uses haptic prompt")

    if packet.packet_type == "warning" and devices.has_haptics:
        return RouteDecision("haptic", "two soft pulses", "warning packets default to low-distraction haptic cue")

    if devices.has_ar and packet.word_count <= 20 and packet.interruption_risk in {"low", "medium"}:
        return RouteDecision("ar_card", packet.cue, "AR can show a short peripheral card")

    if devices.has_audio and packet.word_count <= 14:
        return RouteDecision("audio_whisper", packet.cue, "audio can deliver a short private cue")

    if devices.has_screen:
        return RouteDecision("screen_card", packet.cue, "screen card selected as safest available output surface")

    return RouteDecision("suppress", "", "no safe output modality available", True)


def neural_glyph_for(packet: CognitivePacket) -> str:
    """Return a symbolic placeholder for a future neural-write research output.

    This is not stimulation code. It is a conceptual glyph label for simulations.
    """
    if packet.packet_type == "warning":
        return "glyph:two_dim_pulses"
    if packet.packet_type == "question":
        return "glyph:curved_trace"
    if packet.packet_type == "assistive_candidate":
        return "glyph:selectable_dot_cluster"
    return "glyph:single_anchor_pulse"


def main() -> None:
    parser = argparse.ArgumentParser(description="Route SYMBORG cognitive packets to output modalities.")
    parser.add_argument("json_file")
    parser.add_argument("--speaking", action="store_true")
    parser.add_argument("--walking", action="store_true")
    parser.add_argument("--driving", action="store_true")
    parser.add_argument("--silence", action="store_true")
    parser.add_argument("--assistive", action="store_true")
    parser.add_argument("--neural-research", action="store_true")
    args = parser.parse_args()

    with open(args.json_file, "r", encoding="utf-8") as f:
        raw_packets = json.load(f)

    state = UserState(
        user_is_speaking=args.speaking,
        walking=args.walking,
        driving=args.driving,
        silence_mode=args.silence,
        assistive_mode=args.assistive,
        neural_research_mode=args.neural_research,
    )
    devices = DeviceCapabilities(
        has_assistive_ui=args.assistive,
        has_neural_research_output=args.neural_research,
    )

    decisions = []
    for item in raw_packets:
        packet = packet_from_dict(item)
        decision = route_packet(packet, state, devices)
        decisions.append({"packet": asdict(packet), "route": asdict(decision)})

    print(json.dumps(decisions, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
