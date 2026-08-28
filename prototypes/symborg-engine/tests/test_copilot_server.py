"""The phone as microphone, ear and screen.

The routing work settled the hardware: in the situation this exists for, a pocketed
phone has no way through, so the channel is an earpiece and the phone is what carries
it. These cover the plumbing that makes the phone reachable at all.
"""

from __future__ import annotations

import base64
import http.client
import json
import shutil
import tempfile
import threading
import time
import unittest
from pathlib import Path

from symborg_engine.copilot import Copilot, Memory, Recollection, Situation
from symborg_engine.copilot.rig import EARPIECE, PHONE, Rig
from symborg_engine.providers.browser_audio import BrowserSource
from symborg_engine.providers.offline import OfflineLanguageModel, OfflineSynthesiser
from symborg_engine.ui.copilot_server import (ADDRESS_WINDOW_S, BLOCK_LIMIT,
                                              PHOTO_LIMIT, STATIC, CopilotState,
                                              _certificate, _handler)
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
        rig = Rig()
        rig.attach(PHONE)        # what serve() attaches; a test on an empty rig is a
        rig.attach(EARPIECE)     # test of a device with no hardware in it
        self.state = CopilotState(copilot=copilot, source=BrowserSource(), rig=rig)
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


class _Answers:
    """A model with one canned reply, whatever it is asked."""

    def __init__(self, reply: str) -> None:
        self.reply = reply

    def complete(self, prompt) -> str:
        return self.reply


class _LooksAt:
    """A model that records the picture it was shown."""

    def __init__(self, reply: str) -> None:
        self.reply = reply
        self.seen: bytes | None = None

    def complete(self, prompt) -> str:
        self.seen = prompt.image
        return self.reply


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
            self.assertFalse(copilot.situation.earpiece)

    def test_unplugging_the_earpiece_moves_where_things_go(self):
        """The rig is not a label. Detaching a private channel changes where the next
        sentence lands."""
        copilot = _copilot()
        with _Served(copilot, self.PORT + 9) as served:
            served.request("POST", "/situation",
                           body=json.dumps({"earpiece": True}).encode())
            self.assertTrue(copilot.situation.earpiece)
            served.request("POST", "/situation",
                           body=json.dumps({"earpiece": False}).encode())
            self.assertFalse(copilot.situation.earpiece)
            self.assertIsNone(served.state.rig.ear)

    def test_a_screen_it_does_not_have_cannot_be_visible(self):
        copilot = _copilot()
        with _Served(copilot, self.PORT + 10) as served:
            served.state.rig.detach(PHONE.name)
            served.request("POST", "/situation",
                           body=json.dumps({"screen_visible": True}).encode())
            self.assertFalse(copilot.situation.screen_visible)

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


class TestTheCamera(unittest.TestCase):
    """The photograph route. The safety rule lives in copilot.look; these cover the
    plumbing that carries a picture to it."""

    PORT = 8782

    def test_a_photograph_produces_a_sighting(self):
        model = _LooksAt(json.dumps({
            "seen": "kahverengi mantar", "could_be": ["agarik"], "missing": "lamel",
            "confidence": 0.4, "irreversible": True,
            "whisper": "Fotoğraftan emin olunmaz."}, ensure_ascii=False))
        copilot = Copilot(model=model, synthesiser=OfflineSynthesiser(),
                          memory=Memory(), situation=Situation(earpiece=True))
        with _Served(copilot, self.PORT) as served:
            status, body = served.request(
                "POST", "/look",
                body=json.dumps({"image": base64.b64encode(b"jpegbytes").decode(),
                                 "question": "Bunu yiyebilir miyim?"}).encode())
            self.assertEqual(status, 200)
            self.assertTrue(json.loads(body)["irreversible"])
            self.assertEqual(model.seen, b"jpegbytes")

    def test_a_sighting_reaches_the_page(self):
        model = _LooksAt(json.dumps({
            "seen": "bir şey", "could_be": [], "missing": "", "confidence": 0.3,
            "irreversible": False, "whisper": "Bir şey."}, ensure_ascii=False))
        copilot = Copilot(model=model, synthesiser=OfflineSynthesiser(), memory=Memory())
        with _Served(copilot, self.PORT + 1) as served:
            served.request("POST", "/look",
                           body=json.dumps({"image": base64.b64encode(b"x").decode()}).encode())
            self.assertIn("sighting", served.state.log[-1])

    def test_bad_base64_is_rejected(self):
        with _Served(_copilot(), self.PORT + 2) as served:
            status, _ = served.request("POST", "/look",
                                       body=json.dumps({"image": "!!!"}).encode())
            self.assertEqual(status, 400)

    def test_a_missing_image_is_rejected(self):
        with _Served(_copilot(), self.PORT + 3) as served:
            status, body = served.request("POST", "/look", body=b"{}")
            self.assertEqual(status, 400)
            self.assertEqual(json.loads(body)["error"], "no_image")

    def test_a_photograph_may_be_larger_than_an_audio_block(self):
        """A block of audio and a photograph are different sizes, and one limit for
        both would reject either the picture or nothing at all."""
        self.assertGreater(PHOTO_LIMIT, BLOCK_LIMIT)


class TestBeingAddressedThroughThePage(unittest.TestCase):
    """Press-to-talk. The audio keeps flowing through the same stream; the button only
    marks which turn was meant for it, which is how an earpiece button would behave."""

    PORT = 8772

    def test_pressing_marks_the_next_turn(self):
        with _Served(_copilot(), self.PORT) as served:
            self.assertFalse(served.state.addressing)
            served.request("POST", "/address", body=b"{}")
            self.assertTrue(served.state.addressing)

    def test_an_addressed_turn_always_says_something(self):
        model = _Answers(json.dumps({"want": "unclear", "query": "",
                                     "say_if_unclear": "Anlayamadım."}, ensure_ascii=False))
        copilot = Copilot(model=model, synthesiser=OfflineSynthesiser(), memory=Memory(),
                          situation=Situation(earpiece=True), clock=lambda: 0.0)
        with _Served(copilot, self.PORT + 1) as served:
            status, body = served.request("POST", "/asked",
                                          body=json.dumps({"said": "bir şey"}).encode())
            self.assertEqual(status, 200)
            entry = json.loads(body)
            self.assertTrue(entry["said"])
            self.assertTrue(entry["addressed"])

    def test_saying_nothing_is_rejected(self):
        with _Served(_copilot(), self.PORT + 2) as served:
            status, body = served.request("POST", "/asked",
                                          body=json.dumps({"said": "   "}).encode())
            self.assertEqual(status, 400)
            self.assertEqual(json.loads(body)["error"], "nothing_said")

    def test_a_broken_image_is_rejected_rather_than_ignored(self):
        with _Served(_copilot(), self.PORT + 3) as served:
            status, body = served.request(
                "POST", "/asked",
                body=json.dumps({"said": "bak şuna", "image": "!!!"}).encode())
            self.assertEqual(status, 400)
            self.assertEqual(json.loads(body)["error"], "bad_image")

    def test_both_paths_draw_the_same_shape(self):
        """The overheard and addressed paths share one entry builder so the page cannot
        end up drawing two different things."""
        model = _Answers(json.dumps({"want": "unclear", "query": "",
                                     "say_if_unclear": "Ne?"}, ensure_ascii=False))
        copilot = Copilot(model=model, synthesiser=OfflineSynthesiser(), memory=Memory(),
                          situation=Situation(earpiece=True), clock=lambda: 0.0)
        with _Served(copilot, self.PORT + 4) as served:
            served.request("POST", "/asked",
                           body=json.dumps({"said": "bir şey"}).encode())
            entry = served.state.log[-1]
            for key in ("at", "transcript", "said", "channel", "held", "remembered",
                        "latency_ms", "audio", "addressed", "want", "sighting"):
                self.assertIn(key, entry)


class TestItMakesItsOwnCertificate(unittest.TestCase):
    """A browser only hands over a microphone on localhost or HTTPS, so reaching this
    from a phone needs a certificate. Asking someone to compose an openssl invocation
    before they can try their own prototype is a good way for it never to be tried."""

    @unittest.skipUnless(shutil.which("openssl"), "openssl is not installed")
    def test_one_is_generated_on_first_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            made = _certificate(Path(tmp), "192.168.1.50")
            self.assertIsNotNone(made)
            cert, key = made
            self.assertTrue(Path(cert).exists())
            self.assertIn(b"BEGIN CERTIFICATE", Path(cert).read_bytes())

    @unittest.skipUnless(shutil.which("openssl"), "openssl is not installed")
    def test_it_is_reused_rather_than_remade(self):
        with tempfile.TemporaryDirectory() as tmp:
            first = _certificate(Path(tmp), "192.168.1.50")
            before = Path(first[0]).read_bytes()
            _certificate(Path(tmp), "192.168.1.50")
            self.assertEqual(Path(first[0]).read_bytes(), before)

    @unittest.skipUnless(shutil.which("openssl"), "openssl is not installed")
    def test_a_new_address_gets_a_new_certificate(self):
        """A certificate for last week's wifi proves nothing about this one."""
        with tempfile.TemporaryDirectory() as tmp:
            first = _certificate(Path(tmp), "192.168.1.50")
            before = Path(first[0]).read_bytes()
            _certificate(Path(tmp), "10.0.0.7")
            self.assertNotEqual(Path(first[0]).read_bytes(), before)

    @unittest.skipUnless(shutil.which("openssl"), "openssl is not installed")
    def test_the_private_key_is_not_world_readable(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, key = _certificate(Path(tmp), "192.168.1.50")
            self.assertEqual(Path(key).stat().st_mode & 0o077, 0)


class TestThePageCarriesItsOwnParts(unittest.TestCase):
    """A worklet module cannot be inlined, and the gate is shared with the engine, so
    the page is no longer one file. A missing part fails silently in a browser."""

    PORT = 8762

    def test_every_part_is_served(self):
        with _Served(_copilot(), self.PORT) as served:
            for path, ctype in (("/vad.js", "javascript"), ("/capture.js", "javascript"),
                                ("/manifest.json", "manifest"), ("/icon.svg", "svg")):
                with self.subTest(path=path):
                    status, body = served.request("GET", path)
                    self.assertEqual(status, 200)
                    self.assertTrue(body)

    def test_the_page_asks_for_what_is_served(self):
        page = (STATIC / "copilot.html").read_text(encoding="utf-8")
        for path in ("/vad.js", "/capture.js", "/manifest.json"):
            self.assertIn(path, page)


class TestThePressToTalkWindowCloses(unittest.TestCase):
    """An accidental press that is never followed by speech would otherwise stay armed
    indefinitely, and the next thing anyone in the room said would be treated as
    addressed to the device."""

    PORT = 8752

    def test_pressing_arms_it(self):
        with _Served(_copilot(), self.PORT) as served:
            served.request("POST", "/address", body=b"{}")
            self.assertTrue(served.state.addressing)

    def test_it_disarms_on_its_own(self):
        with _Served(_copilot(), self.PORT + 1) as served:
            served.request("POST", "/address", body=b"{}")
            served.state.addressing_until = time.monotonic() - 0.01
            self.assertFalse(served.state.addressing)

    def test_it_starts_disarmed(self):
        with _Served(_copilot(), self.PORT + 2) as served:
            self.assertFalse(served.state.addressing)

    def test_the_window_is_long_enough_to_gather_a_thought(self):
        """People do not start talking the instant they press a button."""
        self.assertGreaterEqual(ADDRESS_WINDOW_S, 5.0)
        self.assertLessEqual(ADDRESS_WINDOW_S, 30.0)
