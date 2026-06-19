import sys
import json
from pathlib import Path
from .packet import CognitivePacket

TOPIC_PACKETS = {
    "great expectations": [
        CognitivePacket(
            packet_type="anchor",
            cue="Pip's class desire is tied to shame, guilt, and self-escape.",
            confidence=0.86,
            topic="Great Expectations",
            supporting_context=["Pip", "shame", "class desire", "guilt"],
        ),
        CognitivePacket(
            packet_type="question",
            cue="Ask whether Pip wants Estella, or the class world she represents.",
            confidence=0.82,
            topic="Great Expectations",
            supporting_context=["Estella", "class", "desire"],
        ),
        CognitivePacket(
            packet_type="counterpoint",
            cue="Maybe class and shame are not separate; class pressure produces the shame.",
            confidence=0.80,
            topic="Great Expectations",
            supporting_context=["class anxiety", "shame"],
        ),
    ],
    "dickens": [
        CognitivePacket(
            packet_type="anchor",
            cue="Dickens often turns social systems into personal moral pressure.",
            confidence=0.78,
            topic="Charles Dickens",
            supporting_context=["Victorian society", "class", "poverty", "morality"],
        ),
        CognitivePacket(
            packet_type="question",
            cue="Ask how the novel connects private guilt to public class structure.",
            confidence=0.76,
            topic="Charles Dickens",
            supporting_context=["guilt", "class structure"],
        ),
    ],
}

DEFAULT_PACKETS = [
    CognitivePacket(
        packet_type="question",
        cue="Ask for the central tension: is this about facts, values, or identity?",
        confidence=0.55,
        topic="unknown",
    )
]


def detect_topic(text: str) -> str:
    lower = text.lower()
    for topic in TOPIC_PACKETS:
        if topic in lower:
            return topic
    return "unknown"


def generate_packets(text: str):
    topic = detect_topic(text)
    if topic == "unknown":
        return DEFAULT_PACKETS
    return TOPIC_PACKETS[topic]


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python -m symborg.heuristic_engine <transcript.txt>")
        raise SystemExit(1)

    path = Path(sys.argv[1])
    text = path.read_text(encoding="utf-8")
    packets = generate_packets(text)
    print(json.dumps([p.to_dict() for p in packets], ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
