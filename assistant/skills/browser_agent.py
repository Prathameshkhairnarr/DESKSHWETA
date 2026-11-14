"""
Custom Browser Agent â€” Playwright + Gemini for autonomous browsing.
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
        # Persistent browser session: lives on a dedicated background event loop
        # and stays OPEN between tasks, so the user's Brave logins and an
        # in-progress cart / results page survive for them to review and pay.
        self._loop = None
        self._thread = None
        self._pw = None
        self._context = None
        self._cdp_browser = None
        self._profile_active: bool = False

    def _ensure_loop(self) -> None:
        """Start a long-lived background asyncio loop (once) that owns the
        browser, so the browser isn't killed when a single task finishes."""
        if self._loop is not None and self._loop.is_running():
            return
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(
            target=self._loop.run_forever, daemon=True, name="BrowserAgentLoop"
        )
        self._thread.start()

    def execute(self, goal: str) -> Dict[str, Any]:
        """Execute a browser task."""
        if self.is_running:
            return {"status": "error", "message": "Ek task pehle se chal raha hai."}

        self.is_running = True
        start_time = time.time()

        try:
            # Run on the persistent background loop that owns the open browser,
            # instead of a throwaway loop (which would close the browser).
            self._ensure_loop()
            fut = asyncio.run_coroutine_threadsafe(self._run(goal), self._loop)
            result = fut.result(timeout=180)
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

    def _cdp_alive(self, port: int) -> bool:
        """True if a Chrome DevTools endpoint is already listening on the port."""
        import urllib.request
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=1) as r:
                return r.status == 200
        except Exception:
            return False

    async def _ensure_context(self):
        """Attach to 'Shweta's Brave' over CDP — a DEDICATED Brave instance we
        launch with remote-debugging on its own persistent profile. Because it's a
        separate profile from the user's daily Brave, there's NO profile-lock
        conflict (the old launch_persistent_context failed with exitCode 21 when
        Brave was already running). The user logs into Swiggy/Zomato/Amazon ONCE in
        this browser and those logins persist. The browser is launched detached so
        it stays open for the user to review the cart and pay. Falls back to a clean
        managed browser only if CDP can't be established."""
        from playwright.async_api import async_playwright
        from config import BROWSER_PATH

        # Reuse the already-connected session if it's still alive.
        if self._context is not None:
            try:
                _ = self._context.pages
                return self._context
            except Exception:
                self._context = None

        if self._pw is None:
            self._pw = await async_playwright().start()

        import subprocess
        import time as _time
        cdp_port = int(os.getenv("SHWETA_CDP_PORT", "9222"))
        profile_dir = os.getenv("SHWETA_BROWSER_PROFILE") or os.path.join(
            os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "ShwetaBrowser"
        )

        # Launch Shweta's dedicated Brave with remote debugging if it isn't up yet.
        if not self._cdp_alive(cdp_port):
            if BROWSER_PATH and os.path.exists(BROWSER_PATH):
                try:
                    os.makedirs(profile_dir, exist_ok=True)
                    subprocess.Popen(
                        [
                            BROWSER_PATH,
                            f"--remote-debugging-port={cdp_port}",
                            f"--user-data-dir={profile_dir}",
                            "--no-first-run",
                            "--no-default-browser-check",
                            "--start-maximized",
                        ],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                    logger.info(f"[BrowserAgent] Launched Shweta's Brave (CDP :{cdp_port}, profile {profile_dir}).")
                except Exception as e:
                    logger.warning(f"[BrowserAgent] Could not launch Brave for CDP: {e}")
                # Wait for the debugging endpoint to come up.
                for _ in range(24):
                    if self._cdp_alive(cdp_port):
                        break
                    _time.sleep(0.5)

        # Connect over CDP to the running Brave (user's dedicated, logged-in profile).
        if self._cdp_alive(cdp_port):
            try:
                self._cdp_browser = await self._pw.chromium.connect_over_cdp(f"http://127.0.0.1:{cdp_port}")
                self._context = (
                    self._cdp_browser.contexts[0]
                    if self._cdp_browser.contexts
                    else await self._cdp_browser.new_context(no_viewport=True)
                )
                self._profile_active = True
                logger.info("[BrowserAgent] Connected to Shweta's Brave over CDP — saved logins available.")
                return self._context
            except Exception as e:
                logger.warning(f"[BrowserAgent] CDP connect failed ({e}); using a clean browser instead.")

        # Fallback: clean managed browser (no saved logins)
        self._profile_active = False
        browser = await self._pw.chromium.launch(headless=False)
        self._context = await browser.new_context(no_viewport=True)
        return self._context

    async def _run(self, goal: str) -> Dict[str, Any]:
        """Run a browser task. The browser (user's profile) stays OPEN afterwards
        so the user can review the cart / results page and complete payment."""
        try:
            context = await self._ensure_context()
            page = await context.new_page()

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
                # If a click opened the product in a NEW tab, follow it so the next
                # step (e.g. Add to Cart) acts on the product page, not the old search.
                try:
                    if context.pages and context.pages[-1] is not page:
                        page = context.pages[-1]
                        await page.bring_to_front()
                        await asyncio.sleep(0.5)
                except Exception:
                    pass

            # Get page content for summary
            try:
                await asyncio.sleep(3)  # Wait for page to fully load
                url = page.url.lower()
                content = ""

                # CART pages → report what's in the cart, or detect empty (so we can
                # honestly tell the user if the auto-add worked or not).
                if ("/cart" in url or "/gp/cart" in url or "viewcart" in url):
                    try:
                        body_l = (await page.inner_text("body")).lower()
                        if ("cart is empty" in body_l or "your amazon cart is empty" in body_l
                                or "no items in your cart" in body_l or "your cart is empty" in body_l):
                            content = "CART EMPTY"
                        else:
                            cart_items = await page.query_selector_all(
                                '.sc-list-item, [data-name="Active Items"] .sc-list-item-content, .sc-list-item-content'
                            )
                            lines = []
                            for it in cart_items[:8]:
                                t_el = await it.query_selector('.sc-product-title, .a-truncate-cut, .sc-grid-item-product-title')
                                p_el = await it.query_selector('.sc-product-price, .a-price-whole, .sc-price')
                                t = (await t_el.inner_text()) if t_el else ""
                                p = (await p_el.inner_text()) if p_el else ""
                                if t.strip():
                                    lines.append(f"{t.strip()} - {p.strip()}".strip(" -"))
                            content = ("CART ITEMS:\n" + "\n".join(lines)) if lines else "CART EMPTY"
                    except Exception:
                        pass

                # Try structured extraction for known sites
                if not content and "amazon" in url:
                    try:
                        try:
                            await page.wait_for_selector(
                                'div.s-main-slot div[data-asin]:not([data-asin=""]), [data-component-type="s-search-result"]',
                                timeout=9000,
                            )
                        except Exception:
                            pass
                        items = await page.query_selector_all(
                            '[data-component-type="s-search-result"], div.s-main-slot div[data-asin]:not([data-asin=""])'
                        )
                        product_lines = []
                        for item in items[:10]:
                            try:
                                title_el = await item.query_selector('h2 a span, h2 span, .a-size-medium, .a-size-base-plus')
                                price_whole = await item.query_selector('.a-price .a-price-whole, .a-price-whole')
                                rating_el = await item.query_selector('.a-icon-alt')
                                title = await title_el.inner_text() if title_el else ""
                                price = await price_whole.inner_text() if price_whole else "N/A"
                                rating = await rating_el.inner_text() if rating_el else ""
                                if title:
                                    line = f"{title.strip()} - â‚¹{price.strip()}"
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

            # NOTE: browser is intentionally LEFT OPEN so the user can review the
            # cart / results page and finish payment themselves. The persistent
            # context lives on the background loop and is reused for the next task.

            # Summarize results
            summary = self._summarize(goal, results, content)
            return {"success": True, "result": summary, "error": None, "profile": self._profile_active}

        except Exception as e:
            return {"success": False, "result": "", "error": str(e)}

    def _plan_steps(self, goal: str) -> List[Dict]:
        """Use AI (multi-provider) to plan browser steps from goal."""
        # Known sites get a DETERMINISTIC, reliable template — don't gamble on the
        # LLM inventing selectors (it kept Google-searching the whole instruction or
        # missing Amazon's result grid). Direct search URLs + waits are far steadier.
        gl = goal.lower()
        if any(s in gl for s in ("amazon", "flipkart", "swiggy", "zomato", "flight", "google flights")):
            return self._fallback_plan(goal)

        prompt = f"""You are a browser automation planner. Given a goal, output a JSON array of steps.
Each step has: {{"action": "goto|click|type|scroll|wait|extract", "selector": "css selector or url", "value": "text to type or extract description"}}

Goal: {goal}

Rules:
- "goto": selector = URL to navigate to
- "type": selector = input field CSS selector, value = text to type
- "click": selector = button/link CSS selector
- "extract": value = what info to extract from page
- Keep it to 5-8 steps max
- For search: goto site â†’ type in search box â†’ click search â†’ wait â†’ extract results

Output ONLY valid JSON array, nothing else."""

        # Try Groq first
        try:
            import requests as req
            groq_key = os.getenv("GROQ_API_KEY", "")
            if groq_key:
                resp = req.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={"Authorization": f"Bearer {groq_key}", "Content-Type": "application/json"},
                    json={"model": os.getenv("GROQ_MODEL", "openai/gpt-oss-120b"), "messages": [{"role": "user", "content": prompt}], "temperature": 0.2, "max_tokens": 500},
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
                model="gemini-2.5-flash-lite", contents=prompt,
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

        # All failed â€” use fallback
        return self._fallback_plan(goal)

    def _fallback_plan(self, goal: str) -> List[Dict]:
        """Simple fallback plan without AI.

        IMPORTANT: never dump the whole verbose goal into a Google search — that
        triggered Google's bot reCAPTCHA (the flight-booking failure). Instead,
        pull the clean query out of the goal (our order/flight goals wrap it in
        single quotes) and go straight to the RIGHT site (Google Flights / Swiggy)."""
        import re as _re
        from urllib.parse import quote_plus
        goal_lower = goal.lower()
        # Our _book_flight/_order_food goals embed the real query in 'single quotes'.
        qm = _re.search(r"'([^']+)'", goal)
        quoted = qm.group(1).strip() if qm else ""
        # Whether the user actually wants the item ADDED to the cart (vs just shown).
        # We always STOP at the cart — never pay — so a wrong pick is easily removed.
        want_cart = any(w in goal_lower for w in (
            "cart", "add to cart", "order", "buy", "khareed", "daal", "mangwa", "mangao",
        ))

        # FLIGHTS → Google Flights deep link (not a raw search of the instruction)
        if "flight" in goal_lower:
            q = quoted or " ".join(goal.split()[:8])
            return [
                {"action": "goto", "selector": f"https://www.google.com/travel/flights?q={quote_plus('flights ' + q)}", "value": ""},
                {"action": "wait", "selector": "", "value": "4"},
                {"action": "extract", "selector": "", "value": "flight options with airline, time and price"},
            ]

        # FOOD → Swiggy / Zomato
        if any(w in goal_lower for w in ("swiggy", "zomato", "food order", "order food", "khana")):
            q = quoted or " ".join(goal.split()[:8])
            if "zomato" in goal_lower:
                url = f"https://www.zomato.com/search?q={quote_plus(q)}"
            else:
                url = f"https://www.swiggy.com/search?query={quote_plus(q)}"
            steps = [
                {"action": "goto", "selector": url, "value": ""},
                {"action": "wait", "selector": "", "value": "5"},
            ]
            if want_cart:
                # Best-effort add-to-cart: open the first result, then click the first
                # ADD button. Food sites are very dynamic, so each step may miss — the
                # browser is left open on whatever page it reached for the user to finish.
                steps += [
                    {"action": "click", "selector": "a[href*='/restaurants/'], a[href*='/city/'], a[href*='/restaurant/']", "value": ""},
                    {"action": "wait", "selector": "", "value": "4"},
                    {"action": "click", "selector": "button:has-text('ADD'), div:has-text('ADD') button, [aria-label*='Add']", "value": ""},
                    {"action": "wait", "selector": "", "value": "2"},
                    {"action": "extract", "selector": "", "value": "cart items and total price"},
                ]
            else:
                steps += [{"action": "extract", "selector": "", "value": "food items and prices"}]
            return steps

        if "amazon" in goal_lower or "flipkart" in goal_lower:
            # Clean the query (prefer the quoted part), then go STRAIGHT to the
            # search-results URL — typing into a search box was unreliable and often
            # left us on the homepage (only category nav got extracted).
            query = quoted
            if not query:
                query = goal_lower
                for remove in ["amazon", "flipkart", "search", "find", "best", "top", "list",
                               "on", "india", "in", "under", "ke", "andar", "rupees", "rs",
                               "budget", "buy", "khareed", "dhundh", "dhundho", "karo"]:
                    query = _re.sub(rf'\b{_re.escape(remove)}\b', '', query)
                query = " ".join(query.split()).strip() or "headphones"
            if "flipkart" in goal_lower:
                search_url = f"https://www.flipkart.com/search?q={quote_plus(query)}"
                product_sel = "a.CGtC98, a._1fQZEK, a.s1Q9rs, a._2rpwqI, a.wjcEIp"
                addbtn_sel = "button:has-text('Add to cart'), button:has-text('ADD TO CART'), li:has-text('ADD TO CART')"
                cart_url = "https://www.flipkart.com/viewcart"
            else:
                search_url = f"https://www.amazon.in/s?k={quote_plus(query)}"
                product_sel = 'div.s-main-slot div[data-asin]:not([data-asin=""]) h2 a'
                addbtn_sel = "#add-to-cart-button"
                cart_url = "https://www.amazon.in/gp/cart/view.html"

            if want_cart:
                # Open the first matching product, click Add to Cart, then show the cart.
                # We STOP at the cart — never Buy Now / pay — so the user reviews & pays.
                return [
                    {"action": "goto", "selector": search_url, "value": ""},
                    {"action": "wait", "selector": "", "value": "4"},
                    {"action": "click", "selector": product_sel, "value": ""},
                    {"action": "wait", "selector": "", "value": "3"},
                    {"action": "click", "selector": addbtn_sel, "value": ""},
                    {"action": "wait", "selector": "", "value": "2"},
                    {"action": "goto", "selector": cart_url, "value": ""},
                    {"action": "wait", "selector": "", "value": "3"},
                    {"action": "extract", "selector": "", "value": "cart items and total price"},
                ]
            return [
                {"action": "goto", "selector": search_url, "value": ""},
                {"action": "wait", "selector": "", "value": "4"},
                {"action": "extract", "selector": "", "value": "product names and prices"},
                {"action": "scroll", "selector": "", "value": ""},
                {"action": "wait", "selector": "", "value": "2"},
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
            # Never search the whole long instruction (that caused the reCAPTCHA).
            # Use the quoted query, else just the first few words, URL-encoded.
            q = quoted or " ".join(goal.split()[:8])
            return [{"action": "goto", "selector": f"https://www.google.com/search?q={quote_plus(q)}", "value": ""}]

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
            # Try the whole selector, then each comma-separated alternative, so a
            # best-effort list like "btnA, btnB, btnC" clicks the first that exists.
            clicked = False
            candidates = [selector] + [s.strip() for s in selector.split(",") if s.strip()]
            for sel in candidates:
                try:
                    await page.click(sel, timeout=4000)
                    clicked = True
                    await asyncio.sleep(2)
                    break
                except Exception:
                    continue
            if not clicked:
                try:
                    await page.keyboard.press("Enter")
                    await asyncio.sleep(1)
                except Exception:
                    pass

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
                        # Wait for the real result grid; try several selectors since
                        # Amazon's markup varies by page/layout.
                        try:
                            await page.wait_for_selector(
                                'div.s-main-slot div[data-asin]:not([data-asin=""]), [data-component-type="s-search-result"]',
                                timeout=9000,
                            )
                        except Exception:
                            pass
                        items = await page.query_selector_all(
                            '[data-component-type="s-search-result"], div.s-main-slot div[data-asin]:not([data-asin=""])'
                        )
                        results = []
                        for item in items[:10]:  # Top 10 products
                            try:
                                title_el = await item.query_selector('h2 a span, h2 span, .a-size-medium, .a-size-base-plus')
                                price_whole = await item.query_selector('.a-price .a-price-whole, .a-price-whole')
                                title = await title_el.inner_text() if title_el else ""
                                price = await price_whole.inner_text() if price_whole else "N/A"
                                if title:
                                    results.append(f"{title.strip()} - â‚¹{price.strip()}")
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

    def _raw_fallback(self, content: str, goal: str) -> str:
        """A factual, never-refusing message built from the extracted content —
        used when the LLM summary is empty or (wrongly) refuses."""
        if content and "PRODUCTS FOUND:" in content:
            lines = [l for l in content.replace("PRODUCTS FOUND:\n", "").split("\n") if l.strip()][:3]
            if lines:
                return "Ye options mile: " + "; ".join(lines) + ". Browser khula hai — pasand aaye to cart mein daal ke pay kar lena."
        if content and len(content.strip()) >= 40:
            lines = [l.strip() for l in content.split("\n") if len(l.strip()) > 15][:4]
            if lines:
                return ("Browser khula hai — " + " | ".join(lines))[:220]
        return "Browser khol diya hai — results screen pe dekh le, pasand aaye to cart mein daal ke pay kar lena."

    def _clean_summary(self, text: str, content: str, goal: str) -> str:
        """Never let Shweta speak an LLM refusal. If the model says it 'can't' do it
        (it's only summarizing already-fetched results), use a factual fallback."""
        t = (text or "").strip()
        low = t.lower()
        refusal_markers = (
            "i'm sorry", "i am sorry", "i can't", "i cannot", "can't help",
            "cannot help", "can't perform", "cannot perform", "unable to",
            "i'm an ai", "i am an ai", "as an ai", "don't have access", "no access",
            "nahi kar sakta", "nahi kar sakti", "nahi kar paungi", "nahi kar paungi",
            "access nahi", "maaf kij",
        )
        if not t or any(m in low for m in refusal_markers):
            return self._raw_fallback(content, goal)
        return t

    def _summarize(self, goal: str, results: List, content: str) -> str:
        """Summarize browser results with shopping-aware AI prompt."""
        # Cart-status markers get a direct, honest message (no LLM needed).
        c = content or ""
        if "CART ITEMS:" in c:
            items = [l.strip() for l in c.split("CART ITEMS:", 1)[1].split("\n") if l.strip()][:4]
            if items:
                return "Cart mein daal diya: " + "; ".join(items) + ". Browser khula hai — review karke aap pay kar lena."
        if "CART EMPTY" in c:
            return "Cart abhi khaali dikh raha — item apne aap add nahi ho paya. Browser khula hai, aap khud daal ke pay kar lena."

        # Thin/empty content → don't even ask the LLM (that's when it hallucinates
        # a refusal). Just tell the user the browser is open to review.
        if not content or len(content.strip()) < 40:
            return "Browser khol diya hai — results screen pe dekh le aur pasand aaye to cart mein daal ke pay kar lena."

        # Detect if this is a shopping query
        is_shopping = any(w in goal.lower() for w in [
            "best", "recommend", "under", "ke andar", "buy", "khareed",
            "headphone", "earphone", "phone", "laptop", "watch", "speaker",
            "keyboard", "mouse", "camera", "bag", "shoes", "tablet",
            "â‚¹", "rupees", "rs", "budget", "price", "cheap", "sasta",
        ])

        if is_shopping:
            system_prompt = """Tu Shweta hai â€” ek helpful Indian AI assistant jo shopping mein friend ki tarah help karti hai.

RULES:
- Hinglish mein bol, bilkul casual jaise bestie ko bata rahi ho
- TOP 2-3 products recommend kar with exact prices
- Ek clear "Main ye recommend karungi" wala answer de
- 80-100 words mein bol â€” concise reh
- Agar price budget ke andar nahi hai toh clearly bol
- Technical specs mat gina â€” simple benefits bata (bass achha hai, mic clear hai, etc)
- Sound like: "Haan bhai! Main [product] recommend karungi â€” [price] mein milta hai, [benefit]. Dusra option [product2] hai..."
"""
            user_prompt = f"""User ne poocha: "{goal}"

Search results (products found):
{content[:3000]}

Ab in results ke basis pe user ko best 2-3 recommendations de. Prices mention kar. Casual Hinglish mein bol."""
        else:
            system_prompt = """Tu Shweta hai â€” helpful AI assistant. Search results ko padhke user ko clear, concise answer de Hinglish mein. 80-100 words max."""
            user_prompt = f"""User ne poocha: "{goal}"

Search results:
{content[:2500]}

Ab in results ke basis pe user ko clear answer de."""

        # Try Groq (best for this â€” fast + good Hindi)
        try:
            import requests as req
            groq_key = os.getenv("GROQ_API_KEY", "")
            if groq_key:
                resp = req.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={"Authorization": f"Bearer {groq_key}", "Content-Type": "application/json"},
                    json={
                        "model": os.getenv("GROQ_MODEL", "openai/gpt-oss-120b"),
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
                    return self._clean_summary(resp.json()["choices"][0]["message"]["content"], content, goal)
        except Exception:
            pass

        # Try Gemini
        try:
            from google import genai
            from google.genai import types
            client = genai.Client(api_key=GEMINI_API_KEY)
            response = client.models.generate_content(
                model="gemini-2.5-flash-lite",
                contents=f"{system_prompt}\n\n{user_prompt}",
                config=types.GenerateContentConfig(temperature=0.4, max_output_tokens=250)
            )
            return self._clean_summary(response.text, content, goal)
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
                    return self._clean_summary(resp.json()["choices"][0]["message"]["content"], content, goal)
        except Exception:
            pass

        # All AI failed â€” return raw product list directly
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

