from __future__ import annotations

from statistics import mean

from .packet import CognitivePacket

ACTION_WORDS = {
    "ask", "compare", "contrast", "say", "frame", "mention", "check", "verify",
    "question", "connect", "challenge", "choose", "select", "answer"
}


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def brevity_score(packet: CognitivePacket) -> float:
    words = packet.word_count
    if packet.delivery == "audio_whisper":
        target_max = 18
        target_min = 4
    elif packet.delivery == "assistive":
        target_max = 22
        target_min = 3
    else:
        target_max = 25
        target_min = 4

    if words < target_min:
        return clamp(words / target_min)
    if words <= target_max:
        return 1.0
    # Penalize long cues progressively, but not catastrophically.
    return clamp(1.0 - ((words - target_max) / target_max))


def actionability_score(packet: CognitivePacket) -> float:
    cue = packet.cue.lower()
    score = 0.25
    if packet.packet_type in {"question", "counterpoint", "sentence"}:
        score += 0.25
    if any(word in cue for word in ACTION_WORDS):
        score += 0.25
    if "?" in cue or cue.startswith("ask"):
        score += 0.15
    if any(marker in cue for marker in ["=", ":", "+", "->"]):
        score += 0.10
    return clamp(score)


def interruption_score(packet: CognitivePacket) -> float:
    return {"low": 1.0, "medium": 0.6, "high": 0.15}.get(packet.interruption_risk, 0.5)


def cognitive_load_score(packet: CognitivePacket) -> float:
    # cognitive_load is 1 easiest, 5 hardest.
    return clamp(1.15 - (packet.cognitive_load * 0.20))


def score_packet(packet: CognitivePacket) -> dict:
    b = brevity_score(packet)
    a = actionability_score(packet)
    c = packet.confidence
    i = interruption_score(packet)
    l = cognitive_load_score(packet)
    total = (0.25 * b) + (0.25 * a) + (0.20 * c) + (0.15 * i) + (0.15 * l)
    warnings = packet.validation_warnings()
    if total < 0.65:
        warnings.append("low_total_score")
    return {
        "word_count": packet.word_count,
        "brevity_score": round(b, 3),
        "actionability_score": round(a, 3),
        "confidence_score": round(c, 3),
        "interruption_score": round(i, 3),
        "cognitive_load_score": round(l, 3),
        "total_score": round(total, 3),
        "warnings": warnings,
    }


def packet_sort_key(packet: CognitivePacket) -> tuple[float, float, float]:
    score = score_packet(packet)["total_score"]
    # Prefer questions/anchors in live conversation when scores are close.
    type_bias = {"question": 0.03, "anchor": 0.02, "counterpoint": 0.01}.get(packet.packet_type, 0.0)
    return (score + type_bias, packet.confidence, -packet.word_count)


def rank_packets(packets: list[CognitivePacket]) -> list[CognitivePacket]:
    return sorted(packets, key=packet_sort_key, reverse=True)


def summarize_scores(packets: list[CognitivePacket]) -> dict:
    if not packets:
        return {
            "packet_count": 0,
            "mean_score": 0.0,
            "best_packet_type": None,
            "silence_was_better": True,
        }
    scored = [score_packet(packet) for packet in packets]
    best = rank_packets(packets)[0]
    return {
        "packet_count": len(packets),
        "mean_score": round(mean(s["total_score"] for s in scored), 3),
        "best_packet_type": best.packet_type,
        "best_topic": best.topic,
        "silence_was_better": all(s["total_score"] < 0.65 for s in scored),
    }
