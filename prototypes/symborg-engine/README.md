# SYMBORG Assist Engine

Context-aware sentence candidates for people who cannot speak.

The engine listens to the conversation around a person, generates a few complete
sentences they might want to say, and speaks the one they select — in their own banked
voice. It never speaks anything they did not explicitly choose.

Built against [`docs/engine-implementation-spec.md`](../../docs/engine-implementation-spec.md).

## Quick start

No API key, no network, no optional dependencies required:

```bash
cd prototypes/symborg-engine
PYTHONPATH=src python3 -c "
from symborg_engine import Session
s = Session()
s.hear('Ağrın var mı?')
for i, c in enumerate(s.offer().candidates):
    print(i, c.text)
token = s.select(0)          # the person chooses — the only path to speech
print('spoken:', s.speak(token).utterance.text)
"
```

Run the tests:

```bash
PYTHONPATH=src python3 -m unittest discover tests
```

## The authorship invariant

> Nothing is ever spoken that the person did not explicitly select.

Putting words in the mouth of someone who cannot contradict you is the central ethical
risk of this product category, so the guarantee is enforced in code rather than in a
guideline:

- `Session.speak()` accepts a `SpeechAuthorization`, never a string.
- A token can only be minted by `Session.select()`, on a candidate the engine actually
  offered.
- Tokens are signed, single-use, session-scoped, bound to one sentence, and expire.
- Every spoken utterance is logged as `user_confirmed`, so generated text and chosen
  text are always separable after the fact.

`tests/test_authorship.py` attacks this invariant from every angle we could think of —
forged tokens, replayed tokens, swapped text, cross-session tokens, indices that were
never offered. If any of those tests fail, the product is unsafe.

## Design

| Module | Responsibility |
|---|---|
| `authorship.py` | The lock: minting, verifying and redeeming speech authorisations |
| `candidate.py` | Immutable candidates and the record of what was offered |
| `session.py` | The loop: hear → offer → select → speak → learn, with timings |
| `providers/` | Protocols for ASR, LLM and TTS, plus deterministic offline defaults |
| `context/transcript.py` | Bounded rolling transcript |
| `context/vault.py` | Local, user-owned personal context |
| `generate/` | Candidate generation, abbreviation expansion, prompts and filtering |

Three decisions worth knowing:

**Providers are protocols.** The core imports nothing outside the standard library, so
a missing optional dependency can never break an import, and swapping a model never
touches engine logic.

**The offline provider is not a stub.** It is deterministic and returns the same JSON
shape a hosted model does, so tests are hermetic, CI needs no secrets, and the offline
path exercises exactly the same parsing code as the real one.

**Silence is a valid output.** A provider failure or an unusable response yields an
empty offer marked `degraded` — never an invented sentence.

## Using a real model

The engine is vendor-neutral by construction: which company supplies the model is
configuration, not code. Install the extra for whichever you use and set its key in
your environment — never in a file, and never in a prompt.

```bash
pip install '.[openai]'      # or '.[anthropic]', or '.[all]'
export OPENAI_API_KEY=...    # or ANTHROPIC_API_KEY
```

| Variable | Purpose |
|---|---|
| `SYMBORG_LLM_PROVIDER` | `offline` \| `anthropic` \| `openai` — optional; auto-detected from the keys present |
| `SYMBORG_LLM_MODEL` | override the model id |
| `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` | credentials, read from the environment only |

To check what the engine will actually use — without printing your key:

```bash
PYTHONPATH=src python3 -m symborg_engine.doctor
```

The same code path runs against any of them; swapping providers touches no engine
logic. With no key set the engine falls back to the offline provider with a warning —
it never fails, and it never quietly sends data anywhere.

## Latency

`OfferResult.latency_ms` and `SpeakResult.latency_ms` are part of the API because
latency is a product property here, not an implementation detail. Natural conversation
leaves roughly 200 ms between turns; a correct sentence that arrives after the
conversation has moved on has failed.

Measured, generating three Turkish candidates against a hosted model:

| Configuration | Median |
|---|---:|
| Budget (delay starts being noticed) | 500 ms |
| Fastest measured configuration | ~1,180 ms |
| Current defaults | ~1,370 ms |
| Larger token budget, larger model, or a slower tier | 1,800–2,900 ms |

Every configuration converges near the same floor. Model choice, token budget,
constrained decoding and the faster service tier move it by a few hundred
milliseconds each — none of them reach the budget, and the fastest possible hosted
call is still more than twice too slow.

**The conclusion is architectural, and it is why this project exists.** You do not
close this gap by answering faster. You close it by starting earlier: predicting when
the other person is about to finish and generating during their last words, so the
candidates are already waiting when the turn arrives. That predictor — deciding *when*,
not *what* — is the layer this project is actually building.

Reproduce with `PYTHONPATH=src python3 bench/latency.py` (costs a few API calls).

## Turn-end prediction

The predictor is built, and it does what the architecture claimed. Measured on the same
hardware and the same hosted model, playing one Turkish turn as five fragments at
conversational pace:

| | Lead time | What the person waits |
|---|---:|---:|
| Wait for silence (what every system does) | — | **2,166 ms** |
| Predict the turn end and generate during it | 700 ms | **0 ms** |

The call still took its 1.4 seconds. It happened behind the speaker's last two
fragments, so nobody waited for it.

Turkish makes this unusually tractable: the language is verb-final and agglutinative, so
tense, mood and person arrive as suffixes on the last word. Hearing *"gidiyorum"* tells
you the clause has closed — a signal a speaker of an SVO language does not get. The
first predictor reads those suffix shapes directly: no model, no network, no latency.
See `symborg_engine/turntaking/turkish.py`, whose known failure modes are documented in
the code rather than hidden.

```python
session = Session()
for fragment in incoming_speech:
    if session.hear_partial(fragment).fired:
        pass                    # generation has already started
result = session.offer()        # returns immediately; result.speculative is True
```

### How good is the predictor

`eval/turn_end.py` scores it on the two errors that cost something, which are not
symmetric: a **miss** loses the turn to full latency, while an **early fire** wastes one
API call. The threshold sits where that asymmetry puts it, not at balanced accuracy.

On the 36-turn development set, after handling the failure classes it exposed:

| | On time | Early | Missed |
|---|---:|---:|---:|
| Wait for silence | 0% | 0% | **100%** |
| Turkish morphology | **97%** | 0% | 3% |

**That 97% is not a performance claim, and it must not be quoted as one.** The set is
hand-authored, and the predictor was tuned against it until the number stopped moving.
It is a regression harness: it catches breakage and documents known failure classes.
Real evaluation needs recorded two-party Turkish conversation with timing, which is
separate work.

What the loop was actually worth is the failure classes it surfaced, each a real
property of the language rather than a quirk of the data:

- **Verbless predicates.** `Bugün hava çok güzel` — Turkish needs no verb, so there is
  no suffix to read. The largest structural gap, and the clearest argument for a
  learned model over a suffix reader.
- **Bare imperatives.** `Doktoru ara` carries no suffix at all and is still complete.
- **Inflected negative copula.** `değilim` is not `değil` plus a verb ending.
- **Hedges that look finite.** `Sanırım` is a first-person aorist, but a speaker who
  has said only that word is opening a thought, not closing one.
- **Correlatives.** `Hem … hem de …` closes a clause while the turn continues.
- **A correction the measurement forced.** Treating `ne` as a correlative suppressed
  genuine question endings; it cost more than it saved and was removed.

## Status

Research software. Not a medical device. It does not diagnose or treat, and makes no
clinical claims. See [NOTICE.md](../../NOTICE.md).
