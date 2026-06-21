# Inner Voice Mode

SYMBORG Inner Voice is the output mode where AI feedback feels like a quiet companion inside the user's cognitive flow.

It should not be framed as literal voice implantation in the early versions. The first implementation is external but intimate: bone-conduction or open-ear audio.

## Two meanings of inner voice

### 1. Practical inner voice

```text
A very quiet, private audio whisper delivered through an earpiece.
```

This is realistic now.

### 2. Neural inner voice

```text
Direct decoding or writing of inner speech through a BCI.
```

This is clinical/research territory and must be treated with extreme privacy protections.

## Practical inner voice design

The voice should be:

- short
- calm
- optional
- interruptible
- source-aware
- not emotionally manipulative
- not always-on by default

## Cue examples

```text
Anchor:
“Pip: shame plus class desire.”

Question:
“Ask if Estella represents class.”

Warning:
“Low confidence. Phrase as possibility.”

Memory:
“You saved this: Dickens links childhood and social guilt.”
```

## Inner voice safety rules

```text
1. The user can silence it instantly.
2. The system never pretends to be the user's own thought.
3. The system clearly distinguishes AI cue from self-generated thought.
4. The system does not output persuasive emotional commands.
5. The system does not speak during user speech unless emergency/assistive.
6. The system never decodes private inner speech without an explicit unlock/intent gate.
```

## Intent gate

For future BCI-related inner speech, SYMBORG must require an intentional unlock.

Examples:

```text
wake phrase
ring long-press
specific mental command in clinical BCI
eye-gaze confirmation
two-step confirm
```

## Why this matters

A speech BCI that can decode inner speech is powerful, but it creates a privacy problem: it may expose thoughts the user did not intend to communicate. SYMBORG must be built around the concept of an **intent gate**.

## Inner voice UX modes

### Companion mode

Calm micro-cues.

```text
“Use the shame angle.”
```

### Socratic mode

Only questions.

```text
“What assumption are they making?”
```

### Memory mode

Only previously stored user notes.

```text
“You wrote: class anxiety is social self-disgust.”
```

### Assistive mode

Selectable sentence candidates.

```text
“Candidate 1: I need a break.”
```

### Silence mode

No audio. Haptic only.

## Key phrase

```text
SYMBORG should feel like an intelligent whisper, not an occupying voice.
```
