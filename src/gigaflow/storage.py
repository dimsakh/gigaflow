from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Dictation:
    id: int
    created_at: str
    duration_seconds: float
    text: str


class HistoryStore:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(path)
        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS dictations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                duration_seconds REAL NOT NULL,
                text TEXT NOT NULL
            )
            """
        )
        self._connection.commit()

    def add(self, text: str, duration_seconds: float) -> int:
        cursor = self._connection.execute(
            "INSERT INTO dictations(created_at, duration_seconds, text) VALUES (?, ?, ?)",
            (
                datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
                round(duration_seconds, 2),
                text.strip(),
            ),
        )
        self._connection.commit()
        return int(cursor.lastrowid)

    def recent(self, limit: int = 200) -> list[Dictation]:
        rows = self._connection.execute(
            """
            SELECT id, created_at, duration_seconds, text
            FROM dictations
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [Dictation(*row) for row in rows]

    def delete(self, item_id: int) -> None:
        self._connection.execute("DELETE FROM dictations WHERE id = ?", (item_id,))
        self._connection.commit()

    def clear(self) -> None:
        self._connection.execute("DELETE FROM dictations")
        self._connection.commit()

    def close(self) -> None:
        self._connection.close()

