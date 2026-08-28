"""The copilot: something that listens, remembers, and mostly says nothing."""

from __future__ import annotations

from .extract import extract
from .judge import Judgement, judge_moment
from .memory import KINDS, Memory, Recollection
from .salience import (
    DEFAULT_THRESHOLD, MAX_PER_MINUTE, MIN_GAP_S, Moment, Reason, SalienceGate, Verdict,
)

__all__ = [
    "SalienceGate", "Moment", "Verdict", "Reason",
    "judge_moment", "Judgement",
    "Memory", "Recollection", "extract", "KINDS",
    "MIN_GAP_S", "MAX_PER_MINUTE", "DEFAULT_THRESHOLD",
]
