from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse


ROOT = Path(__file__).resolve().parents[2]
CONTEXTUAL_SRC = ROOT / "prototypes" / "contextual-whisper-demo" / "src"
ROUTER_SRC = ROOT / "prototypes" / "output-router-demo" / "src"
STATIC_DIR = Path(__file__).resolve().parent / "static"

for path in (CONTEXTUAL_SRC, ROUTER_SRC):
    path_text = str(path)
    if path_text not in sys.path:
        sys.path.insert(0, path_text)

from symborg.context import InteractionState  # noqa: E402
from symborg.heuristic_engine import generate_packets  # noqa: E402
from symborg_output_router.router import (  # noqa: E402
    DeviceCapabilities,
    UserState,
    packet_from_dict,
    route_packet,
)


DEFAULT_TRANSCRIPTS = {
    "dickens": (
        "A: I think Great Expectations is less about class mobility and more about shame.\n"
        "B: Interesting. What do you think?"
    ),
    "meeting": (
        "A: We need to decide if this startup idea is an MVP or just a feature.\n"
        "B: The investor asked about pricing, user pain, and weekly usage."
    ),
    "clinical": (
        "Doctor: Where is the pain worse?\n"
        "Context note: the patient has neck pain that increases at night and needs help changing position."
    ),
}


def _bool(data: dict[str, Any], key: str, default: bool = False) -> bool:
    value = data.get(key, default)
    return bool(value)


def _int(data: dict[str, Any], key: str, default: int) -> int:
    try:
        return int(data.get(key, default))
    except (TypeError, ValueError):
        return default


def _float(data: dict[str, Any], key: str, default: float) -> float:
    try:
        return float(data.get(key, default))
    except (TypeError, ValueError):
        return default


def _route_payload(packet_data: dict[str, Any], request: dict[str, Any]) -> dict[str, Any]:
    packet = packet_from_dict(packet_data)
    router_state = UserState(
        user_is_speaking=_bool(request, "user_is_speaking"),
        pause_ms=_int(request, "pause_ms", 900),
        walking=_bool(request, "walking"),
        driving=_bool(request, "driving"),
        high_stress=_float(request, "cognitive_load", 0.35) >= 0.75,
        silence_mode=request.get("user_signal") == "long_press" or _bool(request, "silence_mode"),
        assistive_mode=_bool(request, "assistive_mode") or packet.packet_type in {"sentence", "assistive_candidate"},
        neural_research_mode=_bool(request, "neural_research_mode"),
    )
    devices = DeviceCapabilities(
        has_audio=_bool(request, "has_audio", True),
        has_ar=_bool(request, "has_ar", True),
        has_haptics=_bool(request, "has_haptics", True),
        has_screen=_bool(request, "has_screen", True),
        has_assistive_ui=_bool(request, "has_assistive_ui") or _bool(request, "assistive_mode"),
        has_neural_research_output=_bool(request, "has_neural_research_output")
        or _bool(request, "neural_research_mode"),
    )
    decision = route_packet(packet, router_state, devices)
    return {
        "packet": asdict(packet),
        "route": asdict(decision),
    }


def analyze(request: dict[str, Any]) -> dict[str, Any]:
    transcript = str(request.get("transcript", "")).strip()
    scenario = str(request.get("scenario", "")).strip()
    if not transcript:
        transcript = DEFAULT_TRANSCRIPTS.get(scenario, DEFAULT_TRANSCRIPTS["dickens"])

    delivery = str(request.get("delivery", "screen"))
    state = InteractionState(
        user_is_speaking=_bool(request, "user_is_speaking"),
        pause_ms=_int(request, "pause_ms", 900),
        user_signal=str(request.get("user_signal", "none")),
        delivery=delivery,  # type: ignore[arg-type]
        cognitive_load_estimate=_float(request, "cognitive_load", 0.35),
        max_packets=_int(request, "max_packets", 3),
    )
    min_score = _float(request, "min_score", 0.65)
    packet_result = generate_packets(transcript, state=state, min_score=min_score)
    routed = [
        {
            **item,
            "route": _route_payload(item["packet"], request)["route"],
        }
        for item in packet_result["delivered"]
    ]

    return {
        "transcript": transcript,
        "topic": packet_result["topic"],
        "state": packet_result["state"],
        "summary": packet_result["summary"],
        "delivered": routed,
        "suppressed": packet_result["suppressed"],
    }


class DemoHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, directory=str(STATIC_DIR), **kwargs)

    def log_message(self, format: str, *args: Any) -> None:
        sys.stderr.write("symborg-live-demo: " + format % args + "\n")

    def translate_path(self, path: str) -> str:
        requested = unquote(urlparse(path).path)
        if requested == "/":
            return str(STATIC_DIR / "index.html")

        if requested.startswith("/assets/"):
            root = (ROOT / "assets").resolve()
            candidate = (ROOT / requested.lstrip("/")).resolve()
        else:
            root = STATIC_DIR.resolve()
            candidate = (STATIC_DIR / requested.lstrip("/")).resolve()

        if candidate == root or root in candidate.parents:
            return str(candidate)
        return str(STATIC_DIR / "__not_found__")

    def _send_json(self, payload: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path == "/favicon.ico":
            self.send_response(HTTPStatus.NO_CONTENT)
            self.end_headers()
            return
        super().do_GET()

    def do_POST(self) -> None:
        if self.path != "/api/analyze":
            self._send_json({"error": "not_found"}, HTTPStatus.NOT_FOUND)
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length).decode("utf-8")
            request = json.loads(raw) if raw else {}
            self._send_json(analyze(request))
        except Exception as exc:  # pragma: no cover - HTTP boundary
            self._send_json({"error": "analysis_failed", "detail": str(exc)}, HTTPStatus.BAD_REQUEST)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the SYMBORG integrated live demo.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()

    server = ThreadingHTTPServer((args.host, args.port), DemoHandler)
    print(f"SYMBORG live demo: http://{args.host}:{args.port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
