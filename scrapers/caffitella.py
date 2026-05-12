"""Caffitella Duo Tampere.

Caffitella publishes one menu shared across several locations including
Duo Tampere. Structure: a <p><b>Maanantai</b></p> header per weekday,
followed by several <p> blocks of dishes until the next day header.

The page has multiple location groupings; we find the group containing
"Duo Tampere" and parse the day blocks under it.
"""
from __future__ import annotations

import re

from .common import (
    Day, Restaurant, Section, FI_WEEKDAYS, LOUNAS_LABEL,
    WEEKDAY_HEADER_RE, WEEKEND_HEADER_RE,
    fetch, soup, clean_text, extract_lunch_hours, extract_lunch_price,
    week_dates, weekday_index_from_text,
)


# Caffitella tags portion meals (à la carte; not included in the buffet) by
# appending "(Annosruoka ei sis. buffettin)" to the dish line. We strip that
# note and put the dish in its own "Annosruoka" section.
ANNOSRUOKA_NOTE_RE = re.compile(r"\(\s*annosruoka[^)]*\)\s*", re.IGNORECASE)

# Caffitella often glues two Annosruoka dishes into one paragraph, separated
# only by whitespace after the first dish's allergen paren — e.g.
# "Yrttibroileri burger (L)  Vuohenjuusto poke (G,L)". Split on close-paren
# + whitespace + non-paren so we don't accidentally split a single dish that
# carries two parens (e.g. "Dish (M) (suomalaista possua)").
ANNOSRUOKA_SPLIT_RE = re.compile(r"(?<=\))\s+(?=[^(])")

def _parse(html: str) -> tuple[list[Day], str | None]:
    s = soup(html)

    # Find the heading that mentions Duo Tampere, then walk forward and
    # collect day blocks until we hit the next major heading.
    target_heading = None
    for h in s.find_all(["h1", "h2", "h3", "h4"]):
        txt = clean_text(h.get_text(" "))
        if "duo tampere" in txt.lower():
            target_heading = h
            break

    # Restaurant-wide hours and price live in plain paragraphs near the top.
    # Extract them from the full document — extract_lunch_* search for
    # "klo"/"lounas" anchors so unrelated mentions elsewhere are ignored.
    page_text = clean_text(s.get_text(" "))
    hours = extract_lunch_hours(page_text)
    price = extract_lunch_price(page_text)

    days_map: dict[int, list[str]] = {}
    annos_map: dict[int, list[str]] = {}
    current_idx: int | None = None

    iterator = (
        target_heading.find_all_next(["p", "h2", "h3", "h4"])
        if target_heading else s.find_all(["p", "h2", "h3", "h4"])
    )
    for el in iterator:
        if el.name in ("h2", "h3", "h4"):
            txt = clean_text(el.get_text(" "))
            if target_heading is not None and txt and "duo" not in txt.lower():
                # Different location group — stop
                break
            continue
        text = clean_text(el.get_text(" "))
        if not text:
            continue
        if WEEKDAY_HEADER_RE.match(text):
            idx = weekday_index_from_text(text)
            if idx is not None and idx < 5:
                current_idx = idx
                days_map.setdefault(current_idx, [])
            continue
        if WEEKEND_HEADER_RE.match(text):
            # Past Friday — stop collecting for this location group.
            current_idx = None
            continue
        if current_idx is None:
            continue
        low = text.lower()
        if low == "salaattibuffet":
            continue
        if low.startswith(("vko", "päivämäärä", "lounasbuffet", "viikkonumero")):
            continue
        if "annosruoka" in low:
            cleaned = clean_text(ANNOSRUOKA_NOTE_RE.sub("", text))
            if cleaned:
                bucket = annos_map.setdefault(current_idx, [])
                for piece in ANNOSRUOKA_SPLIT_RE.split(cleaned):
                    piece = piece.strip()
                    if piece:
                        bucket.append(piece)
            continue
        days_map[current_idx].append(text)

    dates = week_dates()
    days: list[Day] = []
    for i in range(5):
        sections: list[Section] = []
        main_items = days_map.get(i, [])
        if main_items:
            sections.append(Section(name=LOUNAS_LABEL, dishes=main_items, price=price))
        annos_items = annos_map.get(i, [])
        if annos_items:
            sections.append(Section(name="Annosruoka", dishes=annos_items))
        days.append(Day(date=dates[i].isoformat(), weekday=FI_WEEKDAYS[i], sections=sections))
    return days, hours


def scrape() -> Restaurant:
    url = "https://www.caffitella.fi/lounaslista/"
    days, hours = _parse(fetch(url))
    return Restaurant(
        key="caffitella_duo",
        name="Caffitella Duo Tampere",
        url=url,
        days=days,
        hours=hours,
    )
