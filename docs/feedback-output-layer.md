# SYMBORG Feedback & Output Layer

SYMBORG is not only a retrieval system. Its defining feature is the way it returns knowledge to human attention without replacing thought, overloading working memory, or damaging social presence.

This document defines the **Symbiotic Return Stack**: the layer that decides how information should be returned to the user.

## Core question

```text
AI has found something useful.
How should that information enter the user's conscious field?
```

The answer is not always "show text" or "speak audio". Different contexts need different return channels.

## Symbiotic Return Stack

```text
Cognitive Packet
    |
    v
Output Policy Engine
    |
    v
Modality Router
    |
    +--> Haptic cue
    +--> Audio whisper
    +--> AR peripheral card
    +--> Phone/screen card
    +--> Assistive sentence candidate
    +--> Future neural-write research output
    |
    v
Human attention / perception / expression
```

The **Cognitive Packet Engine** decides what the idea is.

The **Output Policy Engine** decides whether it should be returned at all.

The **Modality Router** decides how it should be returned.

## Output principle

SYMBORG should not maximize output. It should maximize **usable cognitive fit**.

```text
The best packet is not the most complete packet.
The best packet is the smallest cue that lets the human continue thinking.
```

## Output goals

1. **Fast enough**: useful before the user loses the conversational moment.
2. **Small enough**: fits working memory.
3. **Private enough**: does not expose sensitive context to others.
4. **Actionable enough**: helps the user ask, answer, choose, remember, or pause.
5. **Interruptible**: the user can silence it instantly.
6. **Agency-preserving**: the device suggests; the human decides.

## Output types

### 1. Anchor packet

A compact conceptual hook.

```text
Pip = shame + class desire + guilt.
```

### 2. Question packet

A question the user can ask.

```text
Ask: does Pip want Estella, or the class world she represents?
```

### 3. Counterpoint packet

A small alternative perspective.

```text
Counterpoint: class pressure may be what produces the shame.
```

### 4. Memory packet

A cue from the user's own notes or previous context.

```text
You saved a note: “Dickens often links childhood trauma with social ambition.”
```

### 5. Warning packet

A confidence, ethics, or social-risk warning.

```text
Low confidence. Do not state as fact.
```

### 6. Assistive sentence candidate

A selectable sentence for users with limited input.

```text
Candidate 2: I need help changing my position.
```

### 7. Navigation packet

A cue for physical or digital action.

```text
Left door. Elevator after 12 meters.
```

## Modality selection matrix

| Context | Preferred output | Why |
|---|---|---|
| User is speaking | Haptic only or silence | Do not interrupt speech production |
| User is listening | Audio whisper or AR card | User can receive micro-cue |
| Social dinner | Haptic + ultra-short audio | Private and low-distraction |
| Formal meeting | AR peripheral card | Quieter than audio, source/cue visible |
| Walking outside | Audio + haptic | Visual attention must stay on environment |
| Driving | Haptic only / no cognitive output | Safety first |
| Assistive communication | Candidate grid + one-switch/BCI selection | Enables expression with low input bandwidth |
| High stress | Fewer packets, shorter cues | Reduce load |
| Low confidence | Suppress or show warning | Avoid false authority |
| Medical/clinical | Confirmable candidates, audit log | Safety and accountability |

## Delivery budgets

### Audio whisper

```text
Target length: 5-14 words
Maximum live length: 18 words
Tone: quiet, calm, neutral
No paragraphs
No long explanations
```

### AR card

```text
Target length: 5-20 words
Maximum live length: 25 words
Location: peripheral, not center-screen by default
Lifetime: 1-4 seconds unless pinned
```

### Haptic cue

```text
No semantic overload.
Use haptics mainly for status, urgency, control, and very simple signals.
```

### Assistive candidate

```text
Candidate count: 2-4
Each candidate: short, speakable, confirmable
Must support undo/cancel
```

### Neural-write research output

```text
Not a consumer v1 feature.
Do not claim screen-like perception.
Use only as a future clinical/research track.
Prefer symbolic low-bandwidth percepts over complex images.
```

## Feedback loop

SYMBORG should learn from user reactions.

```text
packet delivered
    |
    v
user ignores / taps / speaks / asks for depth / silences
    |
    v
quality update
    |
    v
future output timing improves
```

Useful signals:

- Was the cue used in speech?
- Did the user silence it?
- Did the user ask for depth?
- Did the user pause after receiving it?
- Did the cue appear during speech and cause interruption?
- Did the user later rate it useful?

## The silence rule

SYMBORG must treat silence as an output mode.

```text
When uncertain, overloaded, unsafe, or socially disruptive: say nothing.
```

Silence is not failure. It is part of intelligence.

## Repository implication

Add an output layer after the Cognitive Packet Engine:

```text
Context Engine
    -> Retrieval Engine
    -> Cognitive Packet Engine
    -> Quality Scoring
    -> Delivery Gate
    -> Output Policy Engine
    -> Modality Router
    -> Human perception
```
