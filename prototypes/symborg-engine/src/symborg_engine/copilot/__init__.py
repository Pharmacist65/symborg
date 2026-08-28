"""The copilot: something that listens, remembers, and mostly says nothing."""

from __future__ import annotations

from .extract import extract
from .judge import Judgement, decide, judge_moment
from .contradiction import Mismatch, check
from .memory import KINDS, Memory, Recollection
from .session import Copilot, Heard
from .translate import Rendering, Translator
from .salience import (
    DEFAULT_THRESHOLD, MAX_PER_MINUTE, MIN_GAP_S, Moment, Reason, SalienceGate, Verdict,
)

__all__ = [
    "SalienceGate", "Moment", "Verdict", "Reason",
    "judge_moment", "Judgement",
    "Memory", "Recollection", "extract", "KINDS",
    "Copilot", "Heard", "Mismatch", "check", "decide",
    "Translator", "Rendering",
    "MIN_GAP_S", "MAX_PER_MINUTE", "DEFAULT_THRESHOLD",
]
