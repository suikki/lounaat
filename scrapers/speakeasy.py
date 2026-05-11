"""Speakeasy Hervanta.

The menu lives in a content block with heavy inline styling. Day headers
are uppercase weekday names with a date suffix like "MAANANTAI 11.5."
followed by dishes separated by line breaks. We extract the text content,
split on weekday markers, and clean each line.
"""
from __future__ import annotations

import re
from datetime import date

from .common import (
    Day, Restaurant, Section, FI_WEEKDAYS, FI_WEEKDAY_ALIASES, LOUNAS_LABEL,
    fetch, soup, clean_text, week_dates,
)


DAY_LINE_RE = re.compile(
    r"^(maanantai|tiistai|keskiviikko|torstai|perjantai)\b\s*(\d{1,2})?[./]?\s*(\d{1,2})?\.?\s*$",
    re.IGNORECASE,
)
WEEKEND_LINE_RE = re.compile(r"^(lauantai|sunnuntai)\b", re.IGNORECASE)
ENG_WEEKDAY_RE = re.compile(
    r"^(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b",
    re.IGNORECASE,
)
LEGEND_RE = re.compile(r"^[lgmv]\s*=", re.IGNORECASE)
# Section headers in the page footer that mark the end of menu content
FOOTER_MARKERS = {"menu", "takeaway", "kanta-asiakkaat", "olemme avoinna", "opening hours"}


def _extract_lines(html: str) -> list[str]:
    s = soup(html)
    # Restrict to the main content if available
    content = s.find("article") or s.find("main") or s
    # Replace <br> with newlines
    for br in content.find_all("br"):
        br.replace_with("\n")
    # Replace block elements with newline-separated text
    text = content.get_text("\n")
    lines = [clean_text(line) for line in text.split("\n")]
    return [l for l in lines if l]


def _parse(html: str) -> list[Day]:
    lines = _extract_lines(html)
    days_map: dict[int, list[str]] = {}
    date_map: dict[int, str] = {}
    current: int | None = None
    today = date.today()

    for line in lines:
        m = DAY_LINE_RE.match(line)
        if m:
            current = FI_WEEKDAY_ALIASES[m.group(1).lower()]
            days_map.setdefault(current, [])
            try:
                day_n = m.group(2); month_n = m.group(3)
                if day_n and month_n:
                    date_map[current] = date(today.year, int(month_n), int(day_n)).isoformat()
            except (ValueError, TypeError):
                pass
            continue
        if (
            WEEKEND_LINE_RE.match(line)
            or ENG_WEEKDAY_RE.match(line)
            or LEGEND_RE.match(line)
        ):
            current = None
            continue
        if current is None:
            continue
        low = line.lower()
        if low in FOOTER_MARKERS or any(t in low for t in (
            "tilaa pöytä", "varaa pöytä", "soita", "tervetuloa",
            "lounas tarjoillaan", "yhteystiedot",
        )):
            current = None
            continue
        # Skip fragments left by messy span splitting: single chars, bare
        # punctuation, isolated allergen codes like "(l,", "g", ")".
        if len(line) <= 3:
            continue
        days_map[current].append(line)

    dates = week_dates()
    days: list[Day] = []
    for i in range(5):
        d_iso = date_map.get(i, dates[i].isoformat())
        items = days_map.get(i, [])
        sections = [Section(name=LOUNAS_LABEL, dishes=items)] if items else []
        days.append(Day(date=d_iso, weekday=FI_WEEKDAYS[i], sections=sections))
    return days


def scrape() -> Restaurant:
    url = "https://www.speakeasy.fi/hervanta/lounas/"
    return Restaurant(
        key="speakeasy_hervanta",
        name="Speakeasy Hervanta",
        url=url,
        days=_parse(fetch(url)),
    )
