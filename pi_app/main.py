import json
import os
import time
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, File, Request, UploadFile
from pydantic import BaseModel

from pi_app.burst import aggregate_scene_results
from pi_app import config
from pi_app.hybrid_vision import classify_scene
from pi_app.query import extract_target_object
from pi_app.speech import speak, transcribe_audio
from pi_app.storage import SentinalStore

app = FastAPI(title="Sentinal")
store = SentinalStore(config.DB_PATH)
pending_bursts: dict[str, dict] = {}
auto_burst: dict | None = None
auto_burst_sequence = 0
AUTO_BURST_TOTAL = 3
AUTO_BURST_TIMEOUT_SECONDS = 8.0


class TextQueryRequest(BaseModel):
    transcript: str


@app.on_event("startup")
def startup() -> None:
    global auto_burst, auto_burst_sequence
    config.IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    config.AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    store.initialize()
    pending_bursts.clear()
    auto_burst = None
    auto_burst_sequence = 0


@app.get("/health")
def health() -> dict:
    return {"ok": True, "service": "sentinal-pi"}


@app.post("/upload-image")
async def upload_image(file: UploadFile = File(...)) -> dict:
    config.IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    suffix = Path(file.filename or "image.jpg").suffix or ".jpg"
    path = config.IMAGE_DIR / f"{uuid4().hex}{suffix}"
    path.write_bytes(file.file.read())
    return process_uploaded_image(path, file.filename or path.name)


@app.post("/upload-image-burst")
async def upload_image_burst(files: list[UploadFile] = File(...)) -> dict:
    config.IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    paths = []
    for file in files:
        suffix = Path(file.filename or "image.jpg").suffix or ".jpg"
        path = config.IMAGE_DIR / f"{uuid4().hex}{suffix}"
        path.write_bytes(file.file.read())
        paths.append(path)
    return process_uploaded_burst(paths)


@app.post("/upload_image")
async def upload_image_raw(request: Request) -> dict:
    data = await request.body()
    if not data:
        return {"ok": False, "error": "No image received"}
    config.IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    path = config.IMAGE_DIR / f"{uuid4().hex}.jpg"
    path.write_bytes(data)
    burst_id = request.query_params.get("burst_id")
    if burst_id:
        return process_uploaded_burst_frame(
            path,
            burst_id=burst_id,
            frame=int(request.query_params.get("frame", "1")),
            total=int(request.query_params.get("total", "3")),
        )
    return process_uploaded_auto_burst_frame(path)


def process_uploaded_image(path: Path, original_filename: str) -> dict:
    result = classify_uploaded_image(path)
    if result["object_name"] == "unknown":
        result = _fallback_to_upload_filename(result, original_filename)
    event = store.record_event(
        object_name=result["object_name"],
        location_label=result["location_label"],
        confidence=result["confidence"],
        image_path=str(path),
        raw_model_response=result["raw_model_response"],
        source="upload",
    )
    log_event("vision", f"{event['object_name']} on {event['location_label']} saved to SQL event {event['id']}")
    return {"ok": True, "image_path": str(path), "event": event}


def process_uploaded_burst_frame(path: Path, burst_id: str, frame: int, total: int) -> dict:
    log_event("image", f"burst {burst_id} frame {frame}/{total} received")
    burst = pending_bursts.setdefault(burst_id, {"total": total, "frames": {}})
    burst["total"] = total
    burst["frames"][frame] = path
    received = len(burst["frames"])
    if received < total:
        return {
            "ok": True,
            "status": "pending",
            "burst_id": burst_id,
            "received": received,
            "total": total,
        }

    frames = [burst["frames"][index] for index in sorted(burst["frames"])]
    pending_bursts.pop(burst_id, None)
    body = process_uploaded_burst(frames)
    body["status"] = "complete"
    body["burst_id"] = burst_id
    return body


def process_uploaded_auto_burst_frame(path: Path) -> dict:
    global auto_burst, auto_burst_sequence
    now = current_monotonic()
    if auto_burst is not None and now - auto_burst["started_at"] > AUTO_BURST_TIMEOUT_SECONDS:
        log_event(
            "image",
            f"auto burst {auto_burst['burst_id']} timed out; "
            f"discarded {len(auto_burst['frames'])} frame(s)",
        )
        auto_burst = None

    if auto_burst is None:
        auto_burst_sequence += 1
        auto_burst = {
            "burst_id": f"auto-{auto_burst_sequence}",
            "started_at": now,
            "frames": [],
        }

    auto_burst["frames"].append(path)
    received = len(auto_burst["frames"])
    burst_id = auto_burst["burst_id"]
    log_event("image", f"auto burst {burst_id} frame {received}/{AUTO_BURST_TOTAL} received")
    if received < AUTO_BURST_TOTAL:
        return {
            "ok": True,
            "status": "pending",
            "burst_id": burst_id,
            "received": received,
            "total": AUTO_BURST_TOTAL,
        }

    frames = list(auto_burst["frames"])
    auto_burst = None
    body = process_uploaded_burst(frames)
    body["status"] = "complete"
    body["burst_id"] = burst_id
    return body


def process_uploaded_burst(paths: list[Path]) -> dict:
    scene_results = [classify_uploaded_scene(path) for path in paths]
    result = aggregate_scene_results(scene_results, paths)
    event = store.record_event(
        object_name=result["object_name"],
        location_label=result["location_label"],
        confidence=result["confidence"],
        image_path=result["image_path"],
        raw_model_response=result["raw_model_response"],
        source="upload_burst",
    )
    log_event("vision", f"{event['object_name']} on {event['location_label']} saved to SQL event {event['id']}")
    return {"ok": True, "image_paths": [str(path) for path in paths], "event": event}


@app.post("/upload-audio")
async def upload_audio(file: UploadFile = File(...)) -> dict:
    config.AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    suffix = Path(file.filename or "query.wav").suffix or ".wav"
    path = config.AUDIO_DIR / f"{uuid4().hex}{suffix}"
    path.write_bytes(file.file.read())
    return process_uploaded_audio(path)


@app.post("/upload_audio")
async def upload_audio_raw(request: Request) -> dict:
    data = await request.body()
    if not data:
        return {"ok": False, "error": "No audio received"}
    config.AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    path = config.AUDIO_DIR / f"{uuid4().hex}.wav"
    path.write_bytes(data)
    return process_uploaded_audio(path)


def process_uploaded_audio(path: Path) -> dict:
    log_event("audio", "query received")
    transcript = transcribe_audio(path)
    log_event("stt", transcript or "(empty)")
    result = answer_transcript(transcript, audio_path=str(path))
    log_event("answer", result["response_text"])
    if os.environ.get("SENTINAL_ENABLE_SPEAKER") == "1":
        speak(result["response_text"])
    return {"ok": True, "audio_path": str(path), **result}


@app.get("/events")
def events() -> list[dict]:
    return store.list_events()


@app.get("/latest/{object_name}")
def latest(object_name: str) -> dict:
    event = store.latest_event(object_name)
    return {"ok": event is not None, "event": event}


@app.post("/query-text")
def query_text(request: TextQueryRequest) -> dict:
    return answer_transcript(request.transcript, audio_path="")


def answer_transcript(transcript: str, audio_path: str = "") -> dict:
    target_object = extract_target_object(transcript)
    event = store.latest_event(target_object) if target_object != "unknown" else None
    if target_object == "unknown":
        response_text = "I could not tell which object you are asking about."
    elif event is None:
        response_text = f"I do not have a recent record for your {target_object}."
    else:
        response_text = f"Your {target_object} was last seen on the {event['location_label']}."

    store.record_query(
        transcript=transcript,
        target_object=target_object,
        response_text=response_text,
        audio_path=audio_path,
    )
    return {
        "transcript": transcript,
        "target_object": target_object,
        "event": event,
        "response_text": response_text,
    }


def log_event(kind: str, message: str) -> None:
    print(f"[{kind}] {message}", flush=True)


def current_monotonic() -> float:
    return time.monotonic()


def _labels_from_filename(filename: str) -> tuple[str, str]:
    name = filename.lower()
    object_name = "unknown"
    location_label = "unknown"
    for candidate in config.VALID_OBJECTS:
        if candidate in name:
            object_name = candidate
            break
    for candidate in config.VALID_LOCATIONS:
        if candidate in name:
            location_label = candidate
            break
    return object_name, location_label


def _fallback_to_upload_filename(result: dict, filename: str) -> dict:
    object_name, location_label = _labels_from_filename(filename)
    if object_name == "unknown" and location_label == "unknown":
        return result

    fallback = dict(result)
    if object_name != "unknown":
        fallback["object_name"] = object_name
        fallback["confidence"] = max(float(fallback.get("confidence", 0.0)), 0.6)
    if location_label != "unknown":
        fallback["location_label"] = location_label
    fallback["raw_model_response"] = (
        f"{fallback.get('raw_model_response', '')}; upload filename fallback"
    ).strip("; ")
    return fallback


def classify_uploaded_image(image_path: Path) -> dict:
    try:
        scene = classify_uploaded_scene(image_path)
        confidence = min(
            float(scene.get("object_confidence", 0.0) or 0.0),
            float(scene.get("location_confidence", scene.get("object_confidence", 0.0)) or 0.0),
        )
        return {
            "object_name": scene["object_name"],
            "location_label": scene["location_label"],
            "confidence": round(confidence, 4),
            "raw_model_response": json.dumps(scene, ensure_ascii=True),
        }
    except Exception as exc:
        return {
            "object_name": "unknown",
            "location_label": "unknown",
            "confidence": 0.0,
            "raw_model_response": f"hybrid failed: {exc}",
        }


def classify_uploaded_scene(image_path: Path) -> dict:
    return classify_scene(image_path, force_known_object=True)
