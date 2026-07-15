# Meridian Wealth Management Console

A two-audience dashboard in one static page:

- **For advisors** — a daily market snapshot, top movers, a client-briefing news feed with
  suggested talking points per headline, and an upcoming economic calendar.
- **Portfolio Builder, for clients/family/friends** — build a portfolio from top-100 market-cap
  stocks, S&P 500 ETFs, growth stocks, water-resources funds, bonds, dividend funds, and
  international funds (or start from a risk-based or "Expert Recommended" model portfolio); use
  the **Auto-Build** tool to generate an age-and-risk-based portfolio the way a wealth manager
  would; then compare both portfolios against the S&P 500 — 5-year historical-shaped performance,
  a 10/20/30-year long-term outlook range, and a Return Factors section explaining what drives
  results and what could derail them.

The site is a single static page (`index.html`). Market snapshot, top movers, and news refresh
automatically once a day via a GitHub Actions workflow that fetches real data and commits it —
no server to run, no manual uploading.

## One-time setup (~10 minutes)

### 1. Create a GitHub repository
Create a new **public** repository on [github.com](https://github.com) (public is required for
free GitHub Pages on a personal account) and push these files to it:

```
git init
git add .
git commit -m "Initial commit"
git branch -M main
git remote add origin https://github.com/<your-username>/<repo-name>.git
git push -u origin main
```

### 2. Get a free Finnhub API key
Sign up at [finnhub.io/register](https://finnhub.io/register) (free tier). Copy your API key
from the dashboard.

### 3. Add the key as a repository secret
In your GitHub repo: **Settings → Secrets and variables → Actions → New repository secret**
- Name: `FINNHUB_API_KEY`
- Value: *(paste your key)*

### 4. Enable GitHub Pages
**Settings → Pages → Build and deployment → Source: "Deploy from a branch"**, branch `main`,
folder `/ (root)`. Save. GitHub will give you a URL like:

```
https://<your-username>.github.io/<repo-name>/
```

That's the link to share with family and friends.

### 5. Run the workflow once manually
**Actions tab → "Daily Market Data Update" → Run workflow**. This fetches real data for the
first time and commits `data/*.json`. After that it runs automatically on the schedule below.

## What updates automatically, and what doesn't

| Section | Source | Refresh |
|---|---|---|
| Market Snapshot (indices, oil/gold/silver via ETF proxy, BTC, EUR/USD, 10-Yr yield) | Finnhub (free tier) + FRED (no key needed) | Daily, weekdays ~21:30 UTC |
| Today's Top 5 Movers | Computed from real quotes across ~55 tracked stocks (biggest % movers, not analyst picks) | Daily |
| Daily Macro Briefing | Public RSS feeds (Yahoo Finance, CNBC), tagged by keyword matching | Daily |
| Portfolio Builder return/volatility assumptions | Static reference estimates | **Not automated** — free APIs don't provide reliable 5-year historical backtesting; these are periodically-reviewed approximations, clearly labeled in the UI |

If any single day's fetch fails (rate limit, API hiccup, market holiday), the site just keeps
showing the last successfully-fetched data — it never gets wiped by a failed run.

## Known limitations of the free tier

- Finnhub's free plan is delayed (not real-time) and rate-limited; the fetch script paces
  requests (~1 call/sec) to stay within limits, so the workflow takes 1–2 minutes to run.
- Some index symbols (`^GSPC`, `^DJI`, etc.) may not be available on the free plan — the script
  automatically falls back to the equivalent ETF (SPY, DIA, QQQ, IWM, VIXY) and labels it as such.
- Oil/Gold/Silver are shown via ETF proxies (USO/GLD/SLV), not raw futures spot prices.
- The cron schedule is in UTC and will drift by about an hour around US daylight-saving changes.

## Local testing

Open a terminal in this folder and run:

```
python -m http.server 8000
```

Then visit `http://localhost:8000/index.html`. To test with real data locally, set
`FINNHUB_API_KEY` as an environment variable and run `python scripts/fetch_data.py` first —
it will populate `data/*.json` for the page to load.

## Upgrading later

- **Real analyst picks**: would require a paid research data provider (e.g., TipRanks, Zacks,
  Benzinga) — the free tier only supports the "computed top movers" approach used today.
- **Live daily-recomputed 5-year backtests**: would require a paid historical price-history API
  (Finnhub's candle/history endpoints are not available on the free tier).
- **Custom domain**: add a `CNAME` file and configure DNS, or use Netlify/Vercel instead of
  GitHub Pages if you'd prefer.
