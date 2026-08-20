# The Human–LLM Integration Stack

> An architecture for putting language-model intelligence into a person's loop without
> overloading attention, displacing agency, or making claims the physics does not support.

This document exists to turn an ambition into an engineering problem. The ambition is
easy to state and hard to make precise: *if a machine can retrieve and reason faster than
a person can, how should that capability be integrated into the person's own loop?*

Stated that way it is a slogan. Below it is decomposed into layers, each with a hard
physical constraint, an open problem, and the discipline that owns it. Several of these
problems we cannot solve alone, and they are marked as such — that is the point of
publishing this.

The numbers here come from [Signal to Response](signal-to-response.md), which surveys the
underlying literature and was adversarially fact-checked. Nothing in this document is a
medical claim.

---

## 1. Why a stack, and not a device

Three measured facts constrain every design in this space.

**The loop is an hourglass.** Sensory input runs to 10⁷–10⁹ bit/s. Conscious access passes
roughly 10–60 bit/s. Speech carries about 39 bit/s. The bottleneck is neither the senses
nor the muscles — it is central, and it does not widen. Any system that increases input
pressure on a saturated channel makes the person slower.

**The native sensory channel is the widest write path that exists.** Writing through the
ear or eye is on the order of tens of bits per second — the ~40–60 bit/s figure quoted for
this route is a literature estimate for the channel, not a measured property of any
device, and should be treated as an upper bound. Skin is markedly lower: engineered
tactile devices achieve 5–12 bit/s, against ~22 bit/s for Tadoma, the human ceiling. Even
so, the best cortical stimulation manages ~0.1–1 bit/s. Choosing the sensory route is not
a limitation accepted for lack of resources; on today's numbers it beats every implanted
alternative by one to two orders of magnitude.

**This is a design constraint, not a business case.** Neosensory ceased operations in
February 2025 having executed precisely this thesis — with a neuroscientist founder,
capital, clinical data and a shipping product. The bandwidth argument tells you where to
build. It does not tell you that a company exists there.

**Computation cannot live in the body.** Energy harvested in vivo is on the order of
39 µW. A single token of language-model inference on an edge device costs 52–271 mJ. That
is roughly **one token per hour**. Conversational rate needs ~1.4 W — about 36,000× the
harvest. Wireless power does not rescue it: within electromagnetic safety limits, a
deep-tissue implant receives on the order of 90 µW. And heat is a second wall that
engineering does not move, because tissue sets it.

So intelligence must be distributed across layers that differ by five orders of magnitude
in available power, and the interesting engineering is in what runs where, and in what
crosses each boundary.

---

## 2. The layers

```
        ┌──────────────────────────────────────────────────────────────┐
  L4    │  Cloud — large models, long context          unbounded power │
        ├──────────────────────────────────────────────────────────────┤
  L3    │  Phone — local small model, orchestration    1–10 W, bursty  │
        ├──────────────────────────────────────────────────────────────┤
  L2    │  Wearable accelerator — the real network     30–150 mW       │
        ├──────────────────────────────────────────────────────────────┤
  L1    │  Always-on gatekeeper — decides when to wake 1–10 mW         │
        ├──────────────────────────────────────────────────────────────┤
  L0    │  Sensing & actuation — no model here         10 µW – 1 mW    │
        └──────────────────────────────────────────────────────────────┘
                    ▲                                    │
                    │  what the person emits             │  what returns
                    │  (speech, gaze, residual EMG,      ▼  (audio, visual,
                    │   behavioural state)                   haptic — never
                    └────────────  THE PERSON  ──────────────  implanted)
```

### L0 · Sensing and actuation
**Budget:** 10 µW – 1 mW. **Owns:** acquiring what the person emits; delivering a cue.

At this budget there is no model — this is a sensor and an actuator, pacemaker-class.
Holding a 0.5 GB model in memory alone costs 10–20× this layer's entire envelope.

*Open problem:* robust surface biosignal acquisition on a body that is changing. In
progressive disease the signal degrades over months; an interface calibrated once is
calibrated for a person who no longer exists. Published generic sEMG models degrade
roughly 7.5× on an uncalibrated new user, and personalisation currently means data that a
weakening person cannot afford to give.
*Discipline:* biomedical engineering, wearable bioelectronics.

### L1 · Always-on gatekeeper
**Budget:** 1–10 mW. **Owns:** deciding when anything upstream should wake at all.

This is where "listens continuously without draining the battery" actually lives.
Always-on keyword and voice-activity detection under 1 mW is demonstrated; weights live in
on-die SRAM.

*Open problem:* the gatekeeper must decide to wake *before* the moment it is needed. In
conversation the useful window opens ~200 ms after the partner stops, and a reactive
system has already lost. Waking on prediction rather than on detection, inside a
milliwatt, is unsolved.
*Discipline:* low-power embedded ML.

### L2 · Wearable accelerator
**Budget:** 30–150 mW. **Owns:** the real neural network — separation, enhancement,
turn-end prediction, state estimation.

The only commercially proven "real AI on the body" point. A measured reference: 71.6 mW
accelerator plus 10.3 mW peripherals, 299 kB model, 10 ms algorithmic latency. The binding
design rule is that weights must fit in on-die SRAM; the moment they spill to external
memory the power budget breaks.

*Open problem:* analog in-memory computation could bring this layer into the harvestable
band (3–15 mW), which would change where the boundary between body and device sits. It
does not close the language-model gap and should not be sold as though it does.
*Discipline:* edge AI, NPU and analog compute.

### L3 · Phone
**Budget:** 1–10 W, **bursty and never continuous**. **Owns:** the local language model.

A 0.5–3B model at 5–20 tokens/s, roughly 0.9 J/token. Sustained load is not available:
under ~500 s of continuous work a phone-class SoC throttles to about half clock. The
design pattern is that L1 and L2 decide *when* L3 is allowed to think.

For a team without capital this layer is free — the person already carries and charges the
device. The honest version of "local LLM" lives here, and nowhere lower.

*Open problem:* an inference schedule driven by conversational state rather than by
request. The model should be spending energy while the partner is still speaking, and idle
the rest of the time.
*Discipline:* on-device inference systems.

### L4 · Cloud
**Budget:** unbounded. **Owns:** large models, long context, heavy multimodal work.

The rule that matters at this boundary: send *compressed meaning*, not raw audio. Speech
carries ~39 bit/s of semantic content, so transmitting meaning rather than waveform is
three to four orders of magnitude cheaper in radio energy — and it is also the only
version of this system that is defensible on privacy grounds, because what leaves the body
is then auditable.

*Open problem:* deciding what may leave the device, on-device, without shipping the thing
being judged in order to judge it.
*Discipline:* privacy-preserving systems.

### The return path
**Owns:** getting information back into the person.

Audio, visual, haptic. Never implanted — see §1. The skin deserves specific attention: it
is the only input channel that does not compete with speech or vision, and it remains free
while the person is listening or looking. Its ceiling is modest (engineered devices manage
5–12 bit/s; the human ceiling for tactile speech is ~22 bit/s) but a warning, a direction
or a single bit of state fits comfortably.

*Open problem:* an encoding that a person can learn in hours rather than months, and that
survives being ignored — most of the time the right output is nothing at all.
*Discipline:* psychophysics, human factors.

---

## 3. Invariants across the whole stack

These hold at every layer. They are not aspirations; where they are implemented, they are
enforced in code and covered by tests.

**Authorship.** Nothing is spoken that the person did not explicitly select. In the
[assist engine](../prototypes/symborg-engine/) this is a signed, single-use,
session-scoped token: `speak()` accepts an authorisation and never a string, and the only
way to mint one is an explicit selection of a candidate that was actually offered.

**Silence is a valid output.** A failure, a low-confidence result, or a badly timed moment
produces nothing. A system that must always answer will interrupt a person at the worst
possible moment, and in a saturated channel that is a net harm.

**Locality by default.** Personal context stays on the device the person controls, in a
form they can read, export and delete without this software.

**No claim the physics does not support.** No content is written into the brain, no thought
is decoded, and no clinical benefit is asserted. These are documented in
[Signal to Response](signal-to-response.md) §7 with the numbers that rule them out.

---

## 4. What is built, and what is open

| | Status |
|---|---|
| Authorship lock, enforced and tested | **Built** |
| Candidate generation, offline-capable, provider-agnostic | **Built** |
| Abbreviation expansion | **Built** |
| Local personal vault | **Built** |
| Turn-end prediction (Turkish) | **In progress** — a 5.8M-parameter model runs faster than real time on a CPU |
| Voice banking and cloning | **Planned** |
| L2 wearable accelerator | **Open** — needs an owner |
| L0 biosignal acquisition under progression | **Open** — needs an owner |
| Learnable haptic return encoding | **Open** — needs an owner |
| On-device egress control | **Open** — needs an owner |
| Clinical evaluation | **Open** — needs a clinical partner |

---

## 5. Open problems, as invitations

The rows marked *open* above are not a roadmap we are quietly working through. They are
problems we cannot solve alone, stated precisely enough to be worth someone's time:

1. **Waking on prediction inside a milliwatt.** The conversational window opens ~200 ms
   after the partner stops speaking. A detector is already too late. *(low-power ML)*
2. **Acquisition that survives progression.** A calibration valid at diagnosis is invalid a
   year later, and the person cannot repeatedly supply training data. *(biomedical
   engineering)*
3. **A haptic code learnable in hours.** Modest bandwidth, but on the only channel that is
   free while the person listens and looks. *(psychophysics)*
4. **Egress decisions made on-device.** Judging what may leave without transmitting the
   thing being judged. *(privacy systems)*
5. **An outcome measure clinicians accept.** Words per minute does not capture whether a
   conversation succeeded; the field says so and has not replaced it. *(rehabilitation
   research, speech-language pathology)*

If one of these is your problem, the code is [Apache 2.0](../LICENSE) and the
[correction template](../.github/ISSUE_TEMPLATE/scientific_correction.md) is open. We
would rather be corrected than admired.

---

## 6. What this is not

This is an architecture, not a product, and not a claim about what exists today. Layers L0
through L2 have no hardware behind them yet — the working system is software running on a
phone or tablet, which is exactly where §1 says the intelligence belongs at this stage.

SYMBORG is a communication aid. It is not a medical device, it does not diagnose or treat,
and every choice is made by the person using it.
