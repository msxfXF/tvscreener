"""Background monitoring service that polls TradingView data."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import tvscreener as tvs

from .db import MonitoringDatabase
from .models import MonitorState, RatingChange
from .settings import Settings


LOGGER = logging.getLogger("tvscreener.monitoring")


class MonitorService:
    """Runs the periodic monitoring workflow in the background."""

    def __init__(self, settings: Settings, database: MonitoringDatabase) -> None:
        self.settings = settings
        self.database = database
        self.state = MonitorState()
        self._task: Optional[asyncio.Task[None]] = None
        self._stop_event: Optional[asyncio.Event] = None

    # ---------------------------------------------------------------------
    # Lifecycle management
    # ---------------------------------------------------------------------
    def start(self) -> None:
        """Start the monitoring loop if it is not already running."""

        if self._task and not self._task.done():
            return

        self._stop_event = asyncio.Event()
        self._task = asyncio.create_task(self._run_loop(), name="tvscreener-monitor")
        LOGGER.info(
            "Monitoring service started with interval=%ss range=(%s, %s)",
            self.settings.interval_seconds,
            self.settings.range_start,
            self.settings.range_end,
        )

    async def stop(self) -> None:
        """Stop the monitoring loop and wait for completion."""

        if self._task is None:
            return

        if self._stop_event:
            self._stop_event.set()

        try:
            await self._task
        except asyncio.CancelledError:
            pass
        finally:
            self._task = None
            self._stop_event = None
            LOGGER.info("Monitoring service stopped")

    @property
    def is_running(self) -> bool:
        return bool(self._task and not self._task.done())

    async def trigger_once(self) -> List[RatingChange]:
        """Run the monitoring cycle a single time and return detected changes."""

        return await self._run_cycle()

    # ------------------------------------------------------------------
    # Core loop
    # ------------------------------------------------------------------
    async def _run_loop(self) -> None:
        assert self._stop_event is not None
        while not self._stop_event.is_set():
            await self._run_cycle()
            try:
                await asyncio.wait_for(
                    self._stop_event.wait(), timeout=self.settings.interval_seconds
                )
            except asyncio.TimeoutError:
                continue

    async def _run_cycle(self) -> List[RatingChange]:
        """Execute a full monitoring cycle."""

        now = datetime.now(timezone.utc)
        self.state.last_run = now
        try:
            dataframe = await self._fetch_with_retries()
            changes, processed = await asyncio.to_thread(self.process_dataframe, dataframe)
            self.state.total_snapshots += processed
            self.state.total_rating_changes += len(changes)
            self.state.last_changes = changes
            self.state.last_success = now
            self.state.last_error = None
            for change in changes:
                LOGGER.info(
                    "Analyst rating changed for %s: %s -> %s (price %s -> %s)",
                    change.symbol,
                    change.old_rating,
                    change.new_rating,
                    change.price_before,
                    change.price_after,
                )
            return changes
        except Exception as exc:  # pylint: disable=broad-except
            self.state.last_error = str(exc)
            LOGGER.exception("Monitoring cycle failed: %s", exc)
            return []

    async def _fetch_with_retries(self) -> pd.DataFrame:
        """Fetch data from TradingView with retry handling."""

        attempt = 0
        delay = self.settings.retry_backoff_seconds
        last_exc: Optional[Exception] = None
        while attempt <= self.settings.max_retries:
            try:
                return await asyncio.to_thread(self._fetch_dataframe)
            except Exception as exc:  # pylint: disable=broad-except
                last_exc = exc
                attempt += 1
                if attempt > self.settings.max_retries:
                    break
                LOGGER.warning(
                    "Fetch attempt %s failed: %s. Retrying in %ss", attempt, exc, delay
                )
                await asyncio.sleep(delay)
                delay += self.settings.retry_backoff_seconds
        assert last_exc is not None
        raise last_exc

    def _fetch_dataframe(self) -> pd.DataFrame:
        """Blocking call that retrieves the dataframe from TradingView."""

        screener = tvs.StockScreener()
        start, end = self.settings.as_range()
        screener.set_range(start, end)
        return screener.get()

    # ------------------------------------------------------------------
    # Data processing helpers
    # ------------------------------------------------------------------
    def process_dataframe(self, dataframe: pd.DataFrame) -> Tuple[List[RatingChange], int]:
        """Persist the dataframe and detect analyst rating changes."""

        if dataframe is None or dataframe.empty:
            return [], 0

        retrieved_dt = datetime.now(timezone.utc)
        retrieved_at = retrieved_dt.isoformat()

        records = dataframe.to_dict(orient="records")
        changes: List[RatingChange] = []
        processed = 0
        with self.database.connect() as conn:
            for record in records:
                symbol = self._extract_symbol(record)
                if not symbol:
                    continue
                rating = self._extract_rating(record)
                price = self._extract_price(record)
                clean_record = self._sanitize_record(record)
                previous = self.database.get_last_snapshot(conn, symbol)
                snapshot_rowid = self.database.insert_snapshot(
                    conn,
                    symbol,
                    retrieved_at,
                    rating,
                    price,
                    clean_record,
                )
                processed += 1
                if previous and previous["analyst_rating"] != rating:
                    change = self.database.insert_rating_change(
                        conn,
                        symbol,
                        retrieved_dt,
                        previous["analyst_rating"],
                        rating,
                        previous["price"],
                        price,
                        snapshot_rowid,
                    )
                    changes.append(change)
        return changes, processed

    @staticmethod
    def _sanitize_record(record: Dict[str, Any]) -> Dict[str, Any]:
        clean: Dict[str, Any] = {}
        for key, value in record.items():
            if isinstance(value, datetime):
                clean[key] = value.isoformat()
            elif pd.isna(value):  # type: ignore[arg-type]
                clean[key] = None
            elif hasattr(value, "item"):
                clean[key] = value.item()
            else:
                clean[key] = value
        return clean

    @staticmethod
    def _extract_symbol(record: Dict[str, Any]) -> Optional[str]:
        value = MonitorService._get_value_case_insensitive(record, "symbol")
        if value is None:
            return None
        return str(value)

    @staticmethod
    def _extract_rating(record: Dict[str, Any]) -> Optional[str]:
        value = MonitorService._get_value_case_insensitive(record, "AnalystRating")
        if value is None:
            return None
        return str(value)

    @staticmethod
    def _extract_price(record: Dict[str, Any]) -> Optional[float]:
        value = MonitorService._get_value_case_insensitive(record, "Price")
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _get_value_case_insensitive(record: Dict[str, Any], key: str) -> Optional[Any]:
        lower_key = key.lower()
        for item_key, item_value in record.items():
            if item_key == key or item_key.lower() == lower_key:
                return item_value
        return None


__all__ = ["MonitorService"]
