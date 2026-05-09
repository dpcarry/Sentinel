from pathlib import Path

import numpy as np
import yaml


BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_YOLO_MODEL = BASE_DIR / "models" / "yolov5n.onnx"

COCO_NAMES = [
    "person",
    "bicycle",
    "car",
    "motorcycle",
    "airplane",
    "bus",
    "train",
    "truck",
    "boat",
    "traffic light",
    "fire hydrant",
    "stop sign",
    "parking meter",
    "bench",
    "bird",
    "cat",
    "dog",
    "horse",
    "sheep",
    "cow",
    "elephant",
    "bear",
    "zebra",
    "giraffe",
    "backpack",
    "umbrella",
    "handbag",
    "tie",
    "suitcase",
    "frisbee",
    "skis",
    "snowboard",
    "sports ball",
    "kite",
    "baseball bat",
    "baseball glove",
    "skateboard",
    "surfboard",
    "tennis racket",
    "bottle",
    "wine glass",
    "cup",
    "fork",
    "knife",
    "spoon",
    "bowl",
    "banana",
    "apple",
    "sandwich",
    "orange",
    "broccoli",
    "carrot",
    "hot dog",
    "pizza",
    "donut",
    "cake",
    "chair",
    "couch",
    "potted plant",
    "bed",
    "dining table",
    "toilet",
    "tv",
    "laptop",
    "mouse",
    "remote",
    "keyboard",
    "cell phone",
    "microwave",
    "oven",
    "toaster",
    "sink",
    "refrigerator",
    "book",
    "clock",
    "vase",
    "scissors",
    "teddy bear",
    "hair drier",
    "toothbrush",
]


YOLO_OBJECT_ALIASES = {
    "airpods": "airpods",
    "cell phone": "phone",
    "mobile phone": "phone",
    "phone": "phone",
    "wallet": "wallet",
}


def classify_yolo_detections(detections: list[dict]) -> dict:
    candidates = []
    for detection in detections:
        object_name = YOLO_OBJECT_ALIASES.get(str(detection.get("name", "")).lower())
        if not object_name:
            continue
        candidates.append(
            {
                "object_name": object_name,
                "location_label": "unknown",
                "confidence": float(detection.get("confidence", 0.0)),
            }
        )

    if not candidates:
        return {
            "object_name": "unknown",
            "location_label": "unknown",
            "confidence": 0.0,
            "raw_model_response": str(detections),
        }

    best = max(candidates, key=lambda candidate: candidate["confidence"])
    best["raw_model_response"] = str(detections)
    return best


def load_model_names(metadata_path: Path) -> list[str]:
    metadata = yaml.safe_load(metadata_path.read_text(encoding="utf-8")) or {}
    names = metadata.get("names", [])
    if isinstance(names, dict):
        return [str(names[index]) for index in sorted(names, key=lambda value: int(value))]
    return [str(name) for name in names]


def load_model_image_size(metadata_path: Path) -> int | tuple[int, int]:
    metadata = yaml.safe_load(metadata_path.read_text(encoding="utf-8")) or {}
    image_size = metadata.get("image_size", 640)
    if isinstance(image_size, list):
        if len(image_size) != 2:
            raise ValueError(f"Expected image_size list of length 2, got {image_size}")
        return int(image_size[0]), int(image_size[1])
    return int(image_size)


def classify_image_with_yolo(
    image_path: Path,
    model_name: str = "yolov8n.pt",
    class_names: list[str] | None = None,
    input_size: int | tuple[int, int] = 640,
) -> dict:
    model_path = Path(model_name)
    if model_name == "yolov8n.pt":
        model_path = DEFAULT_YOLO_MODEL
    if not model_path.exists():
        raise FileNotFoundError(f"Missing YOLO model: {model_path}")

    detections = detect_with_yolov5_onnx(
        image_path, model_path, class_names=class_names, input_size=input_size
    )
    return classify_yolo_detections(detections)


def detect_with_yolov5_onnx(
    image_path: Path,
    model_path: Path = DEFAULT_YOLO_MODEL,
    class_names: list[str] | None = None,
    confidence_threshold: float = 0.25,
    nms_threshold: float = 0.45,
    input_size: int | tuple[int, int] = 640,
) -> list[dict]:
    import cv2

    image = cv2.imread(str(image_path))
    if image is None:
        raise FileNotFoundError(f"Could not read image: {image_path}")
    class_names = class_names or COCO_NAMES

    if isinstance(input_size, tuple):
        blob, scale_x, scale_y, pad_x, pad_y = _resize_blob(image, input_size)
    else:
        blob, scale, pad_x, pad_y = _letterbox_blob(image, input_size)
        scale_x = scale
        scale_y = scale
    net = cv2.dnn.readNetFromONNX(str(model_path))
    net.setInput(blob)
    output = net.forward()
    predictions = normalize_yolo_output(output, class_count=len(class_names))

    boxes = []
    confidences = []
    class_ids = []
    for prediction in predictions:
        if len(prediction) == len(class_names) + 4:
            objectness = 1.0
            class_scores = prediction[4:]
        else:
            objectness = float(prediction[4])
            class_scores = prediction[5:]
        class_id = int(np.argmax(class_scores))
        confidence = objectness * float(class_scores[class_id])
        if confidence < confidence_threshold:
            continue
        if class_id >= len(class_names):
            continue

        center_x, center_y, width, height = prediction[:4]
        x = int((center_x - width / 2 - pad_x) / scale_x)
        y = int((center_y - height / 2 - pad_y) / scale_y)
        w = int(width / scale_x)
        h = int(height / scale_y)
        boxes.append([x, y, w, h])
        confidences.append(confidence)
        class_ids.append(class_id)

    keep = cv2.dnn.NMSBoxes(boxes, confidences, confidence_threshold, nms_threshold)
    detections = []
    for index in np.array(keep).flatten() if len(keep) else []:
        detections.append(
            {
                "name": class_names[class_ids[index]],
                "confidence": round(float(confidences[index]), 4),
                "box": boxes[index],
            }
        )
    return detections


def normalize_yolo_output(output: np.ndarray, class_count: int) -> np.ndarray:
    predictions = np.squeeze(output)
    if predictions.ndim != 2:
        raise ValueError(f"Expected 2D YOLO output after squeeze, got {predictions.shape}")
    if predictions.shape[0] == class_count + 4:
        return predictions.T
    return predictions


def _letterbox_blob(image: np.ndarray, input_size: int) -> tuple[np.ndarray, float, int, int]:
    import cv2

    height, width = image.shape[:2]
    scale = min(input_size / width, input_size / height)
    resized_width = int(round(width * scale))
    resized_height = int(round(height * scale))
    resized = cv2.resize(image, (resized_width, resized_height), interpolation=cv2.INTER_LINEAR)

    canvas = np.full((input_size, input_size, 3), 114, dtype=np.uint8)
    pad_x = (input_size - resized_width) // 2
    pad_y = (input_size - resized_height) // 2
    canvas[pad_y : pad_y + resized_height, pad_x : pad_x + resized_width] = resized
    blob = cv2.dnn.blobFromImage(canvas, 1 / 255.0, (input_size, input_size), swapRB=True)
    return blob, scale, pad_x, pad_y


def _resize_blob(
    image: np.ndarray, input_size: tuple[int, int]
) -> tuple[np.ndarray, float, float, int, int]:
    import cv2

    input_width, input_height = input_size
    height, width = image.shape[:2]
    resized = cv2.resize(image, (input_width, input_height), interpolation=cv2.INTER_LINEAR)
    blob = cv2.dnn.blobFromImage(
        resized, 1 / 255.0, (input_width, input_height), swapRB=True
    )
    return blob, input_width / width, input_height / height, 0, 0
