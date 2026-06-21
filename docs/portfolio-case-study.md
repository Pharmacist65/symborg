# SYMBORG Portfolio Case Study

## One-Line Summary

SYMBORG is a non-invasive cognitive front-end concept that turns live context into brief, scored cognitive packets and routes them through attention-sensitive output channels such as screen, audio, AR, haptics, or assistive communication UI.

## Problem

AI systems can retrieve and compress more information than a person can hold in working memory. The interface problem is what happens next.

Most AI products return too much information in the wrong shape: full answers, long chats, dense search results, or notifications that compete with the user's current social and cognitive context.

SYMBORG frames the problem differently:

```text
How should useful information return to human attention without replacing the person's thought?
```

## Product Thesis

The missing layer is not another chatbot. It is an attention-aware routing layer:

```text
Context -> retrieval -> cognitive packet -> quality gate -> output route -> human attention
```

The core unit is a cognitive packet: a short thought seed, question, sentence candidate, source check, or haptic state. A packet is intentionally smaller than an answer and more actionable than a notification.

## Working Prototype

The repository now includes a local browser demo:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 prototypes/symborg-live-demo/server.py
```

Open:

```text
http://127.0.0.1:8765
```

The demo connects three working layers:

- Contextual packet generation
- Quality and interruption gating
- Device-aware output routing

It includes three built-in scenarios:

- **Dickens:** live conversation support through short literary reasoning cues
- **Meeting:** startup/product discussion support through question and counterpoint packets
- **Assistive:** clinical communication support through selectable sentence candidates

## What Was Built

- A practical thought-interface model for where the system should intervene
- A signal ladder separating realistic v0 signals from future BCI-compatible research
- A Cognitive Packet Engine with packet schema, scoring, and evaluation fixtures
- A conservative delivery gate based on pause, speaking state, user signal, cognitive load, and minimum quality score
- A Modality Router for screen, audio whisper, AR card, haptic cue, assistive candidate, and future neural-research glyph simulation
- A browser demo showing the full decision path from transcript to route
- A visual system and prompt library for consistent case-study imagery
- Social launch material written to invite critique without overclaiming

## Evidence In The Repo

- [Live integrated demo](../prototypes/symborg-live-demo)
- [Contextual whisper prototype](../prototypes/contextual-whisper-demo)
- [Output router prototype](../prototypes/output-router-demo)
- [Cognitive packet engine spec](cognitive-packet-engine-spec.md)
- [Evaluation protocol](evaluation-protocol.md)
- [Feedback and output layer](feedback-output-layer.md)
- [Assistive communication mode](assistive-communication-mode.md)
- [Ethics](ethics.md)

## Design Boundaries

The credibility of the project depends on what it refuses to claim.

SYMBORG does not claim:

- Mind reading
- Knowledge upload
- A medical device
- Clinical validation
- Affiliation with Neuralink, OpenAI, Apple, Meta, or any medical device company
- High-resolution information projection into the brain

The first serious version is non-invasive and should rely on L0/L1 signals: conversation, screen context, pause timing, gesture, and user-confirmed control.

## Why Assistive Communication Matters

The strongest serious use case is not making a fluent person sound smarter in meetings. It is helping constrained-input users express meaningful sentences with fewer actions.

In that mode, SYMBORG does not speak for the user. It generates context-aware sentence candidates and lets the user confirm, reject, or navigate them through a minimal signal channel.

That keeps the product anchored in agency, dignity, and practical value.

## Next Build Milestones

1. Replace heuristic topic detection with retrieval-backed context grounding.
2. Add live transcript ingestion with latency and interruption logging.
3. Add a local memory vault with explicit user-controlled sources.
4. Add packet feedback: useful, mistimed, too long, unsafe, or wrong context.
5. Build a recorded demo video from the live browser prototype.
6. Run a small evaluation set measuring packet usefulness, silence decisions, and route correctness.

## Collaboration Ask

The project is ready for critique from people working in:

- Human-computer interaction
- Wearable AI
- Assistive communication
- Accessibility
- Neurotechnology ethics
- Brain-computer interfaces
- Product design for attention-sensitive systems

The useful conversation is not "Is this the next big thing?" The useful conversation is:

```text
What is the right interface contract between AI retrieval and human attention?
```
