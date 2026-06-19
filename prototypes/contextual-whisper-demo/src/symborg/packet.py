from dataclasses import dataclass, asdict
from typing import Literal, Optional, List
import time
import json

PacketType = Literal["anchor", "question", "counterpoint", "source", "sentence", "memory"]
Delivery = Literal["screen", "audio_whisper", "ar", "haptic", "assistive"]

@dataclass
class CognitivePacket:
    packet_type: PacketType
    cue: str
    confidence: float
    topic: str = "unknown"
    depth: int = 1
    delivery: Delivery = "screen"
    interruption_risk: str = "low"
    supporting_context: Optional[List[str]] = None
    created_at_ms: int = 0

    def __post_init__(self) -> None:
        if self.created_at_ms == 0:
            self.created_at_ms = int(time.time() * 1000)
        if self.supporting_context is None:
            self.supporting_context = []

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)
