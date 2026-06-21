# SYMBORG Live Demo

This prototype connects the repository's two working layers into one browser demo:

```text
Transcript -> Cognitive Packet Engine -> Quality Gate -> Output Router -> UI
```

It is intentionally dependency-free. The server uses Python's standard library and imports the local `contextual-whisper-demo` and `output-router-demo` packages directly from the repository.

## Run

From the repository root:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 prototypes/symborg-live-demo/server.py
```

Open:

```text
http://127.0.0.1:8765
```

## API

```bash
curl -sS -X POST http://127.0.0.1:8765/api/analyze \
  -H 'Content-Type: application/json' \
  -d '{"scenario":"dickens","pause_ms":900,"delivery":"screen"}'
```

## What It Demonstrates

- Context detection from a short transcript
- Ranked cognitive packet generation
- Conservative delivery gating based on pause, load, silence, and speech state
- Device-aware routing across screen, audio, AR, haptic, assistive, and neural-research simulation outputs
- A portfolio-grade interface that shows the actual decision chain without claiming clinical validation

## Tests

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover prototypes/symborg-live-demo/tests
```
