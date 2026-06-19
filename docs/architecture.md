# Architecture

## Design Goal

SYMBORG is designed as a cognitive front-end, not an autonomous replacement for human thought. The architecture should optimize for timing, brevity, reliability, and user control.

## High-Level Loop

```text
Signals
  conversation, screen, notes, calendar, user command

Context Engine
  topic, entities, intent, social state, task state

Retrieval Engine
  local memory, trusted documents, source snippets

Cognitive Packet Engine
  compress, rank, time, format

Confidence and Ethics Filter
  source confidence, uncertainty, privacy, manipulation risk

Output Layer
  audio whisper, AR cue, haptic pulse, assistive communication UI

User
  accepts, ignores, deepens, silences, or selects output
```

## Module Responsibilities

### Context Engine

The Context Engine decides what situation the user is in.

Inputs may include:

- Live transcript
- Named entities
- Recent user notes
- Calendar title
- Open document or meeting context
- User gesture or haptic command

The first MVP should use transcript text and manual context only.

### Local Memory Vault

The Local Memory Vault stores user-controlled context.

Examples:

- Notes
- Reading history
- Meeting summaries
- Known people and relationships
- Preferred communication style
- Source documents

Local-first storage is a product principle, not only a technical decision. The more personal the memory, the more conservative the system should be.

### Retrieval Engine

The Retrieval Engine finds relevant material and returns short evidence units. It should separate factual source retrieval from personal memory retrieval.

The system should prefer:

- Local user documents
- Explicitly trusted sources
- Transparent citations
- Low-latency retrieval

### Cognitive Packet Engine

The Cognitive Packet Engine transforms retrieved material into a human-usable cue.

Packet types:

- Fact cue
- Question cue
- Analogy cue
- Counterpoint cue
- Summary cue
- Social tone cue
- Assistive sentence candidate

Packet constraints:

- Usually one sentence or phrase
- No unnecessary detail
- No fake confidence
- No impersonation of the user
- Easy to deepen on command

### Confidence and Ethics Filter

The filter decides whether the system should speak, stay silent, or ask for confirmation.

Checks:

- Source quality
- User consent
- Sensitivity of topic
- Social risk
- Medical/legal/financial risk
- Cognitive load
- Manipulation risk

### Sensory Output Layer

The output channel should match the context.

Audio:

- Best for hands-free use
- Risk: intrusive if verbose

AR:

- Best for peripheral visual cueing
- Risk: distraction and social weirdness

Haptic:

- Best for control and low-bandwidth state cues
- Risk: limited expressiveness

Assistive communication UI:

- Best for constrained input users
- Risk: requires careful evaluation and accessibility testing

## Non-Goals

SYMBORG v1 should not attempt to:

- Read private thoughts
- Infer hidden intent from neural signals
- Replace the user's speech
- Make medical claims
- Operate without clear user control
- Optimize for engagement over agency

