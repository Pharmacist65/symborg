from __future__ import annotations

from .context import InteractionState
from .packet import CognitivePacket
from .quality import score_packet


def should_deliver(packet: CognitivePacket, state: InteractionState, min_score: float = 0.65) -> tuple[bool, list[str]]:
    """Return whether a packet should be delivered right now.

    This is the safety/attention gate. It is intentionally conservative.
    """

    reasons: list[str] = []
    if state.silence_requested:
        reasons.append("silence_requested")
    if state.user_is_speaking:
        reasons.append("user_is_speaking")
    if not state.gate_open:
        reasons.append("gate_closed")

    quality = score_packet(packet)
    if quality["total_score"] < min_score:
        reasons.append("below_min_quality_score")
    if "low_confidence" in quality["warnings"]:
        reasons.append("low_confidence")
    if "audio_cue_too_long" in quality["warnings"]:
        reasons.append("audio_cue_too_long")
    if "high_interruption_risk" in quality["warnings"]:
        reasons.append("high_interruption_risk")

    return (len(reasons) == 0, reasons)


def filter_deliverable_packets(
    packets: list[CognitivePacket],
    state: InteractionState,
    min_score: float = 0.65,
) -> tuple[list[CognitivePacket], list[dict]]:
    delivered: list[CognitivePacket] = []
    suppressed: list[dict] = []

    for packet in packets:
        ok, reasons = should_deliver(packet, state, min_score=min_score)
        if ok and len(delivered) < state.max_packets:
            delivered.append(packet)
        else:
            suppressed.append({
                "packet": packet.to_dict(),
                "reasons": reasons or ["max_packets_exceeded"],
            })

    return delivered, suppressed
