# Research Roadmap

## 1. Track A: Human Thought and Cue Design

Questions:

- What cue length is useful without overloading attention?
- Are questions better than facts?
- When does a cue feel like support vs intrusion?
- How many cues can a user tolerate in a live conversation?

Experiments:

```text
A/B test packet types:
- anchor
- question
- counterpoint
- memory
- source
```

Metrics:

- response quality
- time to answer
- user stress
- interruption rating
- recall after conversation

## 2. Track B: Low-Latency Context Engine

Questions:

- How early can the system detect a useful topic shift?
- Can partial transcript predict likely information needs?
- What should be cached?

Experiments:

- streaming transcript benchmark
- topic prediction from partial utterances
- retrieval latency benchmark
- local vs remote model comparison

Target:

```text
first useful cue < 2 seconds
```

## 3. Track C: Cognitive Load and State Awareness

Questions:

- Can behavioral signals detect overload well enough?
- Does adding physiological data improve timing?
- When should the system stay silent?

Signals:

- pause length
- speech rhythm
- correction rate
- ring commands
- HRV
- eye movement
- optional EEG workload markers

## 4. Track D: BCI-Compatible Assistive Communication

Questions:

- Can context-aware sentence candidates reduce selection time?
- How many options should be shown?
- Can a limited-input user preserve authorship and agency?

Prototype:

```text
input: one-switch or eye-gaze simulation
output: selectable sentence candidates
```

## 5. Track E: Ethics and Governance

Questions:

- What counts as cognitive manipulation?
- How should mental privacy be preserved?
- Should users disclose SYMBORG use in certain contexts?
- What data should never leave the device?

## 6. Milestones

### Milestone 1: Text prototype

- transcript input
- packet output
- latency logging

### Milestone 2: Live audio prototype

- streaming ASR
- live context detection
- audio cue output

### Milestone 3: Feedback prototype

- accept / reject / deepen / silence
- personalization model

### Milestone 4: Assistive communication demo

- sentence candidates
- limited input selection
- confirmation layer

### Milestone 5: Passive sensor research

- cognitive load estimation
- no thought decoding claims

## 7. North Star

```text
Make the right thought easier to reach without making the user less free.
```
