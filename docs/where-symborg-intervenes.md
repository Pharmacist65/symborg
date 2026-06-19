# Where SYMBORG Intervenes

This document defines the exact intervention points in the human cognition loop.

## 1. Core Idea

SYMBORG should not attempt to take over thought. It should enter at narrow, controllable points where the user benefits from faster context, memory, or expression support.

```text
Human cognition loop:

World -> perception -> context -> association -> attention -> thought -> speech/action -> world

SYMBORG intervention:

World -> context engine -> retrieval -> packet -> sensory cue -> human thought -> speech/action
```

## 2. Intervention Point A: Before the User Asks

Most useful assistance happens before the user explicitly asks for it.

The system watches for:

- named entities: people, books, companies, technologies
- topic shifts
- questions directed at the user
- long pauses
- disagreement markers
- uncertainty markers
- meeting agenda items
- references to the user's notes or past context

Example:

```text
Conversation: "What do you think about Dickens and class anxiety?"
SYMBORG detects: Dickens + class anxiety + likely opinion request.
```

Output should not be a lecture. It should be a tiny thought seed:

```text
"Pip = shame + class desire. Ask if ambition is self-escape."
```

## 3. Intervention Point B: Associative Retrieval

The brain performs associative retrieval from memory. SYMBORG can run a parallel artificial retrieval loop:

```text
User context -> entity extraction -> local memory -> trusted sources -> candidate facts -> cue ranking
```

This is like an external hippocampal index, but not a replacement for human memory.

## 4. Intervention Point C: Attention Gate

The system should deliver information only if the expected value exceeds the interruption cost.

```text
Cue value = relevance + urgency + confidence + social utility
Interruption cost = timing risk + cognitive load + social visibility + emotional pressure
```

Only deliver when:

```text
cue_value > interruption_cost
```

If not, stay silent.

## 5. Intervention Point D: Verbal Preparation

SYMBORG should often return a **conversation move**, not raw information.

Useful packet types:

```text
anchor:       one compact idea
question:     one useful question to ask
bridge:       connect current topic to user's knowledge
counterpoint: respectful disagreement angle
memory:       personal note or past context
source:       confidence/source cue
sentence:     assistive communication candidate
```

## 6. Intervention Point E: Assistive Communication

For limited-input users, the system should create sentence candidates from context.

```text
Doctor: "Where is the pain?"
Context: previous notes mention neck pain, worse at night.
Candidates:
1. "The pain is in my neck."
2. "It gets worse at night."
3. "I want to change my position."
```

The user selects with a small signal: eye gaze, one switch, haptic tap, P300 choice, or a future BCI output.

## 7. Non-Intervention Rules

SYMBORG should not intervene when:

- the user is speaking fluently
- the cue confidence is low
- the context is private and no permission exists
- the user has activated silence mode
- the cue would create social deception
- the system is unsure whether the user wants help
- the user is emotionally overloaded and the cue is non-urgent

## 8. Main Design Law

```text
Do not maximize output.
Maximize timely usefulness minus interruption cost.
```
