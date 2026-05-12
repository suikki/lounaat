"""Linkosuo restaurants (Hertta and Orvokki).

Shared parser: the page contains a <dl class="week-lunch"> with
<dt>Maanantai 11.05.</dt><dd>dishes split by <br/>...</dd> pairs.

Each day's dishes are categorised by inline prefix:
  * "Keitto: ..."                            → Keitto
  * "Chef´s menu: ..."                       → Chef's menu
  * "Vegaaniruoka keittiöstä: ..." (Hertta)  → Päivän vegaani
  * "Keittiöstä päivän vegaani: ..." (Orvokki) → Päivän vegaani
  * "Jälkiruoaksi ..."                       → Jälkiruoka
  * everything else                          → main lunch (no header)
"""
from __future__ import annotations

import re
from datetime import date

from .common import (
    Day, Restaurant, Section, FI_WEEKDAYS, LOUNAS_LABEL,
    fetch, soup, clean_text, extract_lunch_hours, extract_lunch_price,
    weekday_index_from_text,
)


DATE_RE = re.compile(r"(\d{1,2})[./](\d{1,2})\.?")

VEGAN_LABEL = "Keittiöstä päivän vegaani"

SECTION_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"^chef[´'`]s\s+menu\s*:\s*", re.IGNORECASE), "Chef's menu"),
    (re.compile(r"^keitto\s*:\s*", re.IGNORECASE), "Keitto"),
    (re.compile(r"^vegaaniruoka\s+keittiöstä\s*:\s*", re.IGNORECASE), VEGAN_LABEL),
    (re.compile(r"^keittiöstä\s+päivän\s+vegaani\s*:\s*", re.IGNORECASE), VEGAN_LABEL),
    (re.compile(r"^päivän\s+vegaani\s*:\s*", re.IGNORECASE), VEGAN_LABEL),
    (re.compile(r"^jälkiruoaksi\s+", re.IGNORECASE), "Jälkiruoka"),
]

SECTION_ORDER: list[str] = [LOUNAS_LABEL, "Keitto", "Chef's menu", VEGAN_LABEL, "Jälkiruoka"]


def _categorize(line: str) -> tuple[str, str]:
    for pat, name in SECTION_PATTERNS:
        m = pat.match(line)
        if m:
            return name, line[m.end():].strip()
    return LOUNAS_LABEL, line


def _parse(html: str) -> tuple[list[Day], str | None]:
    s = soup(html)
    text = clean_text(s.get_text(" "))
    hours = extract_lunch_hours(text)
    buffet_price = extract_lunch_price(text)
    dl = s.find("dl", class_="week-lunch") or s.find(id="current-week-lunch") or s
    days: list[Day] = []
    dts = dl.find_all("dt") if dl else []
    today = date.today()
    for dt in dts:
        title = clean_text(dt.get_text(" "))
        weekday_idx = weekday_index_from_text(title)
        if weekday_idx is None:
            continue
        weekday_name = FI_WEEKDAYS[weekday_idx]

        # Try to extract DD.MM. for the date; assume current year
        d_iso: str
        m = DATE_RE.search(title)
        if m:
            day_n, month_n = int(m.group(1)), int(m.group(2))
            year = today.year
            try:
                d_iso = date(year, month_n, day_n).isoformat()
            except ValueError:
                d_iso = ""
        else:
            d_iso = ""

        dd = dt.find_next_sibling("dd")
        sections_map: dict[str, list[str]] = {}
        note = None
        if dd is not None:
            for br in dd.find_all("br"):
                br.replace_with("\n")
            text = dd.get_text("\n")
            for line in text.split("\n"):
                line = clean_text(line)
                if not line:
                    continue
                low = line.lower()
                if low in ("helatorstai", "suljettu") or "suljettu" in low:
                    note = line
                    continue
                # Skip the morning porridge — it's breakfast, not lunch.
                if "puuro" in low:
                    continue
                sec_name, dish = _categorize(line)
                if dish:
                    sections_map.setdefault(sec_name, []).append(dish)

        ordered = [
            Section(
                name=key,
                dishes=sections_map[key],
                price=buffet_price if key == LOUNAS_LABEL else None,
            )
            for key in SECTION_ORDER if key in sections_map
        ]
        days.append(Day(date=d_iso, weekday=weekday_name, sections=ordered, note=note))

    return days, hours


def _scrape_one(key: str, name: str, url: str) -> Restaurant:
    days, hours = _parse(fetch(url))
    return Restaurant(key=key, name=name, url=url, days=days, hours=hours)


def scrape_hertta() -> Restaurant:
    return _scrape_one(
        "linkosuo_hertta",
        "Linkosuo Hertta",
        "https://linkosuo.fi/toimipaikka/hertta/",
    )


def scrape_orvokki() -> Restaurant:
    return _scrape_one(
        "linkosuo_orvokki",
        "Linkosuo Orvokki",
        "https://linkosuo.fi/toimipaikka/lounasravintola-orvokki/",
    )
