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
    fetch, soup, clean_text, extract_lunch_hours, normalize_price, week_dates,
)


PANEL_IDS = ["panel-Monday", "panel-Tuesday", "panel-Wednesday", "panel-Thursday", "panel-Friday"]
PRICE_RE = re.compile(r"^\s*\d+[,.]?\d*\s*€?\s*$")
DROP_DISHES = {"kahvi", "keksi"}


def _diet_codes(button) -> str | None:
    """Return the dish's diet code list (e.g. ``"G, L"``) from the
    ``accordion__footer__special-diets`` div that sits as a sibling of the
    button's ``accordion`` wrapper, or None if absent/empty. The ``A`` code
    is Antell-specific and not informative to readers, so it's filtered out."""
    li = button.find_parent("li")
    if li is None:
        return None
    footer = li.find("div", class_="accordion__footer__special-diets")
    if footer is None:
        return None
    text = clean_text(footer.get_text(" "))
    tokens = [t.strip() for t in text.split(",") if t.strip() and t.strip().upper() != "A"]
    return ", ".join(tokens) if tokens else None


def _dish_string(button) -> str | None:
    """Return ``"Name (codes)"`` for an accordion button, or None if the
    button should be dropped (empty / on the drop list)."""
    name = clean_text(button.get_text(" "))
    if not name or name.lower() in DROP_DISHES:
        return None
    name = name.rstrip("#").strip()
    codes = _diet_codes(button)
    return f"{name} ({codes})" if codes else name


def _collect_dishes(scope) -> list[str]:
    """Collect dish strings for every accordion button under `scope`."""
    out: list[str] = []
    for btn in scope.find_all("button", class_="accordion__button"):
        s = _dish_string(btn)
        if s is not None:
            out.append(s)
    return out


def _parse_specials(div) -> list[Section]:
    """Walk a tabpanel__specials block in document order, grouping accordion
    buttons under each non-price <h5> heading. A second <h5> after the section
    name carries the price (e.g. "13,80 €")."""
    sections: list[Section] = []
    current: Section | None = None
    for el in div.find_all(["h5", "button"]):
        if el.name == "h5":
            txt = clean_text(el.get_text(" "))
            if not txt:
                continue
            if PRICE_RE.match(txt):
                if current is not None and current.price is None:
                    current.price = normalize_price(txt)
                continue
            current = Section(name=txt, dishes=[])
            sections.append(current)
        elif el.name == "button" and "accordion__button" in (el.get("class") or []):
            if current is None:
                continue
            s = _dish_string(el)
            if s is not None:
                current.dishes.append(s)
    return [s for s in sections if s.dishes]


def _buffet_price(div) -> str | None:
    el = div.find("div", class_="tabpanel__header__price")
    return normalize_price(el.get_text(" ")) if el else None


def _lunch_hours(soup_root) -> str | None:
    entry = soup_root.find("div", class_="entry-content")
    return extract_lunch_hours(entry.get_text(" ")) if entry else None


def _parse(html: str) -> tuple[list[Day], str | None]:
    s = soup(html)
    dates = week_dates()
    out: list[Day] = []
    for i, pid in enumerate(PANEL_IDS):
        section = s.find("section", id=pid)
        sections: list[Section] = []
        note = None

        if section is not None:
            for h in section.find_all("h5"):
                txt = clean_text(h.get_text(" "))
                if txt and "ei lounaslistaa" in txt.lower():
                    note = txt
                    break

            buffet_div = section.find("div", class_="tabpanel__buffet")
            if buffet_div is not None:
                dishes = _collect_dishes(buffet_div)
                if dishes:
                    sections.append(Section(
                        name=LOUNAS_LABEL, dishes=dishes,
                        price=_buffet_price(buffet_div),
                    ))

            specials_div = section.find("div", class_="tabpanel__specials")
            if specials_div is not None:
                sections.extend(_parse_specials(specials_div))

        out.append(Day(
            date=dates[i].isoformat(),
            weekday=FI_WEEKDAYS[i],
            sections=sections,
            note=note,
        ))
    return out, _lunch_hours(s)


def scrape() -> Restaurant:
    url = "https://antell.fi/lounas/tampere/hermianfarmi/"
    days, hours = _parse(fetch(url))
    return Restaurant(
        key="antell_hermianfarmi",
        name="Antell Hermianfarmi",
        url=url,
        days=days,
        hours=hours,
    )
