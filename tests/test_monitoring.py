import sqlite3
from pathlib import Path

import pandas as pd
import pytest

from tvscreener.monitoring.analytics import (
    annotate_rating_scores,
    build_symbol_profile,
    compute_history_metrics,
    rating_to_score,
)
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


def test_fetch_latest_snapshot_includes_raw_payload(temp_settings: Settings, database: MonitoringDatabase):
    service = MonitorService(temp_settings, database)
    df = pd.DataFrame([
        {"Symbol": "AAPL", "AnalystRating": "Buy", "Price": 123.45},
        {"Symbol": "MSFT", "AnalystRating": "Neutral", "Price": 321.0},
    ])

    service.process_dataframe(df)

    latest = database.fetch_latest_snapshot("AAPL")
    assert latest is not None
    assert latest["symbol"] == "AAPL"
    assert pytest.approx(latest["price"] or 0.0) == 123.45
    assert latest["raw"] is not None
    assert latest["raw"].get("Symbol") == "AAPL"
    assert latest["raw"].get("AnalystRating") == "Buy"
    assert pytest.approx(latest["raw"].get("Price") or 0.0) == 123.45


def test_annotate_rating_scores_maps_known_labels():
    rows = [
        {"analyst_rating": "Buy"},
        {"analyst_rating": "Strong Sell"},
        {"analyst_rating": "Hold"},
        {"analyst_rating": None},
    ]

    annotate_rating_scores(rows)

    assert rows[0]["rating_score"] == rating_to_score("Buy")
    assert rows[1]["rating_score"] == rating_to_score("Strong Sell")
    assert rows[2]["rating_score"] == rating_to_score("Hold")
    assert rows[3]["rating_score"] is None


def test_compute_history_metrics_and_profile():
    history = [
        {
            "retrieved_at": "2024-01-01T00:00:00+00:00",
            "price": 100.0,
            "analyst_rating": "Buy",
        },
        {
            "retrieved_at": "2024-01-02T00:00:00+00:00",
            "price": 105.0,
            "analyst_rating": "Strong Buy",
        },
        {
            "retrieved_at": "2024-01-03T00:00:00+00:00",
            "price": 102.5,
            "analyst_rating": "Buy",
        },
    ]

    metrics = compute_history_metrics(history)
    assert metrics["period"]["start"] == history[0]["retrieved_at"]
    assert metrics["period"]["end"] == history[-1]["retrieved_at"]
    assert pytest.approx(metrics["price"]["min"] or 0.0) == 100.0
    assert pytest.approx(metrics["price"]["max"] or 0.0) == 105.0
    assert pytest.approx(metrics["price"]["change"] or 0.0) == 2.5
    assert pytest.approx(metrics["price"]["change_pct"] or 0.0) == 2.5
    assert metrics["ratings"]["counts"]["Buy"] == 2
    assert metrics["ratings"]["counts"]["Strong Buy"] == 1

    latest_row = {
        "symbol": "AAPL",
        "retrieved_at": "2024-01-03T00:00:00+00:00",
        "price": 102.5,
        "analyst_rating": "Buy",
        "raw": {
            "Name": "Apple Inc.",
            "Description": "Consumer electronics",
            "Sector": "Technology",
            "Industry": "Consumer Electronics",
            "Change %": 1.2,
            "Volume": 1_000_000,
            "Average Volume (30 day)": 1_250_000,
            "Average Volume (10 day)": 900_000,
            "Market Capitalization": 2_500_000_000_000,
            "52 Week High": 199.0,
            "52 Week Low": 120.0,
        },
    }

    profile = build_symbol_profile("AAPL", latest_row)
    assert profile["name"] == "Apple Inc."
    assert profile["sector"] == "Technology"
    assert profile["industry"] == "Consumer Electronics"
    labels = {item["label"] for item in profile["attributes"]}
    assert "Last Price" in labels
    assert "Market Cap" in labels
    assert "52 Week High" in labels
