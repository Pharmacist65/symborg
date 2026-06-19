from __future__ import annotations

import argparse
import json
from pathlib import Path

from .context import InteractionState
from .delivery_gate import filter_deliverable_packets
from .packet import CognitivePacket
from .quality import rank_packets, score_packet, summarize_scores


TOPIC_LIBRARY: dict[str, list[dict]] = {
    "great expectations": [
        {
            "packet_type": "anchor",
            "cue": "Pip = shame + class desire + guilt.",
            "confidence": 0.88,
            "topic": "Great Expectations",
            "expected_use": "think",
            "supporting_context": ["Pip", "shame", "class desire", "guilt"],
        },
        {
            "packet_type": "question",
            "cue": "Ask if Pip wants Estella or the class world she represents.",
            "confidence": 0.84,
            "topic": "Great Expectations",
            "expected_use": "ask",
            "supporting_context": ["Pip", "Estella", "class world"],
        },
        {
            "packet_type": "counterpoint",
            "cue": "Maybe class and shame are not separate; class pressure produces the shame.",
            "confidence": 0.80,
            "topic": "Great Expectations",
            "expected_use": "say",
            "supporting_context": ["class anxiety", "shame"],
        },
    ],
    "dickens": [
        {
            "packet_type": "anchor",
            "cue": "Dickens turns social systems into personal moral pressure.",
            "confidence": 0.78,
            "topic": "Charles Dickens",
            "expected_use": "think",
            "supporting_context": ["Victorian society", "class", "poverty", "morality"],
        },
        {
            "packet_type": "question",
            "cue": "Ask how private guilt connects to public class structure.",
            "confidence": 0.76,
            "topic": "Charles Dickens",
            "expected_use": "ask",
            "supporting_context": ["guilt", "class structure"],
        },
    ],
    "clinical pain": [
        {
            "packet_type": "sentence",
            "cue": "My pain is worse at night and I need help changing position.",
            "confidence": 0.82,
            "topic": "Assistive clinical communication",
            "delivery": "assistive",
            "expected_use": "choose",
            "supporting_context": ["pain", "night", "position"],
        },
        {
            "packet_type": "sentence",
            "cue": "I want to explain where the pain is before changing medication.",
            "confidence": 0.74,
            "topic": "Assistive clinical communication",
            "delivery": "assistive",
            "expected_use": "choose",
            "supporting_context": ["pain", "medication", "clarify"],
        },
    ],
    "startup meeting": [
        {
            "packet_type": "anchor",
            "cue": "Clarify user, pain, frequency, and willingness to pay.",
            "confidence": 0.79,
            "topic": "Startup meeting",
            "expected_use": "think",
            "supporting_context": ["user", "pain", "frequency", "willingness to pay"],
        },
        {
            "packet_type": "question",
            "cue": "Ask which problem is urgent enough to change behavior this week.",
            "confidence": 0.81,
            "topic": "Startup meeting",
            "expected_use": "ask",
            "supporting_context": ["urgency", "behavior change"],
        },
        {
            "packet_type": "counterpoint",
            "cue": "A cool feature is not a product until it owns a repeated pain.",
            "confidence": 0.77,
            "topic": "Startup meeting",
            "expected_use": "say",
            "supporting_context": ["feature", "product", "repeated pain"],
        },
    ],
}

KEYWORD_ALIASES: dict[str, list[str]] = {
    "great expectations": ["great expectations", "pip", "estella", "miss havisham"],
    "dickens": ["dickens", "victorian novel", "oliver twist"],
    "clinical pain": ["pain", "doctor", "nurse", "position", "medication", "clinic"],
    "startup meeting": ["startup", "mvp", "customer", "pricing", "investor", "product"],
}

DEFAULT_PACKETS = [
    CognitivePacket(
        packet_type="question",
        cue="Ask for the central tension: facts, values, identity, or action?",
        confidence=0.58,
        topic="unknown",
        expected_use="ask",
        source_basis=["generic_conversation_strategy"],
    )
]


def detect_topic(text: str) -> str:
    lower = text.lower()
    scores: dict[str, int] = {}
    for topic, aliases in KEYWORD_ALIASES.items():
        score = sum(1 for alias in aliases if alias in lower)
        # The word "pain" is broad; require a stronger clinical context unless
        # another clinical keyword also appears.
        if topic == "clinical pain" and "pain" in lower and score == 1:
            score = 0
        if score:
            scores[topic] = score
    if not scores:
        return "unknown"
    return max(scores.items(), key=lambda item: item[1])[0]


def build_packets(topic: str, delivery: str = "screen", deepen: bool = False) -> list[CognitivePacket]:
    if topic == "unknown":
        packets = DEFAULT_PACKETS
    else:
        packets = [
            CognitivePacket(
                delivery=item.get("delivery", delivery),
                depth=2 if deepen else 1,
                cognitive_load=3 if deepen else 2,
                source_basis=["conversation_context", "heuristic_topic_library"],
                **{k: v for k, v in item.items() if k != "delivery"},
            )
            for item in TOPIC_LIBRARY[topic]
        ]
    # Respect requested delivery unless the packet explicitly needs assistive mode.
    normalized: list[CognitivePacket] = []
    for packet in packets:
        if packet.delivery != "assistive":
            packet.delivery = delivery  # type: ignore[assignment]
        normalized.append(packet)
    return normalized


def generate_packets(
    text: str,
    state: InteractionState | None = None,
    min_score: float = 0.65,
) -> dict:
    if state is None:
        state = InteractionState()

    topic = detect_topic(text)
    candidates = build_packets(topic, delivery=state.delivery, deepen=state.wants_depth)
    ranked = rank_packets(candidates)
    delivered, suppressed = filter_deliverable_packets(ranked, state, min_score=min_score)

    return {
        "topic": topic,
        "state": {
            "user_is_speaking": state.user_is_speaking,
            "pause_ms": state.pause_ms,
            "user_signal": state.user_signal,
            "delivery": state.delivery,
            "cognitive_load_estimate": state.cognitive_load_estimate,
            "gate_open": state.gate_open,
        },
        "delivered": [
            {"packet": packet.to_dict(), "score": score_packet(packet)} for packet in delivered
        ],
        "suppressed": suppressed,
        "summary": summarize_scores(ranked),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate SYMBORG cognitive packets from a transcript.")
    parser.add_argument("transcript", type=Path, help="Path to a transcript text file.")
    parser.add_argument("--delivery", choices=["screen", "audio_whisper", "ar", "haptic", "assistive"], default="screen")
    parser.add_argument("--pause-ms", type=int, default=0, help="Detected pause length before delivery.")
    parser.add_argument("--user-speaking", action="store_true", help="Suppress delivery as if the user is speaking.")
    parser.add_argument("--signal", choices=["none", "tap", "double_tap", "long_press", "swipe_up", "swipe_down", "source_check"], default="none")
    parser.add_argument("--cognitive-load", type=float, default=0.35)
    parser.add_argument("--min-score", type=float, default=0.65)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    text = args.transcript.read_text(encoding="utf-8")
    state = InteractionState(
        user_is_speaking=args.user_speaking,
        pause_ms=args.pause_ms,
        user_signal=args.signal,
        delivery=args.delivery,
        cognitive_load_estimate=args.cognitive_load,
    )
    result = generate_packets(text, state=state, min_score=args.min_score)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
