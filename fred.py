"""FRED (Federal Reserve Economic Data) API client.

Fetches macroeconomic time-series from the St. Louis Fed's free API and returns
them as clean, date-indexed pandas Series. All network failures and missing
observations are handled defensively: a failed or unknown series resolves to an
empty Series rather than raising, so one bad series ID never breaks the whole
dashboard (see the Data Health panel in the UI).

This module contains no Streamlit or UI logic. Caching is applied by the app
layer via ``st.cache_data``.
"""

from __future__ import annotations

from typing import Any

import pandas as pd
import requests

import config


class FredError(RuntimeError):
    """Raised only for hard configuration errors (e.g. a missing API key)."""


def _require_key(api_key: str | None) -> str:
    """Return a usable FRED API key or raise a clear configuration error.

    Args:
        api_key: A caller-supplied key (from the sidebar) taking precedence over
            the environment-configured key.

    Returns:
        The resolved API key string.

    Raises:
        FredError: If neither a caller key nor ``config.FRED_API_KEY`` is set.
    """
    key = (api_key or "").strip() or config.FRED_API_KEY
    if not key:
        raise FredError(
            "No FRED API key configured. Get a free key at "
            "https://fredaccount.stlouisfed.org/apikeys and paste it in the "
            "sidebar, or set FRED_API_KEY in your environment / Streamlit secrets."
        )
    return key


def fetch_series(
    series_id: str,
    api_key: str | None = None,
    start: str | None = None,
) -> pd.Series:
    """Fetch a single FRED series as a float Series indexed by date.

    Args:
        series_id: The FRED series identifier (e.g. ``"DGS10"``).
        api_key: Optional override key; falls back to the configured key.
        start: Optional ``YYYY-MM-DD`` lower bound on observations.

    Returns:
        A ``pandas.Series`` of floats indexed by ``DatetimeIndex`` (name set to
        ``series_id``). Empty when the series is unknown, unavailable, or the
        request fails — callers should treat an empty result as ``n/a``.

    Raises:
        FredError: Only when no API key is configured at all.
    """
    key = _require_key(api_key)
    if not series_id:
        return pd.Series(dtype="float64", name=series_id)

    params: dict[str, Any] = {
        "series_id": series_id,
        "api_key": key,
        "file_type": "json",
        "sort_order": "asc",
    }
    if start:
        params["observation_start"] = start

    try:
        resp = requests.get(
            config.FRED_BASE_URL,
            params=params,
            timeout=config.REQUEST_TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
        payload = resp.json()
    except (requests.RequestException, ValueError):
        # Network error, bad status, unknown series id, or non-JSON body.
        return pd.Series(dtype="float64", name=series_id)

    observations = payload.get("observations") if isinstance(payload, dict) else None
    if not observations:
        return pd.Series(dtype="float64", name=series_id)

    dates: list[pd.Timestamp] = []
    values: list[float] = []
    for obs in observations:
        raw = obs.get("value", ".")
        if raw in (".", "", None):  # FRED marks missing values with a dot.
            continue
        try:
            values.append(float(raw))
        except (TypeError, ValueError):
            continue
        dates.append(pd.Timestamp(obs.get("date")))

    series = pd.Series(values, index=pd.DatetimeIndex(dates), name=series_id)
    return series.sort_index()


def fetch_release_dates(
    release_id: int, api_key: str | None = None, limit: int = 24
) -> list[str]:
    """Fetch scheduled release dates for a FRED release (newest first).

    FRED publishes forward-looking dates for major releases, so this includes
    upcoming dates as well as recent past ones.

    Args:
        release_id: The FRED release ID (e.g. 10 for CPI).
        api_key: Optional override key; falls back to the configured key.
        limit: Max number of dates to return.

    Returns:
        A list of ISO ``YYYY-MM-DD`` date strings, or ``[]`` on failure.
    """
    key = _require_key(api_key)
    try:
        resp = requests.get(
            config.FRED_RELEASE_DATES_URL,
            params={
                "release_id": release_id,
                "api_key": key,
                "file_type": "json",
                "sort_order": "desc",
                "limit": limit,
                "include_release_dates_with_no_data": "true",
            },
            timeout=config.REQUEST_TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
        payload = resp.json()
    except (requests.RequestException, ValueError):
        return []
    return [d.get("date") for d in payload.get("release_dates", []) if d.get("date")]


def latest(series: pd.Series) -> tuple[pd.Timestamp | None, float | None]:
    """Return the most recent (date, value) pair of a series, or ``(None, None)``.

    Args:
        series: A date-indexed series (possibly empty).

    Returns:
        A tuple of the latest timestamp and value, or ``(None, None)`` when the
        series is empty.
    """
    if series is None or series.empty:
        return None, None
    return series.index[-1], float(series.iloc[-1])


def change_over(series: pd.Series, months: int) -> float | None:
    """Compute the change in a series over roughly the last ``months`` months.

    Used to gauge policy-rate trajectory for stance classification.

    Args:
        series: A date-indexed series.
        months: Look-back window in months.

    Returns:
        ``latest - value_as_of(latest - months)`` in the series' units, or
        ``None`` when there is not enough history.
    """
    if series is None or series.empty:
        return None
    last_date, last_val = series.index[-1], float(series.iloc[-1])
    cutoff = last_date - pd.DateOffset(months=months)
    prior = series[series.index <= cutoff]
    if prior.empty:
        return None
    return last_val - float(prior.iloc[-1])


def to_yoy(index_series: pd.Series) -> pd.Series:
    """Convert a price *index* series to a year-over-year percent-change series.

    Args:
        index_series: A monthly index level series (e.g. core CPI index).

    Returns:
        A YoY percent-change series (12-period change), NaNs dropped. Empty when
        the input is empty.
    """
    if index_series is None or index_series.empty:
        return pd.Series(dtype="float64")
    yoy = index_series.pct_change(periods=12) * 100.0
    return yoy.dropna()
