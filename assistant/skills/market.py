"""
Market, News & Live Info Skill.
Fetches crypto prices, stock market, and top news — all free APIs.
"""

import logging
from typing import Dict

import requests

from assistant.skills.resilience import resilient_skill

logger = logging.getLogger(__name__)


@resilient_skill(retries=2, delay=1.5, circuit_breaker_threshold=3)
def get_crypto_price(coin: str = "bitcoin") -> Dict[str, str]:
    """
    Get cryptocurrency price from CoinGecko (free, no key).

    Args:
        coin: Coin name (bitcoin, ethereum, dogecoin, etc.)
    """
    try:
        coin = coin.lower().strip()
        # Common aliases
        aliases = {
            "btc": "bitcoin", "eth": "ethereum", "doge": "dogecoin",
            "sol": "solana", "xrp": "ripple", "bnb": "binancecoin",
            "ada": "cardano", "dot": "polkadot", "matic": "matic-network",
        }
        coin = aliases.get(coin, coin)

        url = f"https://api.coingecko.com/api/v3/simple/price?ids={coin}&vs_currencies=inr,usd&include_24hr_change=true"
        resp = requests.get(url, timeout=8)
        data = resp.json()

        if coin in data:
            info = data[coin]
            inr = info.get("inr", 0)
            usd = info.get("usd", 0)
            change = info.get("inr_24h_change", 0)
            direction = "📈" if change > 0 else "📉"

            msg = f"{coin.title()} ka price abhi {inr:,.0f} rupees hai, dollar mein {usd:,.2f} hai. 24 ghante mein {change:+.2f} percent change hua hai."
            return {"status": "success", "message": msg}
        else:
            return {"status": "error", "message": f"'{coin}' nahi mila."}

    except Exception as e:
        return {"status": "error", "message": str(e)}


@resilient_skill(retries=2, delay=1.5, circuit_breaker_threshold=3)
def get_stock_market() -> Dict[str, str]:
    """Get Indian stock market overview (Sensex, Nifty) from free API."""
    try:
        # Use Google Finance scraping for Sensex/Nifty
        headers = {"User-Agent": "Mozilla/5.0"}

        # Nifty 50
        url = "https://query1.finance.yahoo.com/v8/finance/chart/%5ENSEI?interval=1d&range=1d"
        resp = requests.get(url, headers=headers, timeout=8)
        nifty_data = resp.json()

        meta1 = nifty_data["chart"]["result"][0]["meta"]
        nifty_price = meta1.get("regularMarketPrice") or meta1.get("chartPreviousClose", 0)
        nifty_prev = meta1.get("chartPreviousClose") or meta1.get("previousClose") or nifty_price
        nifty_change = ((nifty_price - nifty_prev) / nifty_prev) * 100 if nifty_prev else 0

        # Sensex
        url2 = "https://query1.finance.yahoo.com/v8/finance/chart/%5EBSESN?interval=1d&range=1d"
        resp2 = requests.get(url2, headers=headers, timeout=8)
        sensex_data = resp2.json()

        meta2 = sensex_data["chart"]["result"][0]["meta"]
        sensex_price = meta2.get("regularMarketPrice") or meta2.get("chartPreviousClose", 0)
        sensex_prev = meta2.get("chartPreviousClose") or meta2.get("previousClose") or sensex_price
        sensex_change = ((sensex_price - sensex_prev) / sensex_prev) * 100 if sensex_prev else 0

        n_dir = "📈" if nifty_change > 0 else "📉"
        s_dir = "📈" if sensex_change > 0 else "📉"

        msg = (
            f"Nifty 50 abhi {nifty_price:,.0f} pe hai, {nifty_change:+.2f} percent change. "
            f"Sensex {sensex_price:,.0f} pe hai, {sensex_change:+.2f} percent change."
        )
        return {"status": "success", "message": msg}

    except Exception as e:
        logger.error(f"Stock market error: {e}")
        return {"status": "error", "message": f"Market data nahi mil paya: {str(e)}"}


@resilient_skill(retries=2, delay=1.0, circuit_breaker_threshold=5)
def get_news(topic: str = "india", language: str = "") -> Dict[str, str]:
    """
    Get top news headlines using free RSS/API.
    Returns TTS-friendly natural speech (no numbered lists).

    Args:
        topic: News topic (india, technology, sports, business, etc.)
        language: "hi" for Hindi output, "en" for English, empty = auto-detect
    """
    import re as _re

    def _strip_source(title: str) -> str:
        """Remove ' - Source Name' or ' - www.source.com' suffix from headlines."""
        return _re.sub(r'\s*[-–—]\s*(?:[A-Z][\w\s&.\']+|www\.\S+)$', '', title).strip()

    def _clean_title(title: str) -> str:
        t = title.replace("&amp;", "&").replace("&quot;", '"').replace("&#39;", "'")
        t = _strip_source(t)
        t = _re.sub(r'\s+', ' ', t).strip()
        return t

    try:
        headlines = []

        # Try Google News RSS first (always works, no API key)
        hl_lang = "hi" if language == "hi" else "en-IN"
        rss_url = f"https://news.google.com/rss/search?q={topic}+india&hl={hl_lang}&gl=IN"
        resp = requests.get(rss_url, timeout=8)
        if resp.status_code == 200:
            titles = _re.findall(r"<title>(.*?)</title>", resp.text)
            headlines = [_clean_title(t) for t in titles[2:5] if t.strip()]

        if not headlines:
            # Fallback: newsdata.io
            news_lang = "hi" if language == "hi" else "en"
            url = f"https://newsdata.io/api/1/latest?country=in&language={news_lang}&q={topic}&apikey=pub_0"
            resp = requests.get(url, timeout=8)
            if resp.status_code == 200:
                data = resp.json()
                if "results" in data and data["results"]:
                    headlines = [_clean_title(a.get("title", "")) for a in data["results"][:3]]

        if not headlines:
            return {"status": "error", "message": "News nahi mil payi." if language == "hi" else "Could not fetch news."}

        # Build TTS-friendly spoken output (no numbers, natural connectors)
        if language == "hi":
            connectors = ["Pehli khabar", "Doosri khabar", "Teesri khabar"]
            msg = "Aaj ki top khabaren. "
            for i, h in enumerate(headlines):
                msg += f"{connectors[i]}, {h}. "
        else:
            connectors = ["First", "Second", "Third"]
            msg = "Here are today's top headlines. "
            for i, h in enumerate(headlines):
                msg += f"{connectors[i]}, {h}. "

        return {"status": "success", "message": msg.strip()}

    except Exception as e:
        logger.error(f"News error: {e}")
        return {"status": "error", "message": str(e)}


@resilient_skill(retries=2, delay=1.5, circuit_breaker_threshold=3)
def get_gold_price() -> Dict[str, str]:
    """Get current gold price in India."""
    try:
        # Use metals API or scrape
        url = "https://api.metals.dev/v1/latest?api_key=demo&currency=INR&unit=gram"
        resp = requests.get(url, timeout=8)

        if resp.status_code == 200:
            data = resp.json()
            gold = data.get("metals", {}).get("gold", 0)
            silver = data.get("metals", {}).get("silver", 0)
            msg = f"🥇 Gold: ₹{gold:,.0f}/gram\n🥈 Silver: ₹{silver:,.0f}/gram"
            return {"status": "success", "message": msg}

        return {"status": "error", "message": "Gold price nahi mil paya."}
    except Exception as e:
        return {"status": "error", "message": str(e)}
