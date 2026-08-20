"""Local personal context, owned by the person.

Plain JSON on local disk so it can be read, edited, exported and deleted without this
software. Nothing here is transmitted unless a provider is explicitly configured, and
what is included in a prompt is deliberately narrow.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

__all__ = ["Vault"]


@dataclass(slots=True)
class Vault:
    """Personal context that makes candidates specific to one person's life."""

    display_name: str = ""
    pronouns: str = ""
    relationships: dict[str, str] = field(default_factory=dict)
    recurring_needs: list[str] = field(default_factory=list)
    preferred_phrasings: list[str] = field(default_factory=list)
    accepted_utterances: list[str] = field(default_factory=list)
    notes: str = ""

    MAX_ACCEPTED = 50

    @classmethod
    def load(cls, path: str | Path) -> "Vault":
        """Load a vault, or return an empty one if there is no file yet.

        A corrupt vault is not fatal: candidates get less specific, which is far better
        than refusing to let someone communicate.
        """
        p = Path(path)
        if not p.exists():
            return cls()
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return cls()
        known = {f for f in cls.__slots__ if not f.startswith("_")}
        return cls(**{k: v for k, v in data.items() if k in known})

    def save(self, path: str | Path) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(asdict(self), ensure_ascii=False, indent=2), encoding="utf-8")

    def remember_accepted(self, text: str) -> None:
        """Record an utterance the person chose, so their own phrasing comes back."""
        text = text.strip()
        if not text or text in self.accepted_utterances:
            return
        self.accepted_utterances.append(text)
        if len(self.accepted_utterances) > self.MAX_ACCEPTED:
            del self.accepted_utterances[0]

    def is_empty(self) -> bool:
        return not any([
            self.display_name, self.relationships, self.recurring_needs,
            self.preferred_phrasings, self.accepted_utterances, self.notes,
        ])

    def render(self) -> str:
        """Render for a prompt. Only fields that help phrase a sentence are included."""
        if self.is_empty():
            return ""
        parts: list[str] = []
        if self.display_name:
            parts.append(f"Adı: {self.display_name}")
        if self.pronouns:
            parts.append(f"Zamirleri: {self.pronouns}")
        if self.relationships:
            people = ", ".join(f"{n} ({r})" for n, r in self.relationships.items())
            parts.append(f"Yakınları: {people}")
        if self.recurring_needs:
            parts.append("Sık ihtiyaçları: " + "; ".join(self.recurring_needs))
        if self.preferred_phrasings:
            parts.append("Tercih ettiği ifadeler: " + "; ".join(self.preferred_phrasings))
        if self.accepted_utterances:
            recent = self.accepted_utterances[-5:]
            parts.append("Son seçtiği cümleler: " + "; ".join(recent))
        if self.notes:
            parts.append(f"Notlar: {self.notes}")
        return "\n".join(parts)
