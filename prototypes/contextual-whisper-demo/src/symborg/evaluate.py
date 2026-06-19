from __future__ import annotations

import argparse
import json
from pathlib import Path
from statistics import mean

from .context import InteractionState
from .heuristic_engine import generate_packets


def load_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        rows.append(json.loads(line))
    return rows


def evaluate_fixture(row: dict) -> dict:
    state_data = row.get("state", {})
    state = InteractionState(
        user_is_speaking=state_data.get("user_is_speaking", False),
        pause_ms=state_data.get("pause_ms", 900),
        user_signal=state_data.get("user_signal", "none"),
        delivery=state_data.get("delivery", "screen"),
        cognitive_load_estimate=state_data.get("cognitive_load_estimate", 0.35),
        max_packets=state_data.get("max_packets", 3),
    )
    result = generate_packets(row["context"], state=state, min_score=row.get("min_score", 0.65))
    delivered = result["delivered"]
    scores = [item["score"]["total_score"] for item in delivered]
    expected_topic = row.get("expected_topic")
    passed = True
    failures: list[str] = []

    if expected_topic and result["topic"] != expected_topic:
        passed = False
        failures.append(f"topic_mismatch: expected={expected_topic}, got={result['topic']}")

    min_delivered = row.get("min_delivered", 1)
    if len(delivered) < min_delivered:
        passed = False
        failures.append(f"too_few_delivered: expected_at_least={min_delivered}, got={len(delivered)}")

    if row.get("expect_suppressed", False) and delivered:
        passed = False
        failures.append("expected_suppression_but_packets_delivered")

    min_mean_score = row.get("min_mean_score")
    if min_mean_score is not None and scores and mean(scores) < min_mean_score:
        passed = False
        failures.append(f"mean_score_below_target: target={min_mean_score}, got={round(mean(scores), 3)}")

    return {
        "id": row.get("id", "unknown"),
        "passed": passed,
        "failures": failures,
        "topic": result["topic"],
        "delivered_count": len(delivered),
        "mean_delivered_score": round(mean(scores), 3) if scores else 0.0,
        "best_cue": delivered[0]["packet"]["cue"] if delivered else None,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate SYMBORG fixtures.")
    parser.add_argument("fixtures", type=Path, help="Path to JSONL fixtures.")
    args = parser.parse_args()

    rows = load_jsonl(args.fixtures)
    results = [evaluate_fixture(row) for row in rows]
    passed = sum(1 for r in results if r["passed"])
    summary = {
        "fixture_count": len(results),
        "passed": passed,
        "failed": len(results) - passed,
        "results": results,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if summary["failed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
