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
* **UK**      — ONS website time-series ``/data`` endpoint (CPI annual rate).
* **Argentina** — datos.gob.ar Series API (INDEC national IPC & EPH
  unemployment); ArgentinaDatos (BCRA 30-day deposit rate as a policy proxy).
"""

from __future__ import annotations

import pandas as pd
import requests

import config

_HEADERS: dict[str, str] = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
_OECD_PRICES: str = (
    "https://sdmx.oecd.org/public/rest/data/"
    "OECD.SDD.TPS,DSD_PRICES@DF_PRICES_ALL,1.0/"
)
# National feeds can return large payloads (ONS ~120KB, BCB ~120KB); give them a
# longer timeout so they survive the parallel cold-start fan-out.
_T = max(35, config.REQUEST_TIMEOUT_SECONDS)


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


# --- United Kingdom ---------------------------------------------------------
def gb_cpi_yoy() -> pd.Series:
    """UK CPI annual rate (%), from the ONS website time-series ``/data`` feed.

    Series D7G7 (CPI 12-month rate, all items) in dataset MM23. The value is
    already a YoY percent, so no transform is needed. The legacy
    ``api.ons.gov.uk`` service was decommissioned; the website's own ``/data``
    JSON endpoint remains available.

    Returns:
        A month-indexed YoY % Series, or empty on failure.
    """
    url = ("https://www.ons.gov.uk/economy/inflationandpriceindices/"
           "timeseries/d7g7/mm23/data")
    try:
        months = requests.get(url, headers=_HEADERS, timeout=_T).json()["months"]
    except (requests.RequestException, ValueError, KeyError):
        return _empty()
    dates, vals = [], []
    for entry in months:
        try:  # date like "2026 JUL" -> title-case for %b parsing
            dates.append(pd.to_datetime(entry["date"].title(), format="%Y %b"))
            vals.append(float(entry["value"]))
        except (KeyError, ValueError, TypeError):
            continue
    return pd.Series(vals, index=pd.DatetimeIndex(dates)).sort_index()


# --- Argentina --------------------------------------------------------------
def ar_cpi_yoy() -> pd.Series:
    """Argentina national IPC YoY %, from the datos.gob.ar Series API (INDEC).

    Fetches the national CPI index (base dic-2016) and derives YoY from it.

    Returns:
        A month-indexed YoY % Series, or empty on failure.
    """
    url = "https://apis.datos.gob.ar/series/api/series/"
    try:
        data = requests.get(
            url, headers=_HEADERS, timeout=_T,
            params={"ids": "148.3_INIVELNAL_DICI_M_26", "format": "json",
                    "limit": 1000, "collapse": "month"},
        ).json()["data"]
    except (requests.RequestException, ValueError, KeyError):
        return _empty()
    dates, vals = [], []
    for row in data:
        try:
            dates.append(pd.Timestamp(row[0]))
            vals.append(float(row[1]))
        except (IndexError, ValueError, TypeError):
            continue
    index = pd.Series(vals, index=pd.DatetimeIndex(dates)).sort_index()
    return (index.pct_change(12) * 100.0).dropna()


def ar_policy_rate() -> pd.Series:
    """Argentina policy-rate proxy: BCRA 30-day time-deposit rate (% TNA).

    The BCRA's own "tasa de política monetaria" series was discontinued in mid-
    2025 when the monetary framework changed, so there is no current official
    policy-rate feed. The 30-day wholesale deposit rate (from ArgentinaDatos,
    sourced from the BCRA) is the closest current money-market rate and serves as
    the stance proxy — consistent with the money-market proxies used for other
    non-US/EA economies.

    ArgentinaDatos reports this rate as a decimal fraction in the earlier history
    (e.g. ``0.31`` = 31%) but as a percentage number more recently (e.g. ``32.75``
    = 32.75%); values below 2 are therefore scaled by 100 so the series is a
    continuous percentage. (Argentine deposit TNAs never reached 200%, so no real
    percentage value is < 2 and no fraction is ≥ 2 — the split is unambiguous.)

    Returns:
        A date-indexed Series of the rate in percent, or empty on failure.
    """
    url = "https://api.argentinadatos.com/v1/finanzas/tasas/depositos30Dias"
    try:
        rows = requests.get(url, headers=_HEADERS, timeout=_T).json()
    except (requests.RequestException, ValueError):
        return _empty()
    dates, vals = [], []
    for r in rows:
        try:
            v = float(r["valor"])
            dates.append(pd.Timestamp(r["fecha"]))
            vals.append(v * 100.0 if v < 2 else v)
        except (KeyError, ValueError, TypeError):
            continue
    return pd.Series(vals, index=pd.DatetimeIndex(dates)).sort_index()


def ar_unemployment() -> pd.Series:
    """Argentina national unemployment rate (%), quarterly, via datos.gob.ar.

    INDEC's EPH national total unemployment (series ``45.2_ECTDT_0_T_33``). The
    API reports it as a fraction (``0.078`` = 7.8%), so it is scaled to percent.

    Returns:
        A quarter-indexed Series in percent, or empty on failure.
    """
    url = "https://apis.datos.gob.ar/series/api/series/"
    try:
        data = requests.get(
            url, headers=_HEADERS, timeout=_T,
            params={"ids": "45.2_ECTDT_0_T_33", "format": "json", "limit": 200},
        ).json()["data"]
    except (requests.RequestException, ValueError, KeyError):
        return _empty()
    dates, vals = [], []
    for row in data:
        try:  # parse the value first so a null row never desyncs the two lists
            value = float(row[1]) * 100.0
            date = pd.Timestamp(row[0])
        except (IndexError, ValueError, TypeError):
            continue
        dates.append(date)
        vals.append(value)
    return pd.Series(vals, index=pd.DatetimeIndex(dates)).sort_index()


# --- Japan ------------------------------------------------------------------
def jp_cpi_yoy() -> pd.Series:
    """Japan all-items CPI YoY %, live from the e-Stat API (Statistics Bureau).

    Requires a free ``config.ESTAT_APP_ID``. Uses statsDataId 0003427113 (2020-
    base CPI) with tab=3 (year-on-year %), cat01=0001 (all items), area=00000
    (all Japan) — so the value is already YoY. Returns empty when the app ID is
    absent, so the caller falls back to the FRED series.

    Returns:
        A month-indexed YoY % Series, or empty when unavailable.
    """
    app_id = config.ESTAT_APP_ID
    if not app_id:
        return _empty()
    url = "https://api.e-stat.go.jp/rest/3.0/app/json/getStatsData"
    try:
        payload = requests.get(
            url, headers=_HEADERS, timeout=_T,
            params={"appId": app_id, "statsDataId": "0003427113", "cdTab": "3",
                    "cdCat01": "0001", "cdArea": "00000", "metaGetFlg": "N",
                    "limit": "500"},
        ).json()
        values = payload["GET_STATS_DATA"]["STATISTICAL_DATA"]["DATA_INF"]["VALUE"]
    except (requests.RequestException, ValueError, KeyError):
        return _empty()
    if isinstance(values, dict):
        values = [values]
    dates, vals = [], []
    for v in values:
        code = str(v.get("@time", ""))  # e.g. "2026000404" -> year 2026, month 04
        try:
            year, month = int(code[:4]), int(code[-2:])
            value = float(v.get("$"))
        except (ValueError, TypeError):
            continue
        if 1 <= month <= 12:
            dates.append(pd.Timestamp(year, month, 1))
            vals.append(value)
    return pd.Series(vals, index=pd.DatetimeIndex(dates)).sort_index()


# --- New Zealand ------------------------------------------------------------
def nz_cpi_yoy() -> pd.Series:
    """New Zealand all-items CPI YoY %, from the OECD SDMX API (no key).

    NZ CPI is quarterly and FRED's mirror is stale, so this hits the OECD prices
    dataflow directly. It queries the NZ quarterly block and filters to
    MEASURE=CPI, EXPENDITURE=_T (all items), UNIT_MEASURE=PA, TRANSFORMATION=GY
    (year-on-year growth) — the value is already YoY.

    Returns:
        A quarter-indexed YoY % Series, or empty on failure.
    """
    url = (_OECD_PRICES + "NZL.Q......"
           "?startPeriod=2012-Q1&dimensionAtObservation=AllDimensions")
    headers = {"Accept": "application/vnd.sdmx.data+json", "User-Agent": "Mozilla/5.0"}
    try:
        payload = requests.get(url, headers=headers, timeout=_T).json()
        dims = payload["data"]["structures"][0]["dimensions"]["observation"]
        observations = payload["data"]["dataSets"][0]["observations"]
    except (requests.RequestException, ValueError, KeyError, IndexError):
        return _empty()

    ids = [d["id"] for d in dims]
    codes = [[v["id"] for v in d["values"]] for d in dims]
    try:
        pos = {k: ids.index(k) for k in ("MEASURE", "EXPENDITURE", "UNIT_MEASURE",
                                         "TRANSFORMATION", "TIME_PERIOD")}
    except ValueError:
        return _empty()
    want = {"MEASURE": "CPI", "EXPENDITURE": "_T",
            "UNIT_MEASURE": "PA", "TRANSFORMATION": "GY"}
    q_month = {"1": "01", "2": "04", "3": "07", "4": "10"}

    dates, vals = [], []
    for key, value in observations.items():
        idx = [int(x) for x in key.split(":")]
        if not all(codes[pos[dim]][idx[pos[dim]]] == code for dim, code in want.items()):
            continue
        period = codes[pos["TIME_PERIOD"]][idx[pos["TIME_PERIOD"]]]  # "2026-Q2"
        try:
            year, quarter = period.split("-Q")
            dates.append(pd.Timestamp(f"{year}-{q_month[quarter]}-01"))
            vals.append(float(value[0]))
        except (ValueError, KeyError, TypeError):
            continue
    return pd.Series(vals, index=pd.DatetimeIndex(dates)).sort_index()


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
