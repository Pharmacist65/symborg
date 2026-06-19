# Contextual Whisper Demo

This prototype will be the first working proof of concept for SYMBORG.

## Objective

Given a short live or recorded conversation transcript, the system should produce three ranked cognitive packets:

1. A concise fact or framing cue
2. A useful question or conversational move
3. A deeper optional context cue

The system should also provide confidence and choose silence when the context is too sensitive, too uncertain, or not useful.

## Prototype Scope

Input:

- Transcript text
- Optional user notes
- Optional source snippets
- Manual mode setting

Output:

- Three micro-cues
- Packet type
- Confidence
- Source note
- Silence recommendation when appropriate

## Example API Shape

```json
{
  "context": "A group is discussing Great Expectations and shame.",
  "mode": "conversation",
  "user_goal": "Participate naturally without pretending expertise.",
  "source_snippets": [
    "Pip's aspiration is linked to social shame and self-reinvention."
  ]
}
```

Expected output:

```json
{
  "packets": [
    {
      "type": "framing_cue",
      "text": "Pip links class desire with shame and self-reinvention.",
      "confidence": 0.82
    },
    {
      "type": "question_cue",
      "text": "Ask whether ambition is really escape from self-disgust.",
      "confidence": 0.76
    },
    {
      "type": "depth_cue",
      "text": "Miss Havisham can be read as frozen trauma.",
      "confidence": 0.68
    }
  ],
  "should_speak": true,
  "reason": "The cues are short, context-relevant, and non-sensitive."
}
```

## Evaluation

Measure:

- Time to output
- Cue length
- Usefulness
- Factuality
- Interruption cost
- User agency
- Whether silence would have been better

## Next Build Step

Build a minimal web demo with:

- Transcript input panel
- Optional source snippets
- Packet output cards
- Confidence display
- Silence toggle
- Haptic control simulation

