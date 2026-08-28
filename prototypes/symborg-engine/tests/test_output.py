"""Where a sentence goes.

The rules that matter are the two that stop it: never talk over the person, and never
tell the room something they did not ask you to say.
"""

from __future__ import annotations

import unittest

from symborg_engine.copilot.output import (MAX_WHISPER_WORDS, Channel, Held, Situation,
                                           route)

EARPIECE = Situation(earpiece=True)
ALONE_WITH_PHONE = Situation(others_present=False, screen_visible=True)
MEETING = Situation(others_present=True, screen_visible=True)
MEETING_POCKET = Situation(others_present=True, screen_visible=False)


class TestNothingIsSaidByDefault(unittest.TestCase):
    def test_an_empty_sentence_goes_nowhere(self):
        held = route("   ", EARPIECE)
        self.assertIs(held.channel, Channel.NONE)
        self.assertIs(held.held, Held.NOTHING_TO_SAY)

    def test_a_paragraph_is_not_a_whisper(self):
        long = " ".join(["kelime"] * (MAX_WHISPER_WORDS + 1))
        self.assertIs(route(long, EARPIECE).held, Held.TOO_LONG)

    def test_with_no_channel_at_all_nothing_is_said(self):
        held = route("Salı demiştik.", Situation(others_present=False))
        self.assertIn(held.channel, (Channel.ROOM, Channel.NONE))


class TestItNeverTalksOverThePerson(unittest.TestCase):
    """The one thing it must never do. A device that interrupts you is worse than no
    device, because you cannot stop attending to it."""

    def test_it_waits_for_the_screen_rather_than_interrupting(self):
        self.assertIs(route("Kerem Yıldız.", Situation(earpiece=True, user_speaking=True,
                                                       screen_visible=True)).channel,
                      Channel.SCREEN)

    def test_with_no_screen_it_simply_holds(self):
        held = route("Kerem Yıldız.", Situation(earpiece=True, user_speaking=True))
        self.assertIs(held.channel, Channel.NONE)
        self.assertIs(held.held, Held.WOULD_INTERRUPT)

    def test_a_perishable_thing_is_dropped_not_queued(self):
        """By the time they stop talking the moment it belonged to has closed, and a
        late correction reopens something the room had already settled."""
        held = route("Salı demiştik.", Situation(earpiece=True, user_speaking=True,
                                                 screen_visible=True), perishable=True)
        self.assertIs(held.channel, Channel.NONE)
        self.assertIs(held.held, Held.WOULD_INTERRUPT)


class TestItNeverTellsTheRoom(unittest.TestCase):
    """Speaking aloud in a meeting tells everyone present something the person might
    have chosen to keep to themselves, and they never asked for that."""

    def test_with_others_present_and_no_private_channel_it_stays_quiet(self):
        held = route("Bütçe 150 bin demiştik.", MEETING_POCKET, perishable=True)
        self.assertIs(held.channel, Channel.NONE)
        self.assertIs(held.held, Held.WOULD_TELL_THE_ROOM)

    def test_with_others_present_it_prefers_the_screen(self):
        self.assertIs(route("Bütçe 150 bin demiştik.", MEETING).channel, Channel.SCREEN)

    def test_alone_the_loudspeaker_tells_nobody(self):
        self.assertIs(route("Salı demiştik.",
                            Situation(others_present=False)).channel, Channel.ROOM)

    def test_the_default_situation_assumes_company(self):
        """A copilot that assumes privacy will eventually announce something in a room
        full of people."""
        self.assertTrue(Situation().others_present)
        self.assertFalse(Situation().earpiece)


class TestTheEarComesFirst(unittest.TestCase):
    def test_a_private_channel_wins_when_one_exists(self):
        self.assertIs(route("Kerem Yıldız.", Situation(earpiece=True, screen_visible=True,
                                                       others_present=True)).channel,
                      Channel.EAR)

    def test_noise_does_not_reach_for_the_loudspeaker(self):
        held = route("Kerem Yıldız.", Situation(others_present=False, noisy=True,
                                                screen_visible=True))
        self.assertIs(held.channel, Channel.SCREEN)


class TestTranslationIsMeantToBeHeard(unittest.TestCase):
    """The outbound half is said on the person's behalf, to someone else. Holding up a
    phone is a different act from speaking."""

    def test_it_goes_to_the_room(self):
        self.assertIs(route("How much is this?", MEETING, for_the_room=True).channel,
                      Channel.ROOM)

    def test_a_long_sentence_is_still_spoken(self):
        long = "I would like to ask whether you could possibly offer any discount at all"
        self.assertIs(route(long, MEETING, for_the_room=True).channel, Channel.ROOM)

    def test_it_goes_to_the_room_even_with_an_earpiece(self):
        self.assertIs(route("Thanks.", EARPIECE, for_the_room=True).channel, Channel.ROOM)


if __name__ == "__main__":
    unittest.main()
