# Cognitive Packet Engine Specification

The Cognitive Packet Engine (CPE) is the central mechanism of SYMBORG.
It converts a large context space into a tiny, timely, socially usable cue.

The goal is not to answer everything. The goal is to increase the probability
that the right thought, question, phrase, or memory reaches conscious attention
at the right moment.

## 1. Core Principle

A cognitive packet is a **thought seed**, not an article.

Bad packet:

```text
Charles Dickens was born in 1812 and is considered one of the most important
Victorian novelists. Great Expectations was first published in serialized form...
```

Good packet:

```text
Pip: shame + class desire + guilt. Ask if ambition is self-escape.
```

## 2. Packet Contract

Each packet should be represented as a structured object:

```json
{
  "packet_type": "question",
  "cue": "Ask whether Pip wants Estella, or the class world she represents.",
  "confidence": 0.82,
  "topic": "Great Expectations",
  "depth": 1,
  "delivery": "audio_whisper",
  "interruption_risk": "low",
  "cognitive_load": 2,
  "expected_use": "ask",
  "source_basis": ["conversation_context", "literary_schema"],
  "supporting_context": ["Pip", "Estella", "class desire"],
  "created_at_ms": 1780000000000
}
```

## 3. Packet Types

| Type | Purpose | Example |
|---|---|---|
| `anchor` | give the user a conceptual handle | `Pip = shame + class desire + guilt.` |
| `question` | create a social/conversational move | `Ask if ambition is really self-escape.` |
| `counterpoint` | offer a useful alternative interpretation | `Maybe class and shame are not separate.` |
| `sentence` | assistive or low-bandwidth output candidate | `I think the pain is worse at night.` |
| `source` | provide provenance or confidence context | `Based on your notes from Tuesday.` |
| `memory` | retrieve personal/contextual memory | `You discussed this with Deniz last week.` |

## 4. Design Rules

A packet should be:

1. **Short**: ideally 5-18 words for audio, 5-25 words for screen/AR.
2. **Actionable**: it should suggest a thought move, not merely deliver trivia.
3. **Contextual**: it should fit the current conversation.
4. **Low-interruption**: it should not compete with the person speaking.
5. **Agency-preserving**: it should help the user think, not impersonate them.
6. **Depth-aware**: it should support levels, from tiny cue to deeper expansion.
7. **Source-aware**: when facts matter, it should expose confidence and basis.

## 5. Depth Levels

```text
Depth 0: haptic-only / no semantic content
Depth 1: tiny cue, 5-12 words
Depth 2: short thought move, 12-25 words
Depth 3: sentence candidate or mini-explanation
Depth 4: source-backed expansion
Depth 5: full note or article, not for live whisper mode
```

The default live-conversation mode should stay around depth 1-2.

## 6. Delivery Modes

| Mode | When to use | Rule |
|---|---|---|
| `haptic` | user needs a nudge, not words | never contains semantic overload |
| `audio_whisper` | eyes-free mode | must be very short |
| `screen` | prototype/debug mode | can show metadata |
| `ar` | peripheral visual cue | one line only |
| `assistive` | candidate selection | must be explicit and user-selectable |

## 7. Delivery Gate

A packet may be good but still should not be delivered.

Suppress delivery when:

- the user is already speaking,
- the cue is too long,
- the confidence is too low,
- the interruption risk is high,
- the user used a silence gesture,
- the system cannot explain why the cue is relevant.

## 8. Quality Score

A simple first-pass score:

```text
packet_score =
  0.25 * brevity_score +
  0.25 * actionability_score +
  0.20 * confidence_score +
  0.15 * interruption_score +
  0.15 * cognitive_load_score
```

A packet should usually score above `0.65` to be delivered in live mode.
For assistive mode, a lower score may be acceptable if the user explicitly asks
for candidates.

## 9. What Makes SYMBORG Different

A normal AI assistant tries to answer.

SYMBORG tries to shape information into a form that a human mind can actually
use during a live cognitive moment.

The key product question is:

> Is this packet worth occupying the user's attention right now?
