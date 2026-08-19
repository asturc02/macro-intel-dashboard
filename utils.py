"""Display and formatting helpers shared across modules (no Streamlit here)."""

from __future__ import annotations

from datetime import date

import pandas as pd

import config


def window_start(years: int | None) -> str | None:
    """Return an ISO start date ``years`` back from today, or ``None`` for Max.

    Args:
        years: Number of years of history, or ``None`` for no lower bound.

    Returns:
        An ISO ``YYYY-MM-DD`` string, or ``None`` when ``years`` is ``None``.
    """
    if years is None:
        return None
    today = date.today()
    try:
        start = today.replace(year=today.year - years)
    except ValueError:  # Feb 29 edge case.
        start = today.replace(year=today.year - years, day=28)
    return start.isoformat()


def fmt(value: float | None, suffix: str = "", decimals: int = 2) -> str:
    """Format an optional number for table/metric display.

    Args:
        value: The number to format, or ``None``.
        suffix: Optional unit suffix (e.g. ``"%"``).
        decimals: Number of decimal places.

    Returns:
        A formatted string, or ``"n/a"`` when ``value`` is ``None``/NaN.
    """
    if value is None:
        return "n/a"
    try:
        if pd.isna(value):
            return "n/a"
    except (TypeError, ValueError):
        pass
    return f"{value:.{decimals}f}{suffix}"


def fmt_signed(value: float | None, suffix: str = "", decimals: int = 2) -> str:
    """Like :func:`fmt` but always shows an explicit ``+``/``-`` sign.

    Args:
        value: The number to format, or ``None``.
        suffix: Optional unit suffix.
        decimals: Number of decimal places.

    Returns:
        A signed formatted string, or ``"n/a"``.
    """
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return "n/a"
    return f"{value:+.{decimals}f}{suffix}"


def stance_color(stance: str) -> str:
    """Map a stance label to its brand hex color.

    Args:
        stance: One of ``Hawk`` / ``Neutral`` / ``Dove`` (any case).

    Returns:
        A hex color string; neutral gray for unknown input.
    """
    return {
        config.HAWK: config.COLOR_HAWK,
        config.DOVE: config.COLOR_DOVE,
        config.NEUTRAL: config.COLOR_NEUTRAL,
    }.get(stance, config.COLOR_NEUTRAL)


def stance_badge(stance: str) -> str:
    """Return an emoji-prefixed stance label for compact display.

    Args:
        stance: One of ``Hawk`` / ``Neutral`` / ``Dove``.

    Returns:
        A short badge string such as ``"🦅 Hawk"`` or ``"🕊️ Dove"``.
    """
    return {
        config.HAWK: "🦅 Hawk",
        config.DOVE: "🕊️ Dove",
        config.NEUTRAL: "➖ Neutral",
    }.get(stance, stance)
