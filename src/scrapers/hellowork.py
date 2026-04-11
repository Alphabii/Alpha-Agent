from urllib.parse import urlencode

from loguru import logger
from playwright.sync_api import Page

from src.models import ScrapedJob
from src.scrapers.base import PlatformScraper
from src.utils.browser import browser_manager, human_delay


class HelloWorkScraper(PlatformScraper):
    """Scraper for hellowork.com job listings."""

    platform_name = "hellowork"
    BASE_URL = "https://www.hellowork.com/fr-fr/emploi/recherche.html"

    def scrape_jobs(self, filters: dict) -> list[ScrapedJob]:
        page = browser_manager.new_page(self.platform_name)
        jobs: list[ScrapedJob] = []

        try:
            params = {}
            if filters.get("skills"):
                params["k"] = " ".join(filters["skills"][:3])
            if filters.get("location"):
                loc = filters["location"]
                params["l"] = loc[0] if isinstance(loc, list) else loc

            url = self.BASE_URL
            if params:
                url += "?" + urlencode(params)

            logger.info(f"Navigating to {url}")
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            human_delay(3.0, 5.0)

            # Dismiss cookie banner
            for sel in ["button:has-text('Accepter')", "button:has-text('Tout accepter')", "#didomi-notice-agree-button"]:
                try:
                    btn = page.query_selector(sel)
                    if btn and btn.is_visible():
                        btn.click()
                        human_delay(0.5, 1.0)
                        break
                except Exception:
                    pass

            page.wait_for_selector("[class*='offer'], [class*='job'], article, li[class]", timeout=10000)
            human_delay(1.0, 2.0)

            cards = page.query_selector_all("[class*='offer'], [class*='job-card'], article")
            if not cards:
                cards = page.query_selector_all("li a[href*='/emploi/']")
            logger.info(f"Found {len(cards)} cards")

            for card in cards[:30]:
                try:
                    job = self._parse_card(card)
                    if job:
                        jobs.append(job)
                except Exception as e:
                    logger.debug(f"Failed to parse card: {e}")

        except Exception as e:
            logger.error(f"HelloWork scraping failed: {e}")
        finally:
            page.close()

        logger.info(f"HelloWork: scraped {len(jobs)} jobs")
        return jobs

    def get_job_details(self, job_url: str) -> str:
        page = browser_manager.new_page(self.platform_name)
        try:
            page.goto(job_url, wait_until="domcontentloaded", timeout=30000)
            human_delay(2.0, 3.0)
            for sel in ["[class*='description']", "[class*='content']", "[class*='detail']", "main"]:
                el = page.query_selector(sel)
                if el and len(el.inner_text()) > 100:
                    return el.inner_text().strip()
            return page.inner_text("body")[:5000]
        finally:
            page.close()

    def _parse_card(self, card) -> ScrapedJob | None:
        title_el = card.query_selector("h2, h3, [class*='title'], a[class*='title']")
        if not title_el:
            return None
        title = title_el.inner_text().strip()
        if not title or len(title) < 5:
            return None

        link_el = card.query_selector("a[href*='/emploi/'], a[href]")
        href = ""
        if link_el:
            href = link_el.get_attribute("href") or ""
        if href.startswith("/"):
            href = "https://www.hellowork.com" + href
        if not href:
            return None

        external_id = href.rstrip("/").split("/")[-1]

        company = ""
        comp_el = card.query_selector("[class*='company'], [class*='entreprise']")
        if comp_el:
            company = comp_el.inner_text().strip()

        location = ""
        loc_el = card.query_selector("[class*='location'], [class*='lieu'], [class*='city']")
        if loc_el:
            location = loc_el.inner_text().strip()

        text = card.inner_text().lower()
        remote = "remote" in text or "télétravail" in text

        return ScrapedJob(
            platform=self.platform_name, external_id=external_id, title=title,
            company=company, location=location, remote=remote, skills=[],
            url=href, language="fr",
        )
