"""Shared utilities for restaurant scrapers."""
from __future__ import annotations

import re
from dataclasses import dataclass, field, asdict
from datetime import date, datetime, timezone, timedelta

import requests
from bs4 import BeautifulSoup


USER_AGENT = (
    "Mozilla/5.0 (compatible; lounaat-bot/1.0; "
    "+https://github.com/ aggregating public lunch menus)"
)
HTTP_TIMEOUT = 20

FI_WEEKDAYS = ["Maanantai", "Tiistai", "Keskiviikko", "Torstai", "Perjantai", "Lauantai", "Sunnuntai"]
FI_WEEKDAY_ALIASES = {
    "maanantai": 0, "ma": 0,
    "tiistai": 1, "ti": 1,
    "keskiviikko": 2, "ke": 2,
    "torstai": 3, "to": 3,
    "perjantai": 4, "pe": 4,
    "lauantai": 5, "la": 5,
    "sunnuntai": 6, "su": 6,
}

_FULL_WEEKDAY_NAMES = [k for k in FI_WEEKDAY_ALIASES if len(k) > 2]
_WEEKDAY_ALT = "|".join(n for n in _FULL_WEEKDAY_NAMES if FI_WEEKDAY_ALIASES[n] < 5)
_WEEKEND_ALT = "|".join(n for n in _FULL_WEEKDAY_NAMES if FI_WEEKDAY_ALIASES[n] >= 5)
WEEKDAY_HEADER_RE = re.compile(rf"^\s*({_WEEKDAY_ALT})\s*$", re.IGNORECASE)
WEEKEND_HEADER_RE = re.compile(rf"^\s*({_WEEKEND_ALT})\b", re.IGNORECASE)

# Canonical name for a restaurant's primary lunch section. Every scraper that
# emits a "main lunch" section should use this so it renders identically.
LOUNAS_LABEL = "Lounas"


@dataclass
class Section:
    """A sub-list of dishes within a day. Used when a restaurant offers multiple
    distinct menus per day (e.g. Antell: buffet / grill / deli / pizza; Linkosuo:
    main lunch / keitto / chef's menu / vegaani)."""
    name: str | None = None
    dishes: list[str] = field(default_factory=list)


@dataclass
class Day:
    date: str  # ISO date, e.g. "2026-05-11"
    weekday: str  # Finnish, e.g. "Maanantai"
    sections: list[Section] = field(default_factory=list)
    note: str | None = None  # e.g. "Suljettu" / "Helatorstai"


@dataclass
class Restaurant:
    key: str  # short id, e.g. "linkosuo_hertta"
    name: str
    url: str
    days: list[Day] = field(default_factory=list)
    error: str | None = None

    def to_dict(self) -> dict:
        """Serialise to a JSON-ready dict — single source of truth for the
        published format so any future scraper gets uniform notes and dish
        shape for free.

        Each dish becomes ``{"name": str, "meta": str | None}`` where ``meta``
        holds the trailing parenthesised info (allergen codes + dietary notes)
        that the frontend renders dimmed alongside the name.
        """
        d = asdict(self)
        for day in d.get("days", []):
            if day.get("note"):
                day["note"] = normalize_note(day["note"])
            for sec in day.get("sections", []):
                sec["dishes"] = [normalize_dish(x) for x in sec.get("dishes", [])]
        return d


def fetch(url: str, *, headers: dict | None = None) -> str:
    """Fetch a URL and return text, raising on HTTP errors."""
    h = {"User-Agent": USER_AGENT, "Accept-Language": "fi,en;q=0.7"}
    if headers:
        h.update(headers)
    r = requests.get(url, headers=h, timeout=HTTP_TIMEOUT)
    r.raise_for_status()
    # Trust server's declared encoding, fall back to apparent
    if not r.encoding or r.encoding.lower() == "iso-8859-1":
        r.encoding = r.apparent_encoding or "utf-8"
    return r.text


def soup(html: str) -> BeautifulSoup:
    # lxml is required because Python's stdlib html.parser mis-handles `<br />`
    # in some pages and swallows trailing siblings into the br node.
    return BeautifulSoup(html, "lxml")


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def week_dates(reference: date | None = None) -> list[date]:
    """Return Mon..Fri dates for the week containing `reference` (default today)."""
    ref = reference or date.today()
    monday = ref - timedelta(days=ref.weekday())
    return [monday + timedelta(days=i) for i in range(5)]


def clean_text(s: str) -> str:
    """Collapse whitespace and strip."""
    return " ".join(s.split()).strip()


def weekday_index_from_text(s: str) -> int | None:
    """Find a Finnish weekday name in s and return 0..6, else None."""
    low = s.lower()
    for alias, idx in FI_WEEKDAY_ALIASES.items():
        if alias in low:
            i = low.find(alias)
            before = low[i - 1] if i > 0 else " "
            after = low[i + len(alias)] if i + len(alias) < len(low) else " "
            if not before.isalpha() and not after.isalpha():
                return idx
    return None


# Allergen / diet codes used by Finnish lunch restaurants.
#   M  = maidoton (dairy-free)
#   L  = laktoositon (lactose-free)
#   VL = vähälaktoosinen (low lactose)
#   G  = gluteeniton (gluten-free)
#   VEG / VEGE = vegaani
#   K  = kasvis (vegetarian)
ALLERGEN_TOKENS = {"M", "L", "VL", "G", "VEG", "VEGE", "K"}
ALLERGEN_ORDER = ["L", "M", "VL", "G", "VEG", "VEGE", "K"]

_PAREN_RE = re.compile(r"\(([^)]*)\)")
_INLINE_RE = re.compile(r"(\s)([A-Za-z]{1,4}(?:\s*,\s*[A-Za-z]{1,4})*)(?=\s|$|\()")
_TOKEN_SPLIT_RE = re.compile(r"[,;/\s]+")
_WHITESPACE_RE = re.compile(r"\s+")
_TRAIL_PUNCT_RE = re.compile(r"[\s,;]+$")
_ADJACENT_PARENS_RE = re.compile(r"\(([^)]*)\)(\s*\(([^)]*)\))+")
_ALL_PARENS_RE = re.compile(r"\(([^)]*)\)")
_TRAILING_PAREN_RE = re.compile(r"^(.+?)\s*\(([^)]*)\)\s*$", re.DOTALL)


def normalize_dish(s: str) -> dict:
    """Normalise a dish string and return ``{"name": str, "meta": str | None}``.

    All allergen / diet codes scattered through the source text (``"M, G"``,
    ``"(l,g)"``, ``"(M) (suomalaista possua)"``) are collected and merged with
    any other parenthesised note into a single trailing paren whose contents
    become the ``meta`` field. The frontend renders ``meta`` dimmed beside the
    dish name, without needing to parse anything itself.

    Non-allergen parenthetical notes (``"(maito, sinappi)"``, ``"(suomalaista
    possua)"``) are preserved as-is and merged with the allergen codes.
    """
    found: set[str] = set()

    def replace_paren(m: re.Match[str]) -> str:
        content = m.group(1)
        tokens = [t.strip().upper() for t in _TOKEN_SPLIT_RE.split(content) if t.strip()]
        if tokens and all(t in ALLERGEN_TOKENS for t in tokens):
            found.update(tokens)
            return " "
        return m.group(0)

    s = _PAREN_RE.sub(replace_paren, s)

    def replace_inline(m: re.Match[str]) -> str:
        leading_space, candidate = m.group(1), m.group(2)
        tokens = [t.strip().upper() for t in candidate.split(",") if t.strip()]
        if tokens and all(t in ALLERGEN_TOKENS for t in tokens):
            found.update(tokens)
            return leading_space
        return m.group(0)

    s = _INLINE_RE.sub(replace_inline, s)
    s = _WHITESPACE_RE.sub(" ", s).strip()
    s = _TRAIL_PUNCT_RE.sub("", s).strip()

    if found:
        ordered = [c for c in ALLERGEN_ORDER if c in found]
        s = f"{s} ({', '.join(ordered)})"

    # Merge consecutive parenthetical groups separated only by whitespace into
    # a single comma-separated paren: "(maito, sinappi) (L, G)" → "(maito, sinappi, L, G)".
    s = _merge_adjacent_parens(s)

    m = _TRAILING_PAREN_RE.match(s)
    if m:
        return {"name": m.group(1).strip(), "meta": m.group(2).strip()}
    return {"name": s.strip(), "meta": None}


def normalize_note(s: str | None) -> str | None:
    """Sentence-case a Day.note so notes like ``HELATORSTAI`` and
    ``Helatorstai`` render uniformly across restaurants."""
    if not s:
        return s
    s = s.strip()
    if not s:
        return None
    return s[:1].upper() + s[1:].lower()


def _merge_adjacent_parens(s: str) -> str:
    def merge(m: re.Match[str]) -> str:
        contents = _ALL_PARENS_RE.findall(m.group(0))
        merged = ", ".join(c.strip() for c in contents if c.strip())
        return f"({merged})"
    # One pass suffices: each match collapses into a single paren, which has
    # no adjacent paren left to re-match.
    return _ADJACENT_PARENS_RE.sub(merge, s)
