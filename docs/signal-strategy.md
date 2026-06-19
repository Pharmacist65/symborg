# Signal Strategy

This document explains how SYMBORG should acquire signals faster and more efficiently without overclaiming "mind reading".

## 1. The Signal Ladder

SYMBORG separates signal sources by feasibility, risk, and latency.

```text
L0 — Environmental signal
L1 — Behavioral signal
L2 — Physiological signal
L3 — Non-invasive neural signal
L4 — Invasive BCI signal
```

The product should begin with L0 + L1 because these are fast, useful, and realistic.

## 2. L0: Environmental Signal

Sources:

- live conversation audio
- partial transcript
- screen text
- meeting title
- calendar context
- user notes
- visible objects, if camera permission exists
- location, if relevant and permissioned

Why this is the fastest useful signal:

- The topic usually appears in the environment before the user consciously forms an answer.
- The system can prepare cues while the user is still listening.
- It does not require neural decoding.

Implementation tactics:

```text
- streaming ASR instead of waiting for full sentences
- named entity extraction on partial transcript
- topic cache for likely follow-ups
- local vector search over personal notes
- pre-generated packet candidates
```

## 3. L1: Behavioral Signal

Sources:

- pause length
- speech rhythm
- filler words: "uh", "I mean", "let me think"
- head direction
- gaze direction
- hand/ring command
- manual accept/reject
- user starts speaking / stops speaking

Use:

```text
pause detected      -> offer short cue
user speaking       -> suppress cue
ring double tap     -> deepen cue
long press          -> silence
correction          -> update preference model
```

Behavioral signals are crucial because they are voluntary and socially controllable.

## 4. L2: Physiological Signal

Sources:

- heart rate / HRV
- skin conductance
- breathing rhythm
- eye movement / blink rate
- EMG muscle tension

Use:

- cognitive load estimation
- stress estimation
- fatigue estimation
- delivery intensity control

Do not use L2 to claim thought decoding.

## 5. L3: Non-Invasive Neural Signal

Sources:

- EEG
- fNIRS
- hybrid EEG-fNIRS
- EOG/EMG-adjacent signals

Good uses:

- attention state
- cognitive workload
- simple voluntary control
- P300 selection
- SSVEP selection
- motor imagery research mode

Weak uses:

- open-ended private thought decoding
- full semantic reconstruction in daily life
- reliable inner monologue extraction

SYMBORG's realistic v2 use of EEG is not "what is the user thinking?" It is:

```text
Should I speak less?
Should I wait?
Is the user overloaded?
Did the user select option A/B/C?
```

## 6. L4: Invasive BCI Signal

This is not an early consumer path. It belongs to medical research, clinical studies, and strict regulation.

Possible future-compatible uses:

- attempted speech decoding
- cursor/selection control
- sentence candidate selection
- communication restoration

SYMBORG's role here is not electrode design. It is the cognitive and language layer after a BCI has produced a control or intent signal.

```text
BCI signal -> intent/control -> SYMBORG context layer -> sentence candidates -> user confirmation -> output
```

## 7. Latency Budget

Target for v0:

```text
conversation event -> useful cue < 2 seconds
```

Possible budget:

```text
audio buffer                  50-150 ms
streaming ASR partial         300-800 ms
entity/topic detection         50-150 ms
retrieval                     100-500 ms
packet generation             200-700 ms
delivery                       50-200 ms
------------------------------------------------
total                         ~750-2500 ms
```

The system must be incremental. Waiting for a full paragraph kills the product.

## 8. How to Get the Signal Faster

### 1. Predictive context cache

When a topic appears, prepare likely cues before the user needs them.

```text
Topic: Dickens
Preload: Great Expectations, Oliver Twist, Victorian class, serialized fiction, child poverty
```

### 2. Partial transcript reasoning

Do not wait for full sentences.

```text
"What do you think about Dickens and..."
```

Already enough to preload Dickens packets.

### 3. Ring-first control

The fastest reliable "brain signal" for v1 is not EEG. It is a deliberate micro-gesture.

```text
thumb tap -> more
long press -> silence
swipe -> source
```

### 4. Output gating

Most latency is wasted producing cues the user does not need. Better gating means fewer, better packets.

### 5. Local-first retrieval

Local vector search and small local models reduce network latency and protect privacy.

### 6. Packet templates

Generate from templates when possible:

```text
anchor: {entity} = {theme1} + {theme2} + {theme3}
question: Ask whether {X} is really about {Y}
counterpoint: Maybe it is less about {A}, more about {B}
```

### 7. Continuous ranking

Keep candidates alive and update them as context changes.

```text
candidate_pool = [packet1, packet2, packet3]
new words arrive -> rerank -> deliver only if useful
```

## 9. Efficiency Metric

Do not measure only accuracy. Measure:

```text
helpfulness / interruption
```

Suggested metrics:

- cue latency
- cue acceptance rate
- cue rejection rate
- user interruption score
- conversation naturalness
- time-to-answer improvement
- source accuracy
- cognitive-load self-rating

## 10. Strategic Conclusion

The fastest signal is not always the most biological signal.

For SYMBORG v1, the winning strategy is:

```text
context first, behavior second, physiology third, neural last.
```
