# Latency and Interruption Model

SYMBORG's speed advantage should come from context preloading, not from pretending
to read open-ended thoughts.

## 1. Fastest Useful Signal

The fastest useful signal is often not the deepest neural signal.
It is the context that appears before the user needs to speak.

```text
conversation trigger -> partial transcript -> entity/topic cache -> packet candidates -> delivery gate
```

## 2. Latency Budget

A practical v0 budget:

```text
audio / text chunk                         50-150 ms
partial transcript or input update        300-800 ms
entity/topic detection                      50-150 ms
local retrieval                            100-500 ms
packet generation                          100-700 ms
delivery gate + output                      50-200 ms
----------------------------------------------------
total                                      650-2500 ms
```

The first useful cue should normally appear within 2.5 seconds after a clear
context trigger.

## 3. Interruption Cost

Every packet has a cost:

```text
interruption cost = timing cost + length cost + confidence cost + social cost
```

A packet can be correct and still harmful if it arrives while the user is
speaking, when the social moment requires listening, or when silence is better.

## 4. Suppression Rules

Suppress or delay delivery when:

- user is speaking,
- user used silence gesture,
- pause is shorter than threshold,
- packet confidence is too low,
- cognitive load estimate is high,
- packet is longer than delivery mode allows,
- the same cue was already delivered recently.

## 5. Preloading Strategy

When a topic appears, the system should prepare multiple packets but deliver none
until the gate opens.

Example:

```text
0.0s: user hears "Great Expectations"
0.4s: entity detected
0.8s: Dickens/Pip/Estella/class-shame cache opened
1.1s: three packet candidates prepared
1.5s: user pause detected
1.6s: only best packet delivered
```

## 6. Product Rule

SYMBORG should optimize for:

```text
minimum useful cue, maximum human ownership
```

The user should feel: "I had the thought faster," not "a machine talked through me."
