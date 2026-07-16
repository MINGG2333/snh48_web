"""Recurring debut milestone dates and homepage celebration state."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

from website import config as cfg


BJT = timezone(timedelta(hours=8))
FIRST_MILESTONE_DAY = 300
DEFAULT_300_DATE = date(2026, 7, 31)


def _parse_iso_date(value: str, fallback: Optional[date] = None) -> Optional[date]:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return fallback


def milestone_300_date() -> date:
    """Return the configured formal date of debut day 300."""
    return _parse_iso_date(cfg.DEBUT_300_DATE, DEFAULT_300_DATE) or DEFAULT_300_DATE


def debut_date() -> date:
    """Derive debut day 1 from the authoritative day-300 date."""
    return milestone_300_date() - timedelta(days=FIRST_MILESTONE_DAY - 1)


def milestone_date(day_number: int) -> date:
    """Return the date for a milestone day number such as 300 or 400."""
    if day_number < FIRST_MILESTONE_DAY:
        raise ValueError(f"milestone day must be at least {FIRST_MILESTONE_DAY}")
    return milestone_300_date() + timedelta(days=day_number - FIRST_MILESTONE_DAY)


def reached_milestone_days(on_date: date) -> list[int]:
    """Return all recurring hundred-day milestones reached by a date."""
    first_date = milestone_300_date()
    if on_date < first_date:
        return []
    interval = cfg.DEBUT_MILESTONE_INTERVAL_DAYS
    latest_day = FIRST_MILESTONE_DAY + ((on_date - first_date).days // interval) * interval
    return list(range(FIRST_MILESTONE_DAY, latest_day + 1, interval))


def timeline_milestone_days(on_date: date) -> list[int]:
    """Return permanent timeline milestones, previewing day 300 before it arrives."""
    reached = reached_milestone_days(on_date)
    return reached or [FIRST_MILESTONE_DAY]


def build_homepage_context(on_date: Optional[date] = None) -> dict[str, Any]:
    """Build animation and permanent scroller state for a homepage request."""
    today = on_date or datetime.now(BJT).date()
    reached = reached_milestone_days(today)
    preview_date = _parse_iso_date(cfg.DEBUT_300_TEST_DATE)
    is_preview = preview_date == today

    active_day: Optional[int] = FIRST_MILESTONE_DAY if is_preview else None
    if active_day is None and reached:
        latest_day = reached[-1]
        latest_date = milestone_date(latest_day)
        if today <= latest_date + timedelta(days=cfg.DEBUT_CELEBRATION_DAYS_AFTER):
            active_day = latest_day

    featured_days = list(reached)
    if is_preview and FIRST_MILESTONE_DAY not in featured_days:
        featured_days.append(FIRST_MILESTONE_DAY)
    featured_days.sort()
    featured_texts = [f"祝贺嘉仪出道{day}天！" for day in featured_days]

    display_day = active_day or FIRST_MILESTONE_DAY
    formal_date = milestone_date(display_day)
    trigger_date = preview_date if is_preview else formal_date
    window_end = formal_date + timedelta(days=cfg.DEBUT_CELEBRATION_DAYS_AFTER)
    return {
        # Keep the original keys so a template update remains compatible with
        # an already-running process during staged deployment.
        "active": active_day is not None,
        "featured_text": "||".join(featured_texts),
        "formal_date": formal_date.isoformat(),
        "trigger_date": trigger_date.isoformat(),
        "is_test": is_preview,
        # General recurring-milestone fields.
        "milestone_day": display_day,
        "debut_date": debut_date().isoformat(),
        "window_end": window_end.isoformat(),
        "featured_texts": featured_texts,
    }
