"""How fast, and how faithful, the translation mode is.

Latency is the whole claim here — an interpreter that arrives after the moment has
passed is not an interpreter. Faithfulness is checked by properties rather than by
comparing against a reference sentence: there is no single right translation, but
there are things a translation must never do.

    OPENAI_API_KEY=... PYTHONPATH=src python3 bench/translate.py
"""

from __future__ import annotations

import re
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from symborg_engine.copilot.translate import Translator      # noqa: E402
from symborg_engine.providers import resolve_language_model  # noqa: E402

CONVERSATION = [
    ("in",  "Hi, are you looking for anything in particular?"),
    ("out", "Yok, sadece bakıyorum. Bu ne kadar?"),
    ("in",  "That one's forty-five euros. It's handmade, from a workshop in Porto."),
    ("out", "Biraz pahalı geldi, indirim yapabilir misiniz?"),
    ("in",  "I can do forty, but that's the best I can do."),
    ("out", "Tamam, anlaştık. Kartla ödeyebilir miyim?"),
]

# What a translation must carry through untouched. A dropped digit in a price or a
# date is the failure that costs someone money in a language they do not speak.
CARRIES = [
    ("Toplantı 14 Mart'ta saat 15.30'da, 250 euro bütçeyle.", ["14", "15.30", "250"]),
    ("Kerem Yıldız'ı arayın, 0532 111 22 33.", ["Kerem", "0532", "111", "22", "33"]),
    ("Uçak 07.45'te kalkıyor, kapı B12.", ["07.45", "B12"]),
]

# Blunt things a person said. Softening them is not politeness; it is speaking for them.
BLUNT = [
    ("Hayır.", ["no"]),
    ("Bana yalan söylediniz.", ["lied", "lie"]),
    ("İlgilenmiyorum.", ["not interested", "no interest"]),
]


def main() -> int:
    model = resolve_language_model(None)
    translator = Translator(model, mine="Türkçe", theirs="İngilizce")
    print(f"provider: {type(model).__name__}\n")

    latencies = []
    for direction, text in CONVERSATION:
        rendering = (translator.incoming(text) if direction == "in"
                     else translator.outgoing(text, speak=False))
        latencies.append(rendering.latency_ms)
        print(f"  {'◀' if direction == 'in' else '▶'} {text}")
        print(f"    {rendering.text}   [{rendering.latency_ms} ms]")

    print("\n  carries through untouched:")
    kept = 0
    for turkish, tokens in CARRIES:
        out = translator.outgoing(turkish, speak=False).text
        # Digits only. "15.30" becoming "15:30" is English convention, not a changed
        # number; an earlier version of this check flagged it and would have sent me
        # tuning a prompt that was already right.
        flat = re.sub(r"[^0-9a-zçğıöşü]", "", out.lower())
        missing = [t for t in tokens
                   if re.sub(r"[^0-9a-zçğıöşü]", "", t.lower()) not in flat]
        kept += not missing
        print(f"    {'ok  ' if not missing else 'LOST'} {out}"
              + (f"   missing {missing}" if missing else ""))

    print("\n  says what was said:")
    blunt = 0
    for turkish, expected in BLUNT:
        out = translator.outgoing(turkish, speak=False).text.lower()
        hit = any(re.search(rf"\b{re.escape(e)}", out) for e in expected)
        blunt += hit
        print(f"    {'ok  ' if hit else 'SOFT'} {out}")

    print(f"\n  median   {int(statistics.median(latencies))} ms")
    print(f"  fastest  {min(latencies)} ms")
    print(f"  slowest  {max(latencies)} ms")
    print(f"  spread   {max(latencies) - min(latencies)} ms"
          "   ← the number that decides whether this is usable")
    print(f"  numbers  {kept}/{len(CARRIES)} carried")
    print(f"  bluntness {blunt}/{len(BLUNT)} preserved")
    print("\n  A conversation budget is ~500 ms. Anything past a second is a pause the")
    print("  other person can hear, which is the cost of standing between two people.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
