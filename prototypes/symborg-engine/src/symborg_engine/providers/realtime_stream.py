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
import time
from dataclasses import dataclass, field
from typing import Iterator

from ..stream import Fragment
from ..tls import ensure_trust_store

__all__ = ["RealtimeTranscriptStream", "MicrophoneSource", "TRANSCRIBE_MODEL"]

TRANSCRIBE_MODEL = "gpt-live-transcribe"
"""Streaming transcription. Verified against the live API: it emits deltas while the
speaker is still talking, which is the one property the whole design depends on. The
alternatives that do support server-side turn detection returned nothing until the
buffer was committed, which would be useless here."""

TURN_GAP_MS = 1_400
"""Silence, measured as a gap between deltas, that ends a turn.

This model does not support server-side turn detection — and does not need to, because
the predictor is what decides a turn is ending. This is only the backstop that closes
the turn once the speaker has actually stopped.

Set from measurement rather than intuition. At 700 ms a single Turkish question was
split in two, because deltas do not arrive evenly: an 830 ms gap appeared inside one
sentence while the recogniser caught up. The cost of being late here is small — the
predictor has already committed and the candidates are waiting — while the cost of
being early is cutting someone off mid-sentence."""

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

    def __init__(self, audio_blocks: Iterator[bytes], language: str = "tr",
                 turn_gap_ms: int = TURN_GAP_MS, api_key: str | None = None,
                 drain_s: float = 3.0) -> None:
        """
        Args:
            audio_blocks: 24 kHz mono PCM16 blocks.
            language: Recogniser hint.
            turn_gap_ms: Silence between deltas that closes a turn. Only a backstop —
                the predictor is what decides a turn is *about* to end.
            drain_s: How long to keep listening after the audio source ends, so the
                final transcript arrives before the session closes.
        """
        self._audio = audio_blocks
        self._language = language
        self._turn_gap_ms = turn_gap_ms
        self._api_key = api_key
        self._drain_s = drain_s
        self._out: queue.Queue = queue.Queue()
        self._thread: threading.Thread | None = None
        self._error: BaseException | None = None
        self._last_delta: float | None = None

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
        # A transcription session is opened by intent, not by naming a model in the
        # handshake — passing a transcription model there is rejected outright, and
        # omitting the intent opens a conversational session that refuses this config.
        async with client.realtime.connect(extra_query={"intent": "transcription"}) as conn:
            await conn.session.update(session=self._session_config())
            pump = asyncio.create_task(self._pump(conn))
            consume = asyncio.create_task(self._consume(conn))
            # Whichever finishes first ends the session: the audio source running out
            # is a normal end, not a reason to sit waiting for events that will never
            # come.
            done, pending = await asyncio.wait(
                {pump, consume}, return_when=asyncio.FIRST_COMPLETED,
            )
            for task in pending:
                task.cancel()
            for task in done:
                if task.exception() is not None:
                    raise task.exception()

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
                        "language": self._language,
                    },
                    # Deliberately no turn_detection. This model rejects it, and the
                    # models that accept it do not stream deltas — which would remove
                    # the only thing that makes anticipation possible. Turn boundaries
                    # are decided here instead, which is where they belong.
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
                # The source is exhausted. Commit whatever is buffered so the last turn
                # is transcribed, then give the server a moment to send it.
                try:
                    await conn.input_audio_buffer.commit()
                except Exception:
                    pass
                await asyncio.sleep(self._drain_s)
                return
            await conn.input_audio_buffer.append(audio=base64.b64encode(block).decode())

    async def _consume(self, conn) -> None:
        """Translate server events into fragments, and close turns on silence.

        Deltas are the point: they arrive while the partner is still speaking, which is
        what lets the predictor commit before the turn ends. They also split mid-word
        — verified against the live API, which sent "Ağ", "r", "ın" as three events —
        so they are concatenated verbatim and the assembled partial is emitted whole.
        """
        partial = ""
        started = time.monotonic()
        watchdog = asyncio.create_task(self._close_on_silence(conn))
        try:
            async for event in conn:
                kind = getattr(event, "type", "")

                if kind == "conversation.item.input_audio_transcription.delta":
                    partial += getattr(event, "delta", "") or ""
                    self._last_delta = time.monotonic()
                    if partial.strip():
                        self._out.put(Fragment(
                            text=partial, is_final=False, cumulative=True,
                            at_ms=int((time.monotonic() - started) * 1000),
                        ))

                elif kind in ("conversation.item.input_audio_transcription.completed",
                              "conversation.item.input_audio_transcription.failed"):
                    if partial.strip():
                        # Carry the elapsed time: this is the turn-end timestamp the
                        # lead measurement is taken against.
                        self._out.put(Fragment(
                            text="", is_final=True,
                            at_ms=int((time.monotonic() - started) * 1000),
                        ))
                    partial = ""
                    started = time.monotonic()

                elif kind == "error":
                    raise RuntimeError(f"realtime_error: {getattr(event, 'error', event)}")
        finally:
            watchdog.cancel()

    async def _close_on_silence(self, conn) -> None:
        """Commit the buffer once the speaker has stopped.

        Without server-side turn detection nothing else ends a turn, so this watches
        for a gap between deltas and commits, which produces the completed event.
        """
        while True:
            await asyncio.sleep(0.1)
            if self._last_delta is None:
                continue
            if (time.monotonic() - self._last_delta) * 1000 >= self._turn_gap_ms:
                self._last_delta = None
                try:
                    await conn.input_audio_buffer.commit()
                except Exception:
                    return
