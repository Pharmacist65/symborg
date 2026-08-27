"""Candidate generation and filtering.

Turns transcript plus personal context into a small set of distinct, speakable
sentences. Every rule here has the same purpose: the person should be able to read
three options quickly and find one that is genuinely theirs.
"""

from __future__ import annotations

import json
import re

from ..candidate import Candidate, CandidateKind, MAX_CANDIDATE_WORDS
from ..context.transcript import Transcript
from ..context.vault import Vault
from ..providers.base import LanguageModel, Prompt, ProviderError
from .prompts import (
    CANDIDATE_SYSTEM, EXPANSION_SYSTEM,
    build_candidate_prompt, build_expansion_prompt,
)

__all__ = ["generate_candidates", "expand_abbreviation", "parse_candidates", "dedupe",
           "CANDIDATE_SCHEMA"]

CANDIDATE_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "candidates": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "kind": {"type": "string",
                             "enum": ["reply", "need", "question", "repair", "social"]},
                    "confidence": {"type": "number"},
                },
                "required": ["text", "kind", "confidence"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["candidates"],
    "additionalProperties": False,
}
"""Shape offered to providers that support constrained decoding.

Wrapped in an object because strict structured outputs cannot return a top-level
array. Providers that ignore it still work — the parser accepts either shape."""

_VALID_KINDS = {"reply", "need", "question", "repair", "social"}

_CLINICAL_ASSERTION = re.compile(
    r"teşhis|tanı\s*kon|kanser|tümör|metastaz"
    r"|\d+\s*(?:mg|ml|mcg|ünite|gram)"
    r"|doz\w*\s+(?:artır|azalt|değiştir|yükselt|düşür)"
    r"|ilac\w*\s+(?:kes|bırak|değiştir|artır|azalt)"
    r"|ameliyat\w*\s+(?:ol|gerek)"
)
"""Blocks the system asserting clinical facts in the person's name.

Reporting a symptom in the first person is the person's own speech and is allowed
("my back hurts"); naming a diagnosis or a dose is not something a generator may put
in their mouth.

Deliberately matches stems without a trailing word boundary: Turkish is agglutinative,
so "dozunu artırın" carries suffixes that a \b anchor would reject. This is a coarse
guard, not a clinical safety system — the authorship lock is what makes the product
safe; this only stops an obvious class of generated assertion.
"""


def _fold_tr(text: str) -> str:
    """Case-fold Turkish text for matching.

    Python's str.lower() maps "İ" to "i̇" (i plus a combining dot) and leaves "I" as
    "i", both of which break naive matching on Turkish input. Mapping the two dotted/
    dotless pairs explicitly first avoids that.
    """
    return text.replace("İ", "i").replace("I", "ı").lower()


def parse_candidates(raw: str) -> list[Candidate]:
    """Parse a model response into candidates.

    Tolerant of a model wrapping JSON in prose or a code fence, strict about the result:
    anything that does not parse yields no candidates rather than a guess.
    """
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text).strip()

    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        # Fall back to locating a bare array inside surrounding prose.
        match = re.search(r"\[.*\]", text, re.DOTALL)
        if not match:
            return []
        try:
            payload = json.loads(match.group(0))
        except json.JSONDecodeError:
            return []

    if isinstance(payload, dict):
        # Strict structured outputs cannot return a top-level array, so providers that
        # constrain decoding wrap it in an object. Unwrap the single list it carries.
        payload = next((v for v in payload.values() if isinstance(v, list)), None)
    if not isinstance(payload, list):
        return []

    out: list[Candidate] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        value = str(item.get("text", "")).strip()
        if not value:
            continue
        kind = str(item.get("kind", "reply")).lower()
        if kind not in _VALID_KINDS:
            kind = "reply"
        try:
            confidence = float(item.get("confidence", 0.5))
        except (TypeError, ValueError):
            confidence = 0.5
        out.append(Candidate(text=value, kind=kind, confidence=confidence))  # type: ignore[arg-type]
    return out


def dedupe(candidates: list[Candidate]) -> list[Candidate]:
    """Drop near-duplicates. Three phrasings of one sentence is one option, not three."""
    seen: set[frozenset[str]] = set()
    out: list[Candidate] = []
    for cand in candidates:
        words = frozenset(re.findall(r"\w+", cand.text.lower()))
        if not words:
            continue
        if any(_overlap(words, prev) >= 0.75 for prev in seen):
            continue
        seen.add(words)
        out.append(cand)
    return out


def _overlap(a: frozenset[str], b: frozenset[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _acceptable(cand: Candidate) -> bool:
    if not cand.text or cand.is_too_long:
        return False
    return not _CLINICAL_ASSERTION.search(_fold_tr(cand.text))


def _finalise(parsed: list[Candidate], n: int) -> list[Candidate]:
    usable = dedupe([c for c in parsed if _acceptable(c)])
    usable.sort(key=lambda c: c.confidence, reverse=True)
    selected = usable[:n]
    if selected and not any(c.kind == "repair" for c in selected):
        repair = next((c for c in usable[n:] if c.kind == "repair"), None)
        if repair is not None:
            selected[-1] = repair
    return selected


def generate_candidates(
    model: LanguageModel,
    transcript: Transcript,
    vault: Vault | None = None,
    n: int = 3,
) -> list[Candidate]:
    """Produce up to ``n`` distinct, speakable candidates.

    Returns an empty list if the provider fails or returns nothing usable. A failure
    must surface as silence, never as an invented sentence.
    """
    prompt = Prompt(
        system=CANDIDATE_SYSTEM,
        user=build_candidate_prompt(
            transcript.render(),
            vault.render() if vault else "",
            n,
        ),
        max_tokens=400,
        temperature=0.5,
        json_schema=CANDIDATE_SCHEMA,
    )
    try:
        raw = model.complete(prompt)
    except ProviderError:
        return []
    return _finalise(parse_candidates(raw), n)


def expand_abbreviation(
    model: LanguageModel,
    abbreviation: str,
    transcript: Transcript,
    vault: Vault | None = None,
    n: int = 3,
) -> list[Candidate]:
    """Expand a terse input into full candidate sentences.

    The measured benefit of this path is fewer physical actions per sentence, so the
    fallback matters: if expansion fails, the person's own input is returned unchanged
    rather than replaced by a guess.
    """
    abbreviation = abbreviation.strip()
    if not abbreviation:
        return []

    prompt = Prompt(
        system=EXPANSION_SYSTEM,
        user=build_expansion_prompt(
            abbreviation,
            transcript.render(),
            vault.render() if vault else "",
            n,
        ),
        max_tokens=400,
        temperature=0.4,
        json_schema=CANDIDATE_SCHEMA,
    )
    try:
        raw = model.complete(prompt)
    except ProviderError:
        return [Candidate(text=abbreviation, kind="repair", confidence=0.3)]

    out = _finalise(parse_candidates(raw), n)
    return out or [Candidate(text=abbreviation, kind="repair", confidence=0.3)]
