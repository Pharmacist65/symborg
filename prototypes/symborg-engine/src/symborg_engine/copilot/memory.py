"""What it keeps, and what it lets go.

The difference between a recording and a memory is selection, and selection is
personal. A device that stores every word is a transcript with a search box — cheap to
build, and not what anyone means when they say they want to be remembered for.

So nothing is kept because it was said. Things are kept because they will still matter
later: a date, a number, a name, a promise, a decision. Everything else is heard,
used in the moment, and allowed to go — which is also what makes the store small
enough to live on the person's own device and be read by them.

Retrieval is deliberately plain: token overlap, recency-weighted. No embeddings, no
index, no service. It is good enough to answer "what was that name" and it costs
nothing, and when it stops being good enough the interface it sits behind will not
have to change.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

__all__ = ["Recollection", "Memory", "KINDS", "MAX_ITEMS"]

KINDS = ("fact", "date", "person", "place", "number", "commitment", "decision",
         "preference")
"""What is worth keeping. Everything not in this list is conversation, and
conversation is meant to be let go."""

MAX_ITEMS = 2_000
"""A ceiling, so the store stays something a person could actually read."""

_WORD = re.compile(r"[\wçğıöşüÇĞİÖŞÜ]+", re.UNICODE)

_KIND_CUES: dict[str, tuple[str, ...]] = {
    # What the question is reaching for, when it does not name the thing itself.
    # "adamın adı neydi" shares no words with "Kerem Yıldız" — lexical overlap alone
    # cannot answer the question this product exists to answer.
    "person": ("adı", "ismi", "adam", "kadın", "kişi", "kim", "kimdi", "kimin", "tanıştık"),
    "date": ("ne zaman", "zamandı", "saat", "gün", "tarih", "kaçta", "hangi gün", "randevu"),
    "number": ("kaç", "ne kadar", "tutar", "fiyat", "bütçe", "rakam", "miktar"),
    "commitment": ("söz", "vermiştik", "demiştik", "anlaştık", "taahhüt"),
    "decision": ("karar", "kararlaştır", "seçtik", "belirledik"),
    "preference": ("sever", "sevmez", "tercih", "istemez", "alışkan"),
    "place": ("nerede", "nereye", "nereden", "neresi", "neredeydi", "mekan", "yer",
              "adres", "gitmiştik", "gidecektik"),
}

_STOP = frozenset({
    "ve", "ile", "bir", "bu", "şu", "o", "da", "de", "mi", "mı", "mu", "mü",
    "için", "ama", "çok", "daha", "gibi", "kadar", "ne", "var", "yok", "olarak",
    "the", "a", "an", "and", "or", "of", "to", "in", "is", "was",
})


def _fold(text: str) -> str:
    """Case-fold Turkish. str.lower alone mangles the dotted and dotless i."""
    return text.replace("İ", "i").replace("I", "ı").lower()


STEM_LENGTH = 5
"""How much of a word to keep when matching.

Turkish is agglutinative, so the same word arrives in a dozen shapes: "restoranın",
"restorana", "restoranda". Exact token matching scores all of those as unrelated, which
made recall miss the thing it was literally asked for. Truncating to a stem is crude —
a real analyser would do better — but it is the difference between finding a memory and
not, and it costs nothing."""


def _tokens(text: str) -> set[str]:
    """Word stems, folded for Turkish casing."""
    return {
        w[:STEM_LENGTH]
        for w in _WORD.findall(_fold(text))
        if len(w) > 2 and w not in _STOP
    }


_SEARCHING = (
    "?", " mi", " mı", " mu", " mü",
    "ne zaman", "neydi", "nerede", "nereye", "nereden", "kimdi", "kimdi", "hangi",
    "kaçtı", "kaçtaydı", "kim ", "ne kadar", "nasıldı",
    "hatırlamıyorum", "hatırlayamıyorum", "aklıma gelmiyor", "unuttum", "unutmuşum",
    "çıkmıyor", "bilmiyorum ya",
)


def _is_searching(query: str) -> bool:
    """Whether this sentence is reaching for something, rather than merely mentioning it.

    The distinction matters because a category cue is the weakest evidence there is.
    "Bugün hava güzel" contains a time word without asking about time; treating it as a
    search is how a copilot ends up announcing a meeting date to someone telling a joke.
    """
    lowered = _fold(query)
    return any(cue in lowered for cue in _SEARCHING)


def _sought_kinds(query: str) -> set[str]:
    """Which kinds of thing this question is reaching for.

    Empty unless the sentence is actually searching: mentioning a day is not asking
    about one.
    """
    if not _is_searching(query):
        return set()
    lowered = _fold(query)
    return {kind for kind, cues in _KIND_CUES.items() if any(c in lowered for c in cues)}


def _now_ms() -> int:
    return int(time.time() * 1000)


@dataclass(slots=True)
class Recollection:
    """One thing worth keeping."""

    text: str
    kind: str = "fact"
    at_ms: int = field(default_factory=_now_ms)
    source: str = ""
    """The utterance it came from, so a person can see why this is remembered."""
    confidence: float = 0.7

    def __post_init__(self) -> None:
        self.text = " ".join(self.text.split())
        if self.kind not in KINDS:
            self.kind = "fact"
        self.confidence = max(0.0, min(1.0, float(self.confidence)))

    @property
    def tokens(self) -> set[str]:
        # Text only. The source sentence is provenance, not content: folding it in
        # made every fact from one utterance look like the same fact, so a turn that
        # settled both a date and a budget quietly kept only the date.
        return _tokens(self.text)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(slots=True)
class Memory:
    """A person's own store, on their own device.

        memory = Memory.open("~/symborg/memory.jsonl")
        memory.keep(Recollection("Bütçe 150 bin olarak karara bağlandı", kind="decision"))
        memory.recall("bütçe ne kadardı")
    """

    path: Path | None = None
    items: list[Recollection] = field(default_factory=list)

    @classmethod
    def open(cls, path: str | Path | None) -> "Memory":
        """Load a store, or start an empty one."""
        if path is None:
            return cls()
        p = Path(path).expanduser()
        memory = cls(path=p)
        if p.exists():
            for line in p.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    memory.items.append(Recollection(**json.loads(line)))
                except (json.JSONDecodeError, TypeError):
                    continue      # one bad line must not hide a person's history
        return memory

    # -- keeping ---------------------------------------------------------------

    def keep(self, item: Recollection) -> bool:
        """Store something, unless it is already known.

        Returns:
            Whether it was new. Repetition is normal in conversation and should not
            fill the store with the same fact five times.
        """
        if self._already_known(item):
            return False
        self.items.append(item)
        if len(self.items) > MAX_ITEMS:
            # Drop the oldest low-confidence items first: a weak guess from last year
            # is the cheapest thing to lose.
            self.items.sort(key=lambda i: (i.confidence, i.at_ms))
            self.items = self.items[len(self.items) - MAX_ITEMS:]
            self.items.sort(key=lambda i: i.at_ms)
            self._rewrite()
            return True
        self._append(item)
        return True

    def _already_known(self, item: Recollection) -> bool:
        incoming = item.tokens
        if not incoming:
            return True           # nothing to remember
        for existing in reversed(self.items[-200:]):
            # Compared across kinds on purpose. The kind is a label the extractor put
            # on the fact, not the fact; "the budget is 150k" filed once as a number
            # and once as a decision is still one thing that happened.
            overlap = incoming & existing.tokens
            union = incoming | existing.tokens
            if union and len(overlap) / len(union) >= 0.8:
                return True
        return False

    # -- recall ----------------------------------------------------------------

    def recall(self, query: str, limit: int = 5) -> list[Recollection]:
        """Find what is relevant to what is being said now.

        Scored on token overlap with a mild preference for recent things, because in
        conversation the recent past is usually what is being reached for.
        """
        wanted = _tokens(query)
        sought = _sought_kinds(query)
        if (not wanted and not sought) or not self.items:
            return []

        newest = max(i.at_ms for i in self.items)
        oldest = min(i.at_ms for i in self.items)
        span = max(1, newest - oldest)

        # Words first. Naming the thing is strong evidence; asking for a kind of thing
        # is what remains when someone has forgotten the very word they would search
        # with. So a category guess only decides the answer when nothing was named.
        lexical = {
            id(item): len(wanted & item.tokens) / len(wanted)
            for item in self.items
        } if wanted else {}
        anything_named = any(score > 0 for score in lexical.values())

        scored: list[tuple[float, Recollection]] = []
        for item in self.items:
            relevance = lexical.get(id(item), 0.0)
            matches_kind = item.kind in sought
            if not relevance and not (matches_kind and not anything_named):
                continue
            kind_hit = 0.35 if matches_kind else 0.0
            recency = (item.at_ms - oldest) / span
            score = relevance * 0.9 + kind_hit + recency * 0.12 + item.confidence * 0.05
            scored.append((score, item))

        scored.sort(key=lambda pair: pair[0], reverse=True)
        return [item for _, item in scored[:limit]]

    def render(self, query: str, limit: int = 5) -> str:
        """What to put in front of the judge. Empty when nothing is relevant, so the
        judge is told plainly that it knows nothing rather than left to fill the gap."""
        found = self.recall(query, limit)
        if not found:
            return ""
        return "\n".join(f"- [{i.kind}] {i.text}" for i in found)

    # -- the person's control --------------------------------------------------

    def forget(self, predicate) -> int:
        """Remove everything matching. Returns how many went.

        A memory a person cannot edit is surveillance with a friendly name.
        """
        before = len(self.items)
        self.items = [i for i in self.items if not predicate(i)]
        removed = before - len(self.items)
        if removed:
            self._rewrite()
        return removed

    def forget_all(self) -> int:
        count = len(self.items)
        self.items = []
        self._rewrite()
        return count

    def summary(self) -> dict:
        by_kind: dict[str, int] = {}
        for item in self.items:
            by_kind[item.kind] = by_kind.get(item.kind, 0) + 1
        return {"items": len(self.items), "by_kind": by_kind,
                "path": str(self.path) if self.path else None}

    # -- storage ---------------------------------------------------------------

    def _append(self, item: Recollection) -> None:
        if self.path is None:
            return
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(item.to_dict(), ensure_ascii=False) + "\n")
        except OSError:
            pass          # remembering must never break the conversation

    def _rewrite(self) -> None:
        if self.path is None:
            return
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(
                "\n".join(json.dumps(i.to_dict(), ensure_ascii=False) for i in self.items)
                + ("\n" if self.items else ""),
                encoding="utf-8",
            )
        except OSError:
            pass
