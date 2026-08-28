"""The phone as microphone, ear and screen.

The routing work settled the hardware: in the situation this exists for, a pocketed
phone has no way through, so the channel is an earpiece and the phone is what carries
it. These cover the plumbing that makes the phone reachable at all.
"""

from __future__ import annotations

import http.client
import json
import threading
import time
import unittest

from symborg_engine.copilot import Copilot, Memory, Recollection, Situation
from symborg_engine.providers.browser_audio import BrowserSource
from symborg_engine.providers.offline import OfflineLanguageModel, OfflineSynthesiser
from symborg_engine.ui.copilot_server import BLOCK_LIMIT, CopilotState, _handler
from symborg_engine.ui.server import Broadcaster, QuietServer


class TestAudioFromSomewhereElse(unittest.TestCase):
    """The source is a queue somebody else fills, so nothing downstream knows whether
    the microphone is in this process or in a phone across the room."""

    def test_what_goes_in_comes_out(self):
        source = BrowserSource()
        source.feed(b"ab")
        source.feed(b"cd")
        source.close()
        self.assertEqual(list(source.blocks()), [b"ab", b"cd"])

    def test_empty_blocks_are_ignored(self):
        source = BrowserSource()
        source.feed(b"")
        source.close()
        self.assertEqual(list(source.blocks()), [])

    def test_falling_behind_loses_the_beginning_not_the_present(self):
        """A conversation is made of its recent past."""
        source = BrowserSource(max_blocks=2)
        for i in range(5):
            source.feed(bytes([i]))
        source.close()
        self.assertEqual(list(source.blocks()), [bytes([3]), bytes([4])])
        self.assertEqual(source.dropped, 3)

    def test_closing_does_not_throw_away_the_last_thing_said(self):
        """An earlier version made room for the stop signal by discarding a block."""
        source = BrowserSource(max_blocks=2)
        source.feed(b"one")
        source.feed(b"two")
        source.close()
        self.assertEqual(list(source.blocks()), [b"one", b"two"])

    def test_feeding_after_close_is_ignored(self):
        source = BrowserSource()
        source.close()
        source.feed(b"late")
        self.assertEqual(list(source.blocks()), [])


class _Served:
    """A running server, for tests that need real requests."""

    def __init__(self, copilot: Copilot, port: int) -> None:
        self.state = CopilotState(copilot=copilot, source=BrowserSource())
        self.bus = Broadcaster()
        self.audio: dict[str, bytes] = {}
        self.server = QuietServer(("127.0.0.1", port), _handler(self.state, self.bus,
                                                               self.audio))
        self.port = port
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        time.sleep(0.05)

    def __enter__(self):
        return self

    def __exit__(self, *exc) -> None:
        self.state.source.close()
        self.server.shutdown()
        self.server.server_close()

    def request(self, method: str, path: str, body=None, headers=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        try:
            conn.request(method, path, body=body, headers=headers or {})
            response = conn.getresponse()
            return response.status, response.read()
        finally:
            conn.close()


def _copilot(**kw) -> Copilot:
    return Copilot(model=OfflineLanguageModel(), synthesiser=OfflineSynthesiser(),
                   memory=kw.pop("memory", Memory()),
                   situation=kw.pop("situation", Situation(earpiece=True)), **kw)


class TestTheServer(unittest.TestCase):
    PORT = 8792

    def test_the_page_is_served(self):
        with _Served(_copilot(), self.PORT) as served:
            status, body = served.request("GET", "/")
            self.assertEqual(status, 200)
            self.assertIn(b"<title>SYMBORG", body)

    def test_audio_reaches_the_source(self):
        with _Served(_copilot(), self.PORT + 1) as served:
            status, body = served.request("POST", "/audio", body=b"\x00\x01" * 100)
            self.assertEqual(status, 200)
            self.assertTrue(json.loads(body)["ok"])
            self.assertEqual(served.state.source.waiting, 1)

    def test_an_oversized_block_does_not_take_the_stream_down(self):
        """The page posts audio continuously. Answering mid-body closes the socket
        while it is still writing, and the page sees a broken connection rather than a
        rejection."""
        with _Served(_copilot(), self.PORT + 2) as served:
            conn = http.client.HTTPConnection("127.0.0.1", self.PORT + 2, timeout=5)
            try:
                conn.request("POST", "/audio", body=b"x" * (BLOCK_LIMIT + 1024))
                refused = conn.getresponse()
                self.assertEqual(refused.status, 413)
                refused.read()          # the connection is only reusable once drained
                conn.request("POST", "/audio", body=b"\x00\x01" * 100)
                accepted = conn.getresponse()
                self.assertEqual(accepted.status, 200)
                accepted.read()
            finally:
                conn.close()

    def test_the_situation_can_be_changed_from_the_page(self):
        copilot = _copilot()
        with _Served(copilot, self.PORT + 3) as served:
            served.request("POST", "/situation",
                           body=json.dumps({"earpiece": False}).encode())
            self.assertFalse(copilot.situation.earpiece)

    def test_an_unchanged_field_survives(self):
        copilot = _copilot(situation=Situation(earpiece=True, screen_visible=True))
        with _Served(copilot, self.PORT + 4) as served:
            served.request("POST", "/situation",
                           body=json.dumps({"earpiece": False}).encode())
            self.assertTrue(copilot.situation.screen_visible)

    def test_a_malformed_situation_is_rejected(self):
        with _Served(_copilot(), self.PORT + 5) as served:
            status, _ = served.request("POST", "/situation", body=b"{not json")
            self.assertEqual(status, 400)

    def test_the_person_can_erase_everything(self):
        memory = Memory()
        memory.keep(Recollection("Toplantı salı.", kind="date"))
        copilot = _copilot(memory=memory)
        with _Served(copilot, self.PORT + 6) as served:
            status, body = served.request("POST", "/forget", body=b"{}")
            self.assertEqual(status, 200)
            self.assertEqual(json.loads(body)["removed"], 1)
            self.assertEqual(copilot.memory.items, [])

    def test_an_unknown_path_is_a_404(self):
        with _Served(_copilot(), self.PORT + 7) as served:
            self.assertEqual(served.request("GET", "/nothing")[0], 404)
            self.assertEqual(served.request("POST", "/nothing", body=b"{}")[0], 404)

    def test_the_snapshot_carries_what_the_page_draws(self):
        with _Served(_copilot(), self.PORT + 8) as served:
            snapshot = served.state.snapshot()
            for key in ("heard", "turns", "spoke", "silence", "remembered",
                        "situation", "log"):
                self.assertIn(key, snapshot)


if __name__ == "__main__":
    unittest.main()
