"""
Browser Automation Skill for Shweta AI Desktop Assistant.
Uses Selenium to control Brave browser — mouse movements, typing, clicking.
User can see everything happening live on screen.
"""

import logging
import time
from typing import Dict, Optional

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains

logger = logging.getLogger(__name__)

from config import BROWSER_PATH, BROWSER_USER_DATA


class BrowserAutomation:
    """Controls Brave browser with Selenium — visible mouse, typing, clicking."""

    def __init__(self) -> None:
        """Initialize browser automation (browser not launched until needed)."""
        self.driver: Optional[webdriver.Chrome] = None
        self._is_ready = False

    def _ensure_browser(self) -> bool:
        """Launch Brave browser if not already running."""
        if self.driver and self._is_ready:
            try:
                # Check if browser is still alive
                self.driver.title
                return True
            except Exception:
                self._is_ready = False
                self.driver = None

        try:
            options = Options()
            options.binary_location = BROWSER_PATH
            # Use existing profile (keeps all logins, cookies, extensions)
            user_data = BROWSER_USER_DATA
            options.add_argument(f"--user-data-dir={user_data}")
            options.add_argument("--profile-directory=Default")
            # Keep browser open, don't run headless (user sees everything)
            options.add_argument("--start-maximized")
            options.add_argument("--disable-notifications")
            options.add_argument("--no-first-run")
            options.add_experimental_option("excludeSwitches", ["enable-automation"])
            options.add_experimental_option("useAutomationExtension", False)

            # Selenium 4 auto-downloads chromedriver
            self.driver = webdriver.Chrome(options=options)
            self._is_ready = True
            logger.info("Browser launched with Selenium.")
            return True

        except Exception as e:
            logger.error(f"Failed to launch browser: {e}")
            self._is_ready = False
            return False

    def open_url(self, url: str) -> Dict[str, str]:
        """Navigate to a URL."""
        if not self._ensure_browser():
            return {"status": "error", "message": "Browser launch failed."}

        try:
            if not url.startswith(("http://", "https://")):
                url = "https://" + url
            self.driver.get(url)
            time.sleep(1)
            return {"status": "success", "message": f"Opened: {url}"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def search_youtube(self, query: str) -> Dict[str, str]:
        """Go to YouTube, type in search box, and search."""
        if not self._ensure_browser():
            return {"status": "error", "message": "Browser launch failed."}

        try:
            # Go to YouTube
            self.driver.get("https://www.youtube.com")
            time.sleep(2)

            # Find search box and type
            search_box = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.NAME, "search_query"))
            )

            # Slow typing so user can see
            search_box.click()
            time.sleep(0.3)
            for char in query:
                search_box.send_keys(char)
                time.sleep(0.05)  # Visible typing speed

            time.sleep(0.5)
            search_box.send_keys(Keys.RETURN)
            time.sleep(2)

            return {"status": "success", "message": f"Searched YouTube: {query}"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def play_first_video(self) -> Dict[str, str]:
        """Click the first video in YouTube search results."""
        if not self._ensure_browser():
            return {"status": "error", "message": "Browser launch failed."}

        try:
            # Wait for search results
            time.sleep(2)

            # Find first video thumbnail/title link
            video = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "ytd-video-renderer a#video-title"))
            )

            # Scroll to it and click (visible)
            actions = ActionChains(self.driver)
            actions.move_to_element(video).pause(0.5).click().perform()
            time.sleep(2)

            return {"status": "success", "message": "First video playing."}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def search_and_play(self, query: str) -> Dict[str, str]:
        """Search YouTube and play the first result — full automation."""
        if not self._ensure_browser():
            return {"status": "error", "message": "Browser launch failed."}

        try:
            # Go to YouTube
            self.driver.get("https://www.youtube.com")
            time.sleep(2)

            # Type in search box
            search_box = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.NAME, "search_query"))
            )
            search_box.click()
            time.sleep(0.3)

            # Visible typing
            for char in query:
                search_box.send_keys(char)
                time.sleep(0.04)

            time.sleep(0.5)
            search_box.send_keys(Keys.RETURN)
            time.sleep(3)

            # Click first video
            video = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "ytd-video-renderer a#video-title"))
            )
            actions = ActionChains(self.driver)
            actions.move_to_element(video).pause(0.5).click().perform()
            time.sleep(2)

            return {"status": "success", "message": f"Playing: {query}"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def google_search(self, query: str) -> Dict[str, str]:
        """Go to Google, type query, and search."""
        if not self._ensure_browser():
            return {"status": "error", "message": "Browser launch failed."}

        try:
            self.driver.get("https://www.google.com")
            time.sleep(1.5)

            # Find search box
            search_box = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.NAME, "q"))
            )
            search_box.click()
            time.sleep(0.3)

            # Type visibly
            for char in query:
                search_box.send_keys(char)
                time.sleep(0.04)

            time.sleep(0.5)
            search_box.send_keys(Keys.RETURN)
            time.sleep(2)

            return {"status": "success", "message": f"Google search: {query}"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def click_element(self, text: str) -> Dict[str, str]:
        """Click on an element containing specific text."""
        if not self._ensure_browser():
            return {"status": "error", "message": "Browser launch failed."}

        try:
            # Find element by text
            element = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located(
                    (By.XPATH, f"//*[contains(text(), '{text}')]")
                )
            )
            actions = ActionChains(self.driver)
            actions.move_to_element(element).pause(0.3).click().perform()
            time.sleep(1)

            return {"status": "success", "message": f"Clicked: {text}"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def type_in_page(self, text: str) -> Dict[str, str]:
        """Type text in the currently focused element."""
        if not self._ensure_browser():
            return {"status": "error", "message": "Browser launch failed."}

        try:
            actions = ActionChains(self.driver)
            for char in text:
                actions.send_keys(char).pause(0.04)
            actions.perform()
            return {"status": "success", "message": f"Typed: {text}"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def scroll_down(self) -> Dict[str, str]:
        """Scroll down the page."""
        if not self._ensure_browser():
            return {"status": "error", "message": "Browser launch failed."}

        try:
            self.driver.execute_script("window.scrollBy(0, 500)")
            return {"status": "success", "message": "Scrolled down."}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def scroll_up(self) -> Dict[str, str]:
        """Scroll up the page."""
        if not self._ensure_browser():
            return {"status": "error", "message": "Browser launch failed."}

        try:
            self.driver.execute_script("window.scrollBy(0, -500)")
            return {"status": "success", "message": "Scrolled up."}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def go_back(self) -> Dict[str, str]:
        """Go back in browser history."""
        if not self._ensure_browser():
            return {"status": "error", "message": "Browser launch failed."}

        try:
            self.driver.back()
            time.sleep(1)
            return {"status": "success", "message": "Went back."}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def close_browser(self) -> Dict[str, str]:
        """Close the automated browser."""
        try:
            if self.driver:
                self.driver.quit()
                self.driver = None
                self._is_ready = False
            return {"status": "success", "message": "Browser closed."}
        except Exception as e:
            return {"status": "error", "message": str(e)}
