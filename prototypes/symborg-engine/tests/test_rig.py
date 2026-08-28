"""What is attached to the person right now.

The device is a phone today and will not stay one. Each thing that gets added is either a
way into the system or a way out of it, and the engine should not learn a new concept for
every one — so there is no list of supported hardware, only a list of what is attached and
what each can carry.
"""

from __future__ import annotations

import unittest

from symborg_engine.copilot.rig import (EARPIECE, PHONE, WIRED_EARPHONES, Carries,
                                        Peripheral, Rig)

GLASSES = Peripheral("gözlük", Carries.TEXT | Carries.IMAGE_IN, private=True)
RING = Peripheral("yüzük", Carries.PRESS, private=True)
SPEAKER = Peripheral("hoparlör", Carries.SPEECH_OUT, private=False)


class TestNothingAttached(unittest.TestCase):
    def test_it_says_plainly_what_it_cannot_do(self):
        gaps = Rig().missing()
        self.assertEqual(len(gaps), 4)
        self.assertTrue(all(isinstance(g, str) and g for g in gaps))

    def test_it_cannot_hear_the_room(self):
        self.assertFalse(Rig().can_hear_the_room)

    def test_the_situation_it_produces_is_the_cautious_one(self):
        situation = Rig().situation()
        self.assertFalse(situation.earpiece)
        self.assertFalse(situation.screen_visible)
        self.assertTrue(situation.others_present)


class TestTheHeadIsNotAMicrophone(unittest.TestCase):
    """Earpieces beamform a null at the room on purpose, to isolate the wearer's mouth.
    The people talking nearby are, by that design, noise — so a headset microphone is the
    wrong input for a device whose whole job is hearing them."""

    def test_an_earpiece_does_not_carry_speech_in(self):
        self.assertFalse(EARPIECE.can(Carries.SPEECH_IN))
        self.assertFalse(WIRED_EARPHONES.can(Carries.SPEECH_IN))

    def test_an_earpiece_alone_cannot_hear_the_room(self):
        rig = Rig()
        rig.attach(EARPIECE)
        self.assertFalse(rig.can_hear_the_room)
        self.assertIn("mikrofon", rig.missing()[0])

    def test_the_phone_is_the_room_microphone(self):
        rig = Rig()
        rig.attach(PHONE)
        rig.attach(EARPIECE)
        self.assertEqual(rig.room_mic.name, "phone")

    def test_a_near_field_microphone_does_not_count_as_a_room_one(self):
        rig = Rig()
        rig.attach(Peripheral("yaka mikrofonu", Carries.SPEECH_IN, far_field=False))
        self.assertIsNone(rig.room_mic)


class TestPrivateBeatsPublic(unittest.TestCase):
    """The whole routing discipline is about not telling the room, so for the same job a
    private surface always wins. Without the preference, attaching glasses changed
    nothing — the phone was registered first and kept the eye."""

    def test_glasses_take_the_eye_from_the_phone(self):
        rig = Rig()
        rig.attach(PHONE)
        self.assertEqual(rig.eye.name, "phone")
        rig.attach(GLASSES)
        self.assertEqual(rig.eye.name, "gözlük")

    def test_an_earpiece_takes_the_voice_from_a_speaker(self):
        rig = Rig()
        rig.attach(SPEAKER)
        rig.attach(EARPIECE)
        self.assertEqual(rig.ear.name, "earpiece")

    def test_a_public_speaker_is_not_an_ear(self):
        rig = Rig()
        rig.attach(SPEAKER)
        self.assertIsNone(rig.ear)

    def test_attaching_more_does_not_move_the_room_microphone(self):
        rig = Rig()
        rig.attach(PHONE)
        rig.attach(GLASSES)
        rig.attach(RING)
        self.assertEqual(rig.room_mic.name, "phone")


class TestAddingSomethingNewIsOneLine(unittest.TestCase):
    """The test that matters for everything that has not been invented yet."""

    def test_a_ring_becomes_the_button(self):
        rig = Rig()
        rig.attach(PHONE)
        rig.attach(RING)
        self.assertEqual(rig.button.name, "yüzük")

    def test_something_unheard_of_still_routes(self):
        rig = Rig()
        rig.attach(PHONE)
        rig.attach(Peripheral("boyun bandı", Carries.SPEECH_OUT | Carries.TEXT,
                              private=True))
        self.assertEqual(rig.ear.name, "boyun bandı")
        self.assertEqual(rig.eye.name, "boyun bandı")
        self.assertEqual(rig.missing(), [])

    def test_detaching_gives_the_job_back(self):
        rig = Rig()
        rig.attach(PHONE)
        rig.attach(GLASSES)
        self.assertEqual(rig.eye.name, "gözlük")
        self.assertTrue(rig.detach("gözlük"))
        self.assertEqual(rig.eye.name, "phone")

    def test_detaching_something_absent_says_so(self):
        self.assertFalse(Rig().detach("yok böyle bir şey"))

    def test_attaching_twice_is_one_thing(self):
        rig = Rig()
        rig.attach(PHONE)
        rig.attach(PHONE)
        self.assertEqual(len(rig), 1)


class TestItFeedsTheRouting(unittest.TestCase):
    def test_a_full_rig_gets_the_ear(self):
        rig = Rig()
        rig.attach(PHONE)
        rig.attach(EARPIECE)
        self.assertTrue(rig.situation(alone=False).earpiece)

    def test_a_screen_that_exists_is_not_a_screen_being_looked_at(self):
        rig = Rig()
        rig.attach(PHONE)
        self.assertFalse(rig.situation(screen_visible=False).screen_visible)
        self.assertTrue(rig.situation(screen_visible=True).screen_visible)

    def test_claiming_a_visible_screen_with_none_attached_changes_nothing(self):
        self.assertFalse(Rig().situation(screen_visible=True).screen_visible)

    def test_being_alone_is_something_the_hardware_cannot_know(self):
        rig = Rig()
        rig.attach(PHONE)
        self.assertFalse(rig.situation(alone=True).others_present)
        self.assertTrue(rig.situation(alone=False).others_present)


if __name__ == "__main__":
    unittest.main()
