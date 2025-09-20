"""SQLite persistence for the monitoring service."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple

from .models import RatingChange


def _json_default(value: Any) -> Any:
    """Convert non-serialisable objects to JSON friendly representations."""

    if isinstance(value, (datetime,)):
        return value.isoformat()
    if hasattr(value, "item"):
        return value.item()
    return str(value)


class MonitoringDatabase:
    """Wrapper around SQLite operations used by the monitoring service."""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def initialize(self) -> None:
        """Create the necessary tables if they do not already exist."""

        with self.connect() as conn:
            conn.executescript(
                """
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    retrieved_at TEXT NOT NULL,
                    analyst_rating TEXT,
                    price REAL,
                    raw_json TEXT,
                    UNIQUE(symbol, retrieved_at)
                );
                CREATE TABLE IF NOT EXISTS rating_changes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    changed_at TEXT NOT NULL,
                    old_rating TEXT,
                    new_rating TEXT,
                    price_before REAL,
                    price_after REAL,
                    snapshot_rowid INTEGER,
                    FOREIGN KEY(snapshot_rowid) REFERENCES snapshots(id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_snapshots_symbol_time ON snapshots(symbol, retrieved_at);
                CREATE INDEX IF NOT EXISTS idx_rating_changes_symbol_time ON rating_changes(symbol, changed_at);
                """
            )

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        """Context manager yielding a SQLite connection with sane defaults."""

        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    @staticmethod
    def _serialize_row(record: Dict[str, Any]) -> str:
        return json.dumps(record, default=_json_default)

    def get_last_snapshot(self, conn: sqlite3.Connection, symbol: str) -> Optional[sqlite3.Row]:
        """Return the most recent snapshot for the given symbol."""

        cursor = conn.execute(
            """
            SELECT id, analyst_rating, price, retrieved_at
            FROM snapshots
            WHERE symbol = ?
            ORDER BY retrieved_at DESC
            LIMIT 1
            """,
            (symbol,),
        )
        return cursor.fetchone()

    def insert_snapshot(
        self,
        conn: sqlite3.Connection,
        symbol: str,
        retrieved_at: str,
        analyst_rating: Optional[str],
        price: Optional[float],
        raw_record: Dict[str, Any],
    ) -> int:
        """Insert a new snapshot row and return the SQLite rowid."""

        cursor = conn.execute(
            """
            INSERT INTO snapshots(symbol, retrieved_at, analyst_rating, price, raw_json)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(symbol, retrieved_at) DO UPDATE SET
                analyst_rating=excluded.analyst_rating,
                price=excluded.price,
                raw_json=excluded.raw_json
            """,
            (
                symbol,
                retrieved_at,
                analyst_rating,
                price,
                self._serialize_row(raw_record),
            ),
        )
        snapshot_id = cursor.lastrowid
        if not snapshot_id:
            snapshot_id = conn.execute(
                "SELECT id FROM snapshots WHERE symbol = ? AND retrieved_at = ?",
                (symbol, retrieved_at),
            ).fetchone()[0]
        return snapshot_id

    def insert_rating_change(
        self,
        conn: sqlite3.Connection,
        symbol: str,
        changed_at: datetime,
        old_rating: Optional[str],
        new_rating: Optional[str],
        price_before: Optional[float],
        price_after: Optional[float],
        snapshot_rowid: Optional[int],
    ) -> RatingChange:
        """Persist a rating change event and return the created model."""

        cursor = conn.execute(
            """
            INSERT INTO rating_changes(symbol, changed_at, old_rating, new_rating, price_before, price_after, snapshot_rowid)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                symbol,
                changed_at.isoformat(),
                old_rating,
                new_rating,
                price_before,
                price_after,
                snapshot_rowid,
            ),
        )
        return RatingChange(
            id=cursor.lastrowid,
            symbol=symbol,
            changed_at=changed_at,
            old_rating=old_rating,
            new_rating=new_rating,
            price_before=price_before,
            price_after=price_after,
            snapshot_rowid=snapshot_rowid,
        )

    def fetch_rating_changes(self, limit: int, offset: int = 0) -> Tuple[int, List[dict[str, Any]]]:
        """Return total count and a page of rating change rows."""

        with self.connect() as conn:
            total = conn.execute("SELECT COUNT(*) FROM rating_changes").fetchone()[0]
            cursor = conn.execute(
                """
                SELECT id, symbol, changed_at, old_rating, new_rating, price_before, price_after, snapshot_rowid
                FROM rating_changes
                ORDER BY changed_at DESC
                LIMIT ? OFFSET ?
                """,
                (limit, offset),
            )
            rows = [dict(row) for row in cursor.fetchall()]
        return total, rows

    def fetch_symbol_history(
        self,
        symbol: str,
        limit: int,
        start: Optional[str] = None,
        end: Optional[str] = None,
    ) -> List[dict[str, Any]]:
        """Return historical snapshots for a specific symbol."""

        query = [
            "SELECT symbol, retrieved_at, analyst_rating, price",
            "FROM snapshots",
            "WHERE symbol = ?",
        ]
        params: List[Any] = [symbol]
        if start:
            query.append("AND retrieved_at >= ?")
            params.append(start)
        if end:
            query.append("AND retrieved_at <= ?")
            params.append(end)
        query.append("ORDER BY retrieved_at DESC LIMIT ?")
        params.append(limit)
        statement = " ".join(query)
        with self.connect() as conn:
            cursor = conn.execute(statement, params)
            rows = [dict(row) for row in cursor.fetchall()]
        rows.reverse()
        return rows

    def get_most_recent_snapshot_time(self) -> Optional[str]:
        """Return the timestamp of the latest snapshot across all symbols."""

        with self.connect() as conn:
            row = conn.execute(
                "SELECT retrieved_at FROM snapshots ORDER BY retrieved_at DESC LIMIT 1"
            ).fetchone()
            return row[0] if row else None


__all__ = ["MonitoringDatabase"]
