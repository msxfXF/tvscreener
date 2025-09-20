"""FastAPI application exposing the monitoring service."""

from __future__ import annotations

import asyncio
import logging
import logging.config
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from .analytics import annotate_rating_scores, build_symbol_profile, compute_history_metrics

from .db import MonitoringDatabase
from .service import MonitorService
from .settings import Settings


def configure_logging(settings: Settings) -> None:
    """Configure application logging."""

    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "default": {
                    "format": "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                }
            },
            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                    "formatter": "default",
                    "level": settings.log_level_upper(),
                }
            },
            "root": {
                "handlers": ["console"],
                "level": settings.log_level_upper(),
            },
        }
    )


def create_app(settings: Optional[Settings] = None) -> FastAPI:
    """Create and configure the FastAPI application."""

    settings = settings or Settings()
    configure_logging(settings)

    database = MonitoringDatabase(settings.database_path)
    database.initialize()
    service = MonitorService(settings, database)

    templates = Jinja2Templates(directory=str(Path(__file__).with_name("templates")))

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        service.start()
        try:
            yield
        finally:
            await service.stop()

    app = FastAPI(title="TVScreener Monitoring Service", lifespan=lifespan)
    app.state.settings = settings
    app.state.database = database
    app.state.service = service
    app.state.templates = templates

    def get_settings(request: Request) -> Settings:
        return request.app.state.settings

    def get_database(request: Request) -> MonitoringDatabase:
        return request.app.state.database

    def get_service(request: Request) -> MonitorService:
        return request.app.state.service

    def get_templates(request: Request) -> Jinja2Templates:
        return request.app.state.templates

    @app.get("/", response_class=HTMLResponse)
    async def index(
        request: Request,
        service: MonitorService = Depends(get_service),
        templates: Jinja2Templates = Depends(get_templates),
        settings: Settings = Depends(get_settings),
    ) -> HTMLResponse:
        state_dict = service.state.to_dict()
        context = {
            "request": request,
            "state": state_dict,
            "settings": settings,
        }
        return templates.TemplateResponse("index.html", context)

    @app.get("/api/rating_changes")
    async def rating_changes(
        limit: int = Query(50, ge=1, le=500),
        offset: int = Query(0, ge=0),
        database: MonitoringDatabase = Depends(get_database),
    ) -> dict[str, Any]:
        total, rows = await asyncio.to_thread(database.fetch_rating_changes, limit, offset)
        return {"total": total, "items": rows, "limit": limit, "offset": offset}

    @app.get("/api/symbol/{symbol}/history")
    async def symbol_history(
        symbol: str,
        limit: int = Query(200, ge=1, le=2000),
        start: Optional[str] = Query(None, description="ISO formatted start timestamp"),
        end: Optional[str] = Query(None, description="ISO formatted end timestamp"),
        database: MonitoringDatabase = Depends(get_database),
    ) -> dict[str, Any]:
        start_iso = _validate_isoformat(start, "start") if start else None
        end_iso = _validate_isoformat(end, "end") if end else None
        rows = await asyncio.to_thread(
            database.fetch_symbol_history, symbol, limit, start_iso, end_iso
        )
        annotate_rating_scores(rows)
        latest = await asyncio.to_thread(database.fetch_latest_snapshot, symbol)
        if latest is None:
            raise HTTPException(status_code=404, detail="Symbol not found")
        profile = build_symbol_profile(symbol, latest)
        metrics = compute_history_metrics(rows)
        latest_payload = {
            "retrieved_at": latest.get("retrieved_at"),
            "price": latest.get("price"),
            "analyst_rating": latest.get("analyst_rating"),
        }
        return {
            "symbol": symbol,
            "items": rows,
            "limit": limit,
            "metrics": metrics,
            "profile": profile,
            "latest": latest_payload,
        }

    @app.get("/healthz")
    async def healthz(
        service: MonitorService = Depends(get_service),
        settings: Settings = Depends(get_settings),
        database: MonitoringDatabase = Depends(get_database),
    ) -> dict[str, Any]:
        state_dict = service.state.to_dict()
        latest_snapshot = await asyncio.to_thread(database.get_most_recent_snapshot_time)
        status = "ok" if state_dict["last_error"] is None else "degraded"
        return {
            "status": status,
            "is_running": service.is_running,
            "interval_seconds": settings.interval_seconds,
            "range": {"start": settings.range_start, "end": settings.range_end},
            "state": state_dict,
            "latest_snapshot": latest_snapshot,
        }

    return app


def _validate_isoformat(value: str, field_name: str) -> str:
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:  # pylint: disable=raise-missing-from
        raise HTTPException(status_code=400, detail=f"Invalid {field_name} value")
    return dt.isoformat()


app = create_app()


__all__ = ["create_app", "app"]
