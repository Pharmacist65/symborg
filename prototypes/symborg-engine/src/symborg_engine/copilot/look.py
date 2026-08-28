"""Asking about something in front of the person.

The first thing anyone asks of a device like this is the mushroom question: point it at
something and be told what it is. It is also the one that can kill someone, and the
distance between those two facts is the whole design.

An identification model that is eighty per cent sure will happily say "edible" — and
eighty per cent is a coin flip you take with your life a few times a year. So this
never answers the question that was asked. It answers what it can see, how sure it is,
and what would settle it, and it says plainly that a photograph is not enough to decide
by. That is not hedging: it is the true shape of what a picture can tell you.

Nothing here is medical. It is about the limits of identification from an image, which
apply the same to a mushroom, a snake, a plug socket and a road sign.

Far tier: a photograph the person is about to act on.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from ..providers.base import LanguageModel, Prompt, ProviderError

__all__ = ["Sighting", "look", "LOOK_SYSTEM", "LOOK_SCHEMA", "IRREVERSIBLE"]

IRREVERSIBLE = ("yemek", "yeme", "yenir", "yenebilir", "yiyebilir", "tatmak", "ısırmak",
                "içmek", "toplamak", "zehirli", "zararlı", "güvenli", "dokunabilir",
                "mantar", "yaban", "böcek", "yılan", "ilaç", "hap")
"""Words that mean the person is about to do something they cannot undo. Their presence
does not stop an answer; it decides how the answer has to be framed."""

LOOK_SYSTEM = """Bir fotoğraf ve bir soru vereceğim. Ne GÖRDÜĞÜNÜ söyle.

Üç şeyi ayrı ayrı ver:
1. NE GÖRÜYORSUN — sadece görünen. "Kahverengi şapkalı, beyaz lamelli bir mantar,
   sapında halka var." Tahminini değil, GÖZLEMİ yaz.
2. NE OLABİLİR — en olası birkaç şey, en olasıdan başlayarak. Tek bir cevap verme;
   fotoğraftan tek cevap çıkmıyorsa çıkmıyordur.
3. NEYİ GÖREMİYORSUN — kararı değiştirecek ama fotoğrafta olmayan şey.
   ("sporları, kesitin rengi, kokusu, hangi ağacın altında bittiği")

GERİ ALINAMAZ BİR ŞEY söz konusuysa — yemek, dokunmak, içmek, toplamak —
şunu ASLA yapma: "yenir", "güvenli", "zararsız", "sorun yok" DEME.
Emin görünsen bile deme. Fotoğraftan teşhis, bir şeyi yemeye karar vermeye yetmez;
bu senin çekingenliğin değil, fotoğrafın sınırı.
Bunun yerine: neye benzediğini, neyle karıştırıldığını ve kimin bilebileceğini söyle.
Tehlikeli bir benzeri varsa ONU MUTLAKA söyle — asıl işin bu.

Emin değilsen "emin değilim" de. Uydurma. Görmediğin bir ayrıntıyı varmış gibi anlatma.

Yalnızca JSON:
{"seen": "...", "could_be": ["...", "..."], "missing": "...",
 "confidence": 0.0-1.0, "irreversible": true|false, "whisper": "en fazla 14 kelime"}

whisper: kulağa söylenecek tek cümle. Geri alınamaz bir şeyse, o cümle bir izin değil
bir UYARI olmalı."""

LOOK_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "seen": {"type": "string"},
        "could_be": {"type": "array", "items": {"type": "string"}},
        "missing": {"type": "string"},
        "confidence": {"type": "number"},
        "irreversible": {"type": "boolean"},
        "whisper": {"type": "string"},
    },
    "required": ["seen", "could_be", "missing", "confidence", "irreversible", "whisper"],
    "additionalProperties": False,
}

MAX_WHISPER_WORDS = 14

# Said about something a person is about to eat or touch, any of these is the failure
# this module exists to prevent. Checked in code as well as asked for in the prompt,
# because a prompt is a request and this is a guarantee.
_PERMISSIONS = (
    r"\byenir\b", r"\byenebilir", r"\byiyebilir", r"\bgüvenli\b", r"\bzararsız\b",
    r"\bsorun yok\b", r"\brahatlıkla\b", r"\bafiyet", r"\bedible\b", r"\bsafe to eat\b",
)


@dataclass(slots=True, frozen=True)
class Sighting:
    """What it could tell from the picture."""

    seen: str = ""
    could_be: tuple[str, ...] = ()
    missing: str = ""
    confidence: float = 0.0
    irreversible: bool = False
    whisper: str = ""

    def __bool__(self) -> bool:
        return bool(self.seen.strip() or self.whisper.strip())

    def to_dict(self) -> dict:
        return {"seen": self.seen, "could_be": list(self.could_be),
                "missing": self.missing, "confidence": round(self.confidence, 3),
                "irreversible": self.irreversible, "whisper": self.whisper}


NOTHING = Sighting()


def _grants_permission(text: str) -> bool:
    lowered = text.replace("İ", "i").replace("I", "ı").lower()
    return any(re.search(pattern, lowered) for pattern in _PERMISSIONS)


def look(model: LanguageModel, image: bytes, question: str = "Bu ne?",
         mime: str = "image/jpeg") -> Sighting:
    """Say what can be seen, and what a picture cannot settle.

    Returns:
        A sighting. Empty on any failure — a camera that answers wrongly is worse than
        a camera that says nothing, and this is the one place in the engine where being
        wrong has a physical cost.
    """
    if not image:
        return NOTHING

    asked = question.strip() or "Bu ne?"
    lowered = asked.replace("İ", "i").replace("I", "ı").lower()
    risky = any(word in lowered for word in IRREVERSIBLE)

    prompt = Prompt(
        system=LOOK_SYSTEM,
        user=(f"SORU: {asked}"
              + ("\n\nDİKKAT: Bu soru geri alınamaz bir eylemle ilgili."
                 if risky else "")),
        image=image,
        image_mime=mime,
        max_tokens=600,
        temperature=0.1,
        json_schema=LOOK_SCHEMA,
        tier="far",
    )
    try:
        raw = model.complete(prompt)
    except ProviderError:
        return NOTHING

    payload = _parse(raw)
    if payload is None:
        return NOTHING

    whisper = " ".join(str(payload.get("whisper", "")).split())
    if len(whisper.split()) > MAX_WHISPER_WORDS:
        whisper = ""
    irreversible = bool(payload.get("irreversible", False)) or risky

    if irreversible and _grants_permission(whisper):
        # It granted permission anyway. The prompt asked it not to; this is why the
        # rule is also enforced here, where it cannot be talked around.
        whisper = "Fotoğraftan emin olunmaz. Bilen birine sormadan yeme."

    return Sighting(
        seen=" ".join(str(payload.get("seen", "")).split()),
        could_be=tuple(str(c).strip() for c in payload.get("could_be", []) if str(c).strip()),
        missing=" ".join(str(payload.get("missing", "")).split()),
        confidence=max(0.0, min(1.0, float(payload.get("confidence", 0.0) or 0.0))),
        irreversible=irreversible,
        whisper=whisper,
    )


def _parse(raw: str) -> dict | None:
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text).strip()
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            return None
        try:
            payload = json.loads(match.group(0))
        except json.JSONDecodeError:
            return None
    return payload if isinstance(payload, dict) else None
