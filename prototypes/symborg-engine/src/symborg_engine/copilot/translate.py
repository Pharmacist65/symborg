"""Standing between two people who do not share a language.

This is the one mode where silence is wrong. The copilot's whole discipline is to say
almost nothing; here, every turn the person cannot understand is a turn they need, so
the default inverts and the gate does not apply.

Measured, against the real model: ~1.3 s median per turn, ~450 ms spread. That is over
the ~500 ms conversational budget and the other person can hear it — the pause is the
honest cost of standing between two people, and the way to shrink it is the same
speculative trick the turn-taking work uses, not a faster call. Dropping the JSON
envelope for plain text saves ~130 ms of median and doubles the tail (2.9 s worst
case), so the envelope stays.

Two directions, and they are not symmetrical. Inbound — what the other person said —
must be understood, so it is rendered plainly even where that costs the flavour of the
original. Outbound — what this person wants to say — is spoken aloud in a room by
someone who cannot check it, so it stays close to their words and never improves on
them. Putting a sentence in someone's mouth that they did not intend is the failure
this direction has to avoid, and politeness is not worth it.

Far tier: read aloud to a stranger on the person's behalf. Quality is the product.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field

from ..providers.base import LanguageModel, Prompt, ProviderError, Synthesiser, Utterance, VoiceRef

__all__ = ["Rendering", "Translator", "TRANSLATE_SYSTEM", "TRANSLATE_SCHEMA"]

TRANSLATE_SYSTEM = """Sen iki insanın arasında duran bir çevirmensin. Yorum yapmazsın,
öğüt vermezsin, konuşmaya katılmazsın. Yalnızca çevirirsin.

Kurallar:
- Anlamı koru, kelimeleri değil. HEDEF DİLDE O DURUMDA GERÇEKTEN NE DENİRSE ONU yaz.
  Bir deyimi harfi harfine çevirmek sadakat değildir; karşıdaki insan o cümleyi
  anlamaz ve senin varlığın boşa gider.
    "Tamam, anlaştık."      → "Alright, deal."        değil "we agreed"
    "Biraz pahalı geldi."   → "That's a bit pricey."  değil "it came out expensive"
    "Yolun açık olsun."     → "Safe travels."         değil "may the road be clear"
    "Kolay gelsin."         → "Take it easy."         (birebir karşılığı yoktur)
    "Elinize sağlık."       → "That was delicious."   (yemek içinse)
  Karşılığı yoksa, o durumda söylenecek EN YAKIN doğal cümleyi kur.
- EKLEME YAPMA. Söylenmeyen bir nezaket, bir açıklama, bir yumuşatma koyma.
- ÇIKARMA. Kaba, sert, ya da utandırıcı olsa da olduğu gibi çevir; süslemek senin
  işin değil ve karşındaki insan neyle karşılaştığını bilmeli.
- Soru soruysa soru kalsın. Emirse emir kalsın.
- Kısa tut; konuşma hızında okunacak.
- Rakam, tarih, isim, para birimi AYNEN kalsın. Çevirme, dönüştürme, yuvarlama.

Metni anlamadıysan ya da çevrilecek bir şey yoksa text boş bırak.

Yalnızca JSON:
{"text": "çeviri", "source_language": "algıladığın dilin adı", "literal": ""}

literal alanını yalnızca deyimsel bir şey çevirdiysen ve kişinin ne dendiğini
bilmesi işine yarayacaksa doldur; yoksa boş bırak."""

TRANSLATE_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "text": {"type": "string"},
        "source_language": {"type": "string"},
        "literal": {"type": "string"},
    },
    "required": ["text", "source_language", "literal"],
    "additionalProperties": False,
}


@dataclass(slots=True, frozen=True)
class Rendering:
    """One turn, carried across."""

    text: str
    source_language: str = ""
    literal: str = ""
    latency_ms: int = 0
    utterance: Utterance | None = None

    def __bool__(self) -> bool:
        return bool(self.text.strip())

    def to_dict(self) -> dict:
        return {"text": self.text, "source_language": self.source_language,
                "literal": self.literal, "latency_ms": self.latency_ms}


NOTHING = Rendering("")


@dataclass(slots=True)
class Translator:
    """Carries turns between two languages.

        t = Translator(model, mine="Türkçe", theirs="İngilizce")
        t.incoming("Where did you get this?")   # → what they said, in mine
        t.outgoing("Kadıköy'deki pazardan")     # → what to say, in theirs, spoken
    """

    model: LanguageModel
    synthesiser: Synthesiser | None = None
    mine: str = "Türkçe"
    theirs: str = "İngilizce"
    voice: VoiceRef = field(default_factory=lambda: VoiceRef(voice_id="offline"))

    def incoming(self, said: str) -> Rendering:
        """What the other person just said, in the person's own language.

        Not spoken aloud: it goes to the ear or the screen, because saying it out loud
        would put a second voice into a conversation that already has two.
        """
        return self._render(said, into=self.mine)

    def outgoing(self, said: str, speak: bool = True) -> Rendering:
        """What this person wants to say, in the other language.

        Spoken aloud by default — this direction is the one that has to leave the
        device, and it is why the mode is worth anything.
        """
        rendering = self._render(said, into=self.theirs)
        if not rendering or not speak or self.synthesiser is None:
            return rendering
        try:
            utterance = self.synthesiser.synthesise(rendering.text, self.voice)
        except ProviderError:
            return rendering       # the text still stands; it can be shown instead
        return Rendering(rendering.text, rendering.source_language, rendering.literal,
                         rendering.latency_ms, utterance)

    def _render(self, said: str, into: str) -> Rendering:
        text = said.strip()
        if not text:
            return NOTHING
        started = time.monotonic()
        prompt = Prompt(
            system=TRANSLATE_SYSTEM,
            user=f"HEDEF DİL: {into}\n\nMETİN:\n{text}",
            max_tokens=400,
            temperature=0.1,      # a translation should not vary between runs
            json_schema=TRANSLATE_SCHEMA,
            tier="far",
        )
        try:
            raw = self.model.complete(prompt)
        except ProviderError:
            return NOTHING
        payload = _parse(raw)
        if payload is None:
            return NOTHING
        return Rendering(
            text=" ".join(str(payload.get("text", "")).split()),
            source_language=str(payload.get("source_language", "")),
            literal=" ".join(str(payload.get("literal", "")).split()),
            latency_ms=int((time.monotonic() - started) * 1000),
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
