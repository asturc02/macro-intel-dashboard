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
