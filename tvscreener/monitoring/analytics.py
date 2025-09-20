"""Analytics helpers for the monitoring dashboard."""

from __future__ import annotations

from collections import Counter
from typing import Any, MutableMapping, Sequence


RATING_SCORE_MAP = {
    "STRONGSELL": 0,
    "SELL": 1,
    "UNDERPERFORM": 1,
    "REDUCE": 1,
    "UNDERWEIGHT": 1,
    "HOLD": 2,
    "NEUTRAL": 2,
    "MARKETPERFORM": 2,
    "EQUALWEIGHT": 2,
    "PERFORM": 2,
    "ACCUMULATE": 3,
    "BUY": 3,
    "OUTPERFORM": 3,
    "OVERWEIGHT": 3,
    "ADD": 3,
    "STRONGBUY": 4,
    "CONVICTIONBUY": 4,
}


RATING_SCORE_LABELS = {
    0: "Strong Sell",
    1: "Sell / Underperform",
    2: "Hold / Neutral",
    3: "Buy / Outperform",
    4: "Strong Buy",
}


def normalise_rating(value: Any) -> str | None:
    """Return a normalised textual representation of a rating."""

    if value is None:
        return None
    text = str(value).strip()
    return text or None


def rating_key(value: Any) -> str | None:
    """Return the lookup key for the rating scoring map."""

    normalised = normalise_rating(value)
    if not normalised:
        return None
    return normalised.upper().replace(" ", "").replace("-", "")


def rating_to_score(value: Any) -> int | None:
    """Map an analyst rating string to a numeric score if possible."""

    key = rating_key(value)
    if not key:
        return None
    return RATING_SCORE_MAP.get(key)


def annotate_rating_scores(rows: Sequence[MutableMapping[str, Any]]) -> None:
    """Attach a numeric rating score to each row in-place."""

    for row in rows:
        row["rating_score"] = rating_to_score(row.get("analyst_rating"))


def _coerce_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        return None
    text = text.replace(",", "")
    if text.endswith("%"):
        text = text[:-1]
    try:
        return float(text)
    except ValueError:
        return None


def _add_attribute(
    attributes: list[dict[str, Any]],
    label: str,
    value: Any,
    *,
    fmt: str | None = None,
) -> None:
    if value is None or value == "":
        return
    attributes.append({"label": label, "value": value, "format": fmt})


def build_symbol_profile(symbol: str, latest_row: Mapping[str, Any]) -> dict[str, Any]:
    """Prepare display-oriented information for the latest snapshot."""

    raw: Mapping[str, Any] | None = latest_row.get("raw") if latest_row else None
    attributes: list[dict[str, Any]] = []

    price = latest_row.get("price")
    rating = latest_row.get("analyst_rating")

    _add_attribute(attributes, "Last Price", price, fmt="number")

    if raw:
        change = _coerce_float(raw.get("Change %"))
        _add_attribute(attributes, "Change (Daily)", change, fmt="percent")
        _add_attribute(
            attributes,
            "Volume",
            _coerce_float(raw.get("Volume")),
            fmt="compact",
        )
        _add_attribute(
            attributes,
            "Average Volume (30d)",
            _coerce_float(raw.get("Average Volume (30 day)")),
            fmt="compact",
        )
        _add_attribute(
            attributes,
            "Average Volume (10d)",
            _coerce_float(raw.get("Average Volume (10 day)")),
            fmt="compact",
        )
        _add_attribute(
            attributes,
            "Market Cap",
            _coerce_float(raw.get("Market Capitalization")),
            fmt="compact",
        )
        _add_attribute(
            attributes,
            "52 Week High",
            _coerce_float(raw.get("52 Week High")),
            fmt="number",
        )
        _add_attribute(
            attributes,
            "52 Week Low",
            _coerce_float(raw.get("52 Week Low")),
            fmt="number",
        )

    name = raw.get("Name") if raw else None
    description = raw.get("Description") if raw else None
    sector = raw.get("Sector") if raw else None
    industry = raw.get("Industry") if raw else None

    return {
        "symbol": symbol,
        "name": name or symbol,
        "description": description,
        "sector": sector,
        "industry": industry,
        "retrieved_at": latest_row.get("retrieved_at"),
        "attributes": attributes,
    }


def compute_history_metrics(history: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Compute aggregate statistics for a symbol history."""

    if not history:
        return {
            "price": {},
            "ratings": {"counts": {}, "score_labels": RATING_SCORE_LABELS},
            "period": {"start": None, "end": None},
        }

    period = {
        "start": history[0].get("retrieved_at"),
        "end": history[-1].get("retrieved_at"),
    }

    price_values = [
        float(row["price"]) for row in history if row.get("price") is not None
    ]
    price_metrics: dict[str, Any] = {}
    if price_values:
        price_metrics["min"] = min(price_values)
        price_metrics["max"] = max(price_values)
        price_metrics["average"] = sum(price_values) / len(price_values)

        start_price = next(
            (float(row["price"]) for row in history if row.get("price") is not None),
            None,
        )
        end_price = next(
            (
                float(row["price"])
                for row in reversed(history)
                if row.get("price") is not None
            ),
            None,
        )
        price_metrics["start"] = start_price
        price_metrics["end"] = end_price
        if start_price is not None and end_price is not None:
            change = end_price - start_price
            price_metrics["change"] = change
            price_metrics["change_pct"] = (
                (change / start_price) * 100 if start_price else None
            )

    rating_series = [
        normalise_rating(row.get("analyst_rating")) for row in history
        if row.get("analyst_rating")
    ]
    rating_series = [value for value in rating_series if value]
    rating_counts = Counter(rating_series)

    ratings = {
        "counts": dict(rating_counts),
        "current": rating_series[-1] if rating_series else None,
        "score_labels": RATING_SCORE_LABELS,
    }

    return {
        "price": price_metrics,
        "ratings": ratings,
        "period": period,
    }


__all__ = [
    "annotate_rating_scores",
    "build_symbol_profile",
    "compute_history_metrics",
    "normalise_rating",
    "rating_key",
    "rating_to_score",
    "RATING_SCORE_LABELS",
    "RATING_SCORE_MAP",
]
