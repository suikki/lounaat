# lounaat

Aggregates weekly lunch menus from a handful of Tampere restaurants onto a single static page.

No backend. A GitHub Actions cron job runs `scrape.py` on a schedule, commits the resulting `docs/data/menus.json`, and GitHub Pages serves the static site that reads it.

## Restaurants

- Linkosuo Hertta (Hervanta)
- Linkosuo Orvokki
- Antell Hermianfarmi
- Caffitella Duo Tampere
- Speakeasy Hervanta

## Local development

```bash
python -m venv .venv
.venv\Scripts\activate         # Windows
# source .venv/bin/activate    # macOS/Linux
pip install requests beautifulsoup4 lxml

python scrape.py               # writes docs/data/menus.json
python -m http.server -d docs 8000
# open http://localhost:8000
```

To scrape only one restaurant while iterating:

```bash
python scrape.py antell
```

## Deployment (GitHub Pages + Actions)

1. Push the repo to GitHub (public).
2. Settings → Pages → Source: **Deploy from a branch**, Branch: `main`, Folder: `/docs`.
3. Settings → Actions → General → Workflow permissions: **Read and write permissions** (so the cron can commit `menus.json` back).
4. The workflow at `.github/workflows/scrape.yml` runs weekdays at 05:30 UTC (~07:30–08:30 Helsinki) and can also be triggered manually from the Actions tab.

## Adding a restaurant

Drop a new module in `scrapers/` exposing a `scrape() -> Restaurant` function and add it to the `SCRAPERS` list in `scrape.py`. See an existing scraper for the shape.
