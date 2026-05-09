import json
from pathlib import Path


def aggregate_scene_results(results: list[dict], image_paths: list[Path]) -> dict:
    if not results:
        return {
            "object_name": "unknown",
            "location_label": "unknown",
            "confidence": 0.0,
            "image_path": "",
            "raw_model_response": "empty burst",
        }

    object_name, object_confidence = _weighted_winner(
        results, "object_name", "object_confidence"
    )
    location_label, location_confidence = _weighted_winner(
        results, "location_label", "location_confidence"
    )
    confidence = round(min(object_confidence, location_confidence), 4)

    return {
        "object_name": object_name,
        "location_label": location_label,
        "confidence": confidence,
        "image_path": str(image_paths[0]) if image_paths else "",
        "raw_model_response": json.dumps(
            {
                "method": "burst_weighted_vote",
                "frames": [
                    {"image_path": str(path), "result": result}
                    for path, result in zip(image_paths, results)
                ],
                "object_confidence": object_confidence,
                "location_confidence": location_confidence,
            },
            ensure_ascii=True,
        ),
    }


def _weighted_winner(results: list[dict], label_key: str, confidence_key: str) -> tuple[str, float]:
    scores: dict[str, float] = {}
    counts: dict[str, int] = {}
    for result in results:
        label = str(result.get(label_key) or "unknown")
        confidence = float(result.get(confidence_key, result.get("confidence", 0.0)) or 0.0)
        scores[label] = scores.get(label, 0.0) + confidence
        counts[label] = counts.get(label, 0) + 1

    label = max(scores, key=lambda candidate: (scores[candidate], counts[candidate], candidate))
    average_confidence = scores[label] / counts[label]
    return label, round(average_confidence, 4)
