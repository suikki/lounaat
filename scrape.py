"""Run all restaurant scrapers and emit site/data/menus.json.

Usage:
    python scrape.py              # all restaurants
    python scrape.py haitari      # only one (by key substring)
"""
from __future__ import annotations

import json
import sys
import traceback
from datetime import date
from pathlib import Path

from scrapers.common import now_iso
from scrapers import linkosuo, antell, caffitella, speakeasy


SCRAPERS = [
    ("linkosuo_hertta", linkosuo.scrape_hertta),
    ("linkosuo_orvokki", linkosuo.scrape_orvokki),
    ("antell_hermianfarmi", antell.scrape),
    ("caffitella_duo", caffitella.scrape),
    ("speakeasy_hervanta", speakeasy.scrape),
]


def iso_week(d: date | None = None) -> int:
    return (d or date.today()).isocalendar().week


def main(argv: list[str]) -> int:
    only = argv[1] if len(argv) > 1 else None

    out_path = Path(__file__).parent / "docs" / "data" / "menus.json"

    # Always load the previous output. It serves two purposes: a failed
    # scraper falls back to its last-known-good menu (so a transient outage
    # doesn't blank out a restaurant), and restaurants skipped by `only` are
    # preserved (otherwise iterative dev would wipe them from menus.json).
    existing_by_key: dict[str, dict] = {}
    try:
        prev = json.loads(out_path.read_text(encoding="utf-8"))
        for r in prev.get("restaurants", []):
            existing_by_key[r.get("key", "")] = r
    except FileNotFoundError:
        pass
    except (json.JSONDecodeError, OSError) as e:
        print(f"[scrape] WARNING: could not read previous menus.json: {e}")

    new_results: dict[str, dict] = {}
    any_failed = False
    for key, fn in SCRAPERS:
        if only and only.lower() not in key.lower():
            continue
        print(f"[scrape] {key} ...", flush=True)
        try:
            data = fn().to_dict()
            new_results[key] = data
            n_dishes = sum(
                len(s["dishes"]) for d in data["days"] for s in d.get("sections", [])
            )
            print(f"  ok — {len(data['days'])} days, {n_dishes} dishes")
        except Exception as e:
            any_failed = True
            err = f"{type(e).__name__}: {e}"
            print(f"  FAIL: {err}")
            traceback.print_exc()
            prev_r = existing_by_key.get(key)
            if prev_r and prev_r.get("days"):
                # Keep the last-known-good menu visible; flag the failed
                # refresh via `error` so the frontend can note it's stale.
                new_results[key] = {**prev_r, "error": err}
                print(f"  -> keeping previous data ({len(prev_r['days'])} days)")
            else:
                # No prior data to fall back to — emit a bare error entry.
                new_results[key] = {
                    "key": key,
                    "name": (prev_r or {}).get("name") or key,
                    "url": (prev_r or {}).get("url", ""),
                    "error": err,
                    "days": [],
                }

    # Final order: follow SCRAPERS definition; merge previous results for the
    # restaurants we skipped (only relevant when `only` filter is set).
    results = []
    for key, _ in SCRAPERS:
        if key in new_results:
            results.append(new_results[key])
        elif key in existing_by_key:
            results.append(existing_by_key[key])

    payload = {
        "generated_at": now_iso(),
        "iso_week": iso_week(),
        "restaurants": results,
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    # Write to a temp file then rename — atomic on POSIX, near-atomic on Windows
    tmp = out_path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(out_path)
    print(f"[scrape] wrote {out_path}")

    # Non-zero exit if everything failed, so CI surfaces it. Partial failures are OK.
    if any_failed and not any(r.get("days") for r in results):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
