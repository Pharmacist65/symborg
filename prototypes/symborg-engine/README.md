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
latency is a clinical property here, not an implementation detail. Natural conversation
leaves roughly 200 ms between turns; a correct sentence that arrives after the
conversation has moved on has failed.

## Status

Research software. Not a medical device. It does not diagnose or treat, and makes no
clinical claims. See [NOTICE.md](../../NOTICE.md).
