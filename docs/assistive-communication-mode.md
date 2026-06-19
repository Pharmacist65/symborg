# Assistive Communication Mode

## 1. Why This Mode Matters

The most serious early use case for SYMBORG is not making healthy users sound smarter. It is helping people with limited input channels communicate faster and with more dignity.

This document describes the future-compatible assistive communication layer. It is a concept and research direction, not a medical claim.

## 2. Core Loop

```text
conversation context -> possible intent -> sentence candidates -> user selection -> output
```

## 3. Example Scenario

A clinician asks:

```text
"Where is the pain worse?"
```

User context:

```text
- user has severe motor impairment
- prior note: neck pain worsens at night
- current session: discomfort after sitting for 40 minutes
```

SYMBORG candidates:

```text
1. "The pain is in my neck."
2. "It is worse at night."
3. "I want to change my position."
```

The user selects with:

- eye gaze
- one-switch scanning
- sip-and-puff
- haptic tap
- P300 selection
- future BCI cursor/control signal

## 4. Why SYMBORG Is Useful Here

Traditional assistive communication often requires letter-by-letter or menu-based selection. SYMBORG can use context to make high-probability sentence candidates.

The user remains in control because the system proposes; the user confirms.

## 5. BCI-Compatible Layer

SYMBORG can sit after any control signal:

```text
EEG P300 selection -> choose sentence
Eye tracker -> choose sentence
Invasive BCI cursor -> choose sentence
Attempted speech decoder -> refine sentence
```

SYMBORG's value is language, context, and interaction design, not electrode implantation.

## 6. Safety and Ethics

Requirements:

- never output medical statements without user confirmation
- always show/select candidates before speaking externally
- preserve user agency
- allow immediate cancellation
- keep private context local when possible
- log system-generated vs user-confirmed speech

## 7. Prototype Version

The first prototype can simulate a limited-input user with only three controls:

```text
next candidate
select candidate
cancel
```

This is enough to demonstrate the architecture without any medical hardware.
