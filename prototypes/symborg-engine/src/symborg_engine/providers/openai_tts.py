"""Speech synthesis.

Optional extra: ``pip install '.[openai]'``. Imported lazily, so the core never depends
on it.

This is the last step of the loop and the only one the room hears, so the constraint is
the same as everywhere else: it speaks only what the person selected. The synthesiser
receives text that :class:`~symborg_engine.session.Session` has already redeemed against
an authorisation — it is never handed a candidate directly.
"""

from __future__ import annotations

import os

from .base import Utterance, VoiceRef

__all__ = ["OpenAISynthesiser", "DEFAULT_TTS_MODEL", "DEFAULT_VOICE"]

DEFAULT_TTS_MODEL = "gpt-4o-mini-tts"
DEFAULT_VOICE = "alloy"

DEFAULT_INSTRUCTIONS = (
    "Bunu konuşamayan bir kişi adına, onun kendi cümlesi olarak söyle. "
    "Sakin, doğal ve insan gibi. Aceleci değil, abartılı değil, tiyatral değil. "
    "Bu bir duyuru değil, bir insanın karşısındakine söylediği cümle."
)
"""How the sentence should be delivered.

Worth saying explicitly: this voice is standing in for a person who cannot object to
how they are made to sound. A performed or hurried reading is not a neutral default —
it puts a tone in someone's mouth that they did not choose."""


class OpenAISynthesiser:
    """Adapts the OpenAI speech API to the :class:`Synthesiser` protocol."""

    def __init__(self, model: str | None = None, voice: str | None = None,
                 api_key: str | None = None, timeout_s: float = 10.0,
                 instructions: str | None = None) -> None:
        try:
            import openai
        except ImportError as exc:  # pragma: no cover - optional extra
            raise ImportError(
                "The 'openai' package is required. Install with: pip install '.[openai]'"
            ) from exc

        key = api_key or os.environ.get("OPENAI_API_KEY")
        if not key:
            from .base import ProviderError
            raise ProviderError("no_api_key")

        self._openai = openai
        self._model = model or os.environ.get("SYMBORG_TTS_MODEL", DEFAULT_TTS_MODEL)
        self._voice = voice or os.environ.get("SYMBORG_TTS_VOICE", DEFAULT_VOICE)
        self._instructions = DEFAULT_INSTRUCTIONS if instructions is None else instructions
        self._client = openai.OpenAI(api_key=key, timeout=timeout_s, max_retries=1)

    def synthesise(self, text: str, voice: VoiceRef) -> Utterance:
        """Speak an authorised sentence.

        Raises:
            ProviderError: on failure. The caller surfaces silence rather than
                substituting a different voice or a different sentence.
        """
        from .base import ProviderError

        chosen = voice.voice_id if voice.voice_id and voice.voice_id != "offline" else self._voice
        try:
            response = self._client.audio.speech.create(
                model=self._model,
                voice=chosen,
                input=text,
                instructions=self._instructions,
                response_format="wav",
            )
            audio = response.content
        except self._openai.OpenAIError as exc:
            raise ProviderError(f"synthesis_failed: {exc}") from exc

        if not audio:
            raise ProviderError("empty_audio")

        return Utterance(text=text, audio=audio, mime_type="audio/wav", voice_id=chosen)
