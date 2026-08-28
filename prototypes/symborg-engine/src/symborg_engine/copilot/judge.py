"""Judging whether what was just said is worth saying something about.

The gate in :mod:`salience` decides whether the *moment* allows speaking. This decides
whether the *content* deserves it — and it is deliberately hard to satisfy, because
almost nothing in an ordinary conversation does.

The model is asked the question in the negative: assume silence, and justify departing
from it. Asked the other way round a language model will always find something helpful
to say, which is exactly the failure that emptied this product category.
"""

from __future__ import annotations

import json
import re

from ..providers.base import LanguageModel, Prompt, ProviderError

__all__ = ["Judgement", "judge_moment", "JUDGE_SYSTEM", "JUDGE_SCHEMA"]

JUDGE_SYSTEM = """Sen bir insanın yanında duran sessiz bir yardımcısın.

Varsayılanın SUSMAK. Ama susmak da bir başarısızlık olabilir: bildiğin bir şeyi
söylemediğin için biri bir randevuyu kaçırırsa, orada olmanın anlamı kalmaz.

Sırayla üç soru sor. İlk "evet"te konuş, üçü de "hayır"sa sus.

1. Odada CEVAPLANAMAYAN somut bir soru var mı, ve cevabı BİLDİKLERİN'de var mı?
   ("Ne zamandı?" "Adı neydi?" "Kaç para demiştik?" — ve biri "bilmiyorum" diyorsa)
   → Evet ise KONUŞ. Bu senin varlık sebebin.

   AMA ÖNCE ŞUNU AYIRT ET — her soru cümlesi bilgi istemez:
   "Neden bu kadar erken gitti ki?"  → duygu. Cevap istemiyor. SUS.
   "Ben ne yapacağım şimdi?"          → duygu. SUS.
   "Nasıl dayanacağım?"               → duygu. SUS.
   "Cenaze kaçta?"                    → bilgi. Söyle.
   "Randevu ne zamandı?"              → bilgi. Söyle.
   Testi şu: cevabı duysa RAHATLAR mı, yoksa araya GİRMİŞ mi olursun?
   Emin değilsen duygu say ve sus.

   TEK İSTİSNA — UNUTULAN AD, TARİH, RAKAM: "adı neydi ya", "hiç aklıma gelmiyor",
   "dilimin ucunda" bir sitem değil, ARAYIŞTIR. Kişi o bilgiyi arıyor ve bulamıyor.
   Cevabı biliyorsan söyle; bu, yardımın en saf hâli.

2. Şu an söylenen bir şey, BİLDİKLERİN'deki bir kayıtla ÇELİŞİYOR mu?
   (rakam, tarih, isim, verilmiş bir söz)
   → Evet ise KONUŞ. Kimse yanlış hatırladığını fark etmez.

3. Kişi doğrudan sana mı sordu?
   → Evet ise KONUŞ.

Üçü de hayırsa SUS. Sohbet, hâl hatır, şaka, plan yapma, duygusal an — hepsi sus.
Faydalı ama sorulmamış bilgi de sus; onu söylemek gürültüdür.

MUTLAK SUSMA: yas, ölüm, hastalık, kavga, ağlama. Ne bilirsen bil, sus.

BİLDİKLERİN boşsa, 1 ve 2 otomatik olarak hayırdır — uydurma.

Söyleyeceğin TEK cümle, en fazla 12 kelime. Kulağa fısıldanacak.
Cevabı doğrudan ver: "12 Mart, saat iki." — "Hatırlatmak isterim ki..." deme.

Yalnızca JSON:
{"worth_it": true|false, "score": 0.0-1.0, "say": "...", "why": "hangi madde"}

worth_it false ise say boş. score: 1. madde ~0.9, 2. madde ~0.85, 3. madde ~0.8."""

JUDGE_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "worth_it": {"type": "boolean"},
        "score": {"type": "number"},
        "say": {"type": "string"},
        "why": {"type": "string"},
    },
    "required": ["worth_it", "score", "say", "why"],
    "additionalProperties": False,
}

MAX_WORDS = 12
"""A whisper interrupts. A long one interrupts for longer, and the cost of an
interruption rises with its length."""


class Judgement:
    """What the judge concluded."""

    __slots__ = ("worth_it", "score", "say", "why")

    def __init__(self, worth_it: bool, score: float, say: str, why: str) -> None:
        self.worth_it = bool(worth_it)
        self.score = max(0.0, min(1.0, float(score)))
        self.say = " ".join(say.split())
        self.why = why.strip()

    @property
    def is_too_long(self) -> bool:
        return len(self.say.split()) > MAX_WORDS

    def to_dict(self) -> dict:
        return {"worth_it": self.worth_it, "score": round(self.score, 3),
                "say": self.say, "why": self.why}

    def __repr__(self) -> str:
        return f"Judgement({'speak' if self.worth_it else 'silent'}, {self.score:.2f})"


SILENT = Judgement(worth_it=False, score=0.0, say="", why="")


def judge_moment(model: LanguageModel, transcript: str, memory: str = "",
                 asked: bool = False) -> Judgement:
    """Ask whether this moment deserves an interruption.

    Returns:
        A judgement. Any failure — provider error, unparseable reply, an answer that
        is too long — returns silence. Nothing here invents a reason to speak.
    """
    if not transcript.strip():
        return SILENT

    blocks = []
    if memory.strip():
        blocks.append(f"BİLDİKLERİN:\n{memory}")
    blocks.append(f"KONUŞMA:\n{transcript}")
    if not memory.strip():
        blocks.insert(0, "BİLDİKLERİN: (boş — 1. ve 2. madde otomatik hayır)")
    blocks.append("Kişi sana DOĞRUDAN sordu." if asked else "Kişi sana sormadı.")
    blocks.append("Üç soruyu sırayla uygula.")

    prompt = Prompt(
        system=JUDGE_SYSTEM,
        user="\n\n".join(blocks),
        max_tokens=160,
        temperature=0.2,          # this is a judgement, not a creative act
        json_schema=JUDGE_SCHEMA,
    )

    try:
        raw = model.complete(prompt)
    except ProviderError:
        return SILENT

    judgement = _parse(raw)
    if judgement is None:
        return SILENT
    if judgement.worth_it and (not judgement.say or judgement.is_too_long):
        # A verdict it could not express in one short line was not a clear enough
        # reason to interrupt.
        return SILENT
    return judgement


def _parse(raw: str) -> Judgement | None:
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

    if not isinstance(payload, dict):
        return None
    try:
        return Judgement(
            worth_it=payload.get("worth_it", False),
            score=payload.get("score", 0.0),
            say=str(payload.get("say", "")),
            why=str(payload.get("why", "")),
        )
    except (TypeError, ValueError):
        return None
