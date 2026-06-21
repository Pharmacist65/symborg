# Input Channel Strategy

SYMBORG can receive data through multiple channels. The key design challenge is not collecting everything; it is collecting the minimum needed context with consent and clear boundaries.

## Input channels

```text
I0 - Manual input
I1 - Audio input
I2 - Visual input through glasses/camera
I3 - Screen and digital context
I4 - Personal memory vault
I5 - Behavioral input
I6 - Physiological input
I7 - Non-invasive neural input
I8 - Invasive BCI input
```

## I0: Manual input

The user asks or taps.

Examples:

```text
ring tap
phone prompt
keyboard input
voice command
```

Best for early prototypes because it is explicit and safe.

## I1: Audio input

The system hears conversation, transcribes it, and detects entities.

Examples:

```text
Dickens
Great Expectations
Pip
class anxiety
```

This is the main v0 signal.

## I2: Visual input through glasses/camera

The glasses see what the user sees.

Examples:

- book cover
- street sign
- person's name badge
- slide deck
- object in room
- medicine label
- menu item

Pipeline:

```text
camera frame
    -> object/text/person/context detection
    -> privacy filter
    -> context packet
    -> retrieval
    -> cognitive packet
```

Important rule:

```text
The camera should not become an always-on surveillance system.
```

Use visible indicators, local processing, and capture boundaries.

## I3: Screen and digital context

Sources:

- meeting transcript
- browser tab title
- document content
- email/thread if explicitly connected
- calendar event title
- slide deck

This is often more reliable than neural signal because it contains explicit context.

## I4: Personal Memory Vault

The user's local knowledge base.

Possible content:

- notes
- highlights
- reading history
- meeting notes
- personal preferences
- saved phrases
- medically relevant communication preferences for assistive mode

Principle:

```text
Local-first. User-owned. Deletable. Auditable.
```

## I5: Behavioral input

Signals:

- pause length
- speech rhythm
- hesitation
- head direction
- gaze target
- ring gesture
- typing/backspacing

Use:

```text
when to speak
when to wait
when to deepen
when to silence
```

## I6: Physiological input

Signals:

- heart rate
- HRV
- breathing
- motion
- skin conductance

Use:

```text
cognitive load estimate
stress estimate
attention burden estimate
```

Not use:

```text
emotion manipulation
ads
hidden profiling
```

## I7: Non-invasive neural input

Signals:

- EEG
- fNIRS
- P300
- SSVEP
- motor imagery

Near-term realistic use:

```text
selection
attention/load awareness
binary confirmation
research evaluation
```

Do not claim open-ended thought reading.

## I8: Invasive BCI input

This belongs to clinical/research contexts.

Use cases:

- cursor control
- sentence candidate selection
- speech intent decoding
- motor intent decoding

SYMBORG position:

```text
SYMBORG can consume decoded intent from BCI systems and convert it into better communication outputs.
```

## Best input strategy

Do not wait for perfect brain signal.

```text
The fastest useful signal is often external context.
```

Input priority for v0/v1:

```text
1. Audio conversation
2. Manual/ring control
3. Screen/document context
4. User memory vault
5. Glasses camera in explicit modes
6. Physiology/load awareness
7. Non-invasive neural selection
8. Invasive BCI integration
```
