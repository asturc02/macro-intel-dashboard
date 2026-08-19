# 🌐 Macro Intelligence, Carry Trade & Yield-Curve Dashboard

> A pre-open **macro cockpit** for G10 + key emerging markets: monetary-policy
> divergence, real rates, carry-vs-USD, a volatility-adjusted carry ranking, the
> US yield curve with its **10Y-2Y inversion** signal, and cross-country rates —
> all from **free** data (FRED + ECB), on an interactive terminal-style dashboard.

### 🔗 Live demo → **_deploy URL here_**

[![Open in Streamlit](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://share.streamlit.io/)

![Dashboard screenshot placeholder](docs/screenshot.png)
<!-- Replace docs/screenshot.png with a real screenshot once running. -->

---

## ✨ What it does

- **Carry & Monetary-Divergence Matrix** — a sortable table of every economy's
  policy rate, CPI YoY, **real rate** (policy − CPI), 10Y yield, **carry vs USD**,
  10Y differential vs the US, unemployment, realized FX volatility, and a
  **Carry/Vol** ("implied Sharpe") ranking. Each central bank is auto-classified
  **🦅 Hawk / ➖ Neutral / 🕊️ Dove** by a transparent, rule-based signal.
- **Yield-Curve Visualizer** — the US Treasury par curve (now vs 6 & 12 months
  ago), the **10Y-2Y spread** with its inversion/recession shading, a
  cross-country 10Y bar, and a selectable multi-country 10Y history overlay.
- **Time-Series Explorer** — overlay any metric (policy rate, CPI YoY,
  unemployment, 10Y) across multiple economies over 1Y / 2Y / 5Y / Max, with an
  optional **dual-axis** second metric (e.g. US CPI vs Fed Funds).
- **Data Health** — a live panel showing exactly which FRED series resolved, so
  data coverage is transparent instead of silently faked.

---

## 🧱 Architecture

```
            ┌──────────────┐
            │   app.py     │  Streamlit UI only (layout, CSS, Plotly, tabs)
            └──────┬───────┘
                   │ calls
      ┌────────────┼───────────────┬───────────────┐
      ▼            ▼               ▼               ▼
 ┌─────────┐ ┌──────────┐  ┌────────────┐  ┌──────────┐
 │ fred.py │ │  fx.py   │  │ metrics.py │  │ utils.py │
 │ FRED    │ │ ECB/     │  │ real rate, │  │ format / │
 │ macro   │ │Frankfurter│ │ stance,    │  │ colors / │
 │ series  │ │ FX vol   │  │ carry,     │  │ windows  │
 └────┬────┘ └────┬─────┘  │ Sharpe     │  └────┬─────┘
      │           │        └──────┬─────┘       │
      └───────────┴───────────────┴─────────────┘
                        ▼
             config.py → country/series registry + theme
```

**Separation of concerns:** UI lives only in `app.py`; data access in `fred.py`
/ `fx.py`; the quant logic (real rates, stance, carry, Sharpe) in `metrics.py`.
Every network failure or missing series degrades gracefully to `n/a`.

---

## 📊 Data sources (all free, no paid feeds)

| Data | Source |
|------|--------|
| Policy rates, CPI YoY, unemployment, 10Y yields (G10 + EM) | **FRED** (St. Louis Fed / OECD MEI) |
| US Treasury par curve, 10Y-2Y & 10Y-3M spreads | **FRED** (daily) |
| FX rates & realized volatility | **Frankfurter** (ECB reference rates, no key) |

> International coverage is intentionally **broad but shallow**: where a clean
> free series doesn't exist (e.g. Argentine curves, some EM policy rates), the
> Data Health panel flags it as `n/a` rather than inventing a number.

---

## 🚀 Setup

```bash
# 1. Clone
git clone https://github.com/<your-username>/macro-intel-dashboard.git
cd macro-intel-dashboard

# 2. Create and activate a virtual environment
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # macOS / Linux

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure your FRED key (free)
cp .env.example .env          # Windows: copy .env.example .env
#   then edit .env and set FRED_API_KEY=...   (get one at the link below)
```

Get a **free FRED API key** in ~30 seconds at
[fredaccount.stlouisfed.org/apikeys](https://fredaccount.stlouisfed.org/apikeys).
You can also paste it directly into the app's sidebar instead of using `.env`.

---

## ▶️ Run locally

```bash
streamlit run app.py
```

---

## ☁️ Deploy to Streamlit Community Cloud

1. Push this repo to GitHub.
2. On [share.streamlit.io](https://share.streamlit.io), create a new app pointing
   at `app.py`.
3. Add `FRED_API_KEY` under **App settings → Secrets**. No code changes required.

---

## 🛠️ Skills demonstrated

- **Quantitative macro** — real rates, monetary-divergence, carry vs base
  currency, volatility-adjusted carry, curve inversion — the analytics a macro
  desk actually watches pre-open.
- **API integration** — resilient REST clients for FRED and Frankfurter with
  defensive parsing, timeouts, and graceful degradation.
- **Data engineering** — pandas time-series handling, YoY transforms, realized-
  volatility estimation, cached fan-out over ~40 series.
- **Data visualization** — interactive Plotly on a custom dark theme; sortable,
  formatted tables via Streamlit `column_config`.
- **Python architecture** — clean module separation, type hints, Google-style
  docstrings, environment-based configuration, and BYO-key security.

---

## 👤 Author

**Cristopher Astur** — Freelance Economist | UBA | Python · SQL · AI Integrations

---

## ⚠️ Disclaimer

Portfolio project for educational purposes. Nothing here is financial advice.
Classifications and rankings are transparent, rule-based interpretations of
public data.
