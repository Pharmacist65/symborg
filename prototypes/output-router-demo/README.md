# SYMBORG Output Router Demo

A tiny prototype that routes cognitive packets to the most appropriate output modality.

This is not a device driver. It is a decision model for the SYMBORG Feedback and Output Layer.

## Run

```bash
PYTHONPATH=src python -m symborg_output_router.router examples/packets.json
```

## Test

```bash
PYTHONPATH=src python -m unittest discover tests
```

## Concept

```text
packet + user state + device capabilities
        |
        v
output router
        |
        v
route decision
```

The router can choose:

- `suppress`
- `haptic`
- `audio_whisper`
- `ar_card`
- `screen_card`
- `assistive_candidate`
- `neural_research_glyph`

It is intentionally conservative. It suppresses output when the user is speaking, the cue is too long, risk is too high, or silence mode is active.
