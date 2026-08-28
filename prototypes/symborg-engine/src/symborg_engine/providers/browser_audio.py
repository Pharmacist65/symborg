"""Audio arriving from a browser instead of a local microphone.

The device question answers itself once you watch the routing decide: in the situation
this product exists for — other people talking, a wrong date being agreed — a phone in
a pocket has no way through. The channel is an earpiece, which means the phone is the
microphone and the ear, and the machine running the engine is somewhere else.

So the audio source has to be a queue somebody else fills, rather than a device this
process opens. :class:`RealtimeTranscriptStream` already takes any iterator of PCM
blocks, so nothing downstream knows the difference.
"""

from __future__ import annotations

import queue
import threading
from collections.abc import Iterator

__all__ = ["BrowserSource", "SAMPLE_RATE"]

SAMPLE_RATE = 24_000
"""What the transcription endpoint expects. The page resamples to this before sending,
because doing it in the browser costs nothing and doing it here costs a dependency."""

_STOP = object()


class BrowserSource:
    """A microphone that lives in someone else's browser.

        source = BrowserSource()
        stream = RealtimeTranscriptStream(source.blocks())   # engine side
        source.feed(pcm16_bytes)                             # request handler side

    Thread-safe: fed from request threads, drained by the engine thread.
    """

    def __init__(self, max_blocks: int = 120) -> None:
        """
        Args:
            max_blocks: How much audio to hold when the engine falls behind. Roughly
                12 seconds. Past that the oldest is dropped rather than the newest —
                falling behind on a conversation means losing the beginning of it, and
                the recent past is what a turn is made of.
        """
        self._queue: queue.Queue = queue.Queue(maxsize=max_blocks)
        self._closed = threading.Event()
        self._dropped = 0

    def feed(self, pcm16: bytes) -> None:
        """Accept a block of 24 kHz mono PCM16 from the page."""
        if self._closed.is_set() or not pcm16:
            return
        try:
            self._queue.put_nowait(pcm16)
        except queue.Full:
            try:
                self._queue.get_nowait()      # drop the oldest, keep the present
                self._dropped += 1
                self._queue.put_nowait(pcm16)
            except (queue.Empty, queue.Full):
                pass

    def blocks(self) -> Iterator[bytes]:
        """Yield audio as it arrives, and drain what is left before stopping."""
        while True:
            try:
                block = self._queue.get(timeout=0.1)
            except queue.Empty:
                if self._closed.is_set():
                    return
                continue
            if block is _STOP:
                return
            yield block

    def close(self) -> None:
        """Stop after what has already arrived.

        The sentinel is best-effort: an earlier version made room for it by discarding
        a block, which meant closing threw away the last thing the person said. The
        flag is what actually stops the iterator, so a full queue simply drains first.
        """
        self._closed.set()
        try:
            self._queue.put_nowait(_STOP)
        except queue.Full:
            pass

    @property
    def dropped(self) -> int:
        """Blocks lost to a full buffer. Non-zero means the engine is behind the room."""
        return self._dropped

    @property
    def waiting(self) -> int:
        return self._queue.qsize()
