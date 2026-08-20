"""Macro Intelligence, Carry Trade & Yield Curve Dashboard (Streamlit UI).

A pre-open macro cockpit for G10 + key emerging-market economies: monetary-policy
divergence, real rates, carry-vs-USD, a volatility-adjusted carry ranking, the US
yield curve with its 10Y-2Y inversion signal, cross-country 10Y differentials, and
a multi-country time-series explorer. Data comes free from FRED (macro series) and
Frankfurter/ECB (FX). This module holds UI/layout only; data, FX, and quant logic
live in ``fred.py``, ``fx.py``, and ``metrics.py``.
"""

from __future__ import annotations

import datetime
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import abs_au
import config
import fred
import fx
import metrics
import national
import utils

BUILD_MARKER = "build: macro-intel v13 (UK ONS + AR INDEC)"

st.set_page_config(
    page_title="Macro Intelligence Dashboard",
    page_icon="🌐",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# --- iOS-style design system (GetVision-aligned) ----------------------------
# Deep-navy surfaces, teal accent, rounded layered cards, SF-style typography.
st.markdown(
    """
    <style>
      :root {
        --bg: #0A0E1A; --raised: #151B2C; --elevated: #1E263D;
        --accent: #1F8579; --text: #E7ECF3; --text2: #9AA6B8;
        --hair: rgba(255,255,255,0.06);
        --sf: -apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text",
              "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      }
      html, body, .stApp, [class*="css"] { font-family: var(--sf); }
      .stApp { background: var(--bg); }
      .block-container { padding-top: 2.4rem; max-width: min(1720px, 96vw); }

      h1 { font-weight: 700; letter-spacing: -0.02em; }
      h2, h3 { font-weight: 650; letter-spacing: -0.01em; }
      [data-testid="stCaptionContainer"], .stCaption { color: var(--text2); }

      /* Hero metric tiles -> rounded raised cards, big tabular numbers */
      [data-testid="stMetric"] {
        background: var(--raised); border: 1px solid var(--hair);
        border-radius: 18px; padding: 1rem 1.15rem;
        box-shadow: 0 1px 2px rgba(0,0,0,0.25);
      }
      [data-testid="stMetricLabel"] p {
        font-size: 0.72rem; font-weight: 600; letter-spacing: 0.02em;
        text-transform: uppercase; color: var(--text2);
      }
      [data-testid="stMetricValue"] {
        font-variant-numeric: tabular-nums; font-weight: 700;
        letter-spacing: -0.02em;
      }

      /* Charts sit on their own rounded cards */
      [data-testid="stPlotlyChart"] {
        background: var(--raised); border: 1px solid var(--hair);
        border-radius: 18px; padding: 0.6rem 0.7rem;
        box-shadow: 0 1px 2px rgba(0,0,0,0.25);
      }

      /* Dataframe -> rounded card */
      [data-testid="stDataFrame"] {
        border-radius: 16px; overflow: hidden; border: 1px solid var(--hair);
      }

      /* Tabs -> iOS segmented control */
      .stTabs [data-baseweb="tab-list"] {
        gap: 4px; background: var(--raised); padding: 5px;
        border-radius: 14px; border: 1px solid var(--hair);
      }
      .stTabs [data-baseweb="tab"] {
        height: 38px; border-radius: 10px; padding: 0 18px;
        color: var(--text2); font-weight: 600; font-size: 0.9rem;
      }
      .stTabs [data-baseweb="tab"]:hover { color: var(--text); }
      .stTabs [aria-selected="true"] {
        background: var(--accent) !important; color: #fff !important;
      }
      .stTabs [data-baseweb="tab-highlight"],
      .stTabs [data-baseweb="tab-border"] { background: transparent !important; }

      /* Buttons -> teal pills */
      .stButton > button {
        border-radius: 999px; border: 0; background: var(--accent);
        color: #fff; font-weight: 600; padding: 0.5rem 1.1rem;
        transition: filter 0.15s ease;
      }
      .stButton > button:hover { filter: brightness(1.08); color: #fff; }

      /* Segmented control (history window) accent */
      [data-testid="stSegmentedControl"] button[aria-checked="true"],
      [data-baseweb="segmented-control"] [aria-checked="true"] {
        background: var(--accent) !important; color: #fff !important;
      }

      /* Inputs / multiselect -> rounded, raised */
      [data-baseweb="select"] > div, .stTextInput input,
      [data-baseweb="input"] {
        border-radius: 12px !important; background: var(--raised) !important;
      }
      [data-baseweb="tag"] { background: var(--accent) !important; border-radius: 8px !important; }

      /* Sidebar */
      [data-testid="stSidebar"] { background: #0C1120; border-right: 1px solid var(--hair); }
      [data-testid="stSidebar"] .stButton > button { width: 100%; }

      /* Trim default header chrome */
      [data-testid="stHeader"] { background: transparent; }

      /* Remove the sidebar entirely (controls now live in the top Menu) */
      [data-testid="stSidebar"],
      [data-testid="stSidebarCollapsedControl"],
      [data-testid="collapsedControl"] { display: none !important; }

      /* Top "Menu" popover trigger -> teal pill, right-aligned */
      [data-testid="stPopover"] button {
        border-radius: 999px; border: 1px solid var(--hair);
        background: var(--raised); color: var(--text); font-weight: 600;
      }
      [data-testid="stPopover"] button:hover { background: var(--elevated); }

      /* Footer */
      .mi-footer { color: var(--text2); font-size: 0.85rem; line-height: 1.6; }
      .mi-footer a { color: var(--accent); text-decoration: none; }
      .mi-foot-h { color: var(--text); font-weight: 700; font-size: 0.72rem;
                   letter-spacing: 0.06em; text-transform: uppercase;
                   margin-bottom: 0.35rem; }
    </style>
    """,
    unsafe_allow_html=True,
)


# ============================================================================
# Cached data access
# ============================================================================
@st.cache_data(ttl=config.CACHE_TTL_SECONDS, show_spinner=False)
def get_series(series_id: str | None, api_key: str, start: str | None) -> pd.Series:
    """Cached wrapper around :func:`fred.fetch_series`.

    Args:
        series_id: FRED series ID (``None``/empty returns an empty Series).
        api_key: Resolved FRED key (part of the cache key).
        start: Optional ISO start date.

    Returns:
        A date-indexed float Series (possibly empty).
    """
    if not series_id:
        return pd.Series(dtype="float64")
    return fred.fetch_series(series_id, api_key=api_key, start=start)


def metric_series(
    country: config.Country, metric: str, api_key: str, start: str | None = None
) -> pd.Series:
    """Return a display-ready series for a country metric.

    Handles the index-vs-YoY distinction: for economies whose CPI series is a
    price index (``cpi_is_index``), YoY is computed from full history and then
    sliced to the requested window, so short windows still yield a valid YoY.

    Args:
        country: The economy.
        metric: One of ``policy_rate`` / ``cpi_yoy`` / ``unemployment`` / ``y10``.
        api_key: Resolved FRED key.
        start: Optional ISO lower bound for the window.

    Returns:
        A date-indexed Series in display units (possibly empty).
    """
    # National-source override (e.g. ABS AU CPI, BCB Selic) takes precedence
    # over the stale/missing FRED series for that (country, metric).
    override = NATIONAL_OVERRIDES.get((country.code, metric))
    if override is not None:
        series = override()
    else:
        sid = getattr(country, metric)
        if not sid:
            return pd.Series(dtype="float64")
        if metric == "cpi_yoy" and country.cpi_is_index:
            series = fred.to_yoy(get_series(sid, api_key, None))
        else:
            series = get_series(sid, api_key, start)
    if start and not series.empty:
        series = series[series.index >= pd.Timestamp(start)]
    return series


@st.cache_data(ttl=config.CACHE_TTL_SECONDS, show_spinner=False)
def get_release_dates(release_id: int, api_key: str) -> list[str]:
    """Cached wrapper around :func:`fred.fetch_release_dates`.

    Args:
        release_id: FRED release ID.
        api_key: Resolved FRED key (part of the cache key).

    Returns:
        A list of ISO date strings (possibly empty).
    """
    return fred.fetch_release_dates(release_id, api_key=api_key)


@st.cache_data(ttl=config.CACHE_TTL_SECONDS, show_spinner=False)
def get_fx_vol(currency: str) -> float | None:
    """Cached annualized realized FX volatility versus USD.

    Args:
        currency: ISO currency code.

    Returns:
        Annualized vol in percent, or ``None``.
    """
    return fx.annualized_vol(currency)


@st.cache_data(ttl=config.CACHE_TTL_SECONDS, show_spinner=False)
def get_au_cpi_yoy() -> pd.Series:
    """Cached Australian CPI YoY from the ABS national feed (no key needed)."""
    return abs_au.fetch_cpi_yoy()


@st.cache_data(ttl=config.CACHE_TTL_SECONDS, show_spinner=False)
def _nat(name: str) -> pd.Series:
    """Cached dispatch to a national-source function by name."""
    return {
        "br_selic": national.br_selic,
        "br_ipca_yoy": national.br_ipca_yoy,
        "br_unemployment": national.br_unemployment,
        "ca_cpi_yoy": national.ca_cpi_yoy,
        "no_cpi_yoy": national.no_cpi_yoy,
        "gb_cpi_yoy": national.gb_cpi_yoy,
        "ar_cpi_yoy": national.ar_cpi_yoy,
    }[name]()


# (country_code, metric) -> a zero-arg callable returning the override Series.
# These replace stale/missing FRED series with authoritative national sources.
NATIONAL_OVERRIDES: dict[tuple[str, str], object] = {
    ("AU", "cpi_yoy"): get_au_cpi_yoy,
    ("BR", "policy_rate"): lambda: _nat("br_selic"),
    ("BR", "cpi_yoy"): lambda: _nat("br_ipca_yoy"),
    ("BR", "unemployment"): lambda: _nat("br_unemployment"),
    ("CA", "cpi_yoy"): lambda: _nat("ca_cpi_yoy"),
    ("NO", "cpi_yoy"): lambda: _nat("no_cpi_yoy"),
    ("GB", "cpi_yoy"): lambda: _nat("gb_cpi_yoy"),
    ("AR", "cpi_yoy"): lambda: _nat("ar_cpi_yoy"),
}
# Human-readable source labels for the Data Health panel.
SOURCE_LABEL: dict[tuple[str, str], str] = {
    ("AU", "cpi_yoy"): "ABS (SDMX)",
    ("BR", "policy_rate"): "BCB Selic (SGS 432)",
    ("BR", "cpi_yoy"): "IBGE IPCA",
    ("BR", "unemployment"): "IBGE PNAD",
    ("CA", "cpi_yoy"): "StatCan (v41690973)",
    ("NO", "cpi_yoy"): "SSB (03013)",
    ("GB", "cpi_yoy"): "ONS (D7G7)",
    ("AR", "cpi_yoy"): "INDEC (datos.gob.ar)",
}


def warm_cache(api_key: str) -> None:
    """Pre-fetch all snapshot/health series and FX vols in parallel.

    FRED latency is highly variable; fetching ~50 series sequentially can take
    over a minute on a cold cache. Fanning the requests out across a thread pool
    turns that into roughly one round-trip. Each call populates the same
    ``st.cache_data`` entries the rest of the app reads, so subsequent access is
    an instant cache hit. Safe because the target functions perform pure HTTP
    (no Streamlit calls) inside the worker threads.

    Args:
        api_key: Resolved FRED key.
    """
    series_ids: set[str] = set(config.US_CURVE.values())
    series_ids.update({config.SPREAD_10Y_2Y, config.SPREAD_10Y_3M})
    for c in config.COUNTRIES:
        for attr in ("policy_rate", "cpi_yoy", "unemployment", "y10", "gdp_qoq"):
            sid = getattr(c, attr)
            if sid:
                series_ids.add(sid)
    for label, sid, transform, note in (
        config.LEADING_EMPLOYMENT + config.LEADING_INFLATION
    ):
        series_ids.add(sid)
    currencies = [c.currency for c in config.COUNTRIES if c.currency != "USD"]

    with ThreadPoolExecutor(max_workers=10) as pool:
        for sid in series_ids:
            pool.submit(get_series, sid, api_key, None)
        for ccy in currencies:
            pool.submit(get_fx_vol, ccy)
        for _name, rid, _tier in config.KEY_RELEASES:
            pool.submit(get_release_dates, rid, api_key)
        pool.submit(get_au_cpi_yoy)  # ABS national CPI (Australia)
        for nat_name in ("br_selic", "br_ipca_yoy", "br_unemployment",
                         "ca_cpi_yoy", "no_cpi_yoy", "gb_cpi_yoy", "ar_cpi_yoy"):
            pool.submit(_nat, nat_name)


@st.cache_data(ttl=config.CACHE_TTL_SECONDS, show_spinner=False)
def build_snapshot(api_key: str) -> pd.DataFrame:
    """Build the cross-country macro snapshot used by the Carry matrix.

    For every configured economy this resolves the latest policy rate, CPI YoY,
    unemployment, and 10Y yield, then derives the real rate, carry-vs-USD, 10Y
    differential, 6-month rate trajectory, monetary stance, FX volatility, and a
    volatility-adjusted carry ("implied Sharpe").

    Args:
        api_key: Resolved FRED key.

    Returns:
        A DataFrame indexed by country code with one row per economy.
    """
    # Base (US) legs for carry / differential calculations.
    us = config.COUNTRY_BY_CODE[config.BASE_COUNTRY]
    us_policy = fred.latest(metric_series(us, "policy_rate", api_key))[1]
    us_y10 = fred.latest(metric_series(us, "y10", api_key))[1]

    rows: list[dict] = []
    for c in config.COUNTRIES:
        # metric_series applies national-source overrides where configured.
        policy = fred.latest(metric_series(c, "policy_rate", api_key))[1]
        cpi = fred.latest(metric_series(c, "cpi_yoy", api_key))[1]
        unemp = fred.latest(metric_series(c, "unemployment", api_key))[1]
        y10 = fred.latest(metric_series(c, "y10", api_key))[1]
        rate_chg = fred.change_over(metric_series(c, "policy_rate", api_key), 6)

        # GDP: latest quarter's real QoQ growth, annualized for a comparable
        # baseline (matches the standard "annualized rate" reporting).
        gdp_q = fred.latest(get_series(c.gdp_qoq, api_key, None))[1] if c.gdp_qoq else None
        gdp = round(((1 + gdp_q / 100) ** 4 - 1) * 100, 2) if gdp_q is not None else None

        carry = metrics.carry_vs_base(policy, us_policy)
        vol = get_fx_vol(c.currency) if c.currency != "USD" else None
        # Stance needs a policy-rate trajectory; without it (some EM), inflation
        # alone is not a stance signal, so report n/a rather than a false "Hawk".
        stance = (
            utils.stance_badge(
                metrics.classify_stance(rate_chg, cpi, c.inflation_target)
            )
            if policy is not None
            else "➖ n/a"
        )
        rows.append(
            {
                "code": c.code,
                "Economy": c.name,
                "CCY": c.currency,
                "Central Bank": c.central_bank,
                "Stance": stance,
                "Policy %": policy,
                "CPI YoY %": cpi,
                "Real Rate %": metrics.real_rate(policy, cpi),
                "10Y %": y10,
                "GDP %": gdp,
                "Carry vs USD": carry,
                "10Y vs US": metrics.yield_diff_vs_base(y10, us_y10),
                "Unemp %": unemp,
                "FX Vol %": round(vol, 1) if vol is not None else None,
                "Carry/Vol": metrics.implied_sharpe(carry, vol),
                "EM": c.is_emerging,
            }
        )
    return pd.DataFrame(rows).set_index("code")


def _style_fig(fig: go.Figure, height: int = 420) -> go.Figure:
    """Apply the shared dark theme to a Plotly figure.

    Args:
        fig: The figure to style.
        height: Pixel height.

    Returns:
        The same figure, restyled in place.
    """
    sf_font = '-apple-system, BlinkMacSystemFont, "SF Pro Display", "Segoe UI", sans-serif'
    # Only reserve top space / render a title when one was actually set — this
    # avoids Plotly printing a literal "undefined" on title-less mini charts.
    has_title = bool(fig.layout.title.text)
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",   # inherit the card surface behind it
        plot_bgcolor="rgba(0,0,0,0)",
        height=height,
        # Extra top room so a top-right legend never collides with the title;
        # a little right room so outside bar labels aren't clipped.
        margin=dict(l=10, r=26, t=58 if has_title else 16, b=10),
        font=dict(family=sf_font, color=config.COLOR_TEXT_SEC, size=13),
        # Title top-LEFT, legend top-RIGHT -> they share the top band without overlap.
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=1, xanchor="right",
                    font=dict(color=config.COLOR_TEXT_SEC)),
        hovermode="x unified",
        hoverlabel=dict(bgcolor=config.COLOR_ELEVATED, font_size=12,
                        font_family=sf_font, bordercolor="rgba(0,0,0,0)"),
        colorway=list(config.PALETTE),
    )
    if has_title:
        fig.update_layout(title=dict(
            text=fig.layout.title.text, x=0, xanchor="left", y=0.97, yanchor="top",
            font=dict(family=sf_font, color=config.COLOR_TEXT, size=15),
        ))
    fig.update_xaxes(gridcolor=config.COLOR_GRID, zeroline=False,
                     linecolor=config.COLOR_GRID)
    fig.update_yaxes(gridcolor=config.COLOR_GRID, zeroline=False,
                     linecolor=config.COLOR_GRID)
    return fig


# ============================================================================
# Top menu, footer & shared controls
# ============================================================================
def render_menu() -> str:
    """Render the top-right ``☰ Menu`` popover and return the resolved FRED key.

    Replaces the sidebar: the API key input and data refresh live in a compact
    popover so the main canvas is uncluttered.

    Returns:
        The API key to use (popover input takes precedence over the env key).
    """
    with st.popover("☰  Menu", use_container_width=True):
        st.markdown("**🔑 FRED API key**")
        st.caption(
            "Free key from "
            "[fredaccount.stlouisfed.org](https://fredaccount.stlouisfed.org/apikeys). "
            "Used only in your session; nothing is stored."
        )
        user_key = st.text_input(
            "FRED API key", type="password", label_visibility="collapsed",
            placeholder="Paste your free FRED API key…", key="fred_key_input",
        )
        if st.button("🔄 Refresh data", use_container_width=True):
            st.cache_data.clear()
            st.toast("Cache cleared — pulling fresh data.")
            st.rerun()
    return (user_key or "").strip() or (config.FRED_API_KEY or "")


def render_footer() -> None:
    """Render the bottom footer with Data & Info and Contact columns."""
    st.divider()
    left, right = st.columns(2)
    with left:
        st.markdown(
            """
            <div class="mi-footer">
              <div class="mi-foot-h">Data &amp; Info</div>
              Sources: <a href="https://fred.stlouisfed.org/">FRED</a>,
              <a href="https://www.frankfurter.app/">Frankfurter</a>/ECB,
              <a href="https://www.abs.gov.au/">ABS</a> (AU),
              <a href="https://www.bcb.gov.br/">BCB</a> &amp;
              <a href="https://www.ibge.gov.br/">IBGE</a> (BR),
              <a href="https://www.statcan.gc.ca/">StatCan</a> (CA),
              <a href="https://www.ssb.no/en">SSB</a> (NO),
              <a href="https://www.ons.gov.uk/">ONS</a> (UK),
              <a href="https://datos.gob.ar/">INDEC</a> (AR).<br>
              Portfolio project for educational purposes — <b>not financial advice</b>.
            </div>
            """,
            unsafe_allow_html=True,
        )
    with right:
        st.markdown(
            f"""
            <div class="mi-footer">
              <div class="mi-foot-h">Contact</div>
              Built by <b>Cristopher Astur</b> · UBA Economist<br>
              <a href="mailto:asturcristopher@gmail.com">asturcristopher@gmail.com</a><br>
              Related:
              <a href="https://macro-sentiment-dashboard.streamlit.app/">Fed Sentiment</a> ·
              <a href="https://inflacion-nowcast.streamlit.app/">Inflación Nowcast</a>
              <div style="opacity:0.5; margin-top:0.4rem; font-size:0.75rem;">{BUILD_MARKER}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def window_control(key: str, default: str = "5Y") -> int | None:
    """Render a contextual history-window segmented control.

    Args:
        key: Unique Streamlit widget key (windows are per-section, not global).
        default: Default window label.

    Returns:
        The number of years for the chosen window, or ``None`` for ``Max``.
    """
    label = st.segmented_control(
        "History window", options=list(config.WINDOW_YEARS.keys()),
        default=default, key=key,
    )
    return config.WINDOW_YEARS.get(label or default, config.WINDOW_YEARS[default])


def palette_picker(key: str) -> tuple[str, ...]:
    """Render a color-palette dropdown for comparison charts.

    Args:
        key: Unique Streamlit widget key.

    Returns:
        The tuple of hex colors for the selected palette.
    """
    name = st.selectbox("Chart colors", list(config.PALETTES), key=key)
    return config.PALETTES[name]


# ============================================================================
# Modules
# ============================================================================
def render_country_detail(code: str, api_key: str, snap: pd.DataFrame) -> None:
    """Render a TradingEconomics-style deep-dive for one economy.

    Shows a header, a grid of current-value tiles, and a 2×2 grid of historical
    charts (policy rate, CPI, unemployment, 10Y) over a selectable window.

    Args:
        code: Country code selected in the matrix.
        api_key: Resolved FRED key.
        snap: The cross-country snapshot (for current values).
    """
    c = config.COUNTRY_BY_CODE[code]
    row = snap.loc[code]
    flag = config.FLAGS.get(code, "")

    st.divider()
    head, clear = st.columns([5, 1])
    with head:
        st.markdown(f"### {flag}  {c.name} — deep dive")
        tag = " · emerging market" if c.is_emerging else ""
        st.caption(
            f"{c.currency} · {c.central_bank} · inflation target "
            f"{c.inflation_target:.1f}%{tag}"
        )
    with clear:
        if st.button("✕ Close", use_container_width=True, key=f"close_{code}"):
            st.session_state.pop("carry_table", None)
            st.rerun()

    # --- Current-value tiles ------------------------------------------------
    r1 = st.columns(4)
    r1[0].metric("Policy rate", utils.fmt(row["Policy %"], "%"))
    r1[1].metric("CPI YoY", utils.fmt(row["CPI YoY %"], "%"))
    r1[2].metric("Real rate", utils.fmt(row["Real Rate %"], "%"))
    r1[3].metric("Stance", row["Stance"])
    r2 = st.columns(4)
    r2[0].metric("GDP (annualized)", utils.fmt(row["GDP %"], "%"))
    r2[1].metric("Unemployment", utils.fmt(row["Unemp %"], "%"))
    r2[2].metric("10Y yield", utils.fmt(row["10Y %"], "%"))
    r2[3].metric("10Y vs US", utils.fmt_signed(row["10Y vs US"], " pp"))

    # --- Historical charts (2×2) -------------------------------------------
    window_years = window_control(f"detail_window_{code}", default="5Y")
    start = utils.window_start(window_years)
    charts = [
        ("policy_rate", "Policy rate (%)"),
        ("cpi_yoy", "CPI YoY (%)"),
        ("unemployment", "Unemployment (%)"),
        ("y10", "10Y yield (%)"),
    ]
    grid = st.columns(2)
    for i, (metric, label) in enumerate(charts):
        with grid[i % 2]:
            s = metric_series(c, metric, api_key, start)
            if s.empty:
                st.info(f"{label}: no free data for {c.name}.")
                continue
            fig = go.Figure(go.Scatter(
                x=s.index, y=s.values, mode="lines",
                line=dict(color=config.COLOR_ACCENT, width=2),
                fill="tozeroy", fillcolor="rgba(31,133,121,0.08)",
            ))
            fig.update_layout(title=label, xaxis_title="Date", yaxis_title="")
            st.plotly_chart(_style_fig(fig, 280), use_container_width=True,
                            key=f"detail_{code}_{metric}")


def module_carry(snap: pd.DataFrame, api_key: str) -> None:
    """Render the Carry Trade & Monetary Divergence module.

    Args:
        snap: The cross-country snapshot DataFrame.
        api_key: Resolved FRED key (for the country deep-dive charts).
    """
    st.subheader("Carry Trade & Monetary Divergence Matrix")
    st.caption(
        "Real rate = policy rate − CPI YoY. Carry & 10Y differential are vs USD. "
        "Carry/Vol divides interest-rate carry by annualized realized FX vol — a "
        "transparent, risk-adjusted ranking of carry attractiveness."
    )
    st.caption(
        "ℹ️ Policy rate is the actual target for US (Fed) & EA (ECB); for other "
        "economies it's a money-market proxy (3m interbank / overnight). GDP is "
        "the latest quarter's real growth, annualized. CPI is now current for "
        "US/EA plus AU/CA/NO/GB (ABS/StatCan/SSB/ONS) and AR (INDEC); Brazil adds "
        "BCB Selic + IBGE. Only JP/NZ CPI still lag on free data. See **Data "
        "Health** for the exact source & vintage of every cell."
    )

    hawks = (snap["Stance"].str.contains("Hawk")).sum()
    doves = (snap["Stance"].str.contains("Dove")).sum()
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Economies", f"{len(snap)}")
    c2.metric("🦅 Hawkish", f"{hawks}")
    c3.metric("🕊️ Dovish", f"{doves}")
    best = snap["Carry/Vol"].dropna()
    if not best.empty:
        top = best.idxmax()
        c4.metric("Best carry/vol", snap.loc[top, "CCY"], f"{best.max():+.2f}")

    display_cols = [
        "Economy", "CCY", "Stance", "Policy %", "CPI YoY %", "Real Rate %",
        "GDP %", "10Y %", "Carry vs USD", "10Y vs US", "Unemp %", "FX Vol %",
        "Carry/Vol",
    ]
    num_cols = [
        "Policy %", "CPI YoY %", "Real Rate %", "GDP %", "10Y %", "Carry vs USD",
        "10Y vs US", "Unemp %", "FX Vol %", "Carry/Vol",
    ]
    col_cfg = {c: st.column_config.NumberColumn(c, format="%.2f") for c in num_cols}
    col_cfg["Economy"] = st.column_config.TextColumn("Economy", width="medium")
    col_cfg["GDP %"] = st.column_config.NumberColumn(
        "GDP %", format="%.2f", help="Latest quarter real GDP growth, annualized"
    )
    st.caption("💡 Click any row to open that economy's deep-dive.")
    # Expand the table so every economy is visible without scrolling, and make
    # rows selectable to drill into a country detail view.
    event = st.dataframe(
        snap[display_cols],
        use_container_width=True,
        hide_index=True,
        height=(len(snap) + 1) * 35 + 3,
        column_config=col_cfg,
        on_select="rerun",
        selection_mode="single-row",
        key="carry_table",
    )
    selected = list(event.selection["rows"]) if event is not None else []
    if selected:
        render_country_detail(snap.index[selected[0]], api_key, snap)
        return

    left, right = st.columns(2)
    with left:
        rr = snap.dropna(subset=["Real Rate %"]).sort_values("Real Rate %")
        if rr.empty:
            st.info("No real-rate data resolved yet.")
        else:
            colors = [
                config.COLOR_DOVE if v < 0 else config.COLOR_HAWK
                for v in rr["Real Rate %"]
            ]
            fig = go.Figure(
                go.Bar(
                    x=rr["Real Rate %"], y=rr["CCY"], orientation="h",
                    marker_color=colors,
                    text=[utils.fmt_signed(v) for v in rr["Real Rate %"]],
                    textposition="outside",
                )
            )
            fig.update_layout(
                title="Real policy rate by currency",
                xaxis_title="Real rate (pp)", yaxis_title="Currency",
            )
            # Let outside labels render past the bar ends without clipping.
            fig.update_traces(cliponaxis=False)
            vmin, vmax = rr["Real Rate %"].min(), rr["Real Rate %"].max()
            fig.update_xaxes(range=[vmin - 0.7, vmax + 0.7])
            st.plotly_chart(_style_fig(fig, 380), use_container_width=True)

    with right:
        sc = snap.dropna(subset=["Carry vs USD", "FX Vol %"])
        if sc.empty:
            st.info("No carry/vol data resolved yet.")
        else:
            fig = go.Figure(
                go.Scatter(
                    x=sc["FX Vol %"], y=sc["Carry vs USD"], mode="markers+text",
                    text=sc["CCY"], textposition="top center",
                    marker=dict(
                        size=13, color=sc["Carry vs USD"],
                        colorscale="RdYlGn", line=dict(width=1, color="#333"),
                    ),
                )
            )
            fig.update_layout(
                title="Carry vs USD vs FX volatility",
                xaxis_title="Annualized FX vol (%)",
                yaxis_title="Carry vs USD (pp)",
            )
            fig.add_hline(y=0, line_color=config.COLOR_NEUTRAL, line_width=1)
            st.plotly_chart(_style_fig(fig, 380), use_container_width=True)


def module_regime(api_key: str) -> None:
    """Render the Macro Regime Matrix (growth × inflation quadrant model).

    Args:
        api_key: Resolved FRED key.
    """
    st.subheader("Macro Regime Matrix")
    st.caption(
        "Each economy is placed by **growth momentum** (x) and **inflation "
        "momentum** (y) — the change over the last ~1 year. Right = growth "
        "accelerating, up = inflation rising. The four quadrants are the classic "
        "growth/inflation regimes that drive cross-asset positioning."
    )

    pts: list[dict] = []
    for c in config.COUNTRIES:
        growth = (fred.change_over(get_series(c.gdp_qoq, api_key, None), 12)
                  if c.gdp_qoq else None)
        infl = fred.change_over(metric_series(c, "cpi_yoy", api_key), 12)
        if growth is None or infl is None:
            continue
        pts.append({
            "Economy": c.name, "CCY": c.currency,
            "Regime": metrics.classify_regime(growth, infl),
            "GDP momentum": round(growth, 2), "CPI momentum": round(infl, 2),
        })
    if not pts:
        st.info("Not enough free GDP/CPI history to classify regimes yet.")
        return
    df = pd.DataFrame(pts)

    order = [config.GOLDILOCKS, config.OVERHEATING, config.STAGFLATION,
             config.CONTRACTION]
    labels = {config.GOLDILOCKS: "🟢 Goldilocks", config.OVERHEATING: "🟠 Overheating",
              config.STAGFLATION: "🔴 Stagflation", config.CONTRACTION: "🔵 Contraction"}
    for col, reg in zip(st.columns(4), order):
        col.metric(labels[reg], int((df["Regime"] == reg).sum()))

    xr = max(0.5, df["GDP momentum"].abs().max() * 1.4)
    yr = max(0.5, df["CPI momentum"].abs().max() * 1.4)
    fig = go.Figure()
    for reg in order:
        sub = df[df["Regime"] == reg]
        if sub.empty:
            continue
        fig.add_trace(go.Scatter(
            x=sub["GDP momentum"], y=sub["CPI momentum"], mode="markers+text",
            text=sub["CCY"], textposition="top center", name=reg,
            marker=dict(size=15, color=config.REGIME_COLORS[reg],
                        line=dict(width=1, color=config.COLOR_BG)),
        ))
    fig.add_hline(y=0, line_color=config.COLOR_NEUTRAL, line_width=1)
    fig.add_vline(x=0, line_color=config.COLOR_NEUTRAL, line_width=1)
    corners = [
        (xr * 0.72, yr * 0.88, "OVERHEATING", config.OVERHEATING),
        (-xr * 0.72, yr * 0.88, "STAGFLATION", config.STAGFLATION),
        (xr * 0.72, -yr * 0.88, "GOLDILOCKS", config.GOLDILOCKS),
        (-xr * 0.72, -yr * 0.88, "CONTRACTION", config.CONTRACTION),
    ]
    for x, y, txt, reg in corners:
        fig.add_annotation(x=x, y=y, text=txt, showarrow=False, opacity=0.55,
                           font=dict(color=config.REGIME_COLORS[reg], size=12))
    fig.update_layout(
        title="Growth–Inflation regime map",
        xaxis_title="←  GDP growth momentum (pp)  →",
        yaxis_title="←  CPI momentum (pp)  →",
    )
    fig.update_xaxes(range=[-xr, xr])
    fig.update_yaxes(range=[-yr, yr])
    st.plotly_chart(_style_fig(fig, 500), use_container_width=True)

    st.dataframe(
        df.sort_values("Regime"), use_container_width=True, hide_index=True,
        column_config={
            "GDP momentum": st.column_config.NumberColumn("GDP momentum", format="%+.2f"),
            "CPI momentum": st.column_config.NumberColumn("CPI momentum", format="%+.2f"),
        },
    )
    st.caption(
        "Momentum = latest value minus the value ~12 months earlier (GDP QoQ "
        "growth; CPI YoY). Economies without free GDP data (e.g. Argentina) are "
        "omitted. Not investment advice."
    )


def module_curves(api_key: str) -> None:
    """Render the Yield Curve module (US curve, inversion, cross-country 10Y).

    Args:
        api_key: Resolved FRED key.
    """
    st.subheader("Yield Curve Visualizer")

    # --- US par curve, now vs 6m/1y ago -----------------------------------
    curve_now, curve_6m, curve_12m, mats = [], [], [], []
    for label in config.US_CURVE_ORDER:
        s = get_series(config.US_CURVE[label], api_key, None)
        if s.empty:
            continue
        mats.append(label)
        curve_now.append(float(s.iloc[-1]))
        last_date = s.index[-1]
        s6 = s[s.index <= last_date - pd.DateOffset(months=6)]
        s12 = s[s.index <= last_date - pd.DateOffset(months=12)]
        curve_6m.append(float(s6.iloc[-1]) if not s6.empty else None)
        curve_12m.append(float(s12.iloc[-1]) if not s12.empty else None)

    if mats:
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=mats, y=curve_12m, name="12m ago",
                                 line=dict(color=config.COLOR_NEUTRAL, dash="dot")))
        fig.add_trace(go.Scatter(x=mats, y=curve_6m, name="6m ago",
                                 line=dict(color=config.COLOR_DOVE, dash="dash")))
        fig.add_trace(go.Scatter(x=mats, y=curve_now, name="Now",
                                 line=dict(color=config.COLOR_ACCENT, width=3),
                                 mode="lines+markers"))
        fig.update_layout(title="US Treasury par curve — now vs 6 & 12 months ago",
                          xaxis_title="Maturity", yaxis_title="Yield (%)")
        st.plotly_chart(_style_fig(fig, 380), use_container_width=True)
    else:
        st.info("US curve series did not resolve — check the FRED key / Data Health.")

    # --- Inversion & recession signals ------------------------------------
    st.markdown("###### Rate history")
    window_years = window_control("curves_window")
    start = utils.window_start(window_years)
    left, right = st.columns(2)
    with left:
        sp = get_series(config.SPREAD_10Y_2Y, api_key, start)
        if sp.empty:
            st.info("Spread series unavailable.")
        else:
            fig = go.Figure(go.Scatter(
                x=sp.index, y=sp.values, line=dict(color=config.COLOR_ACCENT),
                fill="tozeroy", fillcolor="rgba(31,133,121,0.18)", name="10Y-2Y",
            ))
            fig.add_hline(y=0, line_color=config.COLOR_HAWK, line_width=1)
            latest_val = float(sp.iloc[-1])
            state = "INVERTED ⚠️" if latest_val < 0 else "normal"
            fig.update_layout(
                title=f"10Y − 2Y spread — {latest_val:+.2f} pp ({state})",
                xaxis_title="Date", yaxis_title="Spread (pp)",
            )
            st.plotly_chart(_style_fig(fig, 340), use_container_width=True)

    with right:
        rows = []
        for c in config.COUNTRIES:
            s = get_series(c.y10, api_key, None)
            if not s.empty:
                rows.append((c.currency, float(s.iloc[-1])))
        if not rows:
            st.info("No 10Y series resolved.")
        else:
            rows.sort(key=lambda r: r[1])
            ccy = [r[0] for r in rows]
            vals = [r[1] for r in rows]
            fig = go.Figure(go.Bar(
                x=vals, y=ccy, orientation="h", marker_color=config.COLOR_DOVE,
                text=[f"{v:.2f}" for v in vals], textposition="outside",
            ))
            fig.update_layout(title="Cross-country 10Y yield (latest)",
                              xaxis_title="10Y yield (%)", yaxis_title="Currency")
            # Headroom + no clipping so the value labels are fully visible.
            fig.update_traces(cliponaxis=False)
            fig.update_xaxes(range=[0, max(vals) * 1.18])
            st.plotly_chart(_style_fig(fig, 340), use_container_width=True)

    # --- Overlay selected 10Y histories -----------------------------------
    st.markdown("###### Overlay 10Y yield history")
    ov1, ov2 = st.columns([3, 1])
    with ov1:
        codes = st.multiselect(
            "Economies", options=[c.code for c in config.COUNTRIES],
            default=["US", "EA", "JP"],
            format_func=lambda x: config.COUNTRY_BY_CODE[x].name, key="curve_overlay",
        )
    with ov2:
        palette = palette_picker("curve_palette")
    if codes:
        fig = go.Figure()
        for i, code in enumerate(codes):
            c = config.COUNTRY_BY_CODE[code]
            s = get_series(c.y10, api_key, start)
            if s.empty:
                continue
            fig.add_trace(go.Scatter(
                x=s.index, y=s.values, name=f"{c.currency} 10Y",
                line=dict(color=palette[i % len(palette)]),
            ))
        fig.update_layout(title="10Y yield history",
                          xaxis_title="Date", yaxis_title="Yield (%)")
        st.plotly_chart(_style_fig(fig, 380), use_container_width=True)


def module_timeseries(api_key: str) -> None:
    """Render the multi-country / multi-metric time-series explorer.

    Args:
        api_key: Resolved FRED key.
    """
    st.subheader("Time-Series Explorer")

    c1, c2 = st.columns([3, 2])
    with c1:
        codes = st.multiselect(
            "Economies", options=[c.code for c in config.COUNTRIES],
            default=["US"], format_func=lambda x: config.COUNTRY_BY_CODE[x].name,
            key="ts_codes",
        )
    with c2:
        metric_key = st.selectbox(
            "Metric", options=list(config.METRIC_LABELS.keys()),
            format_func=lambda k: config.METRIC_LABELS[k], key="ts_metric",
        )

    c3, c4 = st.columns([3, 1])
    with c3:
        window_years = window_control("ts_window")
    with c4:
        palette = palette_picker("ts_palette")
    start = utils.window_start(window_years)

    dual = st.checkbox(
        "Add a second metric on a right axis (uses the first economy)",
        value=False, key="ts_dual",
    )
    metric_key2 = None
    if dual:
        metric_key2 = st.selectbox(
            "Second metric", options=[k for k in config.METRIC_LABELS if k != metric_key],
            format_func=lambda k: config.METRIC_LABELS[k], key="ts_metric2",
        )

    if not codes:
        st.info("Pick at least one economy.")
        return

    fig = go.Figure()
    for i, code in enumerate(codes):
        c = config.COUNTRY_BY_CODE[code]
        s = metric_series(c, metric_key, api_key, start)
        if s.empty:
            continue
        fig.add_trace(go.Scatter(
            x=s.index, y=s.values, name=f"{c.currency} · {config.METRIC_LABELS[metric_key]}",
            line=dict(color=palette[i % len(palette)]),
        ))

    if metric_key2:
        c = config.COUNTRY_BY_CODE[codes[0]]
        s2 = metric_series(c, metric_key2, api_key, start)
        if not s2.empty:
            fig.add_trace(go.Scatter(
                x=s2.index, y=s2.values, name=f"{c.currency} · {config.METRIC_LABELS[metric_key2]}",
                line=dict(color=config.COLOR_ACCENT, dash="dash"), yaxis="y2",
            ))
            fig.update_layout(yaxis2=dict(
                title=config.METRIC_LABELS[metric_key2], overlaying="y",
                side="right", gridcolor=config.COLOR_GRID,
            ))

    fig.update_layout(
        title=f"{config.METRIC_LABELS[metric_key]} over time",
        xaxis_title="Date", yaxis_title=config.METRIC_LABELS[metric_key],
    )
    st.plotly_chart(_style_fig(fig, 460), use_container_width=True)


def _leading_row(
    sid: str, transform: str, api_key: str
) -> tuple[float | None, float | None, pd.Series]:
    """Compute the latest value, change vs prior, and display series for a series.

    Args:
        sid: FRED series ID.
        transform: ``level_k`` (level ÷ 1000), ``mom_diff_k`` (period change), or
            ``yoy`` (12-period % change from an index).
        api_key: Resolved FRED key.

    Returns:
        ``(latest, delta_vs_prior, display_series)``; latest/delta are ``None``
        when unavailable.
    """
    raw = get_series(sid, api_key, None)
    if raw.empty:
        return None, None, raw
    if transform == "level_k":
        disp = raw / 1000.0
    elif transform == "mom_diff_k":
        disp = raw.diff().dropna()
    elif transform == "yoy":
        disp = (raw.pct_change(12) * 100).dropna()
    else:
        disp = raw
    if disp.empty:
        return None, None, disp
    latest = float(disp.iloc[-1])
    delta = float(disp.iloc[-1] - disp.iloc[-2]) if len(disp) > 1 else None
    return latest, delta, disp


def module_leading(api_key: str) -> None:
    """Render the US leading / expectation indicators module.

    Args:
        api_key: Resolved FRED key.
    """
    st.subheader("Leading Indicators — United States")
    st.caption(
        "High-frequency, directional US series watched ahead of the major "
        "releases: employment tends to turn first, and **core PCE** is the Fed's "
        "preferred inflation gauge (prioritized over CPI)."
    )
    window_years = window_control("leading_window", default="2Y")
    start = utils.window_start(window_years)

    st.markdown("###### Employment — leads the cycle")
    for col, (label, sid, transform, note) in zip(
        st.columns(len(config.LEADING_EMPLOYMENT)), config.LEADING_EMPLOYMENT
    ):
        latest, delta, disp = _leading_row(sid, transform, api_key)
        with col:
            if latest is None:
                st.metric(label, "n/a")
                st.caption(note)
                continue
            # Rising jobless claims = softening labor market -> inverse (red up).
            invert = transform == "level_k"
            st.metric(
                label, f"{latest:,.0f}K",
                f"{delta:+,.0f}K" if delta is not None else None,
                delta_color="inverse" if invert else "normal",
            )
            d = disp[disp.index >= pd.Timestamp(start)] if start else disp
            fig = go.Figure(go.Scatter(
                x=d.index, y=d.values, mode="lines",
                line=dict(color=config.COLOR_ACCENT, width=2),
            ))
            fig.update_layout(margin=dict(l=0, r=0, t=6, b=0), showlegend=False)
            st.plotly_chart(_style_fig(fig, 140), use_container_width=True)
            st.caption(note)

    st.markdown("###### Inflation — Fed watches core PCE over CPI")
    yoy_series: dict[str, pd.Series] = {}
    for col, (label, sid, transform, note) in zip(
        st.columns(len(config.LEADING_INFLATION)), config.LEADING_INFLATION
    ):
        latest, delta, disp = _leading_row(sid, transform, api_key)
        yoy_series[label] = disp
        with col:
            if latest is None:
                st.metric(label, "n/a")
                st.caption(note)
                continue
            st.metric(
                label, f"{latest:.2f}%",
                f"{delta:+.2f} pp" if delta is not None else None,
                delta_color="off",
            )
            st.caption(note)

    fig = go.Figure()
    for i, (label, s) in enumerate(yoy_series.items()):
        if s is None or s.empty:
            continue
        d = s[s.index >= pd.Timestamp(start)] if start else s
        fig.add_trace(go.Scatter(
            x=d.index, y=d.values, name=label,
            line=dict(color=config.PALETTE[i % len(config.PALETTE)]),
        ))
    fig.add_hline(y=2.0, line_dash="dot", line_color=config.COLOR_NEUTRAL,
                  annotation_text="2% target")
    fig.update_layout(title="US inflation gauges (YoY %)",
                      xaxis_title="Date", yaxis_title="YoY %")
    st.plotly_chart(_style_fig(fig, 380), use_container_width=True)


def _gcal_link(title: str, date_iso: str) -> str:
    """Build a Google Calendar 'add event' template URL for an all-day event.

    Args:
        title: Event title.
        date_iso: Event date, ISO ``YYYY-MM-DD``.

    Returns:
        A https://www.google.com/calendar/render template URL.
    """
    start = date_iso.replace("-", "")
    end = (datetime.date.fromisoformat(date_iso) + datetime.timedelta(days=1)
           ).isoformat().replace("-", "")
    text = quote(f"{title} — US data release")
    details = quote("US macro data release date (FRED schedule). Free feed has "
                    "dates only, not consensus/forecast.")
    return (f"https://www.google.com/calendar/render?action=TEMPLATE&text={text}"
            f"&dates={start}/{end}&details={details}")


def _build_ics(events: list[tuple[str, str]]) -> str:
    """Build an iCalendar (.ics) document of all-day events.

    Args:
        events: List of ``(title, date_iso)`` pairs.

    Returns:
        The .ics text (CRLF-joined per the spec).
    """
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0",
             "PRODID:-//Macro Intelligence//US Calendar//EN", "CALSCALE:GREGORIAN"]
    for i, (title, date_iso) in enumerate(events):
        start = date_iso.replace("-", "")
        end = (datetime.date.fromisoformat(date_iso) + datetime.timedelta(days=1)
               ).isoformat().replace("-", "")
        lines += ["BEGIN:VEVENT", f"UID:{start}-{i}@macro-intel",
                  f"DTSTART;VALUE=DATE:{start}", f"DTEND;VALUE=DATE:{end}",
                  f"SUMMARY:{title} (US data)", "END:VEVENT"]
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines)


def module_calendar(api_key: str) -> None:
    """Render the US economic calendar (free FRED release schedule).

    Args:
        api_key: Resolved FRED key.
    """
    st.subheader("Economic Calendar — United States")
    st.caption(
        "Upcoming release dates for the major US indicators, from FRED's official "
        "release schedule. The free feed provides the **dates**, not consensus / "
        "forecast numbers (those require a paid provider)."
    )
    today = datetime.date.today()
    today_iso = today.isoformat()

    rows: list[dict] = []
    ics_events: list[tuple[str, str]] = []
    for name, rid, tier in config.KEY_RELEASES:
        dates = sorted(d for d in get_release_dates(rid, api_key) if d >= today_iso)
        if not dates:
            continue
        nxt = dates[0]
        days = (datetime.date.fromisoformat(nxt) - today).days
        rows.append({
            "Release": name, "Next release": nxt, "In (days)": days,
            "Impact": tier, "Add to Google Calendar": _gcal_link(name, nxt),
        })
        ics_events.extend((name, d) for d in dates[:4])

    if not rows:
        st.info("No upcoming release dates resolved.")
        return

    df = pd.DataFrame(rows).sort_values("In (days)").reset_index(drop=True)
    st.dataframe(
        df, use_container_width=True, hide_index=True,
        column_config={
            "In (days)": st.column_config.NumberColumn("In (days)", format="%d d"),
            "Add to Google Calendar": st.column_config.LinkColumn(
                "Add to Google Calendar", display_text="📅 Add"),
        },
    )

    ics_events.sort(key=lambda e: e[1])
    st.download_button(
        "⬇️ Download .ics  (import into Google / Apple / Outlook)",
        data=_build_ics(ics_events), file_name="us_macro_calendar.ics",
        mime="text/calendar",
    )
    st.caption(
        "The .ics bundles the next few dates of each release. Google Calendar → "
        "Settings → Import & export → Import."
    )


def module_health(api_key: str, snap: pd.DataFrame) -> None:
    """Render the Data Health panel: which FRED series resolved, latest values.

    Doubles as a live validator for the series registry — any ``n/a`` row is a
    series ID to review or a genuine free-data gap.

    Args:
        api_key: Resolved FRED key.
        snap: The snapshot (unused values but keeps signature parallel).
    """
    st.subheader("Data Health")
    st.caption(
        "Every configured FRED series and whether it resolved. ‘n/a’ = the free "
        "series is unavailable or the ID needs a fix. Transparency by design."
    )
    rows = []
    fields = [
        ("Policy rate", "policy_rate"),
        ("CPI YoY", "cpi_yoy"),
        ("Unemployment", "unemployment"),
        ("10Y yield", "y10"),
        ("Real GDP QoQ", "gdp_qoq"),
    ]
    for c in config.COUNTRIES:
        for label, attr in fields:
            has_override = (c.code, attr) in NATIONAL_OVERRIDES
            sid = getattr(c, attr)
            if not has_override and not sid:
                rows.append({"Economy": c.name, "Metric": label,
                             "Series ID": "—", "Latest": "n/a", "Value": "n/a"})
                continue
            series = metric_series(c, attr, api_key)
            source = SOURCE_LABEL.get((c.code, attr), sid)
            d, v = fred.latest(series)
            rows.append({
                "Economy": c.name, "Metric": label, "Series ID": source,
                "Latest": d.date().isoformat() if d is not None else "n/a",
                "Value": utils.fmt(v),
            })
    df = pd.DataFrame(rows)
    ok = (df["Value"] != "n/a").sum()
    st.metric("Series resolved", f"{ok} / {len(df)}")
    st.dataframe(df, use_container_width=True, hide_index=True)


# ============================================================================
# Main
# ============================================================================
def main() -> None:
    """Compose the page: top menu, hero header, tabs, and footer."""
    # Top bar: title area + right-aligned Menu popover.
    _, menu_col = st.columns([6, 1])
    with menu_col:
        api_key = render_menu()

    st.markdown(
        f"""
        <div style="margin: 0 0 0.6rem 0;">
          <div style="color:{config.COLOR_ACCENT}; font-weight:700; font-size:0.78rem;
                      letter-spacing:0.09em; text-transform:uppercase;">
            Pre-open macro cockpit
          </div>
          <h1 style="margin:0.15rem 0 0.15rem 0; font-size:2.35rem;">
            Macro Intelligence
          </h1>
          <div style="color:{config.COLOR_TEXT_SEC}; font-size:0.95rem;
                      margin-bottom:0.3rem;">
            by <b style="color:{config.COLOR_TEXT};">Cristopher Astur</b>
          </div>
          <div style="color:{config.COLOR_TEXT_SEC}; font-size:1.02rem;">
            Monetary-policy divergence, real rates, carry-vs-USD & yield curves —
            G10 + key emerging markets.
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if not api_key:
        st.info(
            "**Add a free FRED API key to begin.** Get one in ~30s at "
            "[fredaccount.stlouisfed.org/apikeys](https://fredaccount.stlouisfed.org/apikeys) "
            "and paste it into the top **☰ Menu**. It powers all macro series "
            "(FX needs no key)."
        )
        st.stop()

    with st.spinner("Pulling macro snapshot from FRED…"):
        warm_cache(api_key)          # parallel fan-out; fills the shared cache
        snap = build_snapshot(api_key)

    tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs(
        ["Carry & Divergence", "Regime Matrix", "Yield Curves", "Time-Series",
         "Leading Indicators", "Calendar", "Data Health"]
    )
    with tab1:
        module_carry(snap, api_key)
    with tab2:
        module_regime(api_key)
    with tab3:
        module_curves(api_key)
    with tab4:
        module_timeseries(api_key)
    with tab5:
        module_leading(api_key)
    with tab6:
        module_calendar(api_key)
    with tab7:
        module_health(api_key, snap)

    render_footer()


if __name__ == "__main__":
    main()
