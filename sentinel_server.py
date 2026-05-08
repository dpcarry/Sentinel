from flask import Flask, request
from datetime import datetime
import os

app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

IMAGE_DIR = os.path.join(BASE_DIR, "received_images")
AUDIO_DIR = os.path.join(BASE_DIR, "received_audio")

os.makedirs(IMAGE_DIR, exist_ok=True)
os.makedirs(AUDIO_DIR, exist_ok=True)

@app.route("/", methods=["GET"])
def index():
    return "Sentinel PC receiver is running."

@app.route("/upload_image", methods=["POST"])
def upload_image():
    data = request.data

    if not data:
        return "No image received", 400

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    filename = os.path.join(IMAGE_DIR, f"sentinel_image_{timestamp}.jpg")

    with open(filename, "wb") as f:
        f.write(data)

    print(f"Saved image: {filename}, size = {len(data)} bytes")
    return "OK", 200

@app.route("/upload_audio", methods=["POST"])
def upload_audio():
    data = request.data

    if not data:
        return "No audio received", 400

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    filename = os.path.join(AUDIO_DIR, f"sentinel_audio_{timestamp}.wav")

    with open(filename, "wb") as f:
        f.write(data)

    print(f"Saved audio: {filename}, size = {len(data)} bytes")
    return "OK", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)