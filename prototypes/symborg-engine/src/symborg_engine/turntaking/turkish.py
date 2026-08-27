"""Turkish morphological cues for turn completion.

Turkish is verb-final and agglutinative: the predicate arrives last and carries tense,
mood and person as suffixes stacked on the end of it. A listener therefore gets a
completion signal that a speaker of an SVO language does not — by the time you hear
"gidiyorum" you know the clause is closing.

This module is a first, deliberately cheap reading of that signal: suffix shapes, not
a morphological analyser. It is a baseline to beat, not the finished predictor, and its
error modes are documented rather than hidden.
"""

from __future__ import annotations

import re

__all__ = ["completion_score", "fold", "FINITE_ENDINGS", "CONTINUERS"]


def fold(text: str) -> str:
    """Case-fold Turkish text.

    ``str.lower`` maps "İ" to "i" plus a combining dot and leaves "I" as "i", both of
    which break suffix matching. Mapping the dotted/dotless pairs first avoids that.
    """
    return text.replace("İ", "i").replace("I", "ı").lower()


FINITE_ENDINGS: tuple[str, ...] = (
    # person endings on a finite verb — the strongest single cue that a clause closed
    "yorum", "yorsun", "yoruz", "yorsunuz", "yorlar", "yor",
    "acağım", "eceğim", "acaksın", "eceksin", "acak", "ecek", "acağız", "eceğiz",
    "dım", "dim", "dum", "düm", "tım", "tim", "tum", "tüm",
    "dın", "din", "dun", "dün", "tın", "tin", "tun", "tün",
    "dık", "dik", "duk", "dük", "tık", "tik", "tuk", "tük",
    "dı", "di", "du", "dü", "tı", "ti", "tu", "tü",
    "mış", "miş", "muş", "müş",
    "malı", "meli", "malıyım", "meliyim",
    "arım", "erim", "ırım", "irim", "urum", "ürüm",
    "sın", "sin", "sun", "sün",
    "dır", "dir", "dur", "dür", "tır", "tir", "tur", "tür",
    # copular and existential closers
    "değil", "var", "yok", "evet", "hayır", "tamam", "peki",
)

CONTINUERS: tuple[str, ...] = (
    # conjunctions and subordinators: a clause boundary, but the turn keeps going
    "ve", "ama", "fakat", "ancak", "çünkü", "yani", "ki", "de", "da",
    "eğer", "ya", "hem", "veya", "ayrıca", "üstelik", "sonra", "önce",
    # converbs — the clause is grammatically unfinished
    "ıp", "ip", "up", "üp", "arak", "erek", "ınca", "ince", "unca", "ünce",
    "ken", "madan", "meden", "dıkça", "dikçe",
)

_FILLER = ("şey", "hani", "işte", "falan", "filan", "ıı", "ee", "mmm")

_NOT_VERBS = frozenset({
    # Frequent words whose ending merely looks like a finite suffix. Suffix shape alone
    # cannot tell them apart from a verb, so they are listed. This is the honest cost of
    # not running a morphological analyser, and the list is the first thing a real one
    # would replace.
    "artık", "sanki", "belki", "gibi", "kadar", "değil", "bazı", "başka",
    "birçok", "birkaç", "çünkü", "şimdi", "sadece", "hatta", "tabii",
})

_WORD = re.compile(r"[\wçğıöşüÇĞİÖŞÜ]+", re.UNICODE)

_CONVERBS = tuple(c for c in CONTINUERS if c in {
    "ıp", "ip", "up", "üp", "arak", "erek", "ınca", "ince", "unca", "ünce",
    "ken", "madan", "meden", "dıkça", "dikçe",
})


def _ends_with_converb(word: str) -> bool:
    """Whether a word ends in a converb suffix.

    Short suffixes such as "-ip" match incidentally, so the stem is required to be
    long enough for the match to be morphologically plausible.
    """
    return any(
        word.endswith(suffix) and len(word) >= len(suffix) + 3
        for suffix in _CONVERBS
    )


def completion_score(partial: str) -> float:
    """Estimate how likely it is that this partial utterance has just ended.

    Args:
        partial: What has been heard of the current turn so far.

    Returns:
        A score in ``[0, 1]``. This is a heuristic, not a calibrated probability —
        treat it as a ranking signal and set the threshold empirically.
    """
    text = fold(partial).strip()
    if not text:
        return 0.0

    # Explicit terminal punctuation, when a transcriber provides it, settles the question.
    if text.endswith((".", "?", "!")):
        return 0.95

    words = _WORD.findall(text)
    if not words:
        return 0.0
    last = words[-1]

    # A trailing comma is an explicit continuation marker and outranks suffix shape:
    # "bilmiyorum artık," ends in a verb-looking form but the speaker is not done.
    if text.rstrip().endswith((",", ";", ":")):
        return 0.08

    if last in _FILLER:
        return 0.05        # trailing filler almost always means more is coming
    if last in CONTINUERS:
        return 0.05        # "... ama" — a boundary, but not the end of the turn
    if _ends_with_converb(last):
        return 0.15        # converb: grammatically unfinished

    score = 0.2
    if last in _NOT_VERBS:
        return score
    if any(last.endswith(e) for e in FINITE_ENDINGS):
        score = 0.75       # finite verb form — the clause closed
        if len(words) >= 4:
            score += 0.1   # a longer clause makes an incidental match less likely

    # A question particle at the end is a strong hand-off: the speaker wants a reply.
    if last in {"mi", "mı", "mu", "mü"} or re.search(r"\bm[iıuü](sin|siniz|yim|yiz)?$", last):
        score = max(score, 0.9)

    return min(1.0, score)
