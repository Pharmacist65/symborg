"""Two tiers: what runs near the person, and what is worth sending away.

The work this engine does is not one kind of work. Most of it is constant, shallow and
enormous in volume — every turn of every conversation gets classified, sifted, and thrown
away. A little of it is rare, deep and precise: *who was that man*, and the answer has to
be right.

Sending both to the same hosted model means paying deep-model prices for the shallow
ninety-five per cent, all day, forever. That is the whole of the cost problem.

So each prompt declares which kind it is, and a router decides where it goes. Today both
tiers can point at the same hosted model and nothing changes except that the split becomes
visible and measurable — which is the point of building it before there is a local model
to put behind it. When one arrives it is a constructor argument, not a rewrite.

    engine = TieredModel(near=LocalModel(), far=OpenAILanguageModel())

The names are deliberate. "Local" and "cloud" describe where a thing runs, which is an
implementation detail that will change; near and far describe how much of the person's day
passes through it, which is what actually decides the tier.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from .base import LanguageModel, Prompt, ProviderError

__all__ = ["Tier", "TieredModel", "Ledger"]


class Tier(str, Enum):
    NEAR = "near"
    """Runs constantly, on nearly everything heard.

    Classification, sifting, deciding what a sentence even is. Shallow work whose cost is
    dominated by how often it happens rather than by how hard it is, and where being
    occasionally wrong is survivable because the salience gate stands behind it. This is
    what a small model on the device is for.
    """

    FAR = "far"
    """Runs rarely, when the answer has to be right.

    The question a person actually asked, a photograph they are about to act on, a
    contradiction that will be spoken aloud in their ear. Worth a hosted model precisely
    because it is rare — a few times an hour rather than a few times a minute.
    """


@dataclass(slots=True)
class Ledger:
    """What went where. The number that decides whether a local model is worth having."""

    near_calls: int = 0
    far_calls: int = 0
    near_chars: int = 0
    far_chars: int = 0
    fallbacks: int = 0
    """Near calls that failed and were retried far. A rising count means the near model is
    not carrying its share, and the saving is imaginary."""

    def record(self, tier: Tier, prompt: Prompt) -> None:
        size = len(prompt.system) + len(prompt.user)
        if tier is Tier.NEAR:
            self.near_calls += 1
            self.near_chars += size
        else:
            self.far_calls += 1
            self.far_chars += size

    @property
    def total_calls(self) -> int:
        return self.near_calls + self.far_calls

    @property
    def near_share(self) -> float:
        """How much of the day never needed to leave. Zero until measured."""
        return self.near_calls / self.total_calls if self.total_calls else 0.0

    def to_dict(self) -> dict:
        return {"near_calls": self.near_calls, "far_calls": self.far_calls,
                "near_chars": self.near_chars, "far_chars": self.far_chars,
                "fallbacks": self.fallbacks, "near_share": round(self.near_share, 3)}

    def reset(self) -> None:
        self.near_calls = self.far_calls = 0
        self.near_chars = self.far_chars = 0
        self.fallbacks = 0


@dataclass(slots=True)
class TieredModel:
    """Sends each prompt to the tier it asked for.

        model = TieredModel(near=small, far=big)

    With only one model given, both tiers use it and the ledger still counts — so the
    split can be measured on a real day before anything is bought or installed.
    """

    far: LanguageModel
    near: LanguageModel | None = None
    fall_back: bool = True
    """Whether a failing near model retries far.

    On by default: a small model that cannot answer should cost a slower answer, not a
    silent one. Turn it off to find out how much the near tier can really carry — with
    the fallback on, a near model that fails every call looks exactly like one that works.
    """

    ledger: Ledger = field(default_factory=Ledger)

    def complete(self, prompt: Prompt) -> str:
        tier = _tier_of(prompt)
        if tier is Tier.NEAR and self.near is not None:
            self.ledger.record(Tier.NEAR, prompt)
            try:
                return self.near.complete(prompt)
            except ProviderError:
                if not self.fall_back:
                    raise
                self.ledger.fallbacks += 1
                self.ledger.record(Tier.FAR, prompt)
                return self.far.complete(prompt)

        # No near model, or the prompt asked for depth. Either way it goes far, and the
        # ledger records it as far — a near-tier prompt that had nowhere near to go did
        # not save anything, and counting it as a saving would be lying to ourselves.
        self.ledger.record(Tier.FAR, prompt)
        return self.far.complete(prompt)


def _tier_of(prompt: Prompt) -> Tier:
    """Read a prompt's tier.

    The prompt carries a plain string so :mod:`base` stays stdlib-only, which means it has
    to be converted rather than compared — ``"near" is Tier.NEAR`` is false even though
    ``"near" == Tier.NEAR`` is true, and the identity check silently sent every near-tier
    call far while reporting a perfect saving of zero.
    """
    raw = getattr(prompt, "tier", None)
    if isinstance(raw, Tier):
        return raw
    try:
        return Tier(str(raw).strip().lower())
    except ValueError:
        return Tier.FAR       # an unknown tier is not a licence to use a smaller model
