# Assist Engine v1 — Implementation Specification

> The contract the code must satisfy. This is an engineering document, not a concept note:
> every requirement here is either enforced by a test or is not a requirement.

## 0. Scope

Replace the heuristic prototype (a hand-written topic library with fixed confidence
values) with a real pipeline for the assistive communication path:

```
room audio ──► ASR ──► rolling transcript
                          │
        personal vault ───┼──► candidate generation (LLM) ──► scoring
                          │                                      │
                          └──► abbreviation expansion            ▼
                                                        three ranked candidates
                                                                 │
                                              user selects one ──┤ (explicit, always)
                                                                 ▼
                                                    authorised utterance ──► TTS
```

Out of scope for v1: gaze/switch drivers (the selection signal is an interface, not a
device), AR output, any neural signal acquisition, any clinical deployment.

## 1. The authorship invariant

This is the first requirement because it is the one that must never regress.

> **Nothing is ever spoken that the person did not explicitly select.**

The existing `delivery_gate` decides whether a cue may be *shown*. It says nothing about
speech. v1 introduces a separate, stricter mechanism:

- Speech requires a `SpeechAuthorization` token.
- A token can be minted **only** by a genuine selection of a candidate the engine actually
  offered, and only through `Session.select()`.
- A token is **single-use**, bound to one candidate, and expires.
- `speak()` accepts a token, never raw text. There is no code path from generated text to
  audio that bypasses it.
- Every authorised utterance is logged with its origin, so `system_generated` and
  `user_confirmed` are always separable after the fact.

Required tests: speaking without a token fails; a token for candidate A cannot speak
candidate B; a token cannot be reused; an expired token fails; a forged/hand-constructed
token fails; selecting an index the engine never offered fails.

**Rationale.** Putting words in the mouth of someone who cannot contradict you is the
central ethical risk of this product category. It is enforced in code, not in a guideline.

## 2. Provider boundaries

ASR, LLM, TTS and voice banking are **protocols**, not implementations.

```python
class Transcriber(Protocol):   def transcribe(self, audio: bytes) -> TranscriptChunk: ...
class LanguageModel(Protocol): def complete(self, prompt: Prompt) -> str: ...
class Synthesiser(Protocol):   def synthesise(self, text: str, voice: VoiceRef) -> bytes: ...
```

Requirements:

1. **The core imports nothing outside the standard library.** Whisper, any LLM SDK, and any
   TTS SDK are optional extras. Importing `symborg_engine` must never fail because an
   optional dependency is missing.
2. **A deterministic offline provider ships in the box.** `NullLanguageModel` and friends
   produce fixed, sensible output with no network and no key, so that: CI is green and
   hermetic, contributors can run the demo immediately, and tests never depend on a
   third-party service.
3. **No credentials in the repository.** Configuration comes from the environment. A missing
   key degrades to the offline provider with a clear warning — it never crashes and never
   silently sends data anywhere.
4. Swapping a provider must not require touching engine logic.

## 3. Candidate generation

Input: rolling transcript, the personal vault, and interaction state.
Output: exactly `n` (default 3) ranked `Candidate` objects.

Rules:

- A candidate is a **complete, speakable first-person sentence** — not a cue, not a topic.
  This distinguishes the assistive path from the ambient-cue path.
- Candidates must be materially different from one another. Near-duplicates are collapsed
  and backfilled.
- Length is bounded (default ≤ 22 words) because it is read under time pressure.
- The set must always include a way out — a repair or "that's not what I meant" option —
  so the person is never trapped inside three wrong sentences.
- **No medical assertion is ever generated on the person's behalf.** Reporting a symptom in
  the first person ("my back hurts") is the person's own speech and is fine; a diagnosis,
  a dosage, or a clinical instruction is not, and is filtered.
- Generation failure returns an empty list, never a fabricated candidate.

## 4. Abbreviation expansion

The one intervention with a measured gain in this population: expanding a terse input into
a full sentence using conversational context, rather than typing every word.

- Input: an abbreviated form plus context. Output: ranked expansions.
- The expansion is a **candidate**, subject to the same selection requirement — expansion
  never bypasses authorship.
- Falls back to returning the input unchanged rather than guessing wildly.

## 5. Personal vault

Local, user-owned context: name, relationships, recurring needs, preferred phrasings, and
prior accepted utterances.

- Plain JSON on local disk. The person can read, edit, export and delete it.
- Nothing leaves the device unless a provider is explicitly configured to do so, and what
  is sent is auditable.
- The vault is optional; the engine works without it, with weaker candidates.

## 6. Session orchestration

`Session` owns the loop: ingest transcript → generate → score → offer → await selection →
authorise → speak → learn.

- `offer()` returns candidates and records exactly what was offered.
- `select(index)` is the only path to a `SpeechAuthorization`.
- `reject()` records a negative signal and offers again.
- Every stage is timed and the timings are exposed, because latency is a clinical property
  of this product, not an implementation detail: a turn arriving after the conversation has
  moved on has failed even if the sentence was correct.

## 7. Quality bar

- Type hints throughout; `from __future__ import annotations`; dataclasses for data.
- Docstrings state the contract, not the obvious.
- Tests cover the authorship invariant exhaustively, plus generation, scoring and session
  flow. Tests are hermetic — no network, no keys, no sleeping on wall-clock time.
- No secrets, no personal data, and no patient data in the repository, ever.
- Public API is explicit via `__all__`.

## 8. Definition of done

1. All tests pass offline with no API key set.
2. The engine runs end to end with the offline provider and produces three candidates.
3. With a key configured, the same path runs against a real model with no code change.
4. It is impossible to reach synthesis without an authorisation token, and a test proves it.
5. CI is green on the supported Python versions.
