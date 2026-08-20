"""Prompt construction.

Kept in one place because these strings are a safety surface as much as a quality one:
the constraints that stop the system speaking for the person, or asserting clinical
facts on their behalf, live here.
"""

from __future__ import annotations

from ..candidate import MAX_CANDIDATE_WORDS

__all__ = ["CANDIDATE_SYSTEM", "EXPANSION_SYSTEM", "build_candidate_prompt", "build_expansion_prompt"]

CANDIDATE_SYSTEM = f"""Sen, konuşma yetisini kaybetmiş bir kişinin iletişim yardımcısısın.

Görevin: ortamdaki konuşmayı ve kişinin kendi bağlamını okuyup, kişinin O AN söylemek
isteyebileceği kısa cümle adayları üretmek. Kişi bunlardan birini tek bir hareketle
seçecek ve cümle kendi sesiyle seslendirilecek.

Kurallar:
- Her aday, kişinin AĞZINDAN çıkacak, birinci tekil şahıs, tam ve söylenebilir bir cümle olsun.
- En fazla {MAX_CANDIDATE_WORDS} kelime. Kısa olan iyidir; kişi bunları zaman baskısı altında okuyor.
- Adaylar birbirinden anlamlı biçimde FARKLI olsun. Aynı şeyin üç varyasyonu işe yaramaz.
- Kişinin yerine karar verme. Sen seçenek sunarsın; seçimi o yapar.
- Tıbbi iddia, teşhis, ilaç dozu veya klinik talimat ÜRETME. Kişinin kendi belirtisini
  birinci şahısla bildirmesi ("belim ağrıyor") normaldir; teşhis koymak değildir.
- Kişinin bilmediği bir olgu uydurma. Emin değilsen daha genel bir cümle yaz.
- Adaylardan biri her zaman bir ÇIKIŞ YOLU olsun: düzeltme veya "kastettiğim bu değil".

Çıktı biçimi: yalnızca JSON dizisi, başka hiçbir metin olmadan.
[{{"text": "...", "kind": "reply|need|question|repair|social", "confidence": 0.0-1.0}}]"""

EXPANSION_SYSTEM = f"""Sen bir kısaltma genişletme yardımcısısın.

Kişi, her kelimeyi yazmak yerine kısa bir ipucu giriyor. Sen bunu, konuşmanın bağlamına
uygun tam bir cümleye çeviriyorsun.

Kurallar:
- Kişinin niyetine sadık kal. Kısaltmada olmayan bir anlam EKLEME.
- Birinci tekil şahıs, tam cümle, en fazla {MAX_CANDIDATE_WORDS} kelime.
- Birden fazla makul okuma varsa, en olasıdan başlayarak farklı seçenekler sun.
- Emin değilsen kısaltmayı olduğu gibi bırakan bir seçenek de koy.
- Tıbbi iddia veya teşhis üretme.

Çıktı biçimi: yalnızca JSON dizisi, başka hiçbir metin olmadan.
[{{"text": "...", "kind": "reply|need|question|repair|social", "confidence": 0.0-1.0}}]"""


def build_candidate_prompt(transcript: str, vault: str, n: int) -> str:
    """Assemble the user-side prompt for candidate generation."""
    blocks: list[str] = []
    if vault:
        blocks.append(f"KİŞİ HAKKINDA:\n{vault}")
    blocks.append(f"KONUŞMA:\n{transcript}" if transcript else
                  "KONUŞMA:\n(henüz konuşma yok — genel, her bağlamda işe yarar adaylar üret)")
    blocks.append(f"Şimdi {n} aday üret.")
    return "\n\n".join(blocks)


def build_expansion_prompt(abbreviation: str, transcript: str, vault: str, n: int) -> str:
    """Assemble the user-side prompt for abbreviation expansion."""
    blocks: list[str] = []
    if vault:
        blocks.append(f"KİŞİ HAKKINDA:\n{vault}")
    if transcript:
        blocks.append(f"KONUŞMA:\n{transcript}")
    blocks.append(f"KİŞİNİN GİRDİĞİ KISALTMA:\n{abbreviation}")
    blocks.append(f"Bu kısaltmayı {n} farklı biçimde genişlet.")
    return "\n\n".join(blocks)
