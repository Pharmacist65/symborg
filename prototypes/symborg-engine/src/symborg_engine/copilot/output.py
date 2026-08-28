"""Where a sentence goes: the ear, the screen, the room, or nowhere.

Two facts drive every rule here.

The first is that audio interrupts and a screen waits. A correction is worthless three
sentences after the wrong date was agreed, so it has to arrive while it still changes
something; a recalled name keeps until the person looks down. Which of those a sentence
is decides more than any preference setting.

The second is that a loudspeaker tells the room. "Bütçe 150 bin demiştik" spoken aloud
in a meeting has just told everyone present something the person might have chosen to
keep to themselves — and they never asked it to. So the room is a channel this reaches
for only when it is the point (an outbound translation) or when there is nobody else to
hear. Everything else needs a private channel or waits for the eye.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

__all__ = ["Channel", "Situation", "Delivery", "route", "MAX_WHISPER_WORDS"]

MAX_WHISPER_WORDS = 12
"""One sentence, short enough to land between two of someone else's. Longer than this
and it stops being a whisper and becomes a thing being read to you."""


class Channel(str, Enum):
    EAR = "ear"
    """Private audio. Interrupts, and only this person hears it."""

    ROOM = "room"
    """A loudspeaker. Everyone present hears it, so this is for when that is the point."""

    SCREEN = "screen"
    """Waits to be looked at. Costs nothing if it is never read."""

    NONE = "none"
    """Nowhere. The ordinary case."""


class Held(str, Enum):
    """Why something did not reach the person."""

    NOTHING_TO_SAY = "nothing_to_say"
    TOO_LONG = "too_long"
    WOULD_INTERRUPT = "would_interrupt"
    WOULD_TELL_THE_ROOM = "would_tell_the_room"
    NO_WAY_THROUGH = "no_way_through"
    EXPIRED = "expired"


@dataclass(slots=True, frozen=True)
class Situation:
    """What is true around the person right now.

    Every field defaults to the cautious reading, so a caller that knows nothing gets
    the quiet behaviour rather than the loud one.
    """

    earpiece: bool = False
    """A private audio channel exists. Without one, nothing can be said privately."""

    screen_visible: bool = False
    """The screen can actually be glanced at. A phone in a pocket cannot."""

    user_speaking: bool = False
    others_present: bool = True
    """Assumed true: a copilot that assumes privacy will eventually announce something
    in a room full of people."""

    noisy: bool = False
    """Speech will not be made out. The eye still works."""


@dataclass(slots=True, frozen=True)
class Delivery:
    """Where a sentence ended up, and why."""

    channel: Channel
    text: str = ""
    held: Held | None = None

    @property
    def delivered(self) -> bool:
        return self.channel is not Channel.NONE

    def to_dict(self) -> dict:
        return {"channel": self.channel.value, "text": self.text,
                "held": self.held.value if self.held else None}


def route(text: str, situation: Situation, *, perishable: bool = False,
          for_the_room: bool = False) -> Delivery:
    """Decide where a sentence goes.

    Args:
        text: What would be said. Empty means nothing happens.
        situation: What is true around the person.
        perishable: Whether this stops being useful once the moment passes. A
            correction is; a recalled name is not. Perishable things take the
            interrupting channel or are dropped, because a late correction is worse
            than none — it reopens something the room had already settled.
        for_the_room: Whether being overheard is the intent, as with the outbound half
            of a translation. Only this makes the loudspeaker a first choice.

    Returns:
        The channel and the reason, so a caller can show why nothing was said.
    """
    said = " ".join(text.split())
    if not said:
        return Delivery(Channel.NONE, held=Held.NOTHING_TO_SAY)
    if len(said.split()) > MAX_WHISPER_WORDS and not for_the_room:
        # Nobody can hold a paragraph whispered at them mid-conversation, and the
        # judgement that produced it was not clear enough to be worth the interruption.
        return Delivery(Channel.NONE, said, held=Held.TOO_LONG)

    if for_the_room:
        # Said on the person's behalf, to someone else. The screen is not a substitute:
        # holding up a phone is a different act from speaking.
        return Delivery(Channel.ROOM, said)

    if situation.user_speaking:
        # Talking over the person is the one thing this must never do. A perishable
        # thing is dropped rather than queued; by the time they stop, the moment it
        # belonged to has closed.
        if perishable:
            return Delivery(Channel.NONE, said, held=Held.WOULD_INTERRUPT)
        if situation.screen_visible:
            return Delivery(Channel.SCREEN, said)
        return Delivery(Channel.NONE, said, held=Held.WOULD_INTERRUPT)

    if situation.earpiece:
        return Delivery(Channel.EAR, said)

    if not situation.others_present and not situation.noisy:
        # Alone, so the loudspeaker tells nobody anything.
        return Delivery(Channel.ROOM, said)

    if situation.screen_visible and not perishable:
        return Delivery(Channel.SCREEN, said)

    if situation.screen_visible and perishable:
        # A correction on a screen is still worth something if it is seen in time, and
        # the alternative is announcing it to everyone present.
        return Delivery(Channel.SCREEN, said)

    if situation.others_present:
        return Delivery(Channel.NONE, said, held=Held.WOULD_TELL_THE_ROOM)
    return Delivery(Channel.NONE, said, held=Held.NO_WAY_THROUGH)
