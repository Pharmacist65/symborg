"""Comparing what was just said against what is known.

Split out of :mod:`judge` after repeated measurement showed the same failure: asked to
weigh a factual mismatch and social appropriateness in one breath, the model would spot
the mismatch and then talk itself out of acting on it — "they didn't ask me", "the
other person agreed", "it would be interrupting". Every one of those is true, and none
of them is a reason to let someone walk away with the wrong date.

So this asks one question only, in a vocabulary that has no room for politeness: are
these two the same thing or not. The judgement about whether to speak stays where it
belongs, but it no longer gets to overrule arithmetic.
"""

from __future__ import annotations

import json
import re

from ..providers.base import LanguageModel, Prompt, ProviderError

__all__ = ["Mismatch", "check", "CHECK_SYSTEM", "CHECK_SCHEMA"]

CHECK_SYSTEM = """İki metin vereceğim: KAYIT (doğru bilinen) ve SÖYLENEN (az önce konuşulan).

Tek işin karşılaştırmak. Nezaket, uygunluk, araya girmek — bunlar seni ilgilendirmez.
Kimin sorduğu, kimin onayladığı, konunun hassas olup olmadığı da seni ilgilendirmez.

Şunu sor: SÖYLENEN içinde, KAYIT'takiyle AYNI KONUYA ait ama FARKLI olan somut bir
değer var mı? (rakam, tarih, gün, saat, isim, yer, verilmiş/verilmemiş bir söz)

  KAYIT "Bütçe 150 bin"      SÖYLENEN "200 bin demiştik değil mi"  → FARKLI, doğrusu: 150 bin
  KAYIT "Toplantı salı"      SÖYLENEN "çarşambaydı galiba"         → FARKLI, doğrusu: salı
  KAYIT "yardım sözü verildi" SÖYLENEN "söz vermemiştik ki"        → FARKLI, doğrusu: söz verilmişti
  KAYIT "Bütçe 150 bin"      SÖYLENEN "150 bindi değil mi"         → AYNI
  KAYIT "Toplantı salı"      SÖYLENEN "proje bitse iyi olur"       → İLGİSİZ

"galiba", "sanırım", "değil mi", "evet öyleydi" gibi ifadeler karşılaştırmayı
DEĞİŞTİRMEZ. Değerlere bak, cümlenin tonuna değil.

Yalnızca JSON:
{"differs": true|false, "correct": "doğrusunu söyleyen kısa cümle", "field": "ne"}

correct, kulağa fısıldanacak. Tek başına anlaşılsın, en fazla 8 kelime:
  iyi  : "150 bin demiştik."      kötü : "150 bin"
  iyi  : "Salı demiştik, çarşamba değil."   kötü : "salı"
KAYIT'taki ifadeyi olduğu gibi kullan; saat ve tarihi çevirme.

differs false ise correct boş bırak. Emin değilsen differs false."""

CHECK_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "differs": {"type": "boolean"},
        "correct": {"type": "string"},
        "field": {"type": "string"},
    },
    "required": ["differs", "correct", "field"],
    "additionalProperties": False,
}

MAX_WORDS = 12


class Mismatch:
    """What the comparison found. Falsy when there is nothing to correct, so callers
    read as ``if check(...)``."""

    __slots__ = ("differs", "correct", "field")

    def __init__(self, differs: bool = False, correct: str = "", field: str = "") -> None:
        self.differs = bool(differs)
        self.correct = " ".join(str(correct).split())
        self.field = str(field)

    def __bool__(self) -> bool:
        return self.differs and bool(self.correct) and not self.is_too_long

    @property
    def is_too_long(self) -> bool:
        return len(self.correct.split()) > MAX_WORDS

    def __repr__(self) -> str:
        return f"Mismatch(differs={self.differs}, correct={self.correct!r})"


NONE = Mismatch()


def check(model: LanguageModel, said: str, known: str) -> Mismatch:
    """Compare what was said against what is known.

    Returns:
        A mismatch, falsy unless there is a concrete, short correction to make. Any
        failure returns no mismatch: an uncertain comparison is not a reason to speak.
    """
    if not said.strip() or not known.strip():
        return NONE

    prompt = Prompt(
        system=CHECK_SYSTEM,
        user=f"KAYIT:\n{known}\n\nSÖYLENEN:\n{said}",
        max_tokens=120,
        temperature=0.0,          # a comparison should not vary between runs
        json_schema=CHECK_SCHEMA,
    )
    try:
        raw = model.complete(prompt)
    except ProviderError:
        return NONE

    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text).strip()
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            return NONE
        try:
            payload = json.loads(match.group(0))
        except json.JSONDecodeError:
            return NONE
    if not isinstance(payload, dict):
        return NONE
    return Mismatch(payload.get("differs", False), payload.get("correct", ""),
                    payload.get("field", ""))
