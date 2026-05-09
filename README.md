# Sentinel

Sentinel is an embedded AI prototype for last-seen object logging. A wrist-worn trigger detects likely object interactions, an ESP32-S3 Sense captures images and voice queries, and a Raspberry Pi 5 performs local recognition and memory lookup.

## System Flow

1. The nRF52840 wrist node detects pressure and wrist motion.
2. The wrist node sends a `GRAB` trigger to the ESP32-S3 over BLE.
3. The ESP32-S3 captures three images and uploads them to the Raspberry Pi over Wi-Fi.
4. The Raspberry Pi groups the three images into one event.
5. YOLO detects the object: `phone`, `wallet`, or `airpods`.
6. A lightweight image classifier predicts the environment: `bed` or `table`.
7. SQLite stores the latest object-location memory.
8. A voice query is transcribed locally and used to look up the most recent record.

## Repository Layout

```text
esp32_s3/              ESP32-S3 Sense capture-node firmware
nrf/                   nRF52840 wrist-trigger firmware
pi_app/                Raspberry Pi FastAPI application
scripts/               Pi setup, server, and audio helper commands
models/                Selected runtime model files
sentinal               Pi command wrapper
requirements.txt       Python dependencies for the Pi
```

Generated data, alternate model exports, virtual environments, and local SQLite/audio/image files are intentionally ignored.

## Raspberry Pi Setup

```bash
cd ~/Sentinel
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
./sentinal start
```

The server listens on port `8000`.

Useful endpoints:

```text
GET  /health
POST /upload_image       Raw JPEG body from ESP32-S3
POST /upload_audio       Raw WAV body from ESP32-S3
POST /query-text         Debug text query
GET  /events             Recent object-location records
GET  /latest/{object}    Latest record for one object
```

Typical demo log:

```text
[image] auto burst auto-1 frame 1/3 received
[image] auto burst auto-1 frame 2/3 received
[image] auto burst auto-1 frame 3/3 received
[vision] wallet on table saved to SQL event 1
[audio] query received
[stt] where's my wallet
[answer] Your wallet was last seen on the table.
```

## Runtime Models

The committed runtime model files are:

```text
models/lost_items_yolo_models/best.onnx
models/lost_items_yolo_models/metadata.yaml
models/xiao_classifier/classifier.json
```

For local speech-to-text, download the Vosk small English model and place it at:

```text
models/vosk-model-small-en-us-0.15/
```

The Vosk model is not committed because it is a downloaded runtime asset.
