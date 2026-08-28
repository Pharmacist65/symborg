"""The phone as microphone, ear and screen; the engine somewhere else.

Phase A of the device question. The routing work settled what the hardware has to be:
in the situation this exists for — other people talking, a wrong date being agreed — a
pocketed phone has no way through, so the channel is an earpiece. That makes the phone
the microphone and the ear, and this the thing it talks to.

    PYTHONPATH=src python3 -m symborg_engine.ui.copilot_server

Then open the address it prints. One caveat it prints too: a browser will not hand over
a microphone on a plain-HTTP page unless the address is localhost. Reaching this from a
phone therefore needs TLS — pass --cert and --key, and the module explains how to make
a self-signed pair if you have none.
"""

from __future__ import annotations

import argparse
import base64
import binascii
import json
import queue
import socket
import ssl
import sys
import threading
import time
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler
from pathlib import Path

from ..copilot import Copilot, Memory, Situation
from ..copilot.look import look
from ..copilot.translate import Translator
from ..providers.browser_audio import SAMPLE_RATE, BrowserSource
from ..tls import ensure_trust_store
from .server import Broadcaster, QuietServer

__all__ = ["CopilotState", "serve", "main"]

STATIC = Path(__file__).parent / "static"
DEFAULT_PORT = 8771
BLOCK_LIMIT = 1 << 20      # a page sending more than a megabyte at once is not audio
PHOTO_LIMIT = 1 << 23      # a photograph, base64-encoded, with room to spare
HARD_LIMIT = 1 << 24       # past this, the connection is not worth saving


@dataclass(slots=True)
class CopilotState:
    """What the page is showing, and what the room looks like."""

    copilot: Copilot
    source: BrowserSource
    translator: Translator | None = None
    heard: str = ""
    listening: bool = False
    turns: int = 0
    spoke: int = 0
    asked_count: int = 0
    addressing: bool = False
    """The next turn is meant for it. Set by the page's press-to-talk, and it stays set
    until that turn actually closes — the person releases the button before the words
    have finished arriving."""
    log: list[dict] = field(default_factory=list)

    def snapshot(self) -> dict:
        return {
            "heard": self.heard,
            "listening": self.listening,
            "turns": self.turns,
            "spoke": self.spoke,
            "silence": round(self.copilot.silence_rate, 3),
            "asked": self.asked_count,
            "addressing": self.addressing,
            "remembered": len(self.copilot.memory.items),
            "situation": {
                "earpiece": self.copilot.situation.earpiece,
                "others_present": self.copilot.situation.others_present,
                "screen_visible": self.copilot.situation.screen_visible,
            },
            "log": self.log[-12:],
        }


def _lan_address() -> str:
    """The address a phone on the same network can reach. Best effort."""
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect(("10.255.255.255", 1))     # never sends anything
        return probe.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        probe.close()


def _entry(heard, audio: dict) -> dict:
    """What the page draws for one turn. Shared by the overheard and addressed paths so
    they cannot drift apart."""
    entry = {
        "at": time.strftime("%H:%M"),
        "transcript": heard.transcript,
        "said": heard.said,
        "channel": heard.delivery.channel.value if heard.delivery else "none",
        "held": heard.delivery.held.value if heard.delivery and heard.delivery.held
                else None,
        "remembered": list(heard.remembered),
        "latency_ms": heard.latency_ms,
        "audio": None,
        "addressed": False,
        "want": heard.address.want.value if heard.address else None,
        "sighting": heard.sighting,
    }
    if heard.utterance is not None:
        key = str(int(time.time() * 1000))
        audio[key] = heard.utterance.audio
        for stale in list(audio)[:-8]:
            audio.pop(stale, None)
        entry["audio"] = f"/audio/{key}"
    return entry


def _handler(state: CopilotState, bus: Broadcaster, audio: dict):

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *args) -> None:
            pass

        def _send(self, code: int, body: bytes, ctype: str) -> None:
            try:
                self.send_response(code)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                if self.close_connection:
                    self.send_header("Connection", "close")
                self.end_headers()
                if body:
                    self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                pass

        def _discard(self, length: int, cap: int) -> bool:
            """Read and throw away a body. False if it was too big even for that."""
            if length > cap:
                return False
            left = length
            while left > 0:
                chunk = self.rfile.read(min(65536, left))
                if not chunk:
                    return False
                left -= len(chunk)
            return True

        def _json(self, payload: dict, code: int = 200) -> None:
            self._send(code, json.dumps(payload, ensure_ascii=False).encode(),
                       "application/json; charset=utf-8")

        def do_GET(self) -> None:
            if self.path in ("/", "/index.html"):
                self._send(200, (STATIC / "copilot.html").read_bytes(),
                           "text/html; charset=utf-8")
            elif self.path == "/favicon.ico":
                self._send(204, b"", "image/x-icon")
            elif self.path == "/events":
                self._events()
            elif self.path.startswith("/audio/"):
                data = audio.get(self.path.rsplit("/", 1)[-1])
                self._send(404, b"", "text/plain") if data is None else \
                    self._send(200, data, "audio/wav")
            else:
                self._send(404, b"", "text/plain")

        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length", 0))
            limit = PHOTO_LIMIT if self.path == "/look" else BLOCK_LIMIT
            if length > limit:
                # Discard it rather than refusing to read. Answering mid-body closes
                # the socket while the page is still writing, which the page sees as a
                # broken connection rather than a rejection — and the page posts audio
                # continuously, so one oversized block would take the stream down with
                # it. Reading in bounded chunks keeps memory flat and the connection
                # alive; past the hard cap the connection really is finished.
                if not self._discard(length, HARD_LIMIT):
                    self.close_connection = True
                self._json({"error": "too_large", "limit": limit}, 413)
                return
            body = self.rfile.read(length) if length else b""

            if self.path == "/audio":
                state.source.feed(body)
                if not state.listening:
                    state.listening = True
                    bus.publish(state.snapshot())
                self._json({"ok": True, "waiting": state.source.waiting,
                            "dropped": state.source.dropped})
            elif self.path == "/situation":
                try:
                    payload = json.loads(body or b"{}")
                except json.JSONDecodeError:
                    self._json({"error": "bad_request"}, 400)
                    return
                current = state.copilot.situation
                state.copilot.situation = Situation(
                    earpiece=bool(payload.get("earpiece", current.earpiece)),
                    screen_visible=bool(payload.get("screen_visible",
                                                    current.screen_visible)),
                    others_present=bool(payload.get("others_present",
                                                    current.others_present)),
                    noisy=current.noisy,
                )
                bus.publish(state.snapshot())
                self._json({"ok": True})
            elif self.path == "/address":
                # Press-to-talk. The audio keeps flowing through the same stream; this
                # only marks which turn was meant for it, which is also how an earpiece
                # button would behave.
                state.addressing = True
                bus.publish(state.snapshot())
                self._json({"ok": True})
            elif self.path == "/asked":
                try:
                    payload = json.loads(body or b"{}")
                except json.JSONDecodeError:
                    self._json({"error": "bad_request"}, 400)
                    return
                said = str(payload.get("said", "")).strip()
                if not said:
                    self._json({"error": "nothing_said"}, 400)
                    return
                image = None
                if payload.get("image"):
                    try:
                        image = base64.b64decode(payload["image"], validate=True)
                    except (ValueError, binascii.Error):
                        self._json({"error": "bad_image"}, 400)
                        return
                heard = state.copilot.asked(said, image=image,
                                            translator=state.translator)
                state.asked_count += 1
                entry = _entry(heard, audio)
                entry["addressed"] = True
                state.log.append(entry)
                bus.publish(state.snapshot())
                self._json(entry)
            elif self.path == "/look":
                try:
                    payload = json.loads(body or b"{}")
                    image = base64.b64decode(payload.get("image", ""), validate=True)
                except (json.JSONDecodeError, ValueError, binascii.Error):
                    self._json({"error": "bad_request"}, 400)
                    return
                if not image:
                    self._json({"error": "no_image"}, 400)
                    return
                sighting = look(state.copilot.model, image,
                                str(payload.get("question", "Bu ne?")),
                                mime=str(payload.get("mime", "image/jpeg")))
                entry = {
                    "at": time.strftime("%H:%M"),
                    "transcript": str(payload.get("question", "Bu ne?")),
                    "said": sighting.whisper,
                    "channel": "screen",
                    "held": None,
                    "remembered": [],
                    "latency_ms": 0,
                    "audio": None,
                    "sighting": sighting.to_dict(),
                }
                state.log.append(entry)
                bus.publish(state.snapshot())
                self._json(sighting.to_dict())
            elif self.path == "/forget":
                removed = state.copilot.memory.forget_all()
                bus.publish(state.snapshot())
                self._json({"ok": True, "removed": removed})
            else:
                self._send(404, b"", "text/plain")

        def _events(self) -> None:
            q = bus.subscribe()
            try:
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Connection", "keep-alive")
                self.end_headers()
                self.wfile.write(f"data: {json.dumps(state.snapshot())}\n\n".encode())
                self.wfile.flush()
                while True:
                    try:
                        message = q.get(timeout=15)
                    except queue.Empty:
                        self.wfile.write(b": keep-alive\n\n")   # through proxies
                    else:
                        self.wfile.write(f"data: {message}\n\n".encode())
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
                pass
            finally:
                bus.unsubscribe(q)

    return Handler


def _listen(state: CopilotState, bus: Broadcaster, audio: dict, language: str) -> None:
    """Drive the copilot from whatever the page is sending."""
    from ..providers.realtime_stream import RealtimeTranscriptStream

    stream = RealtimeTranscriptStream(state.source.blocks(), language=language)
    for fragment in stream:
        # The text lives in the partials. The fragment that closes a turn carries the
        # end of the utterance and not its words — reading that one and calling it the
        # turn means every turn arrives empty, and the whole thing looks deaf while the
        # transcription is in fact perfect.
        if fragment.text.strip():
            state.copilot.hear_partial(fragment.text, cumulative=fragment.cumulative)
        if not fragment.is_final:
            state.heard = state.copilot.monitor.partial
            bus.publish(state.snapshot())
            continue

        said = state.copilot.monitor.partial.strip()
        if not said:
            state.copilot.monitor.reset()
            continue

        if state.addressing:
            state.addressing = False
            heard = state.copilot.asked(said, translator=state.translator)
            state.asked_count += 1
            state.heard = ""
            entry = _entry(heard, audio)
            entry["addressed"] = True
            state.log.append(entry)
            bus.publish(state.snapshot())
            continue

        heard = state.copilot.turn_ended(said)
        state.turns += 1
        state.heard = ""
        entry = _entry(heard, audio)
        if entry["audio"]:
            state.spoke += 1
        state.log.append(entry)
        bus.publish(state.snapshot())


def serve(copilot: Copilot, port: int = DEFAULT_PORT, language: str = "tr",
          certfile: str | None = None, keyfile: str | None = None,
          bind: str = "0.0.0.0", mine: str = "Türkçe",
          theirs: str = "İngilizce") -> None:
    """Run the page and the engine together until interrupted."""
    source = BrowserSource()
    state = CopilotState(copilot=copilot, source=source,
                         translator=Translator(copilot.model, mine=mine, theirs=theirs))
    bus = Broadcaster()
    audio: dict[str, bytes] = {}

    server = QuietServer((bind, port), _handler(state, bus, audio))
    scheme = "http"
    if certfile and keyfile:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(certfile, keyfile)
        server.socket = context.wrap_socket(server.socket, server_side=True)
        scheme = "https"

    threading.Thread(target=_listen, args=(state, bus, audio, language),
                     daemon=True).start()

    host = _lan_address()
    print(f"  {scheme}://127.0.0.1:{port}      (this machine)")
    print(f"  {scheme}://{host}:{port}   (a phone on the same network)")
    if scheme == "http":
        print("\n  A browser will not hand over a microphone on a plain-HTTP page unless")
        print("  the address is localhost, so the phone can watch but cannot listen.")
        print("  For the phone's microphone, make a certificate and pass it:\n")
        print(f"    openssl req -x509 -newkey rsa:2048 -nodes -days 365 \\")
        print(f"      -keyout key.pem -out cert.pem -subj '/CN={host}' \\")
        print(f"      -addext 'subjectAltName=IP:{host}'")
        print(f"    ... --cert cert.pem --key key.pem\n")
    print("  Ctrl-C to stop.\n")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  stopped.")
    finally:
        source.close()
        server.shutdown()
        server.server_close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="The copilot, served to a phone.")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--language", default="tr")
    parser.add_argument("--cert", default=None, help="TLS certificate (needed for a phone's microphone)")
    parser.add_argument("--key", default=None)
    parser.add_argument("--memory", default=None, help="Where to keep what it hears")
    parser.add_argument("--bind", default="0.0.0.0")
    parser.add_argument("--mine", default="Türkçe", help="The person's own language")
    parser.add_argument("--theirs", default="İngilizce", help="What to translate into")
    args = parser.parse_args(argv)

    ensure_trust_store()
    copilot = Copilot(memory=Memory.open(args.memory),
                      situation=Situation(earpiece=True, screen_visible=True,
                                          others_present=True))
    print(f"\n  sample rate {SAMPLE_RATE} Hz   language {args.language}")
    serve(copilot, port=args.port, language=args.language,
          certfile=args.cert, keyfile=args.key, bind=args.bind,
          mine=args.mine, theirs=args.theirs)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
