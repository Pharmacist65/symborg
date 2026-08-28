"""The local interface.

The authorship invariant has to survive being exposed over HTTP. A network boundary is
exactly where an invariant quietly stops holding, so it is checked here again from the
outside rather than assumed from the inside.
"""

from __future__ import annotations

import json
import threading
import unittest
import urllib.error
import urllib.request

from symborg_engine import Session
from symborg_engine.providers.base import Prompt, Utterance, VoiceRef
from symborg_engine.ui.server import Broadcaster, UIState, serve


class _Model:
    def complete(self, prompt: Prompt) -> str:
        return ('[{"text": "Evet, ağrım var.", "kind": "reply", "confidence": 0.9},'
                ' {"text": "Hayır, iyiyim.", "kind": "reply", "confidence": 0.8},'
                ' {"text": "Kastettiğim bu değil.", "kind": "repair", "confidence": 0.5}]')


class _Synth:
    def synthesise(self, text: str, voice: VoiceRef) -> Utterance:
        return Utterance(text=text, audio=b"RIFF____WAVEfake", voice_id="test")


class UITest(unittest.TestCase):
    port = 8799

    def setUp(self) -> None:
        self.session = Session(model=_Model(), synthesiser=_Synth())
        self.state = UIState(session=self.session)
        self.bus = Broadcaster()
        UITest.port += 1
        self.base = f"http://127.0.0.1:{UITest.port}"
        self.server = serve(self.state, self.bus, port=UITest.port)

    def tearDown(self) -> None:
        self.server.shutdown()

    def _post(self, index: int):
        request = urllib.request.Request(
            self.base + "/select", data=json.dumps({"index": index}).encode(),
            headers={"Content-Type": "application/json"}, method="POST",
        )
        return urllib.request.urlopen(request, timeout=8)

    def _offer(self):
        self.session.hear("Ağrın var mı?")
        result = self.session.offer()
        self.state.candidates = [{"text": c.text, "kind": c.kind} for c in result.candidates]
        return result

    # -- serving -----------------------------------------------------------

    def test_page_is_served(self) -> None:
        with urllib.request.urlopen(self.base + "/", timeout=8) as response:
            body = response.read()
        self.assertEqual(response.status, 200)
        self.assertIn(b"SYMBORG", body)

    def test_unknown_path_is_not_found(self) -> None:
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(self.base + "/nope", timeout=8)
        self.assertEqual(ctx.exception.code, 404)

    # -- authorship, from outside -------------------------------------------

    def test_selecting_with_no_offer_is_refused(self) -> None:
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self._post(0)
        self.assertEqual(ctx.exception.code, 409)
        self.assertEqual(json.loads(ctx.exception.read())["error"], "no_active_offer")

    def test_selecting_an_index_never_offered_is_refused(self) -> None:
        self._offer()
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self._post(99)
        self.assertEqual(ctx.exception.code, 409)
        self.assertEqual(json.loads(ctx.exception.read())["error"], "index_not_offered")

    def test_a_selection_cannot_be_replayed(self) -> None:
        """One offer authorises one sentence, over HTTP as much as in process."""
        self._offer()
        self._post(0)
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self._post(0)
        self.assertEqual(ctx.exception.code, 409)

    def test_a_valid_selection_speaks_exactly_what_was_chosen(self) -> None:
        result = self._offer()
        with self._post(1) as response:
            payload = json.loads(response.read())
        self.assertEqual(payload["text"], result.candidates[1].text)
        self.assertEqual(self.session.spoken[0]["origin"], "user_confirmed")

    def test_audio_is_served_for_the_selection(self) -> None:
        self._offer()
        with self._post(0) as response:
            payload = json.loads(response.read())
        with urllib.request.urlopen(self.base + payload["audio"], timeout=8) as audio:
            body = audio.read()
        self.assertTrue(body.startswith(b"RIFF"))

    def test_malformed_body_is_rejected(self) -> None:
        request = urllib.request.Request(
            self.base + "/select", data=b"not json",
            headers={"Content-Type": "application/json"}, method="POST",
        )
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(request, timeout=8)
        self.assertEqual(ctx.exception.code, 400)

    # -- live updates -------------------------------------------------------

    def test_state_reaches_a_subscriber(self) -> None:
        received: list[dict] = []

        def listen() -> None:
            with urllib.request.urlopen(self.base + "/events", timeout=10) as stream:
                for line in stream:
                    if line.startswith(b"data:"):
                        received.append(json.loads(line[5:].decode()))
                        if len(received) >= 2:
                            return

        thread = threading.Thread(target=listen, daemon=True)
        thread.start()
        threading.Event().wait(0.4)
        self._offer()
        self.bus.publish(self.state.snapshot())
        thread.join(timeout=6)

        self.assertGreaterEqual(len(received), 2)
        self.assertEqual(len(received[-1]["candidates"]), 3)

    def test_a_stalled_subscriber_does_not_block_publishing(self) -> None:
        """A page that stops reading must not stall the conversation."""
        for _ in range(200):
            self.bus.subscribe()
        self.bus.publish({"partial": "x"})     # must return promptly


if __name__ == "__main__":
    unittest.main()


class DisconnectTest(unittest.TestCase):
    """A browser hanging up is normal, not an error.

    Refreshes, favicon requests and event-stream reconnects close sockets constantly.
    Reporting each one buries the conversation in tracebacks and makes a working system
    look broken — which is exactly how it was first seen in use.
    """

    def setUp(self) -> None:
        UITest.port += 1
        self.port = UITest.port
        self.base = f"http://127.0.0.1:{self.port}"
        self.state = UIState(session=Session(model=_Model(), synthesiser=_Synth()))
        self.bus = Broadcaster()
        self.server = serve(self.state, self.bus, port=self.port)

    def tearDown(self) -> None:
        self.server.shutdown()

    def test_reset_and_broken_pipe_are_swallowed(self) -> None:
        import io
        import sys

        captured = io.StringIO()
        original, sys.stderr = sys.stderr, captured
        try:
            for exc in (ConnectionResetError(), BrokenPipeError(), ConnectionAbortedError()):
                try:
                    raise exc
                except Exception:
                    self.server.handle_error(None, ("127.0.0.1", 1))
        finally:
            sys.stderr = original
        self.assertEqual(captured.getvalue(), "")

    def test_a_real_error_is_still_reported(self) -> None:
        import io
        import sys

        captured = io.StringIO()
        original, sys.stderr = sys.stderr, captured
        try:
            try:
                raise ValueError("something genuinely wrong")
            except Exception:
                self.server.handle_error(None, ("127.0.0.1", 1))
        finally:
            sys.stderr = original
        self.assertIn("something genuinely wrong", captured.getvalue())

    def test_favicon_does_not_404(self) -> None:
        """Browsers always ask; a 404 for it is noise, not information."""
        with urllib.request.urlopen(self.base + "/favicon.ico", timeout=8) as response:
            self.assertEqual(response.status, 204)

    def test_an_abandoned_event_stream_unsubscribes(self) -> None:
        stream = urllib.request.urlopen(self.base + "/events", timeout=8)
        stream.read(1)
        stream.close()
        threading.Event().wait(0.3)
        self.bus.publish({"partial": "still alive"})   # must not raise
