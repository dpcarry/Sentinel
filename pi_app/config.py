from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
IMAGE_DIR = DATA_DIR / "images"
AUDIO_DIR = DATA_DIR / "audio"
DB_PATH = DATA_DIR / "sentinel.sqlite3"
MODEL_DIR = BASE_DIR / "models"

OLLAMA_MODEL = "llava-phi3:3.8b"
USE_OLLAMA = True
USE_YOLO = True
YOLO_MODEL_DIR = BASE_DIR / "models" / "lost_items_yolo_models"
YOLO_MODEL_PATH = YOLO_MODEL_DIR / "best.onnx"
YOLO_METADATA_PATH = YOLO_MODEL_DIR / "metadata.yaml"
VOSK_MODEL_DIR = MODEL_DIR / "vosk-model-small-en-us-0.15"

VALID_OBJECTS = {"phone", "wallet", "airpods"}
VALID_LOCATIONS = {"desk", "bed", "table", "unknown"}
