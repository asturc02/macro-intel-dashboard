# 🌐 Macro Intelligence, Carry Trade & Yield-Curve Dashboard

> A pre-open **macro cockpit** for G10 + key emerging markets: monetary-policy
> divergence, real rates, carry-vs-USD, a volatility-adjusted carry ranking, the
> US yield curve with its **10Y-2Y inversion** signal, US **leading indicators**,
> a free **economic calendar**, and a **click-through country deep-dive** — all
> from **free** data (FRED + ECB), on an iOS-styled dark dashboard.

### 🔗 Live demo → **https://macrointeldashboard.streamlit.app/**

[![Open in Streamlit](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://macrointeldashboard.streamlit.app/)

![Dashboard screenshot placeholder](docs/screenshot.png)
<!-- Replace docs/screenshot.png with a real screenshot once running. -->

---

## ✨ The six modules

| Tab | What it does |
|-----|--------------|
| **🎯 Carry & Divergence** | Sortable matrix of every economy's policy rate, CPI YoY, **real rate**, **GDP** (annualized), 10Y yield, **carry vs USD**, 10Y differential, unemployment, realized FX vol, and a **Carry/Vol** ("implied Sharpe") ranking. Each central bank is auto-classified **🦅 Hawk / ➖ Neutral / 🕊️ Dove**. **Click any row** to drill into that country. |
| **📉 Yield Curves** | US Treasury par curve (now vs 6 & 12 months ago), the **10Y-2Y spread** with inversion shading, a cross-country 10Y bar, and a selectable multi-country 10Y overlay with a color-palette picker. |
| **📈 Time-Series** | Overlay any metric (policy rate, CPI, unemployment, 10Y) across economies over 1Y / 2Y / 5Y / Max, with an optional **dual-axis** second metric. |
| **📊 Leading Indicators** | US directional gauges: initial & continued **jobless claims**, **net payrolls**, plus **core PCE / PCE / PPI / CPI** YoY with a 2%-target overlay (the Fed prioritizes core PCE). |
| **🗓️ Calendar** | Upcoming US release dates (NFP, CPI, PCE, GDP, PPI, jobless claims) from FRED's schedule, with **Add-to-Google-Calendar** links and a **Download .ics**. |
| **🩺 Data Health** | Live panel showing exactly which FRED series resolved and their vintage — transparency by design. |

### Country deep-dive
Clicking a row in the Carry matrix opens a **TradingEconomics-style** detail view:
a flagged header, current-value tiles, and a 2×2 grid of history charts (policy
rate, CPI, unemployment, 10Y) over a per-country window.

---

## 🧱 Architecture

```
            ┌──────────────┐
            │   app.py     │  Streamlit UI only (layout, CSS, Plotly, 6 tabs)
            └──────┬───────┘
                   │ calls
      ┌────────────┼───────────────┬───────────────┐
      ▼            ▼               ▼               ▼
 ┌─────────┐ ┌──────────┐  ┌────────────┐  ┌──────────┐
 │ fred.py │ │  fx.py   │  │ metrics.py │  │ utils.py │
 │ series, │ │ ECB/     │  │ real rate, │  │ format / │
 │ release │ │Frankfurter│ │ stance,    │  │ colors / │
 │ dates   │ │ FX vol   │  │ carry,     │  │ windows  │
 └────┬────┘ └────┬─────┘  │ Sharpe     │  └────┬─────┘
      │           │        └──────┬─────┘       │
      └───────────┴───────────────┴─────────────┘
                        ▼
             config.py → country/series registry + theme
```

**Separation of concerns:** UI lives only in `app.py`; data access in `fred.py`
/ `fx.py`; quant logic (real rates, stance, carry, Sharpe) in `metrics.py`.
Every network failure or missing series degrades gracefully to `n/a`. Cold-start
fetches are **fanned out across a thread pool** for a fast first load.

---

## 📊 Data sources (all free, no paid feeds)

| Data | Source |
|------|--------|
| Policy rates, CPI, unemployment, 10Y yields, GDP (G10 + EM) | **FRED** (St. Louis Fed / OECD) |
| US Treasury par curve, 10Y-2Y & 10Y-3M spreads | **FRED** (daily) |
| US leading indicators (claims, payrolls, PCE, PPI) | **FRED** |
| Economic-calendar release dates | **FRED** release schedule |
| FX rates & realized volatility | **Frankfurter** (ECB reference rates, no key) |

> International coverage is intentionally **broad but shallow**. Because FRED's
> OECD-sourced series froze several pre-computed rates/CPI (~2024–25), policy
> rates for non-US/EA economies use money-market proxies and some CPI prints lag
> ~1yr; Brazil/Argentina policy & curves have no clean free series. The **Data
> Health** tab flags every gap and vintage rather than inventing numbers.

---

## 🚀 Setup

```bash
git clone https://github.com/asturc02/macro-intel-dashboard.git
cd macro-intel-dashboard
python -m venv .venv
.venv\Scripts\activate         # Windows  (source .venv/bin/activate on macOS/Linux)
pip install -r requirements.txt
cp .env.example .env           # then set FRED_API_KEY=...
```

Get a **free FRED API key** in ~30 seconds at
[fredaccount.stlouisfed.org/apikeys](https://fredaccount.stlouisfed.org/apikeys).
You can also paste it into the app's **☰ Menu** instead of using `.env`.

```bash
streamlit run app.py
```

---

## ☁️ Deploy to Streamlit Community Cloud

1. Push this repo to GitHub.
2. On [share.streamlit.io](https://share.streamlit.io), create a new app pointing
   at `app.py`.
3. Under **Advanced settings → Secrets**, add `FRED_API_KEY = "..."`.
4. Deploy — no code changes required.

---

## 🛠️ Skills demonstrated

- **Quantitative macro** — real rates, monetary divergence, carry vs base
  currency, volatility-adjusted carry, curve inversion, leading indicators.
- **API integration** — resilient REST clients for FRED (series, release dates)
  and Frankfurter, with defensive parsing and graceful degradation.
- **Data engineering** — pandas time-series, YoY transforms, realized-vol
  estimation, cached parallel fan-out over ~60 series.
- **Data visualization & UX** — interactive Plotly on a custom iOS-style theme,
  a selectable country drill-down, and a downloadable `.ics` calendar.
- **Python architecture** — clean module separation, type hints, Google-style
  docstrings, environment-based config, and BYO-key security.

---

## 👤 Author

**Cristopher Astur** — Freelance Economist | UBA | Python · SQL · AI Integrations

---

## ⚠️ Disclaimer

Portfolio project for educational purposes. Nothing here is financial advice.
Classifications and rankings are transparent, rule-based interpretations of
public data.
