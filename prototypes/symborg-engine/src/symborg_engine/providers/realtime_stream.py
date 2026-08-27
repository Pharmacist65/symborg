"""Live transcription from the OpenAI Realtime API.

Optional extra: ``pip install '.[realtime]'``. Imported lazily, so the core never
depends on it.

Why this and not our own audio stack: streaming recognition, noise handling and
voice-activity detection are solved engineering, and rebuilding them would cost months
and produce something worse. What this API does not supply is anticipation — every
turn-boundary event it emits fires *after* silence has been observed, and the
speech-stopped event includes the silence window by construction. The classifier that
scores whether a speaker has finished is consumed internally and never exposed.

So the division is clean: the audio pipeline is theirs, and the decision to commit to a
set of candidates *before* the speaker stops stays ours, running on the transcript
deltas this stream produces while the partner is still talking.
"""

from __future__ import annotations

import asyncio
import base64
import queue
import threading
from dataclasses import dataclass, field
from typing import Iterator

from ..stream import Fragment
from ..tls import ensure_trust_store

__all__ = ["RealtimeTranscriptStream", "MicrophoneSource", "TRANSCRIBE_MODEL"]

TRANSCRIBE_MODEL = "gpt-live-transcribe"
"""Streaming transcription. Emits transcript deltas as speech arrives, which is the
property the whole design depends on."""

SAMPLE_RATE = 24_000
"""The API accepts 24 kHz mono PCM16 only."""

BLOCK_FRAMES = 2_400
"""100 ms per block. Small enough that a fragment reaches the predictor promptly,
large enough not to flood the socket."""

_SENTINEL = object()


@dataclass(slots=True)
class MicrophoneSource:
    """Captures microphone audio as 24 kHz mono PCM16 blocks."""

    device: int | str | None = None
    _queue: queue.Queue = field(default_factory=queue.Queue, init=False, repr=False)
    _stream: object | None = field(default=None, init=False, repr=False)

    def __enter__(self):
        try:
            import sounddevice
        except ImportError as exc:  # pragma: no cover - optional extra
            raise ImportError(
                "Microphone capture needs sounddevice. "
                "Install with: pip install '.[realtime]'"
            ) from exc

        def callback(indata, frames, time_info, status) -> None:
            self._queue.put(bytes(indata))

        self._stream = sounddevice.RawInputStream(
            samplerate=SAMPLE_RATE, blocksize=BLOCK_FRAMES, channels=1,
            dtype="int16", device=self.device, callback=callback,
        )
        self._stream.start()
        return self

    def __exit__(self, *exc) -> None:
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        self._queue.put(_SENTINEL)

    def blocks(self) -> Iterator[bytes]:
        while True:
            block = self._queue.get()
            if block is _SENTINEL:
                return
            yield block


class RealtimeTranscriptStream:
    """A :class:`~symborg_engine.stream.TranscriptStream` backed by live transcription.

    Runs the async client on a background thread and exposes a plain iterator, so the
    engine stays synchronous and knows nothing about how audio arrives.

        with MicrophoneSource() as mic:
            stream = RealtimeTranscriptStream(mic.blocks())
            drive(session, stream)
    """

    def __init__(self, audio_blocks: Iterator[bytes], languages: tuple[str, ...] = ("tr", "en"),
                 eagerness: str = "high", api_key: str | None = None) -> None:
        """
        Args:
            audio_blocks: 24 kHz mono PCM16 blocks.
            languages: Hints for the recogniser. The API rejects unsupported codes,
                which makes a session update a cheap way to confirm support.
            eagerness: Caps how long the server waits before declaring a turn over.
                "high" keeps that tail short; it does not make the API anticipate,
                which nothing it offers does.
        """
        self._audio = audio_blocks
        self._languages = list(languages)
        self._eagerness = eagerness
        self._api_key = api_key
        self._out: queue.Queue = queue.Queue()
        self._thread: threading.Thread | None = None
        self._error: BaseException | None = None

    def __iter__(self) -> Iterator[Fragment]:
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        while True:
            item = self._out.get()
            if item is _SENTINEL:
                break
            if isinstance(item, BaseException):
                raise item
            yield item

    # -- background --------------------------------------------------------------

    def _run(self) -> None:
        try:
            asyncio.run(self._listen())
        except BaseException as exc:  # surfaced on the consuming thread
            self._out.put(exc)
        finally:
            self._out.put(_SENTINEL)

    async def _listen(self) -> None:
        # The WebSocket builds its own SSL context, so it inherits the platform's
        # missing trust store where the SDK's HTTP client would not have.
        ensure_trust_store()
        try:
            from openai import AsyncOpenAI
        except ImportError as exc:  # pragma: no cover - optional extra
            raise ImportError(
                "Live transcription needs the realtime extra. "
                "Install with: pip install '.[realtime]'"
            ) from exc

        client = AsyncOpenAI(api_key=self._api_key)
        async with client.realtime.connect() as conn:
            await conn.session.update(session=self._session_config())
            pump = asyncio.create_task(self._pump(conn))
            try:
                await self._consume(conn)
            finally:
                pump.cancel()

    def _session_config(self) -> dict:
        return {
            # Transcription-only: the model listens and never replies. SYMBORG is not
            # a participant in the conversation; it prepares options for one.
            "type": "transcription",
            "audio": {
                "input": {
                    "format": {"type": "audio/pcm", "rate": SAMPLE_RATE},
                    "noise_reduction": {"type": "far_field"},
                    "transcription": {
                        "model": TRANSCRIBE_MODEL,
                        "languages": self._languages,
                        "delay": "minimal",
                    },
                    "turn_detection": {"type": "semantic_vad", "eagerness": self._eagerness},
                }
            },
        }

    async def _pump(self, conn) -> None:
        """Feed captured audio to the socket without blocking the event loop."""
        loop = asyncio.get_running_loop()
        iterator = iter(self._audio)
        while True:
            block = await loop.run_in_executor(None, lambda: next(iterator, None))
            if block is None:
                return
            await conn.input_audio_buffer.append(audio=base64.b64encode(block).decode())

    async def _consume(self, conn) -> None:
        """Translate server events into fragments.

        Deltas are the point: they arrive while the partner is still speaking, which is
        what lets the predictor commit before the turn ends.
        """
        partial = ""
        async for event in conn:
            kind = getattr(event, "type", "")

            if kind == "conversation.item.input_audio_transcription.delta":
                # Deltas are concatenated verbatim: they may split mid-word, so
                # inserting separators here would corrupt the text. The assembled
                # partial is emitted whole and the monitor replaces rather than appends.
                partial += getattr(event, "delta", "") or ""
                if partial.strip():
                    self._out.put(Fragment(text=partial, is_final=False, cumulative=True))

            elif kind == "conversation.item.input_audio_transcription.completed":
                partial = ""
                # The turn is over. An empty final fragment closes it without
                # duplicating text the deltas already delivered.
                self._out.put(Fragment(text="", is_final=True))

            elif kind == "conversation.item.input_audio_transcription.failed":
                partial = ""
                self._out.put(Fragment(text="", is_final=True))

            elif kind == "error":
                raise RuntimeError(f"realtime_error: {getattr(event, 'error', event)}")
