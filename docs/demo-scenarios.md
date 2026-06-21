# Demo Scenarios

These scenarios now map to the working local demo in [prototypes/symborg-live-demo](../prototypes/symborg-live-demo). Use them as recording material, evaluation prompts, and portfolio examples.

```bash
PYTHONDONTWRITEBYTECODE=1 python3 prototypes/symborg-live-demo/server.py
```

Open `http://127.0.0.1:8765`.

## Demo 1: Contextual Whisper

### Goal

Show that SYMBORG can turn live context into short, useful cognitive cues without generating full answers.

### Input

Conversation transcript:

```text
"I think Great Expectations is less about class mobility and more about shame."
```

User profile:

```text
The user has not recently read Dickens but wants to participate naturally.
```

### Output

```text
Cue 1: Pip links class desire with shame and self-reinvention.
Cue 2: Ask whether ambition in the novel is really escape from self-disgust.
Cue 3: Miss Havisham can be framed as frozen trauma, not only eccentricity.
```

### Why It Works

The output gives the user thinking material, not a script.

## Demo 2: Meeting Assistant

### Goal

Help a user stay oriented in a technical meeting without opening another screen.

### Input

```text
"The team is debating whether to move retrieval from cloud search to local vector storage."
```

### Output

```text
Cue 1: Tradeoff: latency and privacy improve, but sync and storage complexity rise.
Cue 2: Ask how source freshness will be handled offline.
Cue 3: Request a failure-mode test before committing.
```

## Demo 3: Learning Support

### Goal

Return a short conceptual anchor during study.

### Input

```text
"Working memory capacity and chunking."
```

### Output

```text
Cue 1: Capacity is limited, but chunks can carry richer meaning than raw items.
Cue 2: Expert memory often works through compressed schemas.
Cue 3: Good interfaces should reduce load, not add more things to track.
```

## Demo 4: Assistive Communication

### Goal

Demonstrate a more serious use case for constrained input.

This is the priority demo for serious reviewers because it shows agency-preserving output rather than a generic productivity assistant.

### Scenario

A user can make one selection signal. A doctor asks:

```text
"How is your pain right now?"
```

Context:

```text
The user's previous note mentions neck pain that increases at night.
```

Candidate outputs:

```text
1. My pain is better right now.
2. The pain is in my neck and gets worse at night.
3. I want to change my position.
```

### Success Metric

The system reduces the number of input actions required to communicate a meaningful sentence.

## Demo 5: Silence Protocol

### Goal

Show restraint.

### Input

The system detects a sensitive emotional conversation with low factual need.

### Output

```text
No cue. Optional haptic state only.
```

### Why It Works

SYMBORG should not optimize for constant intervention. It should optimize for human agency.
