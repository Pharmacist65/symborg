# Contextual Whisper Demo

This is the first working prototype seed for SYMBORG.

## Goal

Take a short conversation transcript and return three ranked cognitive packets:

1. An anchor cue
2. A question cue
3. A counterpoint cue

The first version is intentionally heuristic and can run without an LLM. It proves the packet format and product behavior before adding streaming ASR, retrieval, or model-based rewriting.

## Run

```bash
PYTHONPATH=src python -m symborg.heuristic_engine examples/great_expectations_context.txt
```

## Example Input

```text
A: I think Great Expectations is less about class mobility and more about shame.
B: Interesting. What do you think?
```

## Example Output

```json
[
  {
    "packet_type": "anchor",
    "cue": "Pip's class desire is tied to shame, guilt, and self-escape.",
    "confidence": 0.86,
    "topic": "Great Expectations",
    "delivery": "screen",
    "interruption_risk": "low"
  },
  {
    "packet_type": "question",
    "cue": "Ask whether Pip wants Estella, or the class world she represents.",
    "confidence": 0.82,
    "topic": "Great Expectations",
    "delivery": "screen",
    "interruption_risk": "low"
  },
  {
    "packet_type": "counterpoint",
    "cue": "Maybe class and shame are not separate; class pressure produces the shame.",
    "confidence": 0.8,
    "topic": "Great Expectations",
    "delivery": "screen",
    "interruption_risk": "low"
  }
]
```

## What It Demonstrates

- context extraction
- packet generation
- ranking
- latency-friendly output
- no claim of thought decoding

## Evaluation Targets

Measure:

- cue latency
- cue length
- usefulness
- factuality
- interruption cost
- user agency
- whether silence would have been better

## Next Steps

1. Replace heuristic detection with streaming ASR + entity extraction.
2. Add local vector retrieval.
3. Add optional local LLM packet rewriting.
4. Add user feedback: accept / reject / deepen / silence.
5. Add assistive mode candidate selection.
