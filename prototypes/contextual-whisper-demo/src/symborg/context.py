from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Delivery = Literal["screen", "audio_whisper", "ar", "haptic", "assistive"]
UserSignal = Literal["none", "tap", "double_tap", "long_press", "swipe_up", "swipe_down", "source_check"]


@dataclass(slots=True)
class InteractionState:
    """Current delivery context.

    This is deliberately not a thought decoder. It is a practical model of
    whether a cue should be delivered right now.
    """

    user_is_speaking: bool = False
    pause_ms: int = 0
    user_signal: UserSignal = "none"
    delivery: Delivery = "screen"
    cognitive_load_estimate: float = 0.35
    max_packets: int = 3

    @property
    def silence_requested(self) -> bool:
        return self.user_signal == "long_press"

    @property
    def wants_depth(self) -> bool:
        return self.user_signal in {"double_tap", "swipe_up"}

    @property
    def wants_summary(self) -> bool:
        return self.user_signal == "swipe_down"

    @property
    def wants_source(self) -> bool:
        return self.user_signal == "source_check"

    @property
    def gate_open(self) -> bool:
        if self.silence_requested:
            return False
        if self.user_is_speaking:
            return False
        if self.delivery in {"audio_whisper", "ar"} and self.pause_ms < 550 and self.user_signal == "none":
            return False
        if self.cognitive_load_estimate >= 0.85 and self.user_signal == "none":
            return False
        return True
