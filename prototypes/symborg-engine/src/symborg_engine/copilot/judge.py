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
from .contradiction import check

__all__ = ["Judgement", "judge_moment", "decide", "JUDGE_SYSTEM", "JUDGE_SCHEMA"]

JUDGE_SYSTEM = """Sen bir insanın yanında duran sessiz bir yardımcısın.

Varsayılanın SUSMAK. Ama susmak da bir başarısızlık olabilir: bildiğin bir şeyi
söylemediğin için biri bir randevuyu kaçırırsa, orada olmanın anlamı kalmaz.

Sırayla iki soru sor. İlk "evet"te konuş, ikisi de "hayır"sa sus.
(Yanlış hatırlamayı düzeltmek ayrı bir mekanizmanın işi; burada onu düşünme.)

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

   TEK İSTİSNA — GÖRÜNÜR ARAYIŞ. Kişi bir şeyi hatırlamaya ÇALIŞIYORSA, cümle
   duygusal görünse bile arayıştır: cevabı biliyorsan söyle. Yardımın en saf hâli.
     "adı neydi ya"  "hiç aklıma gelmiyor"  "dilimin ucunda"  "hatırlamıyorum"
     "unuttum"  "çıkmıyor bir türlü"  "neydi o"  "ne zamandı"

   AMA BU İSTİSNA YALNIZCA O İŞARETLERLE AÇILIR. Konunun hafızanda kayıtlı olması
   yetmez; kişinin ARADIĞINI görmen gerekir.
     "Şu projeyi bitirsek iyi olur."  → kimse bir tarih aramıyor. Sen teslim tarihini
        biliyor olabilirsin; sorulmadı. SUS.
     "Yarın toplantı var galiba."     → arayış yok. SUS.
   Hafızanda cevabı var diye soru üretme. Arayış yoksa istisna da yoktur.
   Bu istisna, aşağıdaki son süzgeçten önce gelir.

2. Kişi doğrudan sana mı sordu?
   → Evet ise KONUŞ.

İkisi de hayırsa SUS. Sohbet, hâl hatır, şaka, plan YAPMA, duygusal an — hepsi sus.

   PLAN YAPMA ile PLANI HATIRLAMA ayrı şeylerdir. Türkçe bunu ekle söyler:
   "Akşam nereye gidelim?" / "ne yesek?"  → henüz karar yok. Plan yapıyorlar. SUS.
   "Akşam nereye gidecektik?"             → karar VERİLMİŞ, unutulmuş. SÖYLE.
   "Ne demiştik?" "Kaça anlaşmıştık?" "Nerede buluşacaktık?" → hepsi hatırlama. SÖYLE.
   -AcAktI, -mIştI, "demiştik", "hani" geçmişte kalmış bir kararı arar; -AlIm, -sAk
   henüz yok olan bir kararı önerir. Birincisinde cevabı biliyorsan söyle.
Faydalı ama sorulmamış bilgi de sus; onu söylemek gürültüdür.

SON SÜZGEÇ — SÖYLEYECEĞİN ŞEY, ÖNÜNDEKİ CÜMLENİN KARŞILIĞI OLMALI:
Bir maddeye "evet" dedin diye BİLDİKLERİN'den eline geçen ilk şeyi söyleyemezsin.
Cevabın, tam da o an konuşulan şeye değmiyorsa SUS.
  "Bütçe 200 bindi galiba?" + bildiğin yalnızca toplantı saati → SUS. Bütçeyi bilmiyorsun.
  "Yarın yağmur varmış."    + bildiğin toplantı saati          → SUS. Kimse sormadı.
Testi şu: söyleyeceğin cümle, o kişinin AZ ÖNCE söylediği şeyle ilgili mi?
İlgili değilse, doğru olması seni kurtarmaz.



MUTLAK SUSMA: yas, ölüm, hastalık, kavga, ağlama. Ne bilirsen bil, sus.

BİLDİKLERİN boşsa, 1. madde otomatik olarak hayırdır — uydurma.

Söyleyeceğin TEK cümle, en fazla 12 kelime. Kulağa fısıldanacak.
Cevabı doğrudan ver: "12 Mart, saat iki." — "Hatırlatmak isterim ki..." deme.

Yalnızca JSON:
{"worth_it": true|false, "score": 0.0-1.0, "say": "...", "why": "hangi madde"}

worth_it false ise say boş. score: 1. madde ~0.9, 2. madde ~0.8."""

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

    __slots__ = ("worth_it", "score", "say", "why", "perishable")

    def __init__(self, worth_it: bool, score: float, say: str, why: str,
                 perishable: bool = False) -> None:
        self.worth_it = bool(worth_it)
        self.score = max(0.0, min(1.0, float(score)))
        self.say = " ".join(say.split())
        self.why = why.strip()
        self.perishable = bool(perishable)
        """Whether this stops being useful once the moment passes. A correction does —
        said three sentences late it reopens something the room had settled. A recalled
        name does not; it keeps until the person looks down."""

    @property
    def is_too_long(self) -> bool:
        return len(self.say.split()) > MAX_WORDS

    def to_dict(self) -> dict:
        return {"worth_it": self.worth_it, "score": round(self.score, 3),
                "say": self.say, "why": self.why, "perishable": self.perishable}

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


def decide(model: LanguageModel, said: str, known: str = "",
           asked: bool = False) -> Judgement:
    """The whole content decision: is there anything here worth a whisper.

    Two mechanisms, deliberately kept apart. First a plain comparison against what is
    known — mechanical, temperature zero, no vocabulary for politeness, so it cannot
    talk itself out of a wrong date. Only then the judgement about whether an ordinary
    moment deserves interrupting.

    Everything the product speaks goes through here, and so does everything the eval
    measures; a benchmark that exercises a different path measures a different product.
    """
    mismatch = check(model, said, known)
    if mismatch:
        return Judgement(worth_it=True, score=0.85, say=mismatch.correct,
                         why=f"çelişki: {mismatch.field}", perishable=True)
    return judge_moment(model, said, known, asked=asked)
