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
                content = await page.inner_text("body")
                content = content[:3000]  # More content for better summary
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
            query = goal_lower.split("search")[-1].strip() if "search" in goal_lower else "products"
            return [
                {"action": "goto", "selector": "https://www.amazon.in", "value": ""},
                {"action": "type", "selector": "#twotabsearchtextbox", "value": query},
                {"action": "click", "selector": "#nav-search-submit-button", "value": ""},
                {"action": "wait", "selector": "", "value": "3"},
                {"action": "extract", "selector": "", "value": "product names and prices"},
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
                await page.fill(selector, value, timeout=5000)
            except Exception:
                # Try clicking first then typing
                try:
                    await page.click(selector, timeout=5000)
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
                text = await page.inner_text("body")
                return text[:1000]
            except Exception:
                return None

        return None

    def _summarize(self, goal: str, results: List, content: str) -> str:
        """Summarize browser results. Tries Groq → Gemini → GitHub → raw content."""
        prompt = f"""Summarize this browser task result in 2-3 simple Hinglish sentences.
Goal was: {goal}
Page content (partial): {content[:800]}
Give a short, useful summary in Hinglish. Focus on key info like prices, names, results."""

        # Try Groq
        try:
            import requests as req
            groq_key = os.getenv("GROQ_API_KEY", "")
            if groq_key:
                resp = req.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={"Authorization": f"Bearer {groq_key}", "Content-Type": "application/json"},
                    json={"model": "llama-3.3-70b-versatile", "messages": [{"role": "user", "content": prompt}], "temperature": 0.3, "max_tokens": 150},
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
                model="gemini-2.0-flash-lite", contents=prompt,
                config=types.GenerateContentConfig(temperature=0.3, max_output_tokens=150)
            )
            return response.text.strip()
        except Exception:
            pass

        # Try GitHub
        try:
            import requests as req
            gh_token = os.getenv("GITHUB_TOKEN", "")
            if gh_token:
                resp = req.post(
                    "https://models.inference.ai.azure.com/chat/completions",
                    headers={"Authorization": f"Bearer {gh_token}", "Content-Type": "application/json"},
                    json={"model": "gpt-4o-mini", "messages": [{"role": "user", "content": prompt}], "temperature": 0.3, "max_tokens": 150},
                    timeout=15
                )
                if resp.status_code == 200:
                    return resp.json()["choices"][0]["message"]["content"].strip()
        except Exception:
            pass

        # All AI failed — return raw useful content
        if content:
            lines = [l.strip() for l in content.split("\n") if len(l.strip()) > 15]
            return " | ".join(lines[:5])[:200] or "Results screen pe dikh rahe hain."
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
