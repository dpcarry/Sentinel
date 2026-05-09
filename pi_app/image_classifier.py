from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image


@dataclass(frozen=True)
class ImageExample:
    image_path: Path
    object_name: str
    location_label: str


@dataclass(frozen=True)
class CentroidClassifier:
    feature_size: int
    object_centroids: dict[str, list[float]]
    location_centroids: dict[str, list[float]]
    examples: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "feature_size": self.feature_size,
            "object_centroids": self.object_centroids,
            "location_centroids": self.location_centroids,
            "examples": self.examples,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CentroidClassifier":
        return cls(
            feature_size=int(data["feature_size"]),
            object_centroids={
                str(label): [float(value) for value in values]
                for label, values in data["object_centroids"].items()
            },
            location_centroids={
                str(label): [float(value) for value in values]
                for label, values in data["location_centroids"].items()
            },
            examples=[
                {
                    "object_name": str(example["object_name"]),
                    "location_label": str(example["location_label"]),
                    "feature": [float(value) for value in example["feature"]],
                }
                for example in data.get("examples", [])
            ],
        )


def train_classifier(examples: list[ImageExample]) -> CentroidClassifier:
    if not examples:
        raise ValueError("At least one training example is required")

    features_by_object: dict[str, list[np.ndarray]] = {}
    features_by_location: dict[str, list[np.ndarray]] = {}
    feature_size = 0
    serialized_examples = []
    for example in examples:
        feature = extract_image_feature(example.image_path)
        feature_size = len(feature)
        features_by_object.setdefault(example.object_name, []).append(feature)
        features_by_location.setdefault(example.location_label, []).append(feature)
        serialized_examples.append(
            {
                "object_name": example.object_name,
                "location_label": example.location_label,
                "feature": [round(float(value), 8) for value in feature],
            }
        )

    return CentroidClassifier(
        feature_size=feature_size,
        object_centroids=_build_centroids(features_by_object),
        location_centroids=_build_centroids(features_by_location),
        examples=serialized_examples,
    )


def classify_image(image_path: Path, model: CentroidClassifier) -> dict:
    feature = extract_image_feature(image_path)
    if model.examples:
        object_name, object_confidence = _nearest_example_label(
            feature, model.examples, "object_name"
        )
        location_label, location_confidence = _nearest_example_label(
            feature, model.examples, "location_label"
        )
    else:
        object_name, object_confidence = _nearest_label(feature, model.object_centroids)
        location_label, location_confidence = _nearest_label(feature, model.location_centroids)
    return {
        "object_name": object_name,
        "location_label": location_label,
        "confidence": min(object_confidence, location_confidence),
        "object_confidence": object_confidence,
        "location_confidence": location_confidence,
        "raw_model_response": "xiao knn classifier",
    }


def evaluate_classifier(
    examples: list[ImageExample], model: CentroidClassifier
) -> tuple[dict[str, float | int], list[dict]]:
    rows = []
    object_correct = 0
    location_correct = 0
    for example in examples:
        result = classify_image(example.image_path, model)
        correct_object = result["object_name"] == example.object_name
        correct_location = result["location_label"] == example.location_label
        object_correct += int(correct_object)
        location_correct += int(correct_location)
        rows.append(
            {
                "image_path": str(example.image_path),
                "expected_object": example.object_name,
                "predicted_object": result["object_name"],
                "expected_location": example.location_label,
                "predicted_location": result["location_label"],
                "object_confidence": result["object_confidence"],
                "location_confidence": result["location_confidence"],
                "correct_object": correct_object,
                "correct_location": correct_location,
            }
        )

    total = len(examples)
    summary = {
        "total": total,
        "object_correct": object_correct,
        "location_correct": location_correct,
        "object_accuracy": round(object_correct / total, 4) if total else 0.0,
        "location_accuracy": round(location_correct / total, 4) if total else 0.0,
    }
    return summary, rows


def evaluate_leave_one_out(
    examples: list[ImageExample],
) -> tuple[dict[str, float | int], list[dict]]:
    rows = []
    object_correct = 0
    location_correct = 0
    for index, example in enumerate(examples):
        training_examples = examples[:index] + examples[index + 1 :]
        if not training_examples:
            raise ValueError("At least two examples are required for leave-one-out")
        model = train_classifier(training_examples)
        result = classify_image(example.image_path, model)
        correct_object = result["object_name"] == example.object_name
        correct_location = result["location_label"] == example.location_label
        object_correct += int(correct_object)
        location_correct += int(correct_location)
        rows.append(
            {
                "image_path": str(example.image_path),
                "expected_object": example.object_name,
                "predicted_object": result["object_name"],
                "expected_location": example.location_label,
                "predicted_location": result["location_label"],
                "object_confidence": result["object_confidence"],
                "location_confidence": result["location_confidence"],
                "correct_object": correct_object,
                "correct_location": correct_location,
                "training_count": len(training_examples),
            }
        )

    total = len(examples)
    summary = {
        "total": total,
        "object_correct": object_correct,
        "location_correct": location_correct,
        "object_accuracy": round(object_correct / total, 4) if total else 0.0,
        "location_accuracy": round(location_correct / total, 4) if total else 0.0,
    }
    return summary, rows


def load_classifier(model_path: Path) -> CentroidClassifier:
    import json

    return CentroidClassifier.from_dict(json.loads(model_path.read_text(encoding="utf-8")))


def extract_image_feature(image_path: Path) -> np.ndarray:
    with Image.open(image_path) as image:
        rgb = image.convert("RGB").resize((32, 32))
    pixels = np.asarray(rgb, dtype=np.float32) / 255.0
    thumbnail = pixels.reshape(-1)
    channel_means = pixels.mean(axis=(0, 1))
    channel_stds = pixels.std(axis=(0, 1))
    histograms = [
        np.histogram(pixels[:, :, channel], bins=8, range=(0.0, 1.0), density=True)[0]
        for channel in range(3)
    ]
    feature = np.concatenate([thumbnail, channel_means, channel_stds, *histograms])
    norm = np.linalg.norm(feature)
    if norm == 0:
        return feature
    return feature / norm


def _build_centroids(grouped_features: dict[str, list[np.ndarray]]) -> dict[str, list[float]]:
    centroids = {}
    for label, features in grouped_features.items():
        centroid = np.mean(np.stack(features), axis=0)
        norm = np.linalg.norm(centroid)
        if norm:
            centroid = centroid / norm
        centroids[label] = [round(float(value), 8) for value in centroid]
    return centroids


def _nearest_label(feature: np.ndarray, centroids: dict[str, list[float]]) -> tuple[str, float]:
    if not centroids:
        return "unknown", 0.0
    distances = []
    for label, centroid_values in centroids.items():
        centroid = np.asarray(centroid_values, dtype=np.float32)
        distance = float(np.linalg.norm(feature - centroid))
        distances.append((label, distance))
    distances.sort(key=lambda item: item[1])
    label, distance = distances[0]
    confidence = 1.0 / (1.0 + distance)
    return label, round(confidence, 4)


def _nearest_example_label(
    feature: np.ndarray, examples: list[dict[str, Any]], label_key: str, k: int = 5
) -> tuple[str, float]:
    distances = []
    for example in examples:
        example_feature = np.asarray(example["feature"], dtype=np.float32)
        distance = float(np.linalg.norm(feature - example_feature))
        distances.append((str(example[label_key]), distance))
    distances.sort(key=lambda item: item[1])
    votes: dict[str, float] = {}
    for label, distance in distances[: max(1, min(k, len(distances)))]:
        votes[label] = votes.get(label, 0.0) + 1.0 / (distance + 1e-6)
    label, score = max(votes.items(), key=lambda item: item[1])
    total_score = sum(votes.values())
    confidence = score / total_score if total_score else 0.0
    return label, round(float(confidence), 4)
