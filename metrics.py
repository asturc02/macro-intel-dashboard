"""Quantitative macro metrics: real rates, stance, carry, and differentials.

Pure functions over already-fetched values — no network, no UI. This is the
analytical core an interviewer would look at: transparent, rule-based, and
unit-tested by construction (deterministic given inputs).
"""

from __future__ import annotations

import pandas as pd

import config


def real_rate(policy_rate: float | None, cpi_yoy: float | None) -> float | None:
    """Ex-post real policy rate: nominal policy rate minus CPI YoY.

    Args:
        policy_rate: Nominal central-bank policy rate, in percent.
        cpi_yoy: Headline CPI year-over-year, in percent.

    Returns:
        The real rate in percent, or ``None`` if either input is missing.
    """
    if policy_rate is None or cpi_yoy is None:
        return None
    return round(policy_rate - cpi_yoy, 2)


def classify_stance(
    rate_change_6m: float | None,
    cpi_yoy: float | None,
    inflation_target: float,
) -> str:
    """Classify a central bank as Hawk / Neutral / Dove.

    Deterministic rule combining two signals:

    * **Trajectory** — the change in the policy rate over the last 6 months.
      Hiking is hawkish, cutting is dovish.
    * **Inflation gap** — CPI YoY relative to the bank's target. Running hot adds
      hawkish pressure; running cold adds dovish pressure.

    A point is assigned in each direction and the net sign decides the label.

    Args:
        rate_change_6m: 6-month change in the policy rate (pp), or ``None``.
        cpi_yoy: Headline CPI YoY (%), or ``None``.
        inflation_target: The bank's inflation target (%).

    Returns:
        One of ``config.HAWK``, ``config.NEUTRAL``, ``config.DOVE``.
    """
    score = 0

    if rate_change_6m is not None:
        if rate_change_6m >= config.STANCE_RATE_DELTA:
            score += 1
        elif rate_change_6m <= -config.STANCE_RATE_DELTA:
            score -= 1

    if cpi_yoy is not None:
        gap = cpi_yoy - inflation_target
        if gap >= config.STANCE_CPI_GAP:
            score += 1
        elif gap <= -config.STANCE_CPI_GAP:
            score -= 1

    if score > 0:
        return config.HAWK
    if score < 0:
        return config.DOVE
    return config.NEUTRAL


def classify_regime(
    growth_momentum: float | None, inflation_momentum: float | None
) -> str:
    """Classify an economy into a growth/inflation macro regime.

    Uses the sign of each momentum (change over ~1 year): growth accelerating or
    not, inflation rising or not. The four quadrants are the classic model.

    Args:
        growth_momentum: Change in GDP growth over ~1 year (pp), or ``None``.
        inflation_momentum: Change in CPI YoY over ~1 year (pp), or ``None``.

    Returns:
        One of the regime constants, or ``"n/a"`` when momentum is missing.
    """
    if growth_momentum is None or inflation_momentum is None:
        return "n/a"
    growth_up = growth_momentum >= 0.0
    inflation_up = inflation_momentum >= 0.0
    if growth_up and inflation_up:
        return config.OVERHEATING
    if growth_up and not inflation_up:
        return config.GOLDILOCKS
    if not growth_up and inflation_up:
        return config.STAGFLATION
    return config.CONTRACTION


def carry_vs_base(
    policy_rate: float | None, base_policy_rate: float | None
) -> float | None:
    """Nominal interest-rate carry versus the base currency (USD).

    Args:
        policy_rate: This economy's policy rate (%).
        base_policy_rate: The base economy's policy rate (%).

    Returns:
        ``policy_rate - base_policy_rate`` in percent, or ``None`` if missing.
    """
    if policy_rate is None or base_policy_rate is None:
        return None
    return round(policy_rate - base_policy_rate, 2)


def yield_diff_vs_base(y10: float | None, base_y10: float | None) -> float | None:
    """10-year yield differential versus the base economy (drives FX trends).

    Args:
        y10: This economy's 10Y yield (%).
        base_y10: The base economy's 10Y yield (%).

    Returns:
        ``y10 - base_y10`` in percent, or ``None`` if missing.
    """
    if y10 is None or base_y10 is None:
        return None
    return round(y10 - base_y10, 2)


def periods_per_year(index: pd.DatetimeIndex) -> int:
    """Estimate observations per year from a date index's median spacing.

    Lets the same z-score code work on daily FRED spreads (~252/yr) and monthly
    international yields (12/yr) without hardcoding a frequency.

    Args:
        index: A pandas ``DatetimeIndex``.

    Returns:
        Estimated number of observations per calendar year (>= 1); defaults to
        12 when the index is too short to infer a spacing.
    """
    if index is None or len(index) < 3:
        return 12
    step_days = float(pd.Series(index).diff().dropna().dt.days.median())
    if not step_days or step_days <= 0:
        return 12
    # Snap to the nearest canonical cadence. FRED daily series skip weekends and
    # holidays (median gap ~1 business day), so calendar-day math would overstate
    # them; ~252 trading days/year is the right annualization.
    if step_days <= 4:      # daily / business-day
        return 252
    if step_days <= 10:     # weekly
        return 52
    if step_days <= 45:     # monthly
        return 12
    if step_days <= 135:    # quarterly
        return 4
    return max(1, int(round(365.25 / step_days)))


def rolling_zscore(
    series: pd.Series, window: int, min_periods: int | None = None
) -> pd.Series:
    """Rolling z-score of a series: ``(x − rolling_mean) / rolling_std``.

    Measures how many standard deviations the current level sits from its own
    recent history — a transparent richness/cheapness gauge for a spread. Pure
    and deterministic given inputs.

    Args:
        series: A date-indexed numeric series.
        window: Rolling window length, in observations.
        min_periods: Minimum observations before a z-score is emitted; defaults
            to one third of ``window`` (at least 2).

    Returns:
        A z-score series aligned to ``series`` (leading values are ``NaN`` until
        ``min_periods`` is reached). Empty when the input is empty.
    """
    if series is None or series.empty:
        return pd.Series(dtype="float64")
    mp = min_periods if min_periods is not None else max(2, window // 3)
    mean = series.rolling(window, min_periods=mp).mean()
    std = series.rolling(window, min_periods=mp).std()
    z = (series - mean) / std.replace(0.0, pd.NA)
    return z.astype("float64")


def zscore_label(z: float | None) -> str:
    """Human-readable band for a z-score (how stretched vs recent history).

    Args:
        z: A z-score, or ``None``.

    Returns:
        A short labelled string with a status emoji.
    """
    if z is None or pd.isna(z):
        return "➖ n/a"
    az = abs(z)
    if az >= 2.0:
        return ("🔴 Extremely high" if z > 0 else "🔵 Extremely low") + " vs 3y"
    if az >= 1.0:
        return ("🟠 High" if z > 0 else "🟠 Low") + " vs 3y"
    return "⚪ Near normal"


def implied_sharpe(
    carry: float | None, annualized_vol: float | None
) -> float | None:
    """Volatility-adjusted carry: carry divided by annualized FX volatility.

    A crude, transparent proxy for a carry trade's risk-adjusted attractiveness
    (higher is better). Not a true Sharpe ratio — there is no excess-return time
    series — but it ranks pairs by reward-per-unit-of-FX-risk.

    Args:
        carry: Interest-rate carry versus the base currency (pp).
        annualized_vol: Annualized realized FX volatility (%).

    Returns:
        The ratio (dimensionless), or ``None`` when inputs are missing or vol is
        non-positive.
    """
    if carry is None or annualized_vol is None or annualized_vol <= 0:
        return None
    return round(carry / annualized_vol, 2)
