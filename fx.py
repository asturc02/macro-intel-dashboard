"""Foreign-exchange helpers backed by the Frankfurter API (ECB reference rates).

Frankfurter (https://www.frankfurter.app) serves free, no-key, end-of-day ECB
reference rates. We use it to estimate the annualized *realized volatility* of a
currency versus the USD, which turns a raw interest-rate carry into a crude,
volatility-adjusted (Sharpe-like) expected return in the Carry module.

No Streamlit or UI logic here. Failures degrade to ``None``.
"""

from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd
import requests

import config


def fetch_usd_pair(currency: str, days: int = 365) -> pd.Series:
    """Fetch a daily USD/<currency> series for the trailing ``days`` days.

    The value is units of ``currency`` per 1 USD, so a rising line means the
    foreign currency is weakening against the dollar.

    Args:
        currency: ISO code of the non-USD leg (e.g. ``"JPY"``).
        days: Trailing window length in calendar days.

    Returns:
        A date-indexed ``pandas.Series`` of exchange rates, or an empty Series on
        failure or for USD itself.
    """
    currency = (currency or "").upper()
    if not currency or currency == "USD":
        return pd.Series(dtype="float64", name=currency)

    end = date.today()
    start = end - timedelta(days=days)
    url = f"{config.FRANKFURTER_BASE_URL}/{start.isoformat()}..{end.isoformat()}"
    try:
        resp = requests.get(
            url,
            params={"from": "USD", "to": currency},
            timeout=config.REQUEST_TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
        payload = resp.json()
    except (requests.RequestException, ValueError):
        return pd.Series(dtype="float64", name=currency)

    rates = payload.get("rates") if isinstance(payload, dict) else None
    if not rates:
        return pd.Series(dtype="float64", name=currency)

    dates: list[pd.Timestamp] = []
    values: list[float] = []
    for day, quote in sorted(rates.items()):
        value = quote.get(currency) if isinstance(quote, dict) else None
        if value is None:
            continue
        dates.append(pd.Timestamp(day))
        values.append(float(value))

    return pd.Series(values, index=pd.DatetimeIndex(dates), name=currency)


def fetch_cross(base: str, quote: str, days: int = 365) -> pd.Series:
    """Fetch a daily cross-rate series: units of ``quote`` per 1 ``base``.

    Used for carry *pairs* (e.g. AUD/JPY) where neither leg is the USD. Frankfurter
    accepts any supported currency as the base, so this fetches the direct cross.

    Args:
        base: ISO code of the base (long) leg, e.g. ``"AUD"``.
        quote: ISO code of the quote (funding) leg, e.g. ``"JPY"``.
        days: Trailing window length in calendar days.

    Returns:
        A date-indexed Series of ``base``/``quote`` rates, or empty on failure /
        when the two legs are identical.
    """
    base = (base or "").upper()
    quote = (quote or "").upper()
    if not base or not quote or base == quote:
        return pd.Series(dtype="float64", name=f"{base}{quote}")

    end = date.today()
    start = end - timedelta(days=days)
    url = f"{config.FRANKFURTER_BASE_URL}/{start.isoformat()}..{end.isoformat()}"
    try:
        resp = requests.get(
            url,
            params={"from": base, "to": quote},
            timeout=config.REQUEST_TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
        payload = resp.json()
    except (requests.RequestException, ValueError):
        return pd.Series(dtype="float64", name=f"{base}{quote}")

    rates = payload.get("rates") if isinstance(payload, dict) else None
    if not rates:
        return pd.Series(dtype="float64", name=f"{base}{quote}")

    dates: list[pd.Timestamp] = []
    values: list[float] = []
    for day, quote_map in sorted(rates.items()):
        value = quote_map.get(quote) if isinstance(quote_map, dict) else None
        if value is None:
            continue
        dates.append(pd.Timestamp(day))
        values.append(float(value))

    return pd.Series(values, index=pd.DatetimeIndex(dates), name=f"{base}{quote}")


def cross_vol(base: str, quote: str, days: int = 365) -> float | None:
    """Annualized realized volatility of a ``base``/``quote`` cross rate.

    Args:
        base: ISO code of the base (long) leg.
        quote: ISO code of the quote (funding) leg.
        days: Trailing window used to fetch the price history.

    Returns:
        Annualized volatility in percent, or ``None`` when data is insufficient.
    """
    series = fetch_cross(base, quote, days=days)
    if series is None or len(series) < 30:
        return None
    log_returns = np.log(series / series.shift(1)).dropna()
    if log_returns.empty:
        return None
    return float(log_returns.std() * np.sqrt(252) * 100.0)


def annualized_vol(currency: str, days: int = 365) -> float | None:
    """Estimate annualized realized volatility of USD/<currency> log returns.

    Args:
        currency: ISO code of the non-USD leg.
        days: Trailing window used to fetch the price history.

    Returns:
        Annualized volatility in percent (e.g. ``9.3`` for 9.3%), or ``None``
        when insufficient data is available.
    """
    series = fetch_usd_pair(currency, days=days)
    if series is None or len(series) < 30:
        return None
    log_returns = np.log(series / series.shift(1)).dropna()
    if log_returns.empty:
        return None
    # ~252 trading days per year; ECB data is business-daily.
    return float(log_returns.std() * np.sqrt(252) * 100.0)
