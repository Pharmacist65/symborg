"""What is attached to the person right now.

The device is a phone today. It will not stay a phone. An earpiece, a speaker, glasses, a
watch, a ring, a button on a collar, something that does not exist yet — each of them is
either a way into the system or a way out of it, and the engine should not have to learn
a new concept for every one.

So there is no list of supported hardware. There is a list of what is attached, each item
saying only what it can carry and whether anyone but the person can perceive it. The
routing already asks exactly those two questions — is there a private channel, can the
screen be glanced at, would this tell the room — and now it asks them of the rig instead
of of three hand-set booleans.

Adding glasses later is one registration:

    rig.attach(Peripheral("glasses", Carries.TEXT, private=True))

and a sentence that would have gone to a phone screen goes to them, because they are a
private visual surface and the phone is not.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Flag, auto

from .output import Situation

__all__ = ["Carries", "Peripheral", "Rig", "PHONE", "EARPIECE", "WIRED_EARPHONES"]


class Carries(Flag):
    """What a peripheral can move, in either direction.

    A flag rather than a single kind, because most real hardware does more than one thing
    — earphones with a microphone carry speech both ways, and a phone carries everything.
    """

    NOTHING = 0
    SPEECH_IN = auto()
    """A microphone. Whether it hears the room or only the wearer is the `far_field`
    question, and it is the difference between a copilot and a dictaphone."""

    SPEECH_OUT = auto()
    TEXT = auto()
    """Something that can be read. A screen, a lens, a watch face."""

    IMAGE_IN = auto()
    PRESS = auto()
    """A button, a tap, a gesture. How the person says *this next bit is for you*."""

    EVERYTHING = SPEECH_IN | SPEECH_OUT | TEXT | IMAGE_IN | PRESS


@dataclass(slots=True, frozen=True)
class Peripheral:
    """One piece of hardware, described by what it does rather than what it is."""

    name: str
    carries: Carries = Carries.NOTHING

    private: bool = False
    """Whether only the person perceives its output.

    An earpiece is private; a phone speaker is not; a phone screen is nearly private and
    treated as not, because it is read by holding it up. Getting this wrong is how a
    device announces someone's budget to a meeting.
    """

    far_field: bool = False
    """Whether its microphone hears the room rather than only its wearer.

    Almost always false for anything worn on the head: earpieces beamform a null at the
    room on purpose, to isolate the wearer's mouth. The people talking nearby are, by that
    design, noise — so a headset microphone is the wrong input for a device whose whole
    job is hearing them, however good the link is.
    """

    def can(self, what: Carries) -> bool:
        return bool(self.carries & what)


# The three that exist today. Named so the reasoning is visible at the point of use.
PHONE = Peripheral(
    "phone",
    carries=Carries.EVERYTHING,
    private=False,          # a phone speaker tells the room
    far_field=True,         # its microphone is the one that hears other people
)
"""Playing to a Bluetooth earpiece while the phone's own microphone keeps listening is
not a trick — it is what Android does by default, because A2DP has no capture path at
all. One call destroys it: `setCommunicationDevice` or `MODE_IN_COMMUNICATION` switches
to HFP/SCO, suspends A2DP, drops output to mono 8-16 kHz and moves the microphone to the
headset. Stay in MODE_NORMAL and the design this engine assumes is the default one."""

EARPIECE = Peripheral(
    "earpiece",
    carries=Carries.SPEECH_OUT | Carries.PRESS,
    private=True,
    far_field=False,
)
"""Deliberately not SPEECH_IN. See `far_field` — a headset microphone is engineered to
delete exactly the signal this product exists to hear."""

WIRED_EARPHONES = Peripheral(
    "wired earphones",
    carries=Carries.SPEECH_OUT | Carries.PRESS,
    private=True,
    far_field=False,
)


@dataclass(slots=True)
class Rig:
    """Everything attached, and what that adds up to.

        rig = Rig()
        rig.attach(PHONE)
        rig.attach(EARPIECE)
        copilot.situation = rig.situation(alone=False)
    """

    attached: dict[str, Peripheral] = field(default_factory=dict)

    def attach(self, peripheral: Peripheral) -> None:
        self.attached[peripheral.name] = peripheral

    def detach(self, name: str) -> bool:
        return self.attached.pop(name, None) is not None

    def __contains__(self, name: str) -> bool:
        return name in self.attached

    def __iter__(self):
        return iter(self.attached.values())

    def __len__(self) -> int:
        return len(self.attached)

    # -- what the rig can do ---------------------------------------------------

    def any(self, what: Carries, private: bool | None = None) -> Peripheral | None:
        """Something attached that can do this, preferring the private one.

        The preference is the point rather than a nicety: the whole routing discipline is
        about not telling the room, so a private surface always beats a public one for the
        same job. Without it, attaching glasses changed nothing — the phone was registered
        first and kept the eye.
        """
        matches = [p for p in self.attached.values() if p.can(what)]
        if private is not None:
            matches = [p for p in matches if p.private is private]
        if not matches:
            return None
        matches.sort(key=lambda p: not p.private)
        return matches[0]

    @property
    def ear(self) -> Peripheral | None:
        """Somewhere private to speak. Without one, most of what it knows has nowhere to
        go while anyone else is present."""
        return self.any(Carries.SPEECH_OUT, private=True)

    @property
    def room_mic(self) -> Peripheral | None:
        """A microphone that hears other people, rather than only its wearer."""
        for peripheral in self.attached.values():
            if peripheral.can(Carries.SPEECH_IN) and peripheral.far_field:
                return peripheral
        return None

    @property
    def eye(self) -> Peripheral | None:
        """Something that can show text."""
        return self.any(Carries.TEXT)

    @property
    def button(self) -> Peripheral | None:
        return self.any(Carries.PRESS)

    @property
    def camera(self) -> Peripheral | None:
        return self.any(Carries.IMAGE_IN)

    # -- what it adds up to ----------------------------------------------------

    def situation(self, alone: bool = False, screen_visible: bool = False,
                  noisy: bool = False, user_speaking: bool = False) -> Situation:
        """Turn what is attached into what the routing needs.

        Only the parts the hardware cannot know stay arguments: whether anyone else is
        present, whether the screen is actually being looked at rather than merely
        existing, whether the room is loud. Everything else is a fact about the rig.
        """
        return Situation(
            earpiece=self.ear is not None,
            screen_visible=screen_visible and self.eye is not None,
            others_present=not alone,
            noisy=noisy,
            user_speaking=user_speaking,
        )

    @property
    def can_hear_the_room(self) -> bool:
        """Whether this rig can do the thing the product exists for at all."""
        return self.room_mic is not None

    def missing(self) -> list[str]:
        """What is not attached that the product needs. Plain sentences, because this is
        what a person is told when it cannot do its job."""
        gaps = []
        if self.room_mic is None:
            gaps.append("Odayı duyan bir mikrofon yok — kulaklık mikrofonu odayı silir, "
                        "telefonun kendi mikrofonu gerekir.")
        if self.ear is None:
            gaps.append("Kulağa özel bir çıkış yok — yanında biri varken söyleyeceğini "
                        "söyleyemez.")
        if self.camera is None:
            gaps.append("Kamera yok — bir şey gösteremezsin.")
        if self.button is None:
            gaps.append("Düğme yok — ona hitap etmenin bir yolu yok.")
        return gaps

    def to_dict(self) -> dict:
        return {
            "attached": [p.name for p in self.attached.values()],
            "ear": self.ear.name if self.ear else None,
            "room_mic": self.room_mic.name if self.room_mic else None,
            "eye": self.eye.name if self.eye else None,
            "button": self.button.name if self.button else None,
            "camera": self.camera.name if self.camera else None,
            "missing": self.missing(),
        }
