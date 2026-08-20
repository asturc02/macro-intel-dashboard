"""National statistics-office / central-bank data clients.

For economies whose FRED (OECD-mirrored) series are stale or missing, we go to
the authoritative national source. Every function returns a clean, date-indexed
``pandas.Series`` and degrades to an empty Series on any failure, so the rest of
the dashboard is unaffected. All sources are free and keyless.

Sources
-------
* **Brazil**  — Banco Central do Brasil (SGS) for the Selic policy rate; IBGE
  (servicodados) for IPCA inflation (YoY) and PNAD unemployment.
* **Canada**  — Statistics Canada (WDS) for the CPI; YoY derived from the index.
* **Norway**  — Statistics Norway (SSB PxWebApi) for the CPI; YoY from the index.
"""

from __future__ import annotations

import pandas as pd
import requests

import config

_HEADERS: dict[str, str] = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
_T = config.REQUEST_TIMEOUT_SECONDS


def _empty() -> pd.Series:
    """Return a typed empty Series (the graceful-failure value)."""
    return pd.Series(dtype="float64")


# --- Brazil -----------------------------------------------------------------
def br_selic() -> pd.Series:
    """Brazil Selic *target* policy rate (% p.a.), daily, via BCB SGS series 432.

    Returns:
        A date-indexed Series of the target rate, or empty on failure.
    """
    url = ("https://api.bcb.gov.br/dados/serie/bcdata.sgs.432/dados"
           "?formato=json&dataInicial=01/01/2018")
    try:
        rows = requests.get(url, headers=_HEADERS, timeout=_T).json()
    except (requests.RequestException, ValueError):
        return _empty()
    dates, vals = [], []
    for r in rows:
        try:
            dates.append(pd.to_datetime(r["data"], format="%d/%m/%Y"))
            vals.append(float(r["valor"]))
        except (KeyError, ValueError, TypeError):
            continue
    return pd.Series(vals, index=pd.DatetimeIndex(dates)).sort_index()


def _ibge(aggregate: int, variable: int) -> pd.Series:
    """Fetch an IBGE ``servicodados`` aggregate/variable as a monthly Series.

    Args:
        aggregate: IBGE aggregate (table) id.
        variable: Variable id within the aggregate.

    Returns:
        A date-indexed Series (period ``YYYYMM`` -> month start), or empty.
    """
    url = (f"https://servicodados.ibge.gov.br/api/v3/agregados/{aggregate}"
           f"/periodos/-120/variaveis/{variable}?localidades=N1[1]")
    try:
        payload = requests.get(url, headers=_HEADERS, timeout=_T).json()
        serie = payload[0]["resultados"][0]["series"][0]["serie"]
    except (requests.RequestException, ValueError, KeyError, IndexError):
        return _empty()
    dates, vals = [], []
    for period, value in serie.items():
        try:
            dates.append(pd.Timestamp(f"{period[:4]}-{period[4:6]}-01"))
            vals.append(float(value))
        except (ValueError, TypeError):
            continue
    return pd.Series(vals, index=pd.DatetimeIndex(dates)).sort_index()


def br_ipca_yoy() -> pd.Series:
    """Brazil IPCA inflation, YoY % (12-month accumulated) via IBGE aggregate 1737."""
    return _ibge(1737, 69)


def br_unemployment() -> pd.Series:
    """Brazil unemployment rate (%) via IBGE PNAD Contínua aggregate 4099."""
    return _ibge(4099, 4099)


# --- Canada -----------------------------------------------------------------
def ca_cpi_yoy() -> pd.Series:
    """Canada all-items CPI YoY %, derived from the StatCan index (vector 41690973)."""
    url = ("https://www150.statcan.gc.ca/t1/wds/rest/"
           "getDataFromVectorsAndLatestNPeriods")
    try:
        resp = requests.post(
            url, headers={"Content-Type": "application/json"},
            json=[{"vectorId": 41690973, "latestN": 60}], timeout=_T,
        )
        points = resp.json()[0]["object"]["vectorDataPoint"]
    except (requests.RequestException, ValueError, KeyError, IndexError):
        return _empty()
    dates, vals = [], []
    for p in points:
        try:
            dates.append(pd.Timestamp(p["refPer"]))
            vals.append(float(p["value"]))
        except (KeyError, ValueError, TypeError):
            continue
    index = pd.Series(vals, index=pd.DatetimeIndex(dates)).sort_index()
    return (index.pct_change(12) * 100.0).dropna()


# --- Norway -----------------------------------------------------------------
def no_cpi_yoy() -> pd.Series:
    """Norway all-items CPI YoY %, derived from the SSB index (table 03013)."""
    query = {
        "query": [
            {"code": "Konsumgrp",
             "selection": {"filter": "vs:CoiCop2016niva1", "values": ["TOTAL"]}},
            {"code": "ContentsCode",
             "selection": {"filter": "item", "values": ["KpiIndMnd"]}},
        ],
        "response": {"format": "json-stat2"},
    }
    try:
        resp = requests.post("https://data.ssb.no/api/v0/en/table/03013/",
                             json=query, headers=_HEADERS, timeout=_T)
        payload = resp.json()
        idx_map = payload["dimension"]["Tid"]["category"]["index"]
        values = payload["value"]
    except (requests.RequestException, ValueError, KeyError):
        return _empty()
    periods = sorted(idx_map, key=lambda k: idx_map[k])
    dates, vals = [], []
    for period, value in zip(periods, values):
        if value is None:
            continue
        try:  # SSB month code like "2025M12"
            year, month = period.split("M")
            dates.append(pd.Timestamp(f"{year}-{month}-01"))
            vals.append(float(value))
        except (ValueError, TypeError):
            continue
    index = pd.Series(vals, index=pd.DatetimeIndex(dates)).sort_index()
    return (index.pct_change(12) * 100.0).dropna()
