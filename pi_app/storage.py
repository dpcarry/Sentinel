import sqlite3
from datetime import datetime, timezone
from pathlib import Path


class SentinalStore:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)

    def initialize(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    object_name TEXT NOT NULL,
                    location_label TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    image_path TEXT NOT NULL,
                    raw_model_response TEXT NOT NULL,
                    source TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS queries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    transcript TEXT NOT NULL,
                    target_object TEXT NOT NULL,
                    response_text TEXT NOT NULL,
                    audio_path TEXT NOT NULL
                )
                """
            )

    def record_event(
        self,
        object_name: str,
        location_label: str,
        confidence: float,
        image_path: str,
        raw_model_response: str,
        source: str,
    ) -> dict:
        self.initialize()
        timestamp = datetime.now(timezone.utc).isoformat()
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """
                INSERT INTO events (
                    timestamp, object_name, location_label, confidence,
                    image_path, raw_model_response, source
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    timestamp,
                    object_name,
                    location_label,
                    confidence,
                    image_path,
                    raw_model_response,
                    source,
                ),
            )
            event_id = cursor.lastrowid
        return {
            "id": event_id,
            "timestamp": timestamp,
            "object_name": object_name,
            "location_label": location_label,
            "confidence": confidence,
            "image_path": image_path,
            "raw_model_response": raw_model_response,
            "source": source,
        }

    def latest_event(self, object_name: str) -> dict | None:
        self.initialize()
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM events WHERE object_name = ? ORDER BY id DESC LIMIT 1",
                (object_name,),
            ).fetchone()
        return dict(row) if row else None

    def list_events(self, limit: int = 20) -> list[dict]:
        self.initialize()
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("SELECT * FROM events ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(row) for row in rows]

    def record_query(self, transcript: str, target_object: str, response_text: str, audio_path: str) -> dict:
        self.initialize()
        timestamp = datetime.now(timezone.utc).isoformat()
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """
                INSERT INTO queries (timestamp, transcript, target_object, response_text, audio_path)
                VALUES (?, ?, ?, ?, ?)
                """,
                (timestamp, transcript, target_object, response_text, audio_path),
            )
            query_id = cursor.lastrowid
        return {
            "id": query_id,
            "timestamp": timestamp,
            "transcript": transcript,
            "target_object": target_object,
            "response_text": response_text,
            "audio_path": audio_path,
        }

    def list_queries(self, limit: int = 20) -> list[dict]:
        self.initialize()
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("SELECT * FROM queries ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(row) for row in rows]
