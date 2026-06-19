# Evaluation Protocol

SYMBORG needs an evaluation layer because the core risk is not that the system
says nothing. The core risk is that it says too much, too late, too confidently,
or at the wrong cognitive moment.

## 1. Evaluation Target

The prototype should evaluate packets across six dimensions:

```text
1. Latency
2. Brevity
3. Actionability
4. Context relevance
5. Interruption risk
6. Agency preservation
```

## 2. Minimum v0 Metrics

| Metric | Target |
|---|---:|
| first useful cue latency | < 2.5 seconds after topic trigger |
| audio cue length | 5-18 words |
| screen cue length | 5-25 words |
| default live packets returned | <= 3 |
| low-confidence delivery | suppressed below 0.45 |
| user speaking delivery | suppressed |
| silence gesture respect | 100% |

## 3. Packet-Level Scores

Each packet should be scored with:

```json
{
  "word_count": 13,
  "brevity_score": 0.94,
  "actionability_score": 0.75,
  "confidence_score": 0.82,
  "interruption_score": 1.0,
  "cognitive_load_score": 0.8,
  "total_score": 0.85,
  "warnings": []
}
```

## 4. Session-Level Scores

For a set of packets:

```json
{
  "packet_count": 3,
  "mean_score": 0.81,
  "delivered_count": 2,
  "suppressed_count": 1,
  "best_packet_type": "question",
  "silence_was_better": false
}
```

## 5. Human Evaluation Questions

During user testing, ask:

1. Did the cue help you say something better?
2. Did it arrive too early, too late, or at the right time?
3. Did it feel like your own thought was supported?
4. Did it make you feel fake, overloaded, or interrupted?
5. Would silence have been better?
6. Would you ask for deeper context?

## 6. Assistive Mode Evaluation

For limited-input users, evaluate:

```text
selection count to desired sentence
time to express intent
candidate relevance
candidate dignity
repair ability if wrong
user control over final output
```

The assistive mode should never auto-speak as if it is the user unless the user
explicitly selects or confirms the candidate.

## 7. Failure Cases to Track

- hallucinated facts,
- socially inappropriate cue,
- cue too long,
- cue arrives while user is speaking,
- cue repeats known information,
- cue pushes a manipulative framing,
- cue creates dependency,
- source cannot be explained.

## 8. v0 Research Claim

The first serious claim should be narrow:

> A cognitive packet interface can convert conversation context into short,
> ranked thought cues while measuring brevity, interruption risk, and agency.

Do not claim thought decoding. Do not claim medical benefit. Do not claim memory
upload.
