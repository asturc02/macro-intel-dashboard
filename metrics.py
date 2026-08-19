"""Quantitative macro metrics: real rates, stance, carry, and differentials.

Pure functions over already-fetched values — no network, no UI. This is the
analytical core an interviewer would look at: transparent, rule-based, and
unit-tested by construction (deterministic given inputs).
"""

from __future__ import annotations

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
