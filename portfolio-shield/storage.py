"""
storage.py - Minimal SQLite persistence for hedge recommendations.
"""

import json
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).with_name("portfolio_shield.db")


def init_storage() -> None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS recommendations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                payload_json TEXT NOT NULL
            )
            """
        )
        conn.commit()


def save_recommendation(payload: dict) -> int:
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.execute(
            "INSERT INTO recommendations (payload_json) VALUES (?)",
            (json.dumps(payload),),
        )
        conn.commit()
        return int(cur.lastrowid)
