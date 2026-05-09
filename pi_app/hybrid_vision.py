from pathlib import Path

from pi_app import config
from pi_app.image_classifier import classify_image as classify_location
from pi_app.image_classifier import load_classifier
from pi_app.yolo_vision import (
    classify_image_with_yolo,
    load_model_image_size,
    load_model_names,
)


def default_model_paths() -> dict[str, Path]:
    return {
        "yolo_model_path": config.YOLO_MODEL_PATH,
        "yolo_metadata_path": config.YOLO_METADATA_PATH,
        "classifier_model_path": config.MODEL_DIR / "xiao_classifier" / "classifier.json",
    }


def classify_scene(
    image_path: Path,
    yolo_model_path: Path | None = None,
    yolo_metadata_path: Path | None = None,
    classifier_model_path: Path | None = None,
    input_size: int | tuple[int, int] | None = None,
    force_known_object: bool = False,
) -> dict:
    defaults = default_model_paths()
    yolo_model_path = yolo_model_path or defaults["yolo_model_path"]
    yolo_metadata_path = yolo_metadata_path or defaults["yolo_metadata_path"]
    classifier_model_path = classifier_model_path or defaults["classifier_model_path"]
    class_names = load_model_names(yolo_metadata_path)
    resolved_input_size = input_size or load_model_image_size(yolo_metadata_path)
    location_model = load_classifier(classifier_model_path)
    location_result = classify_location(image_path, location_model)
    object_result = _classify_yolo_with_retries(
        image_path=image_path,
        yolo_model_path=yolo_model_path,
        class_names=class_names,
        input_size=resolved_input_size,
    )
    object_name = object_result["object_name"]
    object_confidence = object_result["confidence"]
    object_source = "yolo"
    forced_object = False
    if force_known_object and object_name == "unknown":
        object_name = location_result["object_name"]
        object_confidence = location_result["object_confidence"]
        object_source = "classifier_fallback"
        forced_object = True

    return {
        "object_name": object_name,
        "location_label": location_result["location_label"],
        "object_confidence": object_confidence,
        "location_confidence": location_result["location_confidence"],
        "method": "yolo_object_plus_classifier_location",
        "object_source": object_source,
        "forced_object": forced_object,
        "raw_object_response": object_result["raw_model_response"],
        "raw_location_response": location_result.get("raw_model_response", ""),
    }


def _classify_yolo_with_retries(
    image_path: Path,
    yolo_model_path: Path,
    class_names: list[str],
    input_size: int | tuple[int, int],
) -> dict:
    errors = []
    for candidate in _candidate_input_sizes(input_size):
        try:
            return classify_image_with_yolo(
                image_path,
                model_name=str(yolo_model_path),
                class_names=class_names,
                input_size=candidate,
            )
        except Exception as exc:
            errors.append(f"{candidate}: {exc}")

    return {
        "object_name": "unknown",
        "location_label": "unknown",
        "confidence": 0.0,
        "raw_model_response": "yolo failed: " + " | ".join(errors),
    }


def _candidate_input_sizes(image_size: int | tuple[int, int]) -> list[int | tuple[int, int]]:
    if isinstance(image_size, int):
        return [image_size]

    width, height = image_size
    aligned_height = _ceil_to_multiple(height, 32)
    aligned_width = _ceil_to_multiple(width, 32)
    if aligned_width != width or aligned_height != height:
        candidates: list[int | tuple[int, int]] = [(aligned_width, aligned_height)]
    else:
        candidates = [(width, height)]
    if aligned_height != height and aligned_width == width:
        candidates.append((width, aligned_height))
    if aligned_width != width and aligned_height == height:
        candidates.append((aligned_width, height))
    if aligned_width != width or aligned_height != height:
        candidates.append((width, height))
    return list(dict.fromkeys(candidates))


def _ceil_to_multiple(value: int, multiple: int) -> int:
    return ((value + multiple - 1) // multiple) * multiple
