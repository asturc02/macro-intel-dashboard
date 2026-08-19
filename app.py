"""Macro Intelligence, Carry Trade & Yield Curve Dashboard (Streamlit UI).

A pre-open macro cockpit for G10 + key emerging-market economies: monetary-policy
divergence, real rates, carry-vs-USD, a volatility-adjusted carry ranking, the US
yield curve with its 10Y-2Y inversion signal, cross-country 10Y differentials, and
a multi-country time-series explorer. Data comes free from FRED (macro series) and
Frankfurter/ECB (FX). This module holds UI/layout only; data, FX, and quant logic
live in ``fred.py``, ``fx.py``, and ``metrics.py``.
"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import config
import fred
import fx
import metrics
import utils

BUILD_MARKER = "build: macro-intel v3"

st.set_page_config(
    page_title="Macro Intelligence Dashboard",
    page_icon="🌐",
    layout="wide",
    initial_sidebar_state="expanded",
)

# --- Custom dark, terminal-inspired styling ---------------------------------
st.markdown(
    """
    <style>
      .stApp { background-color: #0E1117; }
      h1, h2, h3 { letter-spacing: 0.2px; }
      .block-container { padding-top: 2rem; }
      div[data-testid="stMetricValue"] { font-variant-numeric: tabular-nums; }
      .mono { font-family: 'SFMono-Regular', Consolas, monospace; }
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
def get_fx_vol(currency: str) -> float | None:
    """Cached annualized realized FX volatility versus USD.

    Args:
        currency: ISO currency code.

    Returns:
        Annualized vol in percent, or ``None``.
    """
    return fx.annualized_vol(currency)


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
    us_policy = fred.latest(get_series(us.policy_rate, api_key, None))[1]
    us_y10 = fred.latest(get_series(us.y10, api_key, None))[1]

    rows: list[dict] = []
    for c in config.COUNTRIES:
        policy = fred.latest(get_series(c.policy_rate, api_key, None))[1]
        cpi = fred.latest(metric_series(c, "cpi_yoy", api_key))[1]
        unemp = fred.latest(get_series(c.unemployment, api_key, None))[1]
        y10 = fred.latest(get_series(c.y10, api_key, None))[1]
        rate_chg = fred.change_over(get_series(c.policy_rate, api_key, None), 6)

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
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor=config.COLOR_BG,
        plot_bgcolor=config.COLOR_BG,
        height=height,
        margin=dict(l=10, r=10, t=40, b=10),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
        hovermode="x unified",
    )
    fig.update_xaxes(gridcolor=config.COLOR_GRID, zeroline=False)
    fig.update_yaxes(gridcolor=config.COLOR_GRID, zeroline=False)
    return fig


# ============================================================================
# Sidebar
# ============================================================================
def render_sidebar() -> str:
    """Render the sidebar and return the resolved FRED API key.

    Returns:
        The API key to use (sidebar input takes precedence over the env key).
    """
    with st.sidebar:
        st.header("🌐 Macro Intelligence")
        st.caption("Pre-open cockpit — rates, curves & carry across G10 + EM.")

        st.subheader("🔑 FRED API key")
        st.caption(
            "Free key from "
            "[fredaccount.stlouisfed.org](https://fredaccount.stlouisfed.org/apikeys). "
            "Used only in your session; nothing is stored."
        )
        user_key = st.text_input(
            "FRED API key", type="password", label_visibility="collapsed",
            placeholder="Paste your free FRED API key…",
        )
        effective = (user_key or "").strip() or (config.FRED_API_KEY or "")

        st.divider()
        if st.button("🔄 Refresh data", use_container_width=True):
            st.cache_data.clear()
            st.toast("Cache cleared — pulling fresh data.")
            st.rerun()

        st.divider()
        st.caption("**Data:** FRED (macro) · Frankfurter/ECB (FX)")
        st.caption("**Related:** [Fed Sentiment](https://macro-sentiment-dashboard.streamlit.app/) · [Inflación Nowcast](https://inflacion-nowcast.streamlit.app/)")
        st.caption(f"Built by **Cristopher Astur** · UBA Economist\n\n{BUILD_MARKER}")
    return effective


# ============================================================================
# Modules
# ============================================================================
def module_carry(snap: pd.DataFrame) -> None:
    """Render the Carry Trade & Monetary Divergence module.

    Args:
        snap: The cross-country snapshot DataFrame.
    """
    st.subheader("Carry Trade & Monetary Divergence Matrix")
    st.caption(
        "Real rate = policy rate − CPI YoY. Carry & 10Y differential are vs USD. "
        "Carry/Vol divides interest-rate carry by annualized realized FX vol — a "
        "transparent, risk-adjusted ranking of carry attractiveness."
    )
    st.caption(
        "ℹ️ Policy rate is the actual target for US (Fed) & EA (ECB); for other "
        "economies it's a money-market proxy (3m interbank / overnight). CPI is "
        "current for US/EA/JP; some others lag ~1yr on free data. See **Data "
        "Health** for the exact vintage of every cell."
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
        "10Y %", "Carry vs USD", "10Y vs US", "Unemp %", "FX Vol %", "Carry/Vol",
    ]
    num_cols = [
        "Policy %", "CPI YoY %", "Real Rate %", "10Y %", "Carry vs USD",
        "10Y vs US", "Unemp %", "FX Vol %", "Carry/Vol",
    ]
    col_cfg = {
        c: st.column_config.NumberColumn(c, format="%.2f") for c in num_cols
    }
    st.dataframe(
        snap[display_cols],
        use_container_width=True,
        hide_index=True,
        column_config=col_cfg,
    )

    left, right = st.columns(2)
    with left:
        st.markdown("**Real policy rate by currency**")
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
            fig.update_layout(xaxis_title="Real rate (pp)")
            st.plotly_chart(_style_fig(fig, 380), use_container_width=True)

    with right:
        st.markdown("**Carry vs USD  vs  FX volatility**")
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
                xaxis_title="Annualized FX vol (%)",
                yaxis_title="Carry vs USD (pp)",
            )
            fig.add_hline(y=0, line_color=config.COLOR_NEUTRAL, line_width=1)
            st.plotly_chart(_style_fig(fig, 380), use_container_width=True)


def module_curves(api_key: str, window_years: int | None) -> None:
    """Render the Yield Curve module (US curve, inversion, cross-country 10Y).

    Args:
        api_key: Resolved FRED key.
        window_years: History window for time-series charts (``None`` = max).
    """
    st.subheader("Yield Curve Visualizer")
    start = utils.window_start(window_years)

    # --- US par curve, now vs 6m/1y ago -----------------------------------
    st.markdown("**US Treasury par curve** — current vs 6 & 12 months ago")
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
        fig.update_layout(xaxis_title="Maturity", yaxis_title="Yield (%)")
        st.plotly_chart(_style_fig(fig, 380), use_container_width=True)
    else:
        st.info("US curve series did not resolve — check the FRED key / Data Health.")

    # --- Inversion & recession signals ------------------------------------
    left, right = st.columns(2)
    with left:
        st.markdown("**10Y − 2Y spread** (inversion → recession signal)")
        sp = get_series(config.SPREAD_10Y_2Y, api_key, start)
        if sp.empty:
            st.info("Spread series unavailable.")
        else:
            fig = go.Figure(go.Scatter(
                x=sp.index, y=sp.values, line=dict(color=config.COLOR_ACCENT),
                fill="tozeroy", fillcolor="rgba(245,166,35,0.15)", name="10Y-2Y",
            ))
            fig.add_hline(y=0, line_color=config.COLOR_HAWK, line_width=1)
            latest_val = float(sp.iloc[-1])
            state = "INVERTED ⚠️" if latest_val < 0 else "normal"
            fig.update_layout(
                yaxis_title="Spread (pp)",
                title=f"Current: {latest_val:+.2f} pp ({state})",
            )
            st.plotly_chart(_style_fig(fig, 340), use_container_width=True)

    with right:
        st.markdown("**Cross-country 10Y yield** (latest)")
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
            fig.update_layout(xaxis_title="10Y yield (%)")
            st.plotly_chart(_style_fig(fig, 340), use_container_width=True)

    # --- Overlay selected 10Y histories -----------------------------------
    st.markdown("**Overlay 10Y yield history**")
    codes = st.multiselect(
        "Economies", options=[c.code for c in config.COUNTRIES],
        default=["US", "EA", "JP"], format_func=lambda x: config.COUNTRY_BY_CODE[x].name,
        key="curve_overlay",
    )
    if codes:
        fig = go.Figure()
        for i, code in enumerate(codes):
            c = config.COUNTRY_BY_CODE[code]
            s = get_series(c.y10, api_key, start)
            if s.empty:
                continue
            fig.add_trace(go.Scatter(
                x=s.index, y=s.values, name=f"{c.currency} 10Y",
                line=dict(color=config.PALETTE[i % len(config.PALETTE)]),
            ))
        fig.update_layout(yaxis_title="Yield (%)")
        st.plotly_chart(_style_fig(fig, 380), use_container_width=True)


def module_timeseries(api_key: str, window_years: int | None) -> None:
    """Render the multi-country / multi-metric time-series explorer.

    Args:
        api_key: Resolved FRED key.
        window_years: History window (``None`` = max).
    """
    st.subheader("Time-Series Explorer")
    start = utils.window_start(window_years)

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
            line=dict(color=config.PALETTE[i % len(config.PALETTE)]),
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

    fig.update_layout(yaxis_title=config.METRIC_LABELS[metric_key])
    st.plotly_chart(_style_fig(fig, 460), use_container_width=True)


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
    ]
    for c in config.COUNTRIES:
        for label, attr in fields:
            sid = getattr(c, attr)
            if not sid:
                rows.append({"Economy": c.name, "Metric": label,
                             "Series ID": "—", "Latest": "n/a", "Value": "n/a"})
                continue
            series = (
                metric_series(c, "cpi_yoy", api_key)
                if attr == "cpi_yoy"
                else get_series(sid, api_key, None)
            )
            d, v = fred.latest(series)
            rows.append({
                "Economy": c.name, "Metric": label, "Series ID": sid,
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
    """Compose the page: header, sidebar, and the four analytical tabs."""
    api_key = render_sidebar()

    st.title("🌐 Macro Intelligence, Carry & Yield-Curve Dashboard")
    st.caption(
        "Monetary-policy divergence, real rates, carry-vs-USD, the US yield curve "
        "and cross-country rates for G10 + key EM — a pre-open macro cockpit."
    )

    if not api_key:
        st.info(
            "**Add a free FRED API key to begin.** Get one in ~30s at "
            "[fredaccount.stlouisfed.org/apikeys](https://fredaccount.stlouisfed.org/apikeys) "
            "and paste it into the sidebar. It powers all macro series (FX needs no key)."
        )
        st.stop()

    window_label = st.radio(
        "History window", options=list(config.WINDOW_YEARS.keys()),
        index=2, horizontal=True, key="global_window",
    )
    window_years = config.WINDOW_YEARS[window_label]

    with st.spinner("Pulling macro snapshot from FRED…"):
        snap = build_snapshot(api_key)

    tab1, tab2, tab3, tab4 = st.tabs(
        ["🎯 Carry & Divergence", "📉 Yield Curves", "📈 Time-Series", "🩺 Data Health"]
    )
    with tab1:
        module_carry(snap)
    with tab2:
        module_curves(api_key, window_years)
    with tab3:
        module_timeseries(api_key, window_years)
    with tab4:
        module_health(api_key, snap)

    st.divider()
    st.caption(
        "⚠️ Portfolio project for educational purposes — not financial advice. "
        "Sources: FRED (St. Louis Fed) & Frankfurter/ECB. "
        "Built by **Cristopher Astur**, UBA Economist."
    )


if __name__ == "__main__":
    main()
