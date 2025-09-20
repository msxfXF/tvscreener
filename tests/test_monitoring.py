import sqlite3
from pathlib import Path

import pandas as pd
import pytest

from tvscreener.monitoring.db import MonitoringDatabase
from tvscreener.monitoring.models import RatingChange
from tvscreener.monitoring.service import MonitorService
from tvscreener.monitoring.settings import Settings


@pytest.fixture()
def temp_settings(tmp_path: Path) -> Settings:
    return Settings(
        interval_seconds=60,
        range_start=0,
        range_end=2,
        db_path=str(tmp_path / "monitor.db"),
        max_retries=0,
    )


@pytest.fixture()
def database(temp_settings: Settings) -> MonitoringDatabase:
    db = MonitoringDatabase(temp_settings.database_path)
    db.initialize()
    return db


def test_process_dataframe_detects_rating_change(temp_settings: Settings, database: MonitoringDatabase):
    service = MonitorService(temp_settings, database)

    df_initial = pd.DataFrame([
        {"Symbol": "AAPL", "AnalystRating": "Buy", "Price": 189.2},
        {"Symbol": "MSFT", "AnalystRating": "Neutral", "Price": 327.5},
    ])

    changes, processed = service.process_dataframe(df_initial)
    assert processed == 2
    assert changes == []

    df_updated = pd.DataFrame([
        {"Symbol": "AAPL", "AnalystRating": "Sell", "Price": 185.0},
        {"Symbol": "MSFT", "AnalystRating": "Neutral", "Price": 328.1},
    ])

    changes, processed = service.process_dataframe(df_updated)
    assert processed == 2
    assert len(changes) == 1
    change: RatingChange = changes[0]
    assert change.symbol == "AAPL"
    assert change.old_rating == "Buy"
    assert change.new_rating == "Sell"
    assert pytest.approx(change.price_before or 0) == 189.2
    assert pytest.approx(change.price_after or 0) == 185.0

    total, rows = database.fetch_rating_changes(limit=10)
    assert total == 1
    assert rows[0]["symbol"] == "AAPL"


def test_process_dataframe_handles_missing_values(temp_settings: Settings, database: MonitoringDatabase):
    service = MonitorService(temp_settings, database)
    df = pd.DataFrame([
        {"Symbol": "TSLA", "AnalystRating": None, "Price": float("nan")},
    ])

    changes, processed = service.process_dataframe(df)
    assert processed == 1
    assert changes == []

    with database.connect() as conn:
        row = conn.execute(
            "SELECT analyst_rating, price FROM snapshots WHERE symbol = ?",
            ("TSLA",),
        ).fetchone()
    assert row["analyst_rating"] is None
    assert row["price"] is None
