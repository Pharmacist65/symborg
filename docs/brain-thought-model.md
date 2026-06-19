# Brain Thought Model

This document defines the working cognitive model used by SYMBORG. It is not a claim that the brain literally works like software. It is a practical abstraction for designing a human-AI cognitive interface.

## 1. Why SYMBORG Needs a Thought Model

A cognitive interface cannot simply "send information" to a person. The human mind has limited conscious bandwidth. If the system gives too much information, too late, or in the wrong format, it increases load instead of helping.

SYMBORG therefore models thought as a loop:

```text
Trigger -> salience -> association -> competition -> conscious access -> expression -> feedback
```

The goal is not to control the loop. The goal is to support it at the right moment.

## 2. The Seven-Stage Thought Loop

### 1. Trigger

A thought usually begins with a trigger:

- a word in conversation
- a question
- an image
- a social cue
- a memory fragment
- a bodily feeling
- a goal
- a problem to solve

Example:

```text
Someone says: "Great Expectations is really about shame."
```

This trigger activates concepts around Dickens, Pip, class, guilt, ambition, and memory.

### 2. Predictive and Salience Filtering

The brain estimates what matters:

```text
Is this relevant?
Is this socially risky?
Do I need to answer?
Do I already know this?
Is there emotional weight here?
```

SYMBORG should respect this layer. If the user is overloaded, the system should reduce output or stay silent.

### 3. Associative Activation

One cue activates many possible associations:

```text
"apple" -> fruit, color, taste, memory, Apple Inc., childhood, Newton, health, smell
"Dickens" -> Victorian England, poverty, class, serialized novels, Pip, Oliver, social criticism
```

Human memory is not a file search. It is partial activation and reconstruction. SYMBORG can act like an external associative index, but it must not pretend that retrieval equals understanding.

### 4. Working-Memory Competition

Several candidate thoughts compete for a small conscious workspace.

Example candidates:

```text
A. "I remember Pip."
B. "Class anxiety is important."
C. "I forgot the details."
D. "Maybe I should ask a question."
E. "Don't look uninformed."
```

A bad AI assistant adds more candidates and creates noise. A good SYMBORG cue reduces the search space.

### 5. Conscious Access

A small amount of information becomes reportable:

```text
"Pip's ambition is tied to shame."
```

This is the human "front-end" layer: the part the user can feel, speak, hold, and act on.

### 6. Verbal / Action Preparation

The thought becomes a sentence, question, gesture, decision, or silence.

SYMBORG can help here by producing:

- an anchor phrase
- a clarifying question
- a counterpoint
- a memory cue
- a source cue
- a sentence candidate

### 7. Feedback

The environment responds. The next loop begins.

```text
The other person answers -> new context -> new cue -> updated thought
```

## 3. Front-End / Back-End Analogy

This analogy is useful, but imperfect.

```text
Brain back-end:
- parallel associations
- emotional weighting
- body state
- memory reconstruction
- prediction
- language preparation
- social risk estimation

Brain front-end:
- conscious thought
- inner speech
- attention
- selected phrase
- reportable decision
```

SYMBORG does not replace the back-end. It acts as an external retrieval and packetization layer that feeds the front-end through normal sensory channels.

## 4. Where SYMBORG Can Help

```text
Human loop stage       SYMBORG support
------------------------------------------------------------
Trigger                Detect topic shift and named entities
Association             Retrieve relevant knowledge and personal notes
Competition             Reduce options into 1-3 useful cue packets
Conscious access        Deliver low-load cue through audio/AR/haptic
Verbal preparation      Suggest phrase, question, or answer shape
Feedback                Learn which cue was accepted, ignored, or rejected
```

## 5. Design Principle

The system should not ask:

```text
How do we put more data into the user?
```

It should ask:

```text
What is the smallest cue that helps the user's own mind complete the thought?
```

## 6. Important Boundary

SYMBORG v1 does not read thoughts. It reads context and assists thought.

That distinction is the ethical and technical foundation of the project.
