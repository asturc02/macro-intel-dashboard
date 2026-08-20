"""Configuration, constants, and the country/series registry.

Central place for the FRED API key (read from the environment or Streamlit
secrets — never hardcoded), the map of G10 + emerging-market economies to their
FRED series IDs, monetary-policy targets, and UI theme colors. Consumed by the
``fred``, ``fx``, ``metrics``, and ``app`` modules.

Series-ID note
--------------
International macro series come mostly from the OECD "Main Economic Indicators"
collection mirrored on FRED, which uses consistent naming:

* ``IRLTLT01<CC>M156N`` — 10-year government bond yield (monthly, %)
* ``IRSTCB01<CC>M156N`` — central-bank / immediate policy rate (monthly, %)
* ``CPALTT01<CC>M659N`` — CPI, all items, YoY % (monthly; some countries Q)
* ``LRHUTTTT<CC>M156S`` — harmonized unemployment rate (monthly, % SA)

Coverage is intentionally broad but shallow: where a country lacks a clean free
series the dashboard degrades gracefully to ``n/a`` rather than failing. The
built-in **Data Health** panel shows exactly which series resolved.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env from this module's directory explicitly, so the key is found even
# when Streamlit is launched from a different working directory.
load_dotenv(Path(__file__).resolve().parent / ".env")

# --- Secrets (environment / Streamlit secrets only) -------------------------
# FRED API keys are free (https://fredaccount.stlouisfed.org/apikeys). Read from
# the environment here; the app also accepts a key pasted into the sidebar so it
# runs on Streamlit Cloud without committing anything.
FRED_API_KEY: str | None = os.getenv("FRED_API_KEY")

# Optional free e-Stat (Japan Statistics Bureau) application ID. When present,
# Japan CPI is pulled live from e-Stat; when absent, JP falls back to the
# (lagging) World-Bank series. Register at https://www.e-stat.go.jp/api/.
ESTAT_APP_ID: str | None = os.getenv("ESTAT_APP_ID")

# --- FRED API ---------------------------------------------------------------
FRED_BASE_URL: str = "https://api.stlouisfed.org/fred/series/observations"
FRED_RELEASE_DATES_URL: str = "https://api.stlouisfed.org/fred/release/dates"
REQUEST_TIMEOUT_SECONDS: int = 20

# --- Economic calendar: key US releases (FRED release IDs) ------------------
# FRED publishes forward-looking release dates for these. Free data gives the
# schedule (dates) but not consensus/forecast numbers. (name, release_id, tier).
KEY_RELEASES: tuple[tuple[str, int, str], ...] = (
    ("Employment Situation (NFP + unemployment)", 50, "High"),
    ("Consumer Price Index (CPI)", 10, "High"),
    ("Personal Income & Outlays (PCE)", 54, "High"),
    ("Gross Domestic Product (GDP)", 53, "High"),
    ("Producer Price Index (PPI)", 46, "Medium"),
    ("Jobless Claims (weekly)", 180, "Medium"),
)

# --- FX (Frankfurter, ECB-sourced, no key) ----------------------------------
FRANKFURTER_BASE_URL: str = "https://api.frankfurter.app"

# --- Caching ----------------------------------------------------------------
BASE_DIR: Path = Path(__file__).resolve().parent
DATA_DIR: Path = BASE_DIR / "data"
CACHE_TTL_SECONDS: int = 60 * 60 * 6  # 6h: macro series update slowly.

# --- Monetary-policy stance thresholds --------------------------------------
# Rule-based, transparent classification (no LLM needed): combine the 6-month
# change in the policy rate with the gap between CPI YoY and the inflation
# target. Deterministic and defensible in an interview.
STANCE_RATE_DELTA: float = 0.10   # pp move over 6m that counts as tightening/easing
STANCE_CPI_GAP: float = 1.00      # pp above/below target that adds hawk/dove pressure

HAWK: str = "Hawk"
NEUTRAL: str = "Neutral"
DOVE: str = "Dove"

# --- Macro regime quadrant (growth momentum x inflation momentum) -----------
# Momentum = change over ~1 year: right = growth accelerating, up = inflation
# rising. The four regimes follow the classic growth/inflation quadrant model.
GOLDILOCKS: str = "Goldilocks"    # growth up, inflation down/stable
OVERHEATING: str = "Overheating"  # growth up, inflation up
STAGFLATION: str = "Stagflation"  # growth down, inflation up
CONTRACTION: str = "Contraction"  # growth down, inflation down
REGIME_COLORS: dict[str, str] = {
    GOLDILOCKS: "#10B981",   # emerald — benign
    OVERHEATING: "#F59E0B",  # amber — hot
    STAGFLATION: "#EF4444",  # rose — worst
    CONTRACTION: "#60A5FA",  # blue — cooling / reflation
}

# --- US Treasury par curve (daily, very reliable) ---------------------------
# Maturity label -> FRED series ID. Used by the Yield Curve module for the deep,
# guaranteed-solid US curve and the 10Y-2Y inversion signal.
US_CURVE: dict[str, str] = {
    "3M": "DGS3MO",
    "1Y": "DGS1",
    "2Y": "DGS2",
    "5Y": "DGS5",
    "10Y": "DGS10",
    "20Y": "DGS20",
    "30Y": "DGS30",
}
US_CURVE_ORDER: tuple[str, ...] = ("3M", "1Y", "2Y", "5Y", "10Y", "20Y", "30Y")

# Ready-made spread series (daily) for the inversion / recession indicators.
SPREAD_10Y_2Y: str = "T10Y2Y"
SPREAD_10Y_3M: str = "T10Y3M"


class Country:
    """Static description of one economy and its FRED series IDs.

    Attributes:
        code: Short display code (e.g. ``"US"``).
        name: Human-readable country/area name.
        currency: ISO currency code (e.g. ``"USD"``).
        central_bank: Name of the monetary authority.
        inflation_target: Central-bank inflation target, in percent.
        policy_rate: FRED series ID for the policy rate. For most non-US/EA
            economies this is a money-market proxy (3-month interbank or the
            immediate/overnight rate), since the exact target rate is not
            published as a current free FRED series — labeled as such in the UI.
        cpi_yoy: FRED series ID for CPI. Either an already-computed YoY series or
            a price *index* (see ``cpi_is_index``).
        unemployment: FRED series ID for the unemployment rate.
        y10: FRED series ID for the 10-year government bond yield.
        gdp_qoq: FRED series ID for real GDP QoQ growth (OECD ``NAEXKP01..Q657S``,
            annualized for display). ``None`` where no current free series exists.
        cpi_is_index: When ``True``, ``cpi_yoy`` points at a price index and YoY
            must be computed from it (used for US/EA, whose live series are
            indices rather than pre-computed growth rates).
        is_emerging: Flag used to visually group EM economies apart from G10.
    """

    def __init__(
        self,
        code: str,
        name: str,
        currency: str,
        central_bank: str,
        inflation_target: float,
        policy_rate: str | None,
        cpi_yoy: str | None,
        unemployment: str | None,
        y10: str | None,
        gdp_qoq: str | None = None,
        cpi_is_index: bool = False,
        is_emerging: bool = False,
    ) -> None:
        self.code = code
        self.name = name
        self.currency = currency
        self.central_bank = central_bank
        self.inflation_target = inflation_target
        self.policy_rate = policy_rate
        self.cpi_yoy = cpi_yoy
        self.unemployment = unemployment
        self.y10 = y10
        self.gdp_qoq = gdp_qoq
        self.cpi_is_index = cpi_is_index
        self.is_emerging = is_emerging


# G10 + key emerging markets. Germany (DE) stands in for the euro area's bond
# market (the Bund is the EUR benchmark); the ECB policy rate is used for EUR.
# Series IDs below were validated live against FRED. Because the OECD "MEI"
# collection froze many pre-computed rate/CPI series on FRED (~2024-25), current
# free coverage is: 10Y yields & unemployment (fresh, all G10); US/EA policy &
# CPI (fresh); other G10 policy via money-market proxies (fresh); other G10 CPI
# via OECD growth series (lag ~1yr); EM policy/curve largely unavailable. The
# Data Health tab surfaces the exact vintage of every cell.
COUNTRIES: tuple[Country, ...] = (
    Country(
        code="US", name="United States", currency="USD",
        central_bank="Federal Reserve", inflation_target=2.0,
        policy_rate="DFEDTARU",           # Fed funds target, upper bound (daily)
        cpi_yoy="CPIAUCSL", cpi_is_index=True,   # index -> YoY computed (live)
        unemployment="UNRATE",
        y10="IRLTLT01USM156N",
        gdp_qoq="NAEXKP01USQ657S",
    ),
    Country(
        code="EA", name="Euro Area", currency="EUR",
        central_bank="ECB", inflation_target=2.0,
        policy_rate="ECBDFR",             # ECB deposit facility rate (key rate)
        cpi_yoy="CP0000EZ19M086NEST", cpi_is_index=True,  # Eurostat HICP index
        unemployment="LRHUTTTTDEM156S",   # Germany proxy (live)
        y10="IRLTLT01DEM156N",            # Bund 10Y (EUR benchmark)
        gdp_qoq="NAEXKP01DEQ657S",
    ),
    Country(
        code="JP", name="Japan", currency="JPY",
        central_bank="Bank of Japan", inflation_target=2.0,
        policy_rate="IR3TIB01JPM156N",    # 3m interbank (policy proxy)
        cpi_yoy="FPCPITOTLZGJPN",         # World Bank annual CPI YoY (live-ish)
        unemployment="LRHUTTTTJPM156S",
        y10="IRLTLT01JPM156N",
        gdp_qoq="NAEXKP01JPQ657S",
    ),
    Country(
        code="GB", name="United Kingdom", currency="GBP",
        central_bank="Bank of England", inflation_target=2.0,
        policy_rate="IRSTCI01GBM156N",    # immediate rate (Bank Rate proxy)
        cpi_yoy="CPALTT01GBM659N",
        unemployment="LRHUTTTTGBM156S",
        y10="IRLTLT01GBM156N",
        gdp_qoq="NAEXKP01GBQ657S",
    ),
    Country(
        code="AU", name="Australia", currency="AUD",
        central_bank="Reserve Bank of Australia", inflation_target=2.5,
        policy_rate="IRSTCI01AUM156N",    # immediate rate (cash rate proxy)
        cpi_yoy="CPALTT01AUQ659N",        # quarterly
        unemployment="LRHUTTTTAUM156S",
        y10="IRLTLT01AUM156N",
        gdp_qoq="NAEXKP01AUQ657S",
    ),
    Country(
        code="NZ", name="New Zealand", currency="NZD",
        central_bank="RBNZ", inflation_target=2.0,
        policy_rate="IR3TIB01NZM156N",    # 3m interbank (OCR proxy)
        cpi_yoy="FPCPITOTLZGNZL",         # World Bank annual (OECD quarterly froze 2023)
        unemployment="LRHUTTTTNZQ156S",   # quarterly
        y10="IRLTLT01NZM156N",
        gdp_qoq="NAEXKP01NZQ657S",
    ),
    Country(
        code="CA", name="Canada", currency="CAD",
        central_bank="Bank of Canada", inflation_target=2.0,
        policy_rate="IR3TIB01CAM156N",    # 3m interbank (policy proxy)
        cpi_yoy="CPALTT01CAM659N",
        unemployment="LRHUTTTTCAM156S",
        y10="IRLTLT01CAM156N",
        gdp_qoq="NAEXKP01CAQ657S",
    ),
    Country(
        code="NO", name="Norway", currency="NOK",
        central_bank="Norges Bank", inflation_target=2.0,
        policy_rate="IRSTCI01NOM156N",    # immediate rate (policy proxy)
        cpi_yoy="CPALTT01NOM659N",
        unemployment="LRHUTTTTNOM156S",
        y10="IRLTLT01NOM156N",
        gdp_qoq="NAEXKP01NOQ657S",
    ),
    # --- Emerging markets (free-data gaps expected; shown honestly as n/a) ---
    Country(
        code="BR", name="Brazil", currency="BRL",
        central_bank="Banco Central do Brasil", inflation_target=3.0,
        policy_rate=None,                 # Selic not on free FRED; n/a
        cpi_yoy="FPCPITOTLZGBRA",         # World Bank annual CPI YoY
        unemployment=None,                # no live free series; n/a
        y10=None,                         # no clean free curve; n/a
        gdp_qoq="NAEXKP01BRQ657S",
        is_emerging=True,
    ),
    Country(
        code="AR", name="Argentina", currency="ARS",
        central_bank="BCRA", inflation_target=0.0,
        policy_rate=None,                 # no clean free series; n/a
        cpi_yoy="FPCPITOTLZGARG",         # World Bank annual CPI %, best-effort
        unemployment=None,
        y10=None,
        is_emerging=True,
    ),
)

# Flag emoji per economy, for the country deep-dive header.
FLAGS: dict[str, str] = {
    "US": "🇺🇸", "EA": "🇪🇺", "JP": "🇯🇵", "GB": "🇬🇧", "AU": "🇦🇺",
    "NZ": "🇳🇿", "CA": "🇨🇦", "NO": "🇳🇴", "BR": "🇧🇷", "AR": "🇦🇷",
}

# Fast lookup by code.
COUNTRY_BY_CODE: dict[str, Country] = {c.code: c for c in COUNTRIES}
BASE_COUNTRY: str = "US"  # carry / differentials are measured against the USD leg

# --- Time-series explorer -------------------------------------------------
METRIC_LABELS: dict[str, str] = {
    "policy_rate": "Policy Rate (%)",
    "cpi_yoy": "CPI YoY (%)",
    "unemployment": "Unemployment (%)",
    "y10": "10Y Gov. Bond Yield (%)",
}
WINDOW_YEARS: dict[str, int | None] = {"1Y": 1, "2Y": 2, "5Y": 5, "Max": None}

# --- US leading / expectation indicators ------------------------------------
# Directional, high-frequency US series watched ahead of the big releases. All
# are current and free on FRED. Each row: (label, series_id, transform, note).
# Transforms: "level_k" latest level in thousands; "mom_diff_k" month-over-month
# change (net additions) in thousands; "yoy" year-over-year % from an index.
LEADING_EMPLOYMENT: tuple[tuple[str, str, str, str], ...] = (
    ("Initial jobless claims", "ICSA", "level_k",
     "Weekly · first-time filers. Rising = labor market softening."),
    ("Continued claims", "CCSA", "level_k",
     "Weekly · still collecting benefits. Trend > level."),
    ("Net payrolls (MoM)", "PAYEMS", "mom_diff_k",
     "Monthly · change in nonfarm payrolls (jobs added)."),
)
LEADING_INFLATION: tuple[tuple[str, str, str, str], ...] = (
    ("Core PCE", "PCEPILFE", "yoy",
     "The Fed's preferred inflation gauge — prioritized over CPI."),
    ("Headline PCE", "PCEPI", "yoy", "Total PCE inflation, YoY."),
    ("PPI (final demand)", "PPIFIS", "yoy",
     "Producer/pipeline prices — often lead consumer inflation."),
    ("CPI (headline)", "CPIAUCSL", "yoy", "Shown for comparison with PCE."),
)

# --- Theme (GetVision-aligned iOS dark system) ------------------------------
# Deep-navy layered surfaces, a single teal brand accent used sparingly, and
# jewel-tone data colors (emerald/rose/amber/violet). Depth comes from surface
# layering (base -> raised -> elevated), not heavy borders or shadows.
COLOR_BG: str = "#0A0E1A"        # base app background
COLOR_RAISED: str = "#151B2C"    # card surface
COLOR_ELEVATED: str = "#1E263D"  # raised card / hover / muted bars
COLOR_ACCENT: str = "#1F8579"    # brand teal (CTAs, active, hero lines)
COLOR_HAWK: str = "#EF4444"      # rose   — restrictive / hawkish
COLOR_DOVE: str = "#10B981"      # emerald — accommodative / dovish
COLOR_NEUTRAL: str = "#6B7488"   # slate — neutral / tertiary
COLOR_TEXT: str = "#E7ECF3"      # primary text
COLOR_TEXT_SEC: str = "#9AA6B8"  # secondary text
COLOR_GRID: str = "rgba(255,255,255,0.06)"
# Qualitative jewel-tone palette for multi-country overlays.
PALETTE: tuple[str, ...] = (
    "#1F8579", "#10B981", "#8B5CF6", "#F59E0B", "#EF4444",
    "#22D3EE", "#60A5FA", "#F472B6", "#4ADE80", "#FBBF24",
)

# User-selectable palettes for comparison charts (color-customization dropdown).
PALETTES: dict[str, tuple[str, ...]] = {
    "Teal & Jewel": PALETTE,
    "Colorblind-safe": (
        "#0072B2", "#E69F00", "#009E73", "#CC79A7", "#56B4E9",
        "#D55E00", "#F0E442", "#999999", "#000000", "#8DD3C7",
    ),
    "Vivid": (
        "#EF4444", "#F59E0B", "#10B981", "#3B82F6", "#8B5CF6",
        "#EC4899", "#22D3EE", "#84CC16", "#F97316", "#A855F7",
    ),
    "Mono Teal": (
        "#0B3D3A", "#125E57", "#1F8579", "#2FA694", "#54C3B0",
        "#8AD9CC", "#B7E8DF", "#5EEAD4", "#0E7490", "#99F6E4",
    ),
}
