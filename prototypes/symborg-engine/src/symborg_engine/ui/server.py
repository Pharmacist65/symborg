"""A local interface a person can actually use.

Until now candidates were selected by typing an index into Python, which is fine for a
pipeline and useless for the person the pipeline exists for. This serves them to a
browser, large and high-contrast, and accepts the inputs someone with very little
movement actually has.

Standard library only, so it runs anywhere the engine does:

    PYTHONPATH=src python3 -m symborg_engine.ui.server

Then open http://127.0.0.1:8770. The page is served to the local machine only.
"""

from __future__ import annotations

import json
import queue
import threading
import time
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from ..authorship import AuthorizationError
from ..session import Session

__all__ = ["Broadcaster", "UIState", "serve"]

STATIC = Path(__file__).parent / "static"


@dataclass(slots=True)
class UIState:
    """What the page is currently showing."""

    session: Session
    partial: str = ""
    candidates: list[dict] = field(default_factory=list)
    spoken: str = ""
    listening: bool = False
    level: int = 0

    def snapshot(self) -> dict:
        return {
            "partial": self.partial,
            "candidates": self.candidates,
            "spoken": self.spoken,
            "listening": self.listening,
            "level": self.level,
        }


class Broadcaster:
    """Pushes state to every connected page.

    Server-sent events rather than polling: a person reading slowly should not have
    options appear a beat after they were decided.
    """

    def __init__(self) -> None:
        self._clients: list[queue.Queue] = []
        self._lock = threading.Lock()

    def subscribe(self) -> queue.Queue:
        q: queue.Queue = queue.Queue(maxsize=64)
        with self._lock:
            self._clients.append(q)
        return q

    def unsubscribe(self, q: queue.Queue) -> None:
        with self._lock:
            if q in self._clients:
                self._clients.remove(q)

    def publish(self, payload: dict) -> None:
        message = json.dumps(payload, ensure_ascii=False)
        with self._lock:
            clients = list(self._clients)
        for q in clients:
            try:
                q.put_nowait(message)
            except queue.Full:
                pass          # a stalled page must not block the conversation


def _handler(state: UIState, bus: Broadcaster, audio: dict):

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *args) -> None:      # keep the console for the engine
            pass

        # -- responses ---------------------------------------------------------

        def _send(self, code: int, body: bytes, ctype: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, payload: dict, code: int = 200) -> None:
            self._send(code, json.dumps(payload, ensure_ascii=False).encode(),
                       "application/json; charset=utf-8")

        # -- routes ------------------------------------------------------------

        def do_GET(self) -> None:
            if self.path in ("/", "/index.html"):
                body = (STATIC / "index.html").read_bytes()
                self._send(200, body, "text/html; charset=utf-8")
            elif self.path == "/events":
                self._events()
            elif self.path.startswith("/audio/"):
                key = self.path.rsplit("/", 1)[-1]
                data = audio.get(key)
                if data is None:
                    self._send(404, b"", "text/plain")
                else:
                    self._send(200, data, "audio/wav")
            else:
                self._send(404, b"", "text/plain")

        def do_POST(self) -> None:
            if self.path != "/select":
                self._send(404, b"", "text/plain")
                return
            length = int(self.headers.get("Content-Length", 0))
            try:
                payload = json.loads(self.rfile.read(length) or b"{}")
                index = int(payload.get("index", -1))
            except (ValueError, json.JSONDecodeError):
                self._json({"error": "bad_request"}, 400)
                return

            try:
                token = state.session.select(index)
                result = state.session.speak(token)
            except AuthorizationError as exc:
                # The lock refusing is correct behaviour, not a server error: it means
                # nothing was offered, or the offer is already spent.
                self._json({"error": str(exc)}, 409)
                return

            key = str(int(time.time() * 1000))
            audio[key] = result.utterance.audio
            for stale in list(audio)[:-8]:
                audio.pop(stale, None)

            state.spoken = result.utterance.text
            state.candidates = []
            bus.publish(state.snapshot())
            self._json({"text": result.utterance.text, "audio": f"/audio/{key}"})

        def _events(self) -> None:
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "keep-alive")
            self.end_headers()

            q = bus.subscribe()
            try:
                self.wfile.write(f"data: {json.dumps(state.snapshot(), ensure_ascii=False)}\n\n"
                                 .encode())
                self.wfile.flush()
                while True:
                    try:
                        message = q.get(timeout=15)
                        self.wfile.write(f"data: {message}\n\n".encode())
                    except queue.Empty:
                        self.wfile.write(b": keep-alive\n\n")
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                pass
            finally:
                bus.unsubscribe(q)

    return Handler


def serve(state: UIState, bus: Broadcaster, host: str = "127.0.0.1",
          port: int = 8770) -> ThreadingHTTPServer:
    """Start the interface on a background thread."""
    audio: dict[str, bytes] = {}
    server = ThreadingHTTPServer((host, port), _handler(state, bus, audio))
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


# ---------------------------------------------------------------- entry point

def main() -> int:
    """Run the interface with a live microphone."""
    import argparse
    import array
    import math
    import sys

    from ..providers.realtime_stream import MicrophoneSource, RealtimeTranscriptStream
    from ..stream import drive

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--port", type=int, default=8770)
    ap.add_argument("--device", default=None, help="input device name or index")
    ap.add_argument("--gap", type=int, default=None, help="silence in ms that ends a turn")
    args = ap.parse_args()

    session = Session()
    if type(session.model).__name__ == "OfflineLanguageModel":
        print("Offline provider — candidates would be canned. Set a key first.",
              file=sys.stderr)
        return 1

    state = UIState(session=session)
    bus = Broadcaster()
    serve(state, bus, port=args.port)

    print(f"\n  SYMBORG  →  http://127.0.0.1:{args.port}")
    print(f"  transcription: gpt-live-transcribe   candidates: {session.model._model}")
    print(f"  speech: {type(session.synthesiser).__name__}")
    print("  Ctrl+C to stop.\n")

    def level_of(block: bytes) -> int:
        samples = array.array("h")
        samples.frombytes(block)
        if not samples:
            return 0
        return int(math.sqrt(sum(v * v for v in samples) / len(samples)))

    def metered(blocks):
        for block in blocks:
            state.level = level_of(block)
            state.listening = True
            yield block

    def on_fragment(fragment, fired: bool) -> None:
        state.partial = fragment.text
        bus.publish(state.snapshot())

    def on_turn(turn) -> None:
        state.partial = turn.partial
        state.candidates = [
            {"text": c.text, "kind": c.kind} for c in turn.result.candidates
        ]
        bus.publish(state.snapshot())
        lead = f"{turn.lead_ms} ms" if turn.anticipated else "—"
        print(f"  {turn.partial}   [lead {lead}]")

    try:
        with MicrophoneSource(device=args.device) as mic:
            kwargs = {"turn_gap_ms": args.gap} if args.gap else {}
            stream = RealtimeTranscriptStream(metered(mic.blocks()), **kwargs)
            drive(session, stream, on_turn=on_turn, on_fragment=on_fragment)
    except KeyboardInterrupt:
        pass
    except Exception as exc:
        print(f"\n{type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    finally:
        state.listening = False
        bus.publish(state.snapshot())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
