"""Australian Bureau of Statistics (ABS) data client — current AU CPI.

FRED's OECD-sourced Australian CPI froze at 2025-Q1, so this pulls the live
All-groups CPI from the free **ABS Data API** (SDMX-JSON, no key) and derives a
year-over-year series by compounding the quarterly changes. Used *only* for
Australia; every other economy stays on FRED. The RBA republishes the same ABS
figures but sits behind a CDN that blocks programmatic access, so we go to the
source.

This module contains no Streamlit or UI logic; failures degrade to an empty
Series so the rest of the dashboard is unaffected.
"""

from __future__ import annotations

import pandas as pd
import requests

import config

# All-groups CPI, quarterly % change from previous period, Australia (weighted
# average of eight capital cities). SDMX key = MEASURE.INDEX.TSEST.REGION.FREQ:
#   2      = percentage change from previous period (QoQ)
#   10001  = All groups CPI
#   10     = Original (not seasonally adjusted)
#   50     = Australia
#   Q      = Quarterly
ABS_CPI_QOQ_URL: str = (
    "https://data.api.abs.gov.au/rest/data/CPI/2.10001.10.50.Q"
    "?startPeriod=2014-Q1&format=jsondata"
)
_HEADERS: dict[str, str] = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
_QUARTER_START_MONTH: dict[str, str] = {"1": "01", "2": "04", "3": "07", "4": "10"}


def _period_to_timestamp(period: str) -> pd.Timestamp | None:
    """Convert an SDMX quarter id (``"2026-Q2"``) to a quarter-start Timestamp.

    Quarter-start dates match FRED's quarterly convention (e.g. Q2 -> 04-01),
    so the resulting series aligns with the FRED GDP series for momentum maths.

    Args:
        period: SDMX period identifier such as ``"2026-Q2"``.

    Returns:
        A ``pandas.Timestamp`` at the quarter start, or ``None`` if unparseable.
    """
    try:
        year, quarter = period.split("-Q")
        return pd.Timestamp(f"{year}-{_QUARTER_START_MONTH[quarter]}-01")
    except (ValueError, KeyError):
        return None


def fetch_cpi_yoy() -> pd.Series:
    """Fetch Australian All-groups CPI and return a YoY % series (quarterly).

    YoY is derived by compounding the trailing four quarterly changes, since the
    ABS CPI dataflow exposes the quarter-on-quarter measure reliably.

    Returns:
        A date-indexed ``pandas.Series`` of YoY percent values (named
        ``"AU_CPI_YoY"``), or an empty Series on any network/parse failure.
    """
    try:
        resp = requests.get(
            ABS_CPI_QOQ_URL, headers=_HEADERS,
            timeout=config.REQUEST_TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
        payload = resp.json()
    except (requests.RequestException, ValueError):
        return pd.Series(dtype="float64")

    try:
        structure = payload["data"]["structures"][0]
        periods = [v["id"] for v in structure["dimensions"]["observation"][0]["values"]]
        series = payload["data"]["dataSets"][0]["series"]
        observations = next(iter(series.values()))["observations"]
    except (KeyError, IndexError, StopIteration, TypeError):
        return pd.Series(dtype="float64")

    rows: list[tuple[pd.Timestamp, float]] = []
    for idx, value in observations.items():
        ts = _period_to_timestamp(periods[int(idx)])
        if ts is not None and value and value[0] is not None:
            rows.append((ts, float(value[0])))
    if len(rows) < 5:
        return pd.Series(dtype="float64")

    rows.sort()
    qoq = pd.Series(
        [v for _, v in rows], index=pd.DatetimeIndex([d for d, _ in rows])
    )
    # YoY = trailing four-quarter compounded QoQ growth.
    factors = 1.0 + qoq / 100.0
    yoy = (factors.rolling(4).apply(lambda x: x.prod(), raw=True) - 1.0) * 100.0
    return yoy.dropna().rename("AU_CPI_YoY")
