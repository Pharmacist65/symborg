"""Deciding what, out of everything said, is worth keeping.

Almost nothing is. A conversation is mostly greetings, jokes, thinking aloud and things
that were true for a minute. Keeping all of it produces a transcript nobody reads;
keeping the wrong things produces a device that confidently misremembers.

So this is asked in the negative, like the salience judge: assume nothing here needs
keeping, and justify each exception. The test is whether someone might reach for it
later and not find it in their own head.
"""

from __future__ import annotations

import json
import re

from ..providers.base import LanguageModel, Prompt, ProviderError
from .memory import KINDS, Recollection

__all__ = ["extract", "EXTRACT_SYSTEM", "EXTRACT_SCHEMA"]

EXTRACT_SYSTEM = """Bir konuşma parçası vereceğim. Görevin, ileride HATIRLANMASI GEREKEN
şeyleri ayıklamak.

Varsayılanın hiçbir şey almamak. Konuşmanın büyük kısmı saklanmaya değmez.

SAKLA:
- tarih ve saat ("toplantı salı ikide")
- rakam ve tutar ("bütçe 150 bin")
- kişi ve kimliği ("Kerem Yıldız, Vega Yazılım")
- verilen söz veya alınan karar ("yardım edeceğiz", "o modeli seçtik")
- yer ve isim ("Meze Han, Moda")
- kalıcı tercih ("sütsüz içiyor", "sabahları toplantı istemiyor")

SAKLAMA:
- selamlaşma, hâl hatır, şaka
- duygu ifadeleri
- "belki", "bakarız", "düşünelim" gibi kararsız şeyler
- o an geçerli olan geçici durumlar ("şimdi yağmur yağıyor")
- zaten herkesin bildiği genel bilgi
- konuşanın kendi düşünmesi olan cümleler

Testi şu: bu kişi bunu iki hafta sonra ARAYABİLİR mi, ve kendi kafasında BULAMAZ mı?
Hayırsa alma.

Her madde TEK cümle ve KENDİ BAŞINA anlaşılır olmalı. İki şart:
- "o dedi ki" değil → "Kerem Yıldız, Vega Yazılım'da ürün müdürü"
- NE OLDUĞUNU da yaz. Kişi iki hafta sonra o adı hatırlamıyor olacak; hatırladığı
  tek şey TÜRÜ olacak.
    kötü : "Meze Han, Moda"
    iyi  : "Meze Han, Moda'da bir restoran; 14 Şubat'ta gidildi"
    kötü : "Vega Yazılım"
    iyi  : "Vega Yazılım, Kerem Yıldız'ın çalıştığı şirket"

Yalnızca JSON:
{"items": [{"text": "...", "kind": "fact|date|person|number|commitment|decision|preference", "confidence": 0.0-1.0}]}

Saklanacak bir şey yoksa {"items": []}. Emin değilsen alma."""

EXTRACT_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "kind": {"type": "string", "enum": list(KINDS)},
                    "confidence": {"type": "number"},
                },
                "required": ["text", "kind", "confidence"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["items"],
    "additionalProperties": False,
}

MAX_PER_TURN = 4
"""A single turn that yields five separate durable facts is almost certainly the model
being agreeable rather than the conversation being dense."""


def extract(model: LanguageModel, transcript: str) -> list[Recollection]:
    """Pull the durable things out of a turn.

    Returns:
        What is worth keeping, possibly nothing. Any failure returns nothing: a
        memory that invents is worse than one that forgets.
    """
    if not transcript.strip():
        return []

    prompt = Prompt(
        system=EXTRACT_SYSTEM,
        user=f"KONUŞMA:\n{transcript}\n\nSaklanacak bir şey var mı?",
        max_tokens=300,
        temperature=0.1,
        json_schema=EXTRACT_SCHEMA,
    )
    try:
        raw = model.complete(prompt)
    except ProviderError:
        return []

    payload = _parse(raw)
    if payload is None:
        return []

    out: list[Recollection] = []
    for entry in payload[:MAX_PER_TURN]:
        text = str(entry.get("text", "")).strip()
        if not text:
            continue
        try:
            confidence = float(entry.get("confidence", 0.7))
        except (TypeError, ValueError):
            confidence = 0.7
        if confidence < 0.5:
            continue          # an uncertain memory is worse than none
        out.append(Recollection(
            text=text,
            kind=str(entry.get("kind", "fact")),
            source=transcript[:200],
            confidence=confidence,
        ))
    return out


def _parse(raw: str) -> list[dict] | None:
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
    if isinstance(payload, dict):
        payload = payload.get("items")
    return payload if isinstance(payload, list) else None
