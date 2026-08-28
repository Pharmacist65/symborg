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
PYTHONPATH=src python3 -m unittest discover -t . -s tests
```

The suite runs offline: `tests/__init__.py` clears provider credentials so a key in
your shell cannot turn a unit run into a paid integration run. The `-t .` matters —
without it discovery imports the test modules as top-level modules, the package
initialiser never runs, and the tests quietly start calling the network. To exercise
the real providers on purpose, set `SYMBORG_TEST_LIVE=1`.

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

## The interface

Until now candidates were selected by typing an index into Python, which is adequate
for a pipeline and useless for the person the pipeline exists for.

```bash
PYTHONPATH=src python3 -m symborg_engine.ui.server
```

Then open `http://127.0.0.1:8770`. It listens, shows what it heard, and presents the
candidates large and high-contrast. Selection works three ways, because a person may
have very little movement available:

| Input | |
|---|---|
| Click or tap | direct |
| <kbd>1</kbd> <kbd>2</kbd> <kbd>3</kbd> | direct |
| <kbd>space</kbd> then <kbd>enter</kbd> | **single-switch scanning** — space moves the highlight, enter commits |

The last row is the one that matters: most access switches emulate exactly those two
keys, so a person with one reliable movement can drive the whole thing.

Standard library only — no framework, no build step, and it binds to localhost.

**The authorship lock holds across the network boundary too**, which is where an
invariant most easily stops holding. Selecting an index that was never offered returns
409, and a selection cannot be replayed. `tests/test_ui.py` checks that from outside the
process rather than trusting it from within.

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

### Live audio

Speech capture, streaming recognition and voice-activity detection are solved
engineering, so the engine adopts them rather than rebuilding them. The transcript
source sits behind one protocol; the OpenAI Realtime API is one implementation of it.

```bash
pip install '.[realtime]'
```

```python
from symborg_engine import Session, drive
from symborg_engine.providers.realtime_stream import MicrophoneSource, RealtimeTranscriptStream

session = Session()
with MicrophoneSource() as mic:
    drive(session, RealtimeTranscriptStream(mic.blocks()),
          on_turn=lambda t: print(t.lead_ms, [c.text for c in t.result.candidates]))
```

It runs a **transcription-only** session: the model listens and never replies. SYMBORG
is not a participant in the conversation — it prepares options for one.

The configuration was arrived at by probing the live API, because the documentation
does not make the constraint obvious. A transcription session is opened by `intent`
rather than by naming a model in the handshake; `gpt-live-transcribe` is the model that
streams deltas while someone is still speaking; and it does not accept server-side turn
detection. The models that do accept turn detection returned nothing until the buffer
was committed — which would remove the only thing that makes anticipation possible. So
turn boundaries are decided here instead, which is where they belong.

Verified end to end against a real microphone: two turns, gate committing mid-sentence,
median lead 3,543 ms, candidates waiting when each turn ended.

That run also exposed the real cost of committing early, which was not what had been
assumed. The gate fired on *"Ağrın var"* and the speaker continued *"…mı? Doktoru
çağırmamı ister misin?"* — so the candidates answered a question that was never asked.
An early fire does not cost a wasted API call. It costs **a wrong sentence, offered to
someone who cannot easily correct it**, which is much worse and worth a second call to
avoid.

So speculation is now refreshed when the turn materially outgrows it (`stale_after_words`,
default 3). Small continuations are ignored, because regenerating on every word would
make the options flicker while the person is trying to read them. With the refresh in
place the same audio produces candidates that answer both halves of the question.

**What that API does not supply is anticipation, and this is the reason the predictor
still exists.** Every turn-boundary event it emits fires after silence has been
observed, and the speech-stopped event includes the silence window by construction. The
classifier that scores whether a speaker has finished is consumed internally to set a
timeout and is never exposed. What the API does give — transcript deltas arriving while
the partner is still speaking — is exactly what the predictor needs to run on.

There is a second reason, and it is the one that matters more in use. Since deltas
arrive continuously, a system could simply regenerate on every one and always hold
fresh candidates. But then the options on screen keep changing while the person is
trying to read them — and this is a person who may read slowly and select with a single
switch. The predictor's real job is to say *commit now, stop changing*. It is less a
latency optimisation than a legibility guarantee.

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
