import random
import time

from playwright.sync_api import BrowserContext, Page, sync_playwright

from src.config import settings
from loguru import logger


class BrowserManager:
    """Manages persistent Playwright browser contexts per platform."""

    def __init__(self):
        self._playwright = None
        self._browser = None
        self._contexts: dict[str, BrowserContext] = {}

    def start(self):
        """Initialize Playwright."""
        self._playwright = sync_playwright().start()
        logger.info("Playwright started")

    def stop(self):
        """Close all contexts and stop Playwright."""
        for name, ctx in self._contexts.items():
            ctx.close()
            logger.debug(f"Closed browser context: {name}")
        self._contexts.clear()
        if self._playwright:
            self._playwright.stop()
            logger.info("Playwright stopped")

    def get_context(self, platform: str, headless: bool = True) -> BrowserContext:
        """Get or create a persistent browser context for a platform."""
        if platform in self._contexts:
            return self._contexts[platform]

        if not self._playwright:
            self.start()

        profile_dir = settings.profiles_dir / platform
        profile_dir.mkdir(parents=True, exist_ok=True)

        context = self._playwright.chromium.launch_persistent_context(
            user_data_dir=str(profile_dir),
            headless=headless,
            viewport={"width": 1280, "height": 800},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            ),
            locale="fr-FR",
            timezone_id="Europe/Paris",
        )

        self._contexts[platform] = context
        logger.info(f"Created browser context for {platform}")
        return context

    def new_page(self, platform: str, headless: bool = True) -> Page:
        """Get a new page in the platform's browser context."""
        ctx = self.get_context(platform, headless)
        return ctx.new_page()

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *args):
        self.stop()


def human_delay(min_sec: float = 0.5, max_sec: float = 2.0):
    """Sleep for a random duration to mimic human behavior."""
    time.sleep(random.uniform(min_sec, max_sec))


def human_type(page: Page, selector: str, text: str, delay_ms: int = 80):
    """Type text character by character with random delays."""
    page.click(selector)
    for char in text:
        page.keyboard.type(char, delay=random.randint(delay_ms - 30, delay_ms + 50))
    human_delay(0.3, 0.8)


# Global browser manager instance
browser_manager = BrowserManager()
