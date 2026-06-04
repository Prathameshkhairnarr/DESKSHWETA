"""
Custom Browser Agent — Playwright + Gemini for autonomous browsing.
No paid API needed. Uses Playwright for browser control + Gemini for decisions.
"""

import asyncio
import json
import logging
import os
import threading
import time
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from config import GEMINI_API_KEY, PROJECT_ROOT

logger = logging.getLogger(__name__)

TASK_LOG = PROJECT_ROOT / "logs" / "browser_tasks.log"


class BrowserAgent:
    """Autonomous browser agent using Playwright + Gemini."""

    def __init__(self) -> None:
        self.is_running: bool = False
        self.task_history: List[Dict] = []

    def execute(self, goal: str) -> Dict[str, Any]:
        """Execute a browser task."""
        if self.is_running:
            return {"status": "error", "message": "Ek task pehle se chal raha hai."}

        self.is_running = True
        start_time = time.time()

        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(self._run(goal))
            loop.close()
        except Exception as e:
            result = {"success": False, "result": "", "error": str(e)}
        finally:
            self.is_running = False

        # Log
        elapsed = time.time() - start_time
        entry = {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "goal": goal,
            "success": result.get("success", False),
            "result": result.get("result", "")[:200],
            "time": f"{elapsed:.1f}s"
        }
        self.task_history.append(entry)
        self._log(entry)

        # Return in standard format
        msg = result.get("result", "") or result.get("error", "Task complete.")
        return {"status": "success", "message": msg}

    async def _run(self, goal: str) -> Dict[str, Any]:
        """Run browser task with Playwright."""
        from playwright.async_api import async_playwright

        browser = None
        try:
            pw = await async_playwright().start()
            browser = await pw.chromium.launch(headless=False)
            page = await browser.new_page()

            # Use Gemini to plan steps
            steps = self._plan_steps(goal)
            logger.info(f"Browser Agent: {len(steps)} steps planned for: {goal}")

            results = []
            for i, step in enumerate(steps):
                logger.info(f"Step {i+1}: {step['action']}")
                try:
                    result = await self._execute_step(page, step)
                    if result:
                        results.append(result)
                except Exception as e:
                    logger.warning(f"Step {i+1} failed: {e}")

            # Get page content for summary
            try:
                await asyncio.sleep(3)  # Wait for page to fully load
                url = page.url.lower()
                content = ""
                
                # Try structured extraction for known sites
                if "amazon" in url:
                    try:
                        await page.wait_for_selector('[data-component-type="s-search-result"]', timeout=5000)
                        items = await page.query_selector_all('[data-component-type="s-search-result"]')
                        product_lines = []
                        for item in items[:10]:
                            try:
                                title_el = await item.query_selector('h2 a span, h2 span')
                                price_whole = await item.query_selector('.a-price-whole')
                                rating_el = await item.query_selector('.a-icon-alt')
                                title = await title_el.inner_text() if title_el else ""
                                price = await price_whole.inner_text() if price_whole else "N/A"
                                rating = await rating_el.inner_text() if rating_el else ""
                                if title:
                                    line = f"{title.strip()} - ₹{price.strip()}"
                                    if rating:
                                        line += f" ({rating.strip()})"
                                    product_lines.append(line)
                            except Exception:
                                continue
                        if product_lines:
                            content = "PRODUCTS FOUND:\n" + "\n".join(product_lines)
                    except Exception:
                        pass
                
                if not content:
                    content = await page.inner_text("body")
                    # Skip navigation junk
                    if len(content) > 500:
                        content = content[300:]
                content = content[:4000]
            except Exception:
                content = ""

            await browser.close()
            await pw.stop()

            # Summarize results
            summary = self._summarize(goal, results, content)
            return {"success": True, "result": summary, "error": None}

        except Exception as e:
            if browser:
                try:
                    await browser.close()
                except Exception:
                    pass
            return {"success": False, "result": "", "error": str(e)}

    def _plan_steps(self, goal: str) -> List[Dict]:
        """Use AI (multi-provider) to plan browser steps from goal."""
        prompt = f"""You are a browser automation planner. Given a goal, output a JSON array of steps.
Each step has: {{"action": "goto|click|type|scroll|wait|extract", "selector": "css selector or url", "value": "text to type or extract description"}}

Goal: {goal}

Rules:
- "goto": selector = URL to navigate to
- "type": selector = input field CSS selector, value = text to type
- "click": selector = button/link CSS selector
- "extract": value = what info to extract from page
- Keep it to 5-8 steps max
- For search: goto site → type in search box → click search → wait → extract results

Output ONLY valid JSON array, nothing else."""

        # Try Groq first
        try:
            import requests as req
            groq_key = os.getenv("GROQ_API_KEY", "")
            if groq_key:
                resp = req.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={"Authorization": f"Bearer {groq_key}", "Content-Type": "application/json"},
                    json={"model": "llama-3.3-70b-versatile", "messages": [{"role": "user", "content": prompt}], "temperature": 0.2, "max_tokens": 500},
                    timeout=10
                )
                if resp.status_code == 200:
                    text = resp.json()["choices"][0]["message"]["content"].strip()
                    if text.startswith("```"): text = "\n".join(text.split("\n")[1:-1])
                    return json.loads(text)
        except Exception:
            pass

        # Try Gemini
        try:
            from google import genai
            from google.genai import types
            client = genai.Client(api_key=GEMINI_API_KEY)
            response = client.models.generate_content(
                model="gemini-2.0-flash-lite", contents=prompt,
                config=types.GenerateContentConfig(temperature=0.2, max_output_tokens=500)
            )
            text = response.text.strip()
            if text.startswith("```"): text = "\n".join(text.split("\n")[1:-1])
            return json.loads(text)
        except Exception:
            pass

        # Try GitHub Models
        try:
            import requests as req
            gh_token = os.getenv("GITHUB_TOKEN", "")
            if gh_token:
                resp = req.post(
                    "https://models.inference.ai.azure.com/chat/completions",
                    headers={"Authorization": f"Bearer {gh_token}", "Content-Type": "application/json"},
                    json={"model": "gpt-4o-mini", "messages": [{"role": "user", "content": prompt}], "temperature": 0.2, "max_tokens": 500},
                    timeout=15
                )
                if resp.status_code == 200:
                    text = resp.json()["choices"][0]["message"]["content"].strip()
                    if text.startswith("```"): text = "\n".join(text.split("\n")[1:-1])
                    return json.loads(text)
        except Exception:
            pass

        # All failed — use fallback
        return self._fallback_plan(goal)

    def _fallback_plan(self, goal: str) -> List[Dict]:
        """Simple fallback plan without AI."""
        goal_lower = goal.lower()

        if "amazon" in goal_lower:
            # Extract search query from goal
            query = goal_lower
            for remove in ["amazon", "search", "find", "best", "top", "list", "on", "india", "in", "under", "ke", "andar", "rupees", "rs", "budget"]:
                query = query.replace(remove, "")
            query = " ".join(query.split()).strip() or "headphones"
            return [
                {"action": "goto", "selector": "https://www.amazon.in", "value": ""},
                {"action": "wait", "selector": "", "value": "2"},
                {"action": "type", "selector": "#twotabsearchtextbox", "value": query},
                {"action": "click", "selector": "#nav-search-submit-button", "value": ""},
                {"action": "wait", "selector": "", "value": "3"},
                {"action": "extract", "selector": "", "value": "product names and prices"},
                {"action": "scroll", "selector": "", "value": ""},
                {"action": "extract", "selector": "", "value": "more product names and prices"},
            ]
        elif "google" in goal_lower:
            query = goal_lower.replace("google", "").replace("search", "").strip()
            return [
                {"action": "goto", "selector": "https://www.google.com", "value": ""},
                {"action": "type", "selector": "textarea[name=q]", "value": query},
                {"action": "click", "selector": "input[name=btnK]", "value": ""},
                {"action": "wait", "selector": "", "value": "2"},
                {"action": "extract", "selector": "", "value": "search results"},
            ]
        else:
            return [{"action": "goto", "selector": f"https://www.google.com/search?q={goal}", "value": ""}]

    async def _execute_step(self, page, step: Dict) -> Optional[str]:
        """Execute a single browser step."""
        action = step.get("action", "")
        selector = step.get("selector", "")
        value = step.get("value", "")

        if action == "goto":
            await page.goto(selector, wait_until="domcontentloaded", timeout=15000)
            await asyncio.sleep(2)

        elif action == "type":
            try:
                # Clear existing text first, then fill
                await page.click(selector, timeout=5000)
                await page.fill(selector, "", timeout=3000)  # Clear
                await page.fill(selector, value, timeout=5000)
            except Exception:
                # Try clicking first then typing character by character
                try:
                    await page.click(selector, timeout=5000)
                    await page.keyboard.type(value, delay=50)
                except Exception:
                    # Last resort: try Tab to find input and type
                    try:
                        await page.keyboard.press("Tab")
                        await page.keyboard.type(value, delay=50)
                    except Exception:
                        pass

        elif action == "click":
            try:
                await page.click(selector, timeout=5000)
                await asyncio.sleep(2)
            except Exception:
                # Try pressing Enter as fallback
                await page.keyboard.press("Enter")
                await asyncio.sleep(2)

        elif action == "scroll":
            await page.evaluate("window.scrollBy(0, 500)")
            await asyncio.sleep(1)

        elif action == "wait":
            seconds = int(value) if value.isdigit() else 2
            await asyncio.sleep(seconds)

        elif action == "extract":
            try:
                # Try specific selectors for common sites first
                url = page.url.lower()
                text = ""
                
                # Amazon product results
                if "amazon" in url:
                    try:
                        # Wait for search results to load
                        await page.wait_for_selector('[data-component-type="s-search-result"]', timeout=5000)
                        items = await page.query_selector_all('[data-component-type="s-search-result"]')
                        results = []
                        for item in items[:10]:  # Top 10 products
                            try:
                                title_el = await item.query_selector('h2 a span, h2 span')
                                price_whole = await item.query_selector('.a-price-whole')
                                title = await title_el.inner_text() if title_el else ""
                                price = await price_whole.inner_text() if price_whole else "N/A"
                                if title:
                                    results.append(f"{title.strip()} - ₹{price.strip()}")
                            except Exception:
                                continue
                        if results:
                            text = "\n".join(results)
                    except Exception:
                        pass
                
                # Flipkart product results
                if not text and "flipkart" in url:
                    try:
                        items = await page.query_selector_all('._1AtVbE, [data-id]')
                        results = []
                        for item in items[:10]:
                            try:
                                title_el = await item.query_selector('._4rR01T, .s1Q9rs, a[title]')
                                price_el = await item.query_selector('._30jeq3, ._1_WHN1')
                                title = await title_el.inner_text() if title_el else ""
                                price = await price_el.inner_text() if price_el else "N/A"
                                if title:
                                    results.append(f"{title.strip()} - {price.strip()}")
                            except Exception:
                                continue
                        if results:
                            text = "\n".join(results)
                    except Exception:
                        pass
                
                # Google search results
                if not text and "google" in url:
                    try:
                        items = await page.query_selector_all('#search .g, .tF2Cxc')
                        results = []
                        for item in items[:8]:
                            try:
                                title_el = await item.query_selector('h3')
                                snippet_el = await item.query_selector('.VwiC3b, .IsZvec')
                                title = await title_el.inner_text() if title_el else ""
                                snippet = await snippet_el.inner_text() if snippet_el else ""
                                if title:
                                    results.append(f"{title.strip()}: {snippet.strip()[:100]}")
                            except Exception:
                                continue
                        if results:
                            text = "\n".join(results)
                    except Exception:
                        pass
                
                # Fallback: get main content area, skip nav/header/footer
                if not text:
                    try:
                        # Try main content selectors
                        for selector in ['main', '#content', '#main-content', '[role="main"]', 'article', '.content']:
                            el = await page.query_selector(selector)
                            if el:
                                text = await el.inner_text()
                                if len(text) > 100:
                                    break
                    except Exception:
                        pass
                
                # Final fallback: full body but skip first 500 chars (usually nav)
                if not text:
                    text = await page.inner_text("body")
                    if len(text) > 500:
                        text = text[500:]  # Skip navigation
                
                return text[:2000]
            except Exception:
                return None

        return None

    def _summarize(self, goal: str, results: List, content: str) -> str:
        """Summarize browser results with shopping-aware AI prompt."""
        # Detect if this is a shopping query
        is_shopping = any(w in goal.lower() for w in [
            "best", "recommend", "under", "ke andar", "buy", "khareed",
            "headphone", "earphone", "phone", "laptop", "watch", "speaker",
            "keyboard", "mouse", "camera", "bag", "shoes", "tablet",
            "₹", "rupees", "rs", "budget", "price", "cheap", "sasta",
        ])

        if is_shopping:
            system_prompt = """Tu Shweta hai — ek helpful Indian AI assistant jo shopping mein friend ki tarah help karti hai.

RULES:
- Hinglish mein bol, bilkul casual jaise bestie ko bata rahi ho
- TOP 2-3 products recommend kar with exact prices
- Ek clear "Main ye recommend karungi" wala answer de
- 80-100 words mein bol — concise reh
- Agar price budget ke andar nahi hai toh clearly bol
- Technical specs mat gina — simple benefits bata (bass achha hai, mic clear hai, etc)
- Sound like: "Haan bhai! Main [product] recommend karungi — [price] mein milta hai, [benefit]. Dusra option [product2] hai..."
"""
            user_prompt = f"""User ne poocha: "{goal}"

Search results (products found):
{content[:3000]}

Ab in results ke basis pe user ko best 2-3 recommendations de. Prices mention kar. Casual Hinglish mein bol."""
        else:
            system_prompt = """Tu Shweta hai — helpful AI assistant. Search results ko padhke user ko clear, concise answer de Hinglish mein. 80-100 words max."""
            user_prompt = f"""User ne poocha: "{goal}"

Search results:
{content[:2500]}

Ab in results ke basis pe user ko clear answer de."""

        # Try Groq (best for this — fast + good Hindi)
        try:
            import requests as req
            groq_key = os.getenv("GROQ_API_KEY", "")
            if groq_key:
                resp = req.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={"Authorization": f"Bearer {groq_key}", "Content-Type": "application/json"},
                    json={
                        "model": "llama-3.3-70b-versatile",
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt}
                        ],
                        "temperature": 0.4,
                        "max_tokens": 250
                    },
                    timeout=10
                )
                if resp.status_code == 200:
                    return resp.json()["choices"][0]["message"]["content"].strip()
        except Exception:
            pass

        # Try Gemini
        try:
            from google import genai
            from google.genai import types
            client = genai.Client(api_key=GEMINI_API_KEY)
            response = client.models.generate_content(
                model="gemini-2.0-flash-lite",
                contents=f"{system_prompt}\n\n{user_prompt}",
                config=types.GenerateContentConfig(temperature=0.4, max_output_tokens=250)
            )
            return response.text.strip()
        except Exception:
            pass

        # Try GitHub Models
        try:
            import requests as req
            gh_token = os.getenv("GITHUB_TOKEN", "")
            if gh_token:
                resp = req.post(
                    "https://models.inference.ai.azure.com/chat/completions",
                    headers={"Authorization": f"Bearer {gh_token}", "Content-Type": "application/json"},
                    json={
                        "model": "gpt-4o-mini",
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt}
                        ],
                        "temperature": 0.4,
                        "max_tokens": 250
                    },
                    timeout=15
                )
                if resp.status_code == 200:
                    return resp.json()["choices"][0]["message"]["content"].strip()
        except Exception:
            pass

        # All AI failed — return raw product list directly
        if content and "PRODUCTS FOUND:" in content:
            lines = content.replace("PRODUCTS FOUND:\n", "").split("\n")[:3]
            return "Maine ye options dekhe: " + ", ".join(lines) + ". Amazon pe check kar."
        elif content:
            lines = [l.strip() for l in content.split("\n") if len(l.strip()) > 15]
            return " | ".join(lines[:4])[:200] or "Results screen pe dikh rahe hain."
        return "Search ho gaya, results screen pe dekh le."
        return "Task complete, browser mein results dekh lo."

    def get_history(self) -> List[Dict]:
        return self.task_history[-10:]

    def _log(self, entry: Dict) -> None:
        try:
            TASK_LOG.parent.mkdir(exist_ok=True)
            with open(TASK_LOG, "a", encoding="utf-8") as f:
                f.write(f"[{entry['timestamp']}] {entry['goal']} | {entry['time']}\n")
                f.write(f"  Result: {entry['result'][:100]}\n{'='*40}\n")
        except Exception:
            pass
