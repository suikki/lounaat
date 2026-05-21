"""Shared utilities for restaurant scrapers."""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field, asdict
from datetime import date, datetime, timezone, timedelta

import requests
from bs4 import BeautifulSoup


USER_AGENT = (
    "Mozilla/5.0 (compatible; lounaat-bot/1.0; "
    "+https://github.com/ aggregating public lunch menus)"
)
HTTP_TIMEOUT = 20
HTTP_RETRIES = 2          # total attempts per URL (the daily cron retries too)
HTTP_RETRY_BACKOFF = 3    # seconds; multiplied by the attempt number

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
    main lunch / keitto / chef's menu / vegaani).

    ``price`` is best-effort metadata; renders dimmed next to the section
    heading when present. (Hours live on Restaurant since they're typically
    the same for every section.)
    """
    name: str | None = None
    dishes: list[str] = field(default_factory=list)
    price: str | None = None  # e.g. "13,80 €"


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
    hours: str | None = None  # daily lunch hours, e.g. "10:30–13:00"
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
    """Fetch a URL and return text, raising on HTTP errors.

    Transient failures — connection errors, timeouts, 5xx responses — are
    retried with a short backoff, since restaurant sites are often briefly
    unreachable. 4xx responses are not retried; they won't fix themselves.
    """
    h = {"User-Agent": USER_AGENT, "Accept-Language": "fi,en;q=0.7"}
    if headers:
        h.update(headers)
    last_exc: Exception | None = None
    for attempt in range(1, HTTP_RETRIES + 1):
        try:
            r = requests.get(url, headers=h, timeout=HTTP_TIMEOUT)
            r.raise_for_status()
            # Trust server's declared encoding, fall back to apparent
            if not r.encoding or r.encoding.lower() == "iso-8859-1":
                r.encoding = r.apparent_encoding or "utf-8"
            return r.text
        except requests.HTTPError as e:
            status = e.response.status_code if e.response is not None else None
            if status is not None and status < 500:
                raise  # client error — a retry won't help
            last_exc = e
        except (requests.ConnectionError, requests.Timeout) as e:
            last_exc = e
        if attempt < HTTP_RETRIES:
            print(
                f"  [fetch] {url} failed ({last_exc.__class__.__name__}); "
                f"retry {attempt + 1}/{HTTP_RETRIES}",
                flush=True,
            )
            time.sleep(HTTP_RETRY_BACKOFF * attempt)
    assert last_exc is not None  # loop ran at least once
    raise last_exc


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


_HOURS_RE = re.compile(r"(\d{1,2})[\.:]?(\d{0,2})\s*[-–]\s*(\d{1,2})[\.:]?(\d{0,2})")
_DIGIT_SPLIT_RE = re.compile(r"(?<=\d)\s+(?=\d)")
_TIME_RANGE = r"(\d{1,2}[\.:]?\d{0,2}\s*[-–]\s*\d{1,2}[\.:]?\d{0,2})"
# Try most specific first — "lounas ... klo TIME" — so a page with both an
# unrelated earlier "klo" (e.g. breakfast hours) and a real "lounas klo" line
# still picks the lunch range. Fall back to "klo TIME" then "lounas ... TIME".
_LOUNAS_KLO_HOURS_RE = re.compile(
    rf"lounas\b[^.]{{0,80}}?\bk\s*lo\b\s+{_TIME_RANGE}",
    re.IGNORECASE | re.DOTALL,
)
_KLO_HOURS_RE = re.compile(rf"\bk\s*lo\b\s+{_TIME_RANGE}", re.IGNORECASE)
_LOUNAS_HOURS_RE = re.compile(rf"lounas\b[^.]{{0,80}}?{_TIME_RANGE}", re.IGNORECASE | re.DOTALL)
_PRICE_NUM_RE = re.compile(r"(\d+)[,.](\d{1,2})")
_LUNCH_PRICE_RE = re.compile(r"lounas[^.]{0,40}?(\d+[,.]\d+)\s*€", re.IGNORECASE)


def normalize_hours(s: str | None) -> str | None:
    """Normalise a time range to ``HH:MM–HH:MM`` (en-dash). Accepts the many
    formats Finnish lunch pages use: ``"10.30-14"``, ``"8:30 – 13.00"``,
    ``"10:30-13:30"``. Returns None if no plausible range is found."""
    if not s:
        return None
    m = _HOURS_RE.search(s)
    if not m:
        return None
    h1, mm1, h2, mm2 = m.groups()
    return f"{int(h1):02d}:{(mm1 or '00').ljust(2, '0')}–{int(h2):02d}:{(mm2 or '00').ljust(2, '0')}"


def normalize_price(s: str | None) -> str | None:
    """Return a price string in canonical ``"X,XX €"`` form (Finnish comma
    decimal, single space, trailing euro sign), or None if no price found."""
    if not s:
        return None
    m = _PRICE_NUM_RE.search(s)
    if not m:
        return None
    return f"{m.group(1)},{m.group(2).ljust(2, '0')} €"


def extract_lunch_hours(text: str | None) -> str | None:
    """Find a time range near 'klo' or 'lounas' in `text` and normalise it.

    Pre-collapses single-whitespace between digits so pages whose markup
    splits numbers across spans (e.g. Speakeasy's ``"1 4.30"``) still match.
    """
    if not text:
        return None
    text = _DIGIT_SPLIT_RE.sub("", text)
    m = (
        _LOUNAS_KLO_HOURS_RE.search(text)
        or _KLO_HOURS_RE.search(text)
        or _LOUNAS_HOURS_RE.search(text)
    )
    return normalize_hours(m.group(1)) if m else None


def extract_lunch_price(text: str | None) -> str | None:
    """Find a buffet/lunch price near 'lounas' in `text` and normalise it."""
    if not text:
        return None
    m = _LUNCH_PRICE_RE.search(text)
    return normalize_price(m.group(1)) if m else None


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
