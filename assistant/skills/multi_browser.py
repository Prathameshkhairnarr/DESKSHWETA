"""
Multi-Tab Browser Orchestrator for Shweta AI Desktop Assistant.
Opens multiple tabs in user's Brave browser (with logged-in profile) simultaneously.

FAST approach:
1. Detect sites/tasks from command (regex-based, no AI call for common patterns)
2. Open all URLs in Brave using subprocess (instant, uses existing profile)
3. For complex interactions (search, play), use Playwright connecting to Brave

Example: "YouTube kholo, TradingView pe NVDA chart kholo, Prime Video pe The Boys play karo"
"""

import json
import logging
import os
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from config import GEMINI_API_KEY, GROQ_API_KEY, GITHUB_TOKEN, PROJECT_ROOT

logger = logging.getLogger(__name__)

# Brave browser paths
BRAVE_PATH = r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe"
BRAVE_PROFILE = os.path.join(os.environ.get("LOCALAPPDATA", ""), "BraveSoftware", "Brave-Browser", "User Data")


class MultiBrowserAgent:
    """Opens multiple browser tabs fast using Brave with user's logged-in profile."""

    def __init__(self) -> None:
        self.is_running: bool = False
        # Verify Brave exists
        if not Path(BRAVE_PATH).exists():
            logger.warning(f"Brave not found at {BRAVE_PATH}")

    def execute(self, goal: str) -> Dict[str, Any]:
        """Execute multi-tab browser task — FAST mode."""
        if self.is_running:
            return {"status": "error", "message": "Ek task pehle se chal raha hai."}

        self.is_running = True
        start_time = time.time()

        try:
            # Step 1: Parse the goal into tab tasks
            tabs = self._parse_goal(goal)

            if not tabs:
                # Fallback: ask AI to plan
                tabs = self._ai_plan(goal)

            if not tabs:
                return {"status": "error", "message": "Samajh nahi aaya kya open karna hai."}

            # Step 2: Open all simple URLs directly in Brave (FAST — no Playwright needed)
            simple_tabs = [t for t in tabs if not t.get("needs_interaction")]
            complex_tabs = [t for t in tabs if t.get("needs_interaction")]

            results = []

            # Open simple tabs instantly via subprocess
            if simple_tabs:
                urls = [t["url"] for t in simple_tabs if t.get("url")]
                if urls:
                    self._open_in_brave(urls)
                    for t in simple_tabs:
                        results.append(f"✅ {t.get('title', 'Tab')} — opened")

            # Handle complex tabs (need typing/clicking) via Playwright + Brave
            if complex_tabs:
                complex_results = self._handle_complex_tabs(complex_tabs)
                results.extend(complex_results)

            elapsed = time.time() - start_time
            logger.info(f"MultiBrowser done in {elapsed:.1f}s — {len(results)} tabs")

            summary = self._build_summary(results)
            return {"status": "success", "message": summary}

        except Exception as e:
            logger.error(f"MultiBrowser error: {e}")
            return {"status": "error", "message": f"Error: {str(e)}"}
        finally:
            self.is_running = False

    def _open_in_brave(self, urls: List[str]) -> None:
        """Open URLs in Brave browser using existing profile (instant, logged in)."""
        try:
            cmd = [BRAVE_PATH, f"--profile-directory=Default"]
            cmd.extend(urls)
            subprocess.Popen(cmd, shell=False)
            logger.info(f"Opened {len(urls)} tabs in Brave")
        except Exception as e:
            logger.error(f"Brave open failed: {e}")
            # Fallback: try opening with os.startfile
            for url in urls:
                try:
                    os.startfile(url)
                except Exception:
                    pass

    def _handle_complex_tabs(self, tabs: List[Dict]) -> List[str]:
        """Handle tabs that need interaction (search, click, play) via Playwright + Brave CDP."""
        import asyncio

        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            results = loop.run_until_complete(self._run_complex(tabs))
            loop.close()
            return results
        except Exception as e:
            logger.error(f"Complex tabs failed: {e}")
            # Fallback: just open the URLs
            urls = [t["url"] for t in tabs if t.get("url")]
            if urls:
                self._open_in_brave(urls)
            return [f"⚠️ {t.get('title', 'Tab')} — opened (interaction skipped)" for t in tabs]

    async def _run_complex(self, tabs: List[Dict]) -> List[str]:
        """Run complex tab interactions using Playwright with Brave."""
        from playwright.async_api import async_playwright

        results = []

        try:
            pw = await async_playwright().start()
            # Launch Brave with Playwright (uses user's profile = logged in)
            browser = await pw.chromium.launch(
                executable_path=BRAVE_PATH,
                headless=False,
                args=[
                    f"--user-data-dir={BRAVE_PROFILE}",
                    "--profile-directory=Default",
                    "--no-first-run",
                    "--disable-blink-features=AutomationControlled",
                ]
            )

            context = browser.contexts[0] if browser.contexts else await browser.new_context()

            for tab in tabs:
                try:
                    page = await context.new_page()
                    url = tab.get("url", "")
                    title = tab.get("title", "Tab")
                    actions = tab.get("actions", [])

                    if url:
                        await page.goto(url, wait_until="domcontentloaded", timeout=15000)
                        await asyncio.sleep(1.5)

                    # Execute actions
                    for action in actions:
                        await self._do_action(page, action)

                    results.append(f"✅ {title} — done")
                except Exception as e:
                    results.append(f"❌ {tab.get('title', 'Tab')} — {str(e)[:40]}")

            # Don't close browser — leave open for user
            # await browser.close()
            await pw.stop()

        except Exception as e:
            logger.error(f"Playwright+Brave failed: {e}")
            # Fallback: open URLs directly
            urls = [t["url"] for t in tabs if t.get("url")]
            if urls:
                self._open_in_brave(urls)
            results = [f"⚠️ {t.get('title', 'Tab')} — opened (basic)" for t in tabs]

        return results

    async def _do_action(self, page, action: Dict) -> None:
        """Execute a single action on a page."""
        action_type = action.get("type", "")
        selector = action.get("selector", "")
        value = action.get("value", "")

        if action_type == "wait":
            await asyncio.sleep(int(value) if value and value.isdigit() else 2)

        elif action_type == "type":
            try:
                await page.click(selector, timeout=5000)
                await page.fill(selector, value, timeout=5000)
            except Exception:
                try:
                    await page.keyboard.type(value, delay=30)
                except Exception:
                    pass

        elif action_type == "press":
            import asyncio as aio
            await page.keyboard.press(value or "Enter")
            await aio.sleep(1)

        elif action_type == "click":
            try:
                await page.click(selector, timeout=5000)
            except Exception:
                try:
                    await page.get_by_text(value or selector, exact=False).first.click(timeout=5000)
                except Exception:
                    pass
            await asyncio.sleep(1)

        elif action_type == "search":
            # Type + Enter combo
            try:
                await page.click(selector, timeout=5000)
                await page.fill(selector, value, timeout=5000)
            except Exception:
                await page.keyboard.type(value, delay=30)
            await page.keyboard.press("Enter")
            await asyncio.sleep(2)

    def _parse_goal(self, goal: str) -> List[Dict]:
        """Fast regex-based parsing — no AI needed for common patterns."""
        goal_lower = goal.lower()
        tabs = []

        # Split by common separators
        parts = self._split_tasks(goal_lower)

        for part in parts:
            tab = self._detect_tab(part)
            if tab:
                tabs.append(tab)

        # If no split worked, try the whole goal
        if not tabs:
            tab = self._detect_tab(goal_lower)
            if tab:
                tabs.append(tab)

        return tabs

    def _split_tasks(self, text: str) -> List[str]:
        """Split a multi-task command into individual tasks."""
        import re
        # Split on: "aur", "and", "fir", "then", "plus", "ek tab pe...ek pe..."
        # But be careful not to split within a task description
        separators = [
            r'\baur\s+ek\b', r'\baur\s+dusre\b', r'\baur\s+teesre\b',
            r'\bfir\s+ek\b', r'\bthen\b', r'\bplus\b',
            r'\baur\b(?=.*(?:khol|open|play|laga|chala|search|pe\s))',
            r'\,\s*(?=ek|youtube|trading|prime|netflix|amazon|google|spotify)',
            r'\,\s*',
        ]

        # Try each separator pattern
        for sep in separators:
            parts = re.split(sep, text)
            if len(parts) > 1:
                # Clean parts
                parts = [p.strip() for p in parts if p and p.strip()]
                if len(parts) > 1:
                    return parts

        # If nothing split, return as single task
        return [text]

    def _detect_tab(self, text: str) -> Optional[Dict]:
        """Detect what site/action a text chunk refers to."""

        # YouTube
        if "youtube" in text:
            query = self._extract_after(text, ["pe", "par", "mein", "search", "play", "bajao", "laga"])
            if query:
                return {
                    "title": f"YouTube — {query[:30]}",
                    "url": f"https://www.youtube.com/results?search_query={query.replace(' ', '+')}",
                    "needs_interaction": False,
                }
            return {"title": "YouTube", "url": "https://www.youtube.com", "needs_interaction": False}

        # TradingView
        if "tradingview" in text or "trading view" in text or ("chart" in text and any(s in text for s in ["nvda", "nvidia", "nifty", "reliance", "btc", "sensex", "aapl", "tsla", "banknifty"])):
            symbol = self._extract_symbol(text)
            url = f"https://www.tradingview.com/chart/?symbol={symbol}" if symbol else "https://www.tradingview.com/chart/"
            return {"title": f"TradingView — {symbol or 'Chart'}", "url": url, "needs_interaction": False}

        # Prime Video
        if "prime" in text or "primevideo" in text:
            query = self._extract_show(text)
            if query:
                url = f"https://www.primevideo.com/search?phrase={query.replace(' ', '+')}"
                return {"title": f"Prime Video — {query[:30]}", "url": url, "needs_interaction": False}
            return {"title": "Prime Video", "url": "https://www.primevideo.com", "needs_interaction": False}

        # Netflix
        if "netflix" in text:
            query = self._extract_show(text)
            if query:
                url = f"https://www.netflix.com/search?q={query.replace(' ', '+')}"
                return {"title": f"Netflix — {query[:30]}", "url": url, "needs_interaction": False}
            return {"title": "Netflix", "url": "https://www.netflix.com", "needs_interaction": False}

        # Amazon
        if "amazon" in text:
            query = self._extract_after(text, ["pe", "par", "search", "dhund", "khoj"])
            if query:
                url = f"https://www.amazon.in/s?k={query.replace(' ', '+')}"
                return {"title": f"Amazon — {query[:30]}", "url": url, "needs_interaction": False}
            return {"title": "Amazon", "url": "https://www.amazon.in", "needs_interaction": False}

        # Flipkart
        if "flipkart" in text:
            query = self._extract_after(text, ["pe", "par", "search", "dhund"])
            if query:
                url = f"https://www.flipkart.com/search?q={query.replace(' ', '+')}"
                return {"title": f"Flipkart — {query[:30]}", "url": url, "needs_interaction": False}
            return {"title": "Flipkart", "url": "https://www.flipkart.com", "needs_interaction": False}

        # Google
        if "google" in text:
            query = self._extract_after(text, ["pe", "par", "search", "khoj"])
            if query:
                url = f"https://www.google.com/search?q={query.replace(' ', '+')}"
                return {"title": f"Google — {query[:30]}", "url": url, "needs_interaction": False}
            return {"title": "Google", "url": "https://www.google.com", "needs_interaction": False}

        # Spotify (web)
        if "spotify" in text:
            return {"title": "Spotify", "url": "https://open.spotify.com", "needs_interaction": False}

        # GitHub
        if "github" in text:
            return {"title": "GitHub", "url": "https://github.com", "needs_interaction": False}

        # ChatGPT
        if "chatgpt" in text or "chat gpt" in text:
            return {"title": "ChatGPT", "url": "https://chat.openai.com", "needs_interaction": False}

        # Twitter/X
        if "twitter" in text or " x " in text or text.startswith("x "):
            return {"title": "X/Twitter", "url": "https://x.com", "needs_interaction": False}

        # Instagram
        if "instagram" in text or "insta" in text:
            return {"title": "Instagram", "url": "https://www.instagram.com", "needs_interaction": False}

        # LinkedIn
        if "linkedin" in text:
            return {"title": "LinkedIn", "url": "https://www.linkedin.com", "needs_interaction": False}

        # Reddit
        if "reddit" in text:
            return {"title": "Reddit", "url": "https://www.reddit.com", "needs_interaction": False}

        # WhatsApp Web
        if "whatsapp" in text:
            return {"title": "WhatsApp Web", "url": "https://web.whatsapp.com", "needs_interaction": False}

        # Generic URL detection
        if "http" in text or "www." in text or ".com" in text:
            import re
            url_match = re.search(r'(https?://\S+|www\.\S+|\S+\.com\S*)', text)
            if url_match:
                url = url_match.group(0)
                if not url.startswith("http"):
                    url = "https://" + url
                return {"title": url[:30], "url": url, "needs_interaction": False}

        return None

    def _extract_symbol(self, text: str) -> str:
        """Extract trading symbol from text."""
        symbols = {
            "nvda": "NVDA", "nvidia": "NVDA",
            "nifty": "NIFTY", "banknifty": "BANKNIFTY",
            "reliance": "RELIANCE", "tata": "TATAMOTORS",
            "btc": "BTCUSD", "bitcoin": "BTCUSD",
            "eth": "ETHUSD", "ethereum": "ETHUSD",
            "aapl": "AAPL", "apple": "AAPL",
            "tsla": "TSLA", "tesla": "TSLA",
            "googl": "GOOGL", "google stock": "GOOGL",
            "msft": "MSFT", "microsoft": "MSFT",
            "amzn": "AMZN", "sensex": "SENSEX",
            "infosys": "INFY", "wipro": "WIPRO",
            "hdfc": "HDFCBANK", "sbi": "SBIN",
            "adani": "ADANIENT", "icici": "ICICIBANK",
        }
        for key, val in symbols.items():
            if key in text:
                return val
        return ""

    def _extract_show(self, text: str) -> str:
        """Extract show/movie name from text."""
        import re
        # Try to find content after play/watch keywords
        for kw in ["play", "laga", "dekh", "chala", "dekhna", "chalao"]:
            if kw in text:
                after = text.split(kw, 1)[-1].strip()
                # Clean stop words at end
                for stop in ["karo", "do", "de", "kar", "na"]:
                    if after.endswith(f" {stop}"):
                        after = after[:-(len(stop)+1)].strip()
                if after:
                    return after

        # Try after "pe" or "par"
        for kw in ["pe ", "par ", "mein "]:
            if kw in text:
                parts = text.split(kw)
                if len(parts) > 1:
                    after = parts[-1].strip()
                    # Remove site names
                    for site in ["prime", "video", "netflix", "hotstar"]:
                        after = after.replace(site, "").strip()
                    if after and len(after) > 2:
                        return after
        return ""

    def _extract_after(self, text: str, keywords: List[str]) -> str:
        """Extract meaningful text after keywords."""
        for kw in keywords:
            if f" {kw} " in f" {text} ":
                parts = text.split(kw, 1)
                if len(parts) > 1:
                    after = parts[-1].strip()
                    # Remove common stop words
                    for stop in ["khol", "kholo", "open", "karo", "kar", "do", "de"]:
                        after = after.replace(f" {stop}", "").strip()
                        if after.endswith(stop):
                            after = after[:-(len(stop))].strip()
                    # Remove site names that might have leaked
                    for site in ["youtube", "tradingview", "prime", "netflix", "amazon"]:
                        after = after.replace(site, "").strip()
                    if after and len(after) > 1:
                        return after
        return ""

    def _ai_plan(self, goal: str) -> List[Dict]:
        """Fallback: use AI to plan tabs when regex parsing fails."""
        prompt = f"""Break this browser command into separate tab tasks. Output JSON array.

Command: {goal}

Each item: {{"title":"short name","url":"full URL","needs_interaction":false}}

Rules:
- Use direct URLs with search params when possible (faster)
- YouTube search: https://www.youtube.com/results?search_query=QUERY
- Amazon search: https://www.amazon.in/s?k=QUERY
- TradingView: https://www.tradingview.com/chart/?symbol=SYMBOL
- Prime Video: https://www.primevideo.com/search?phrase=QUERY
- Google: https://www.google.com/search?q=QUERY
- Set needs_interaction=false for all (we open URLs directly)
- Output ONLY valid JSON array, nothing else."""

        result = self._call_ai(prompt)
        if result:
            try:
                if result.startswith("```"):
                    result = "\n".join(result.split("\n")[1:-1])
                start = result.find("[")
                end = result.rfind("]")
                if start != -1 and end != -1:
                    tabs = json.loads(result[start:end + 1])
                    if isinstance(tabs, list):
                        return tabs
            except Exception:
                pass
        return []

    def _call_ai(self, prompt: str) -> Optional[str]:
        """Quick AI call for planning."""
        import requests

        # Try Groq (fastest)
        if GROQ_API_KEY:
            try:
                resp = requests.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
                    json={"model": "llama-3.3-70b-versatile", "messages": [{"role": "user", "content": prompt}], "temperature": 0.1, "max_tokens": 600},
                    timeout=8
                )
                if resp.status_code == 200:
                    return resp.json()["choices"][0]["message"]["content"].strip()
            except Exception:
                pass

        # Try Gemini
        if GEMINI_API_KEY:
            try:
                from google import genai
                from google.genai import types
                client = genai.Client(api_key=GEMINI_API_KEY)
                response = client.models.generate_content(
                    model="gemini-2.0-flash-lite", contents=prompt,
                    config=types.GenerateContentConfig(temperature=0.1, max_output_tokens=600)
                )
                return response.text.strip()
            except Exception:
                pass

        return None

    def _build_summary(self, results: List[str]) -> str:
        """Build short summary."""
        done = sum(1 for r in results if "✅" in r)
        total = len(results)
        lines = "\n".join(f"  {r}" for r in results)
        if done == total:
            return f"Done! {total} tabs khol diye Brave mein:\n{lines}"
        return f"{done}/{total} tabs ready:\n{lines}"
