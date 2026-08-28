"""When the person is talking to it, rather than near it.

This is the exact inverse of :mod:`salience`. Everywhere else the default is silence and
speaking has to be justified; here someone has deliberately turned to the device, and
saying nothing is the failure. The gate does not apply, the rate limit does not apply,
and being unsure is not a reason to stay quiet — it is a reason to say what it does know.

The work is deciding what they actually want, because the answers come from different
places. "Ne demişti adamın adı" is memory. "Bak şuna" needs the camera and cannot be
answered until a frame arrives. "Bunu İngilizce nasıl derim" is the translator. Getting
this wrong is not dangerous, only useless — but useless twice and nobody addresses it a
third time.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from enum import Enum

from ..providers.base import LanguageModel, Prompt, ProviderError

__all__ = ["Wants", "Address", "understand", "answer",
           "ADDRESS_SYSTEM", "ADDRESS_SCHEMA", "ANSWER_SYSTEM", "ANSWER_SCHEMA"]


class Wants(str, Enum):
    ANSWER = "answer"
    """Something it may already know. Comes from memory."""

    LOOK = "look"
    """Something in front of them. Needs a frame from the camera before it can answer."""

    TRANSLATE = "translate"
    """Something to say to someone else, or something just said that they did not follow."""

    REMEMBER = "remember"
    """Keep this on purpose, rather than waiting for the extractor to judge it worth
    keeping. A person saying "bunu unutma" outranks any confidence score."""

    FORGET = "forget"
    """Drop something. Always obeyed, never argued with."""

    UNCLEAR = "unclear"
    """It could not tell. Says so and asks, rather than guessing at an action."""


ADDRESS_SYSTEM = """Kişi SANA hitap etti. Ne istediğini anla.

Beş şeyden biri:

  answer     — bildiğin bir şeyi soruyor
               "adamın adı neydi", "toplantı ne zamandı", "ne demiştim ben"
  look       — önündeki bir şeye bakmanı istiyor
               "bak şuna", "bu ne", "şuna bir bakar mısın", "bunu tanıyor musun"
               Telefonu kaldırıp bir şey gösteriyor. Kamera gerekir.
  translate  — çeviri istiyor
               "bunu İngilizce nasıl derim", "ne dedi bu adam", "çevir"
  remember   — bir şeyi bilerek saklatmak istiyor
               "bunu unutma", "not al", "aklında tut"
  forget     — sildirmek istiyor
               "bunu unut", "sil şunu", "hiçbir şey hatırlama"
  unclear    — SON ÇARE. Yalnızca ortada bir istek YOKSA: dolgu sesi, yarım kalmış
               cümle, anlamsız parça. "Hımm şey ya işte", "Ee", "Şey..."
               Bir SORU sorulduysa unclear DEĞİLDİR. Cevabını bilmiyor olabilirsin —
               o ayrı mesele, önce ne istendiğini sınıflandır.
               "Sunum kaç sayfaydı" → answer. Bilmiyorsan sonra "bilmiyorum" dersin.

query alanına, o isteği yerine getirmek için gereken ŞEYİ yaz:
  "adamın adı neydi ya"        → want=answer,    query="adamın adı"
  "bak şuna, bu mantar ne"     → want=look,      query="bu mantar ne"
  "bunu İngilizce nasıl derim" → want=translate, query=çevrilecek metin
  "toplantıyı unutma"          → want=remember,  query="toplantı"

Kişi bir şeyi göstererek soruyorsa ("bu", "şu", "şuradaki") ve elle tutulur bir nesneden
bahsediyorsa want=look'tur — cevabı hafızanda arama, göremezsin.

AYIRIM — geçmişteki bir şey mi, önündeki bir şey mi:
  "bu mantar ne"        → şu an önünde bir mantar var        → look
  "o restoranın adı ne" → geçmişte gidilmiş bir yer          → answer
  "bu ne yazıyor"       → önünde bir yazı var                → look
  "ne demiştim ben"     → geçmişte söylenmiş bir şey          → answer

query — çeviri isteğinde ÇEVRİLECEK METNİ ayıkla, isteğin kendisini DEĞİL:
  "bunu İngilizce nasıl derim: hesabı alabilir miyiz"
      → query="hesabı alabilir miyiz"     ("bunu İngilizce nasıl derim" ÇEVRİLMEZ)
  "şunu çevir, biraz pahalı geldi"
      → query="biraz pahalı geldi"
  "ne dedi bu adam"
      → query=""   (çevrilecek metin karşı tarafın sözü; sen zaten duyacaksın)
Yanlış yaparsan, bir yabancıya senin isteğin okunur. Yalnızca söylenecek şeyi yaz.

Yalnızca JSON:
{"want": "answer|look|translate|remember|forget|unclear", "query": "...",
 "say_if_unclear": "anlamadıysan soracağın kısa soru, en fazla 10 kelime"}"""

ADDRESS_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "want": {"type": "string",
                 "enum": ["answer", "look", "translate", "remember", "forget", "unclear"]},
        "query": {"type": "string"},
        "say_if_unclear": {"type": "string"},
    },
    "required": ["want", "query", "say_if_unclear"],
    "additionalProperties": False,
}

# Cheap signals, checked before paying for a model call. Deliberately narrow: these decide
# only the obvious cases, and anything they do not catch goes to the model rather than
# being forced into a guess.
# Only the unambiguous ones. "bu ne" and "ne bu" belong to both worlds — "bu ne" while
# holding up a mushroom is the camera, and "İngilizcesi ne bunun" is not — so they go to
# the model, which has the present-versus-past distinction spelled out for it. A cheap
# path should catch what is certain and hand over what is not.
_LOOK_CUES = ("bak şu", "bak buna", "baksana", "bir bak", "şuna bak", "buna bak",
              "bunu tanı", "gördün mü", "kameraya", "şuna baksana")
_FORGET_CUES = ("unut", "sil ", "sil,", "sil.", "silme yap")
_REMEMBER_CUES = ("unutma", "not al", "aklında tut", "kaydet", "hatırlat")
_TRANSLATE_CUES = ("çevir", "nasıl derim", "nasıl denir", "ne dedi", "ne diyor",
                   "ingilizce", "almanca", "fransızca", "arapça")


def _fold(text: str) -> str:
    return text.replace("İ", "i").replace("I", "ı").lower()


def _has_cue(lowered: str, cues: tuple[str, ...]) -> bool:
    """Whether any cue appears as whole words.

    Plain substring matching put "ne bu" inside "İngilizcesi ne bunun", so asking for a
    translation opened the camera instead. Turkish suffixes make the ends of words
    unreliable, but the start of one is not.
    """
    return any(re.search(rf"(?<![a-zçğıöşüA-ZÇĞİÖŞÜ]){re.escape(cue)}", lowered)
               for cue in cues)


@dataclass(slots=True, frozen=True)
class Address:
    """What the person turned to it for."""

    want: Wants = Wants.UNCLEAR
    query: str = ""
    say_if_unclear: str = "Anlayamadım, tekrar söyler misin?"
    said: str = ""

    @property
    def needs_camera(self) -> bool:
        return self.want is Wants.LOOK

    def to_dict(self) -> dict:
        return {"want": self.want.value, "query": self.query,
                "say_if_unclear": self.say_if_unclear, "said": self.said}


def understand(model: LanguageModel, said: str) -> Address:
    """Work out what was asked of it.

    Returns:
        What they want. Never silence: this is the one path where having nothing to say
        is itself the failure, so an unreadable request comes back as a question rather
        than as nothing.
    """
    text = " ".join(said.split())
    if not text:
        return Address(said=text)

    lowered = _fold(text)

    # "Bunu unutma" is remember and "bunu unut" is forget, so the longer phrase has to be
    # tested first or every request to keep something deletes it instead.
    if _has_cue(lowered, _REMEMBER_CUES):
        return Address(Wants.REMEMBER, query=text, said=text)
    if _has_cue(lowered, _FORGET_CUES):
        return Address(Wants.FORGET, query=text, said=text)
    if _has_cue(lowered, _LOOK_CUES):
        return Address(Wants.LOOK, query=text, said=text)
    # Translation is deliberately not shortcut. The cues find the intent easily enough,
    # but the payload has to be separated from the request — "bunu İngilizce nasıl derim:
    # hesabı alabilir miyiz" came back as "How do I say this in English: Can we get the
    # bill?", which is the whole sentence read aloud to a waiter.

    prompt = Prompt(
        system=ADDRESS_SYSTEM,
        user=text,
        max_tokens=200,
        temperature=0.0,
        json_schema=ADDRESS_SCHEMA,
    )
    try:
        raw = model.complete(prompt)
    except ProviderError:
        # It cannot tell what was wanted, but it was definitely addressed. Answering from
        # memory is the safe guess: the worst case is recalling something irrelevant,
        # where guessing "look" would open a camera nobody pointed at anything.
        return Address(Wants.ANSWER, query=text, said=text)

    payload = _parse(raw)
    if payload is None:
        return Address(Wants.ANSWER, query=text, said=text)

    try:
        want = Wants(str(payload.get("want", "unclear")))
    except ValueError:
        want = Wants.UNCLEAR
    unclear = " ".join(str(payload.get("say_if_unclear", "")).split())
    return Address(
        want=want,
        query=" ".join(str(payload.get("query", "")).split()) or text,
        say_if_unclear=unclear or "Anlayamadım, tekrar söyler misin?",
        said=text,
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


ANSWER_SYSTEM = """Kişi sana doğrudan sordu. BİLDİKLERİN'e bakarak cevapla.

Kurallar:
- Kısa. Tek cümle, en fazla 14 kelime. Kulağa söylenecek.
- Cevabı doğrudan ver. "Hatırlattığım kadarıyla", "kayıtlarıma göre" deme.
- KENDİNDEN BAHSETME. "BİLDİKLERİN", "kayıtlarım", "hafızamda", "verilerimde" gibi
  ifadeler insanın duyacağı cümlede yeri olmayan makine sözleridir.
  kötü : "Bilmiyorum, BİLDİKLERİN'de sunum bilgisi yok."
  iyi  : "Bilmiyorum."
- BİLDİKLERİN'de yoksa "bilmiyorum" de. UYDURMA. Bilmemek, yanlış söylemekten iyidir.
- Emin değilsen ne kadar emin olduğunu söyle: "Salı sanırım, ama emin değilim."

Sana soruldu; susmak burada yanlış. Bilmiyorsan bile bir şey söyle."""

ANSWER_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "say": {"type": "string"},
        "knew": {"type": "boolean", "description": "Whether the answer came from memory"},
    },
    "required": ["say", "knew"],
    "additionalProperties": False,
}

MAX_ANSWER_WORDS = 14


def answer(model: LanguageModel, question: str, known: str) -> str:
    """Answer a direct question from what is remembered.

    Never returns nothing. Being asked and saying nothing is the one failure this path
    has; not knowing is an answer, and a short honest "bilmiyorum" is worth more than a
    confident guess.
    """
    asked = " ".join(question.split())
    if not asked:
        return "Anlayamadım."
    if not known.strip():
        return "Bunu bilmiyorum."

    prompt = Prompt(
        system=ANSWER_SYSTEM,
        user=f"BİLDİKLERİN:\n{known}\n\nSORU:\n{asked}",
        max_tokens=160,
        temperature=0.1,
        json_schema=ANSWER_SCHEMA,
    )
    try:
        raw = model.complete(prompt)
    except ProviderError:
        return "Şu an bakamıyorum."

    payload = _parse(raw)
    if payload is None:
        return "Bunu bilmiyorum."
    say = " ".join(str(payload.get("say", "")).split())
    if not say:
        return "Bunu bilmiyorum."
    if _leaks_machinery(say):
        # It described its own storage instead of answering. Asked for in the prompt and
        # caught here, because the person hears this and none of it is theirs.
        return "Bunu bilmiyorum."
    if len(say.split()) > MAX_ANSWER_WORDS:
        say = " ".join(say.split()[:MAX_ANSWER_WORDS])
    return say


_MACHINERY = ("bildiklerin", "bildiklerim", "kayıtlarım", "hafızamda", "verilerimde",
              "veritaban", "bağlamımda", "sistemde kayıtlı", "json", "prompt")


def _leaks_machinery(text: str) -> bool:
    """Whether the answer talks about its own storage rather than answering."""
    lowered = text.replace("İ", "i").replace("I", "ı").lower()
    return any(word in lowered for word in _MACHINERY)
