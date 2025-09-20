"""Entry point for running the monitoring FastAPI application."""

from tvscreener.monitoring.app import app, create_app

__all__ = ["app", "create_app"]
