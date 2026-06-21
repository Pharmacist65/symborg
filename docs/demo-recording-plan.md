# Demo Recording Plan

Use this plan to record a short, credible demo for LinkedIn, X, or a portfolio page. Keep the tone calm and technical. The goal is to show a working system, not to make a science-fiction pitch.

## Setup

Run the live demo from the repository root:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 prototypes/symborg-live-demo/server.py
```

Open:

```text
http://127.0.0.1:8765
```

Recommended recording format:

- 16:9 desktop capture
- 60 to 90 seconds
- No browser bookmarks or personal tabs in frame
- Zoom at 100 percent
- Show the repository link only at the end

## 75-Second Structure

### 0-6 seconds: Title

On-screen:

```text
SYMBORG
Cognitive Packet Pipeline
```

Voiceover:

```text
SYMBORG is a prototype for a cognitive front-end layer between AI retrieval and human attention.
```

### 6-22 seconds: Context To Packet

Action:

- Show the Dickens transcript.
- Click **Run Pipeline**.
- Let the packet list appear.

Voiceover:

```text
Instead of returning a long answer, the system generates short cognitive packets: questions, anchors, or counterpoints that fit into working memory.
```

### 22-38 seconds: Quality And Route

Action:

- Point to score, gate, and route panels.
- Change delivery between screen and audio/AR/haptic if useful.

Voiceover:

```text
Each packet is scored for brevity, actionability, confidence, interruption risk, and cognitive load. Then the router chooses the safest available output surface.
```

### 38-58 seconds: Assistive Scenario

Action:

- Click **Assistive**.
- Show sentence candidates and assistive route.

Voiceover:

```text
The strongest serious use case is assistive communication: generating selectable sentence candidates for a user with limited input, while preserving confirmation and agency.
```

### 58-68 seconds: Restraint

Action:

- Toggle **Speaking** or use a long-press signal.
- Show suppressed output.

Voiceover:

```text
The system is designed to stay silent when interruption would be worse than help.
```

### 68-75 seconds: Close

On-screen:

```text
github.com/Pharmacist65/symborg
```

Voiceover:

```text
I am looking for critique from people working on HCI, wearable AI, accessibility, assistive communication, and neurotechnology ethics.
```

## Caption Copy

```text
SYMBORG live demo:
Transcript -> cognitive packets -> quality gate -> output route.

The goal is not to make AI louder.
The goal is to return less information, at the right moment, in a form human attention can actually use.
```

## What To Avoid

- Do not say "mind reading."
- Do not say "knowledge upload."
- Do not say "the next Neuralink."
- Do not imply clinical validation.
- Do not ask for funding in the post.
- Do not show private browser tabs, personal accounts, or unrelated desktop windows.

## Best Demo Order

1. Dickens scenario for the general cognitive packet idea.
2. Assistive scenario for seriousness and social value.
3. Speaking/silence state for restraint.
4. Repository link and collaboration ask.
