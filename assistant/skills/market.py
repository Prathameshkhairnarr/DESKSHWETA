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

        nifty_price = nifty_data["chart"]["result"][0]["meta"]["regularMarketPrice"]
        nifty_prev = nifty_data["chart"]["result"][0]["meta"]["previousClose"]
        nifty_change = ((nifty_price - nifty_prev) / nifty_prev) * 100

        # Sensex
        url2 = "https://query1.finance.yahoo.com/v8/finance/chart/%5EBSESN?interval=1d&range=1d"
        resp2 = requests.get(url2, headers=headers, timeout=8)
        sensex_data = resp2.json()

        sensex_price = sensex_data["chart"]["result"][0]["meta"]["regularMarketPrice"]
        sensex_prev = sensex_data["chart"]["result"][0]["meta"]["previousClose"]
        sensex_change = ((sensex_price - sensex_prev) / sensex_prev) * 100

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
def get_news(topic: str = "india") -> Dict[str, str]:
    """
    Get top news headlines using free RSS/API.

    Args:
        topic: News topic (india, technology, sports, business, etc.)
    """
    try:
        # Use Google News RSS feed (free, no key)
        topic_map = {
            "india": "CAAqIQgKIhtDQkFTRGdvSUwyMHZNRE55YXpBU0FtVnVLQUFQAQ",
            "technology": "CAAqJggKIiBDQkFTRWdvSUwyMHZNRGRqTVhZU0FtVnVHZ0pKVGlnQVAB",
            "sports": "CAAqJggKIiBDQkFTRWdvSUwyMHZNRFp1ZEdvU0FtVnVHZ0pKVGlnQVAB",
            "business": "CAAqJggKIiBDQkFTRWdvSUwyMHZNRGx6TVdZU0FtVnVHZ0pKVGlnQVAB",
            "entertainment": "CAAqJggKIiBDQkFTRWdvSUwyMHZNREpxYW5RU0FtVnVHZ0pKVGlnQVAB",
        }

        # Simple approach: use newsdata.io free tier or scrape
        # Using a simple free news API
        url = f"https://newsdata.io/api/1/latest?country=in&language=en,hi&q={topic}&apikey=pub_0"
        resp = requests.get(url, timeout=8)

        # If that fails, use alternative
        if resp.status_code != 200:
            # Fallback: use Google News RSS
            rss_url = f"https://news.google.com/rss/search?q={topic}+india&hl=en-IN&gl=IN"
            resp = requests.get(rss_url, timeout=8)
            # Parse RSS XML simply
            import re
            titles = re.findall(r"<title>(.*?)</title>", resp.text)
            headlines = titles[2:7]  # Skip first 2 (feed title)
            if headlines:
                msg = f"Top {topic} news:\n"
                for i, h in enumerate(headlines, 1):
                    # Clean HTML entities
                    h = h.replace("&amp;", "&").replace("&quot;", '"')
                    msg += f"  {i}. {h}\n"
                return {"status": "success", "message": msg}

        # Parse newsdata response
        data = resp.json()
        if "results" in data and data["results"]:
            headlines = data["results"][:5]
            msg = f"Top {topic} news:\n"
            for i, article in enumerate(headlines, 1):
                title = article.get("title", "")
                msg += f"  {i}. {title}\n"
            return {"status": "success", "message": msg}

        return {"status": "error", "message": "News nahi mil payi."}

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
