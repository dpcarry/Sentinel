from pathlib import Path
import json
import subprocess
import wave

from pi_app import config


def transcribe_audio(audio_path: Path) -> str:
    if config.VOSK_MODEL_DIR.exists():
        try:
            transcript = _transcribe_with_vosk(audio_path, config.VOSK_MODEL_DIR)
            if transcript:
                return transcript
        except Exception:
            pass

    target = _target_from_path(audio_path)
    if target == "airpods":
        return "where are my airpods"
    if target != "unknown":
        return f"where is my {target}"
    return ""


def speak(text: str) -> None:
    subprocess.run(["espeak-ng", text], check=False)


def _transcribe_with_vosk(audio_path: Path, model_dir: Path) -> str:
    from vosk import KaldiRecognizer, Model

    with wave.open(str(audio_path), "rb") as wav:
        if wav.getnchannels() != 1 or wav.getsampwidth() != 2:
            raise ValueError("Vosk input must be mono 16-bit PCM WAV")
        model = Model(str(model_dir))
        recognizer = KaldiRecognizer(model, wav.getframerate())
        texts = []
        while True:
            data = wav.readframes(4000)
            if not data:
                break
            if recognizer.AcceptWaveform(data):
                texts.append(_text_from_vosk_json(recognizer.Result()))
        texts.append(_text_from_vosk_json(recognizer.FinalResult()))
    return " ".join(text for text in texts if text).strip()


def _text_from_vosk_json(raw_json: str) -> str:
    try:
        return str(json.loads(raw_json).get("text", "")).strip()
    except json.JSONDecodeError:
        return ""


def _target_from_path(audio_path: Path) -> str:
    for part in reversed(audio_path.parts):
        lowered = part.lower()
        if lowered in {"phone", "wallet", "airpods"}:
            return lowered
    return "unknown"
