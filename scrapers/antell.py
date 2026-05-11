"""Antell Hermianfarmi.

Each day's `<section id="panel-Monday">` contains two sibling blocks:

  * `<div class="tabpanel__buffet">` — the Lounasbuffet, with internal
    sub-sections marked by <h5> (Pääruoaksi, Pääruoan kaveriksi, Jälkiruoaksi).
    We flatten these into one "Lounasbuffet" section and drop "Kahvi" since
    coffee is included with every lunch and not a dish.

  * `<div class="tabpanel__specials">` — the alternatives (Grilliannos,
    Delilounas, Pizzalounas), each introduced by its own <h5>. Each becomes
    its own section.

When the day's menu is unavailable, Antell renders
`<h5>Ei lounaslistaa saatavilla</h5>` and we capture that as the day's note.
"""
from __future__ import annotations

import re

from .common import (
    Day, Restaurant, Section, FI_WEEKDAYS, LOUNAS_LABEL,
    fetch, soup, clean_text, week_dates,
)


PANEL_IDS = ["panel-Monday", "panel-Tuesday", "panel-Wednesday", "panel-Thursday", "panel-Friday"]
PRICE_RE = re.compile(r"^\s*\d+[,.]?\d*\s*€?\s*$")
DROP_DISHES = {"kahvi", "keksi"}


def _collect_dishes(scope) -> list[str]:
    """Collect accordion button names within a scope, dropping uninteresting
    items and stripping the trailing '#' annotation Antell's CMS surfaces
    without a legend."""
    out: list[str] = []
    for btn in scope.find_all("button", class_="accordion__button"):
        name = clean_text(btn.get_text(" "))
        if not name:
            continue
        if name.lower() in DROP_DISHES:
            continue
        name = name.rstrip("#").strip()
        out.append(name)
    return out


def _parse_specials(div) -> list[Section]:
    """Walk a tabpanel__specials block in document order, grouping accordion
    buttons under each non-price <h5> heading."""
    sections: list[Section] = []
    current: Section | None = None
    for el in div.find_all(["h5", "button"]):
        if el.name == "h5":
            txt = clean_text(el.get_text(" "))
            if not txt or PRICE_RE.match(txt):
                continue
            current = Section(name=txt, dishes=[])
            sections.append(current)
        elif el.name == "button" and "accordion__button" in (el.get("class") or []):
            if current is None:
                continue
            name = clean_text(el.get_text(" "))
            if not name or name.lower() in DROP_DISHES:
                continue
            current.dishes.append(name.rstrip("#").strip())
    # Drop sections that ended up empty (no dishes found)
    return [s for s in sections if s.dishes]


def _parse(html: str) -> list[Day]:
    s = soup(html)
    dates = week_dates()
    out: list[Day] = []
    for i, pid in enumerate(PANEL_IDS):
        section = s.find("section", id=pid)
        sections: list[Section] = []
        note = None

        if section is not None:
            # "No menu available" note
            for h in section.find_all("h5"):
                txt = clean_text(h.get_text(" "))
                if txt and "ei lounaslistaa" in txt.lower():
                    note = txt
                    break

            buffet_div = section.find("div", class_="tabpanel__buffet")
            if buffet_div is not None:
                dishes = _collect_dishes(buffet_div)
                if dishes:
                    sections.append(Section(name=LOUNAS_LABEL, dishes=dishes))

            specials_div = section.find("div", class_="tabpanel__specials")
            if specials_div is not None:
                sections.extend(_parse_specials(specials_div))

        out.append(Day(
            date=dates[i].isoformat(),
            weekday=FI_WEEKDAYS[i],
            sections=sections,
            note=note,
        ))
    return out


def scrape() -> Restaurant:
    url = "https://antell.fi/lounas/tampere/hermianfarmi/"
    return Restaurant(
        key="antell_hermianfarmi",
        name="Antell Hermianfarmi",
        url=url,
        days=_parse(fetch(url)),
    )
