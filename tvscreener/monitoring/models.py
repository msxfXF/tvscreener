"""Data models used by the monitoring service."""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any, List, Optional


@dataclass
class RatingChange:
    """Represents a change in the analyst rating for a stock symbol."""

    symbol: str
    changed_at: datetime
    old_rating: Optional[str]
    new_rating: Optional[str]
    price_before: Optional[float]
    price_after: Optional[float]
    snapshot_rowid: Optional[int]
    id: Optional[int] = None

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON serialisable representation of the rating change."""

        data = asdict(self)
        data["changed_at"] = self.changed_at.isoformat()
        return data


@dataclass
class MonitorState:
    """Holds runtime metadata about the monitoring loop."""

    last_run: Optional[datetime] = None
    last_success: Optional[datetime] = None
    last_error: Optional[str] = None
    total_snapshots: int = 0
    total_rating_changes: int = 0
    last_changes: List[RatingChange] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Return a serialisable version of the state for the API/UI."""

        return {
            "last_run": self.last_run.isoformat() if self.last_run else None,
            "last_success": self.last_success.isoformat() if self.last_success else None,
            "last_error": self.last_error,
            "total_snapshots": self.total_snapshots,
            "total_rating_changes": self.total_rating_changes,
            "last_changes": [change.to_dict() for change in self.last_changes],
        }


__all__ = ["RatingChange", "MonitorState"]
