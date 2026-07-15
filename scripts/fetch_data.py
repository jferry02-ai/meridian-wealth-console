#!/usr/bin/env python3
"""
Daily data fetcher for the Meridian Portfolio Studio dashboard.

Pulls:
  - Market snapshot (indices via ETF proxies where needed, commodities via ETF
    proxies, BTC, EUR/USD, 10-Yr Treasury yield) -> data/market-data.json
  - Top 5 movers across the tracked stock universe -> data/movers.json
  - Recent finance headlines from public RSS feeds -> data/news.json

Uses only the Python standard library (no pip install step required in CI).
Requires the FINNHUB_API_KEY environment variable (free tier at finnhub.io).
"""
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import xml.etree.ElementTree as ET

FINNHUB_KEY = os.environ.get("FINNHUB_API_KEY", "").strip()
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
REQUEST_TIMEOUT = 10
FINNHUB_PACE_SECONDS = 1.1  # stay comfortably under the free-tier 60/min limit

now_iso = datetime.now(timezone.utc).isoformat(timespec="seconds")


def http_get(url, headers=None):
    req = urllib.request.Request(url, headers=headers or {"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
        return resp.read()


def http_get_json(url, headers=None, retries=2):
    for attempt in range(retries + 1):
        try:
            return json.loads(http_get(url, headers).decode("utf-8"))
        except Exception as e:  # noqa: BLE001
            if attempt == retries:
                print(f"WARN: failed to fetch {url}: {e}", file=sys.stderr)
                return None
            time.sleep(1.5)


def finnhub_quote(symbol):
    if not FINNHUB_KEY:
        return None
    url = (
        "https://finnhub.io/api/v1/quote?symbol="
        + urllib.parse.quote(symbol)
        + "&token="
        + FINNHUB_KEY
    )
    data = http_get_json(url)
    time.sleep(FINNHUB_PACE_SECONDS)
    if not data:
        return None
    o, c, pc = data.get("o"), data.get("c"), data.get("pc")
    if not o and not c:
        return None
    return {"open": o, "close": c, "prevClose": pc}


# ---------------------------------------------------------------------------
# Market snapshot
# ---------------------------------------------------------------------------
INDEX_PROXIES = [
    ("SPX", "^GSPC", "SPY", "S&P 500"),
    ("DJI", "^DJI", "DIA", "Dow Jones Industrial"),
    ("IXIC", "^IXIC", "QQQ", "Nasdaq Composite"),
    ("RUT", "^RUT", "IWM", "Russell 2000"),
    ("VIX", "^VIX", "VIXY", "CBOE Volatility Index"),
]
COMMODITY_ETF_PROXIES = [
    ("WTI", "USO", "Crude Oil (USO ETF proxy)"),
    ("XAU", "GLD", "Gold (GLD ETF proxy)"),
    ("XAG", "SLV", "Silver (SLV ETF proxy)"),
]
CRYPTO_SYMBOLS = [("BTC", "BINANCE:BTCUSDT", "Bitcoin (BTC/USD)")]
FOREX_SYMBOLS = [("EURUSD", "OANDA:EUR_USD", "Euro / US Dollar")]


def fetch_treasury_10y():
    """10-Yr Treasury yield from FRED's public CSV endpoint (no API key required)."""
    url = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DGS10"
    try:
        raw = http_get(url).decode("utf-8").splitlines()
    except Exception as e:  # noqa: BLE001
        print(f"WARN: FRED fetch failed: {e}", file=sys.stderr)
        return None
    rows = [r.split(",") for r in raw[1:] if r.strip()]
    values = [(d, v) for d, v in rows if v not in (".", "")]
    if len(values) < 2:
        return None
    latest, prior = values[-1][1], values[-2][1]
    try:
        latest_f, prior_f = float(latest), float(prior)
    except ValueError:
        return None
    return {"open": prior_f, "close": latest_f, "prevClose": prior_f}


def build_market_snapshot():
    items = []

    for symbol, try_sym, fallback_sym, name in INDEX_PROXIES:
        q = finnhub_quote(try_sym)
        display_name = name
        if not q:
            q = finnhub_quote(fallback_sym)
            display_name = f"{name} ({fallback_sym} ETF proxy)"
        if q:
            items.append({"symbol": symbol, "name": display_name, "fmt": "index" if symbol != "VIX" else "price", **q})

    for symbol, etf_sym, name in COMMODITY_ETF_PROXIES:
        q = finnhub_quote(etf_sym)
        if q:
            items.append({"symbol": symbol, "name": name, "fmt": "price", **q})

    yield10 = fetch_treasury_10y()
    if yield10:
        items.append({"symbol": "US10Y", "name": "10-Yr Treasury Yield", "fmt": "yield", **yield10})

    for symbol, fh_sym, name in CRYPTO_SYMBOLS:
        q = finnhub_quote(fh_sym)
        if q:
            items.append({"symbol": symbol, "name": name, "fmt": "price", **q})

    for symbol, fh_sym, name in FOREX_SYMBOLS:
        q = finnhub_quote(fh_sym)
        if q:
            items.append({"symbol": symbol, "name": name, "fmt": "fx", **q})

    return items


# ---------------------------------------------------------------------------
# Top movers (real stock universe, mirrors the ASSETS list in index.html)
# ---------------------------------------------------------------------------
STOCKS = [
    ("AAPL", "Apple Inc.", "Technology"), ("MSFT", "Microsoft Corp.", "Technology"),
    ("GOOGL", "Alphabet Inc.", "Communication Services"), ("AMZN", "Amazon.com Inc.", "Consumer Discretionary"),
    ("NVDA", "NVIDIA Corp.", "Semiconductors"), ("META", "Meta Platforms Inc.", "Communication Services"),
    ("AVGO", "Broadcom Inc.", "Semiconductors"), ("TSM", "Taiwan Semiconductor Mfg.", "Semiconductors"),
    ("LLY", "Eli Lilly and Co.", "Healthcare"), ("JPM", "JPMorgan Chase & Co.", "Financials"),
    ("JNJ", "Johnson & Johnson", "Healthcare"), ("KO", "Coca-Cola Co.", "Consumer Staples"),
    ("XOM", "Exxon Mobil Corp.", "Energy"), ("ORCL", "Oracle Corp.", "Technology"),
    ("CRM", "Salesforce Inc.", "Technology"), ("ADBE", "Adobe Inc.", "Technology"),
    ("AMD", "Advanced Micro Devices Inc.", "Semiconductors"), ("INTC", "Intel Corp.", "Semiconductors"),
    ("CSCO", "Cisco Systems Inc.", "Technology"), ("IBM", "International Business Machines", "Technology"),
    ("NOW", "ServiceNow Inc.", "Technology"), ("PLTR", "Palantir Technologies Inc.", "Technology"),
    ("CRWD", "CrowdStrike Holdings Inc.", "Technology"), ("NFLX", "Netflix Inc.", "Communication Services"),
    ("DIS", "Walt Disney Co.", "Communication Services"), ("TMUS", "T-Mobile US Inc.", "Communication Services"),
    ("TSLA", "Tesla Inc.", "Consumer Discretionary"), ("HD", "Home Depot Inc.", "Consumer Discretionary"),
    ("MCD", "McDonald's Corp.", "Consumer Discretionary"), ("NKE", "Nike Inc.", "Consumer Discretionary"),
    ("SBUX", "Starbucks Corp.", "Consumer Discretionary"), ("PG", "Procter & Gamble Co.", "Consumer Staples"),
    ("WMT", "Walmart Inc.", "Consumer Staples"), ("COST", "Costco Wholesale Corp.", "Consumer Staples"),
    ("PEP", "PepsiCo Inc.", "Consumer Staples"), ("BAC", "Bank of America Corp.", "Financials"),
    ("WFC", "Wells Fargo & Co.", "Financials"), ("GS", "Goldman Sachs Group Inc.", "Financials"),
    ("MS", "Morgan Stanley", "Financials"), ("V", "Visa Inc.", "Financials"),
    ("MA", "Mastercard Inc.", "Financials"), ("BRK.B", "Berkshire Hathaway Inc.", "Financials"),
    ("UNH", "UnitedHealth Group Inc.", "Healthcare"), ("PFE", "Pfizer Inc.", "Healthcare"),
    ("ABBV", "AbbVie Inc.", "Healthcare"), ("MRK", "Merck & Co.", "Healthcare"),
    ("TMO", "Thermo Fisher Scientific Inc.", "Healthcare"), ("CVX", "Chevron Corp.", "Energy"),
    ("COP", "ConocoPhillips", "Energy"), ("BA", "Boeing Co.", "Industrials"),
    ("CAT", "Caterpillar Inc.", "Industrials"), ("GE", "General Electric Co.", "Industrials"),
    ("HON", "Honeywell International Inc.", "Industrials"), ("NEE", "NextEra Energy Inc.", "Utilities"),
]


def build_movers():
    results = []
    for ticker, name, sector in STOCKS:
        finnhub_symbol = ticker.replace(".", "-")  # Finnhub uses BRK-B not BRK.B
        q = finnhub_quote(finnhub_symbol)
        if not q or not q.get("prevClose") or not q.get("close"):
            continue
        pct = (q["close"] - q["prevClose"]) / q["prevClose"] * 100
        results.append({
            "ticker": ticker, "name": name, "sector": sector,
            "price": q["close"], "changePct": round(pct, 2),
        })
    results.sort(key=lambda r: abs(r["changePct"]), reverse=True)
    return results[:5]


# ---------------------------------------------------------------------------
# News (public RSS feeds, no API key required)
# ---------------------------------------------------------------------------
RSS_FEEDS = [
    ("Yahoo Finance", "https://finance.yahoo.com/news/rssindex"),
    ("CNBC Markets", "https://www.cnbc.com/id/20910258/device/rss/rss.html"),
]

TAG_KEYWORDS = [
    ("Rates", ["fed ", "federal reserve", "fomc", "interest rate", "powell", "rate cut", "rate hike"]),
    ("Inflation", ["inflation", "cpi", "consumer price", "pce"]),
    ("Labor", ["jobs report", "payroll", "unemployment", "labor market"]),
    ("Geopolitics", ["tariff", "trade war", "geopolit", "sanction", "china", "conflict"]),
    ("Earnings", ["earnings", "quarterly results", "eps ", "guidance"]),
    ("Energy", ["oil", "opec", "crude", "energy prices", "gas prices"]),
]


def tag_for(title):
    lower = title.lower()
    for tag, keywords in TAG_KEYWORDS:
        if any(kw in lower for kw in keywords):
            return tag
    return "Markets"


def strip_html(text):
    return re.sub(r"<[^>]+>", "", text or "").strip()


def parse_rss(source, url):
    items = []
    try:
        raw = http_get(url)
        root = ET.fromstring(raw)
    except Exception as e:  # noqa: BLE001
        print(f"WARN: failed to fetch/parse RSS {url}: {e}", file=sys.stderr)
        return items

    for item in root.findall(".//item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        desc = strip_html(item.findtext("description") or "")
        pub = (item.findtext("pubDate") or "").strip()
        if not title:
            continue
        published_iso = None
        if pub:
            try:
                published_iso = parsedate_to_datetime(pub).astimezone(timezone.utc).isoformat(timespec="seconds")
            except Exception:  # noqa: BLE001
                published_iso = None
        items.append({
            "tag": tag_for(title),
            "icon": tag_for(title)[:3].upper(),
            "title": title,
            "body": desc[:220] + ("…" if len(desc) > 220 else ""),
            "source": source,
            "link": link,
            "published": published_iso,
        })
    return items


def build_news():
    all_items = []
    for source, url in RSS_FEEDS:
        all_items.extend(parse_rss(source, url))

    seen_titles = set()
    deduped = []
    for it in all_items:
        key = it["title"].lower().strip()
        if key in seen_titles:
            continue
        seen_titles.add(key)
        deduped.append(it)

    deduped.sort(key=lambda it: it["published"] or "", reverse=True)
    return deduped[:8]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def write_json(filename, items):
    os.makedirs(DATA_DIR, exist_ok=True)
    path = os.path.join(DATA_DIR, filename)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"updated": now_iso, "items": items}, f, indent=2)
    print(f"Wrote {len(items)} item(s) to {path}")


def main():
    if not FINNHUB_KEY:
        print("WARN: FINNHUB_API_KEY is not set — market snapshot and movers will be skipped.", file=sys.stderr)

    market_items = build_market_snapshot() if FINNHUB_KEY else []
    movers_items = build_movers() if FINNHUB_KEY else []
    news_items = build_news()

    if market_items:
        write_json("market-data.json", market_items)
    else:
        print("WARN: no market snapshot data fetched; leaving existing file untouched.", file=sys.stderr)

    if movers_items:
        write_json("movers.json", movers_items)
    else:
        print("WARN: no movers data fetched; leaving existing file untouched.", file=sys.stderr)

    if news_items:
        write_json("news.json", news_items)
    else:
        print("WARN: no news data fetched; leaving existing file untouched.", file=sys.stderr)

    if not market_items and not movers_items and not news_items:
        print("ERROR: all fetches failed — check FINNHUB_API_KEY and network access.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
