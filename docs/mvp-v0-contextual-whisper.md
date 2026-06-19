# MVP v0: Contextual Whisper

## 1. Goal

Build the smallest working version of SYMBORG:

```text
Input: live or recorded conversation text
Output: three ranked micro-cues
```

The demo should prove that SYMBORG can detect context and return useful thought seeds without overwhelming the user.

## 2. Non-Goals

The MVP does not:

- decode thoughts
- use an implant
- claim medical function
- generate long essays
- speak for the user without confirmation

## 3. User Flow

```text
1. User enters or streams conversation transcript.
2. Context Engine detects topic, entities, and likely intent.
3. Retrieval Engine pulls relevant notes or source snippets.
4. Cognitive Packet Engine creates cue candidates.
5. Ranking system selects top 3.
6. User accepts, rejects, deepens, or silences.
```

## 4. Example

Input:

```text
A: I think Great Expectations is less about class mobility and more about shame.
B: Interesting. What do you think?
```

Output:

```json
[
  {
    "type": "anchor",
    "cue": "Pip's class desire is tied to shame and self-escape.",
    "confidence": 0.86
  },
  {
    "type": "question",
    "cue": "Ask whether Estella represents love or access to a higher class world.",
    "confidence": 0.79
  },
  {
    "type": "counterpoint",
    "cue": "Maybe class and shame are not separate; class pressure produces the shame.",
    "confidence": 0.82
  }
]
```

## 5. Suggested Technical Stack

Prototype options:

```text
ASR: Whisper / faster-whisper / browser speech recognition
Local LLM: llama.cpp / Ollama / MLX / small cloud model for early demo
Embeddings: sentence-transformers / nomic / OpenAI-compatible embedding API
Vector DB: Chroma / Qdrant / SQLite + vector extension
App UI: Streamlit / Next.js / Tauri
Audio output: local TTS or system voice
Haptic: later, via BLE ring or mobile vibration
```

## 6. Latency Goal

```text
first useful cue under 2 seconds after the relevant topic appears
```

## 7. Acceptance Criteria

A demo is successful if:

- It returns a useful cue in under 2 seconds on prepared scenarios.
- It returns no cue when the user is speaking fluently.
- It can explain why it produced a cue.
- It produces at least three packet types: anchor, question, counterpoint.
- It logs latency and user feedback.

## 8. Evaluation

Measure:

```text
- cue latency
- user acceptance rate
- user rejection rate
- perceived interruption
- factual accuracy
- conversation naturalness
- user's ability to answer faster or better
```

## 9. First Demo Scenarios

1. Literary conversation: Dickens / Great Expectations
2. Work meeting: project risk and decision
3. Learning mode: lecture explanation
4. Assistive mode: limited-input sentence selection
5. Social mode: remembering names and personal context

## 10. Immediate Build Steps

1. Implement transcript input.
2. Implement keyword/entity extraction.
3. Implement mock retrieval from a local JSON knowledge base.
4. Implement packet templates.
5. Add scoring.
6. Add CLI output.
7. Add simple UI.
8. Add optional LLM backend.
