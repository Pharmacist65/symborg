# Output Router Visuals

These diagrams describe how SYMBORG returns cognitive packets to the user after packet generation and evaluation.

## Symbiotic Return Stack

```mermaid
flowchart TD
    A["Real-world context"] --> B["Context Engine"]
    B --> C["Retrieval Engine"]
    C --> D["Cognitive Packet Engine"]
    D --> E["Quality Scoring"]
    E --> F["Delivery Gate"]
    F --> G["Output Policy Engine"]
    G --> H["Modality Router"]
    H --> I["Haptic cue"]
    H --> J["Audio whisper"]
    H --> K["AR peripheral card"]
    H --> L["Phone / screen card"]
    H --> M["Assistive sentence candidate"]
    H --> N["Future neural-write research glyph"]
    I --> O["Human attention / perception"]
    J --> O
    K --> O
    L --> O
    M --> O
    N --> O
```

## Device Family Roadmap

```mermaid
flowchart LR
    A["SYMBORG App<br/>screen cards"] --> B["SYMBORG Ear<br/>audio whisper"]
    B --> C["SYMBORG Ring<br/>haptic control"]
    C --> D["SYMBORG Glass<br/>AR peripheral cards"]
    D --> E["SYMBORG Band<br/>load-aware delivery"]
    E --> F["SYMBORG Assist<br/>candidate selection"]
    F --> G["SYMBORG Neural<br/>future research layer"]
```

## Output Routing Decision

```mermaid
flowchart TD
    A["Cognitive packet"] --> B{"Silence mode?"}
    B -- yes --> Z["Suppress"]
    B -- no --> C{"User speaking?"}
    C -- yes --> D{"Warning or assistive status?"}
    D -- yes --> E["Haptic status only"]
    D -- no --> Z
    C -- no --> F{"Driving?"}
    F -- yes --> G{"Urgent warning/navigation?"}
    G -- yes --> E
    G -- no --> Z
    F -- no --> H{"Low confidence?"}
    H -- yes --> Z
    H -- no --> I{"Assistive mode?"}
    I -- yes --> J["Assistive candidate UI"]
    I -- no --> K{"Walking?"}
    K -- yes --> L["Audio whisper or haptic prompt"]
    K -- no --> M{"Short visual cue?"}
    M -- yes --> N["AR peripheral card"]
    M -- no --> O["Screen card fallback"]
```

## Design Note

The neural-write branch is intentionally framed as a future research track. It is not an early consumer feature and should not be presented as high-resolution internal display technology.

