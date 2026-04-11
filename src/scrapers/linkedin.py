from urllib.parse import urlencode

from loguru import logger
from playwright.sync_api import Page

from src.models import ScrapedJob
from src.scrapers.base import PlatformScraper
from src.utils.browser import browser_manager, human_delay


class LinkedInScraper(PlatformScraper):
    """Scraper for LinkedIn job listings."""

    platform_name = "linkedin"
    BASE_URL = "https://www.linkedin.com/jobs/search/"

    def scrape_jobs(self, filters: dict) -> list[ScrapedJob]:
        page = browser_manager.new_page(self.platform_name)
        jobs: list[ScrapedJob] = []

        try:
            params = {"sortBy": "DD"}  # Sort by date
            if filters.get("skills"):
                params["keywords"] = " ".join(filters["skills"][:3])
            if filters.get("location"):
                loc = filters["location"]
                params["location"] = loc[0] if isinstance(loc, list) else loc

            url = self.BASE_URL + "?" + urlencode(params)
            logger.info(f"Navigating to {url}")
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            human_delay(3.0, 5.0)

            page.wait_for_selector("[class*='job-card'], [class*='jobs-search'], li", timeout=10000)
            human_delay(1.0, 2.0)

            # Scroll to load more
            for _ in range(3):
                page.keyboard.press("End")
                human_delay(1.0, 2.0)

            cards = page.query_selector_all("[class*='job-card-container'], [class*='job-card'], li[class*='jobs']")
            logger.info(f"Found {len(cards)} cards")

            for card in cards[:25]:
                try:
                    job = self._parse_card(card)
                    if job:
                        jobs.append(job)
                except Exception as e:
                    logger.debug(f"Failed to parse card: {e}")

        except Exception as e:
            logger.error(f"LinkedIn scraping failed: {e}")
        finally:
            page.close()

        logger.info(f"LinkedIn: scraped {len(jobs)} jobs")
        return jobs

    def get_job_details(self, job_url: str) -> str:
        page = browser_manager.new_page(self.platform_name)
        try:
            page.goto(job_url, wait_until="domcontentloaded", timeout=30000)
            human_delay(2.0, 3.0)
            for sel in ["[class*='description']", "[class*='show-more']", "main"]:
                el = page.query_selector(sel)
                if el and len(el.inner_text()) > 100:
                    return el.inner_text().strip()
            return page.inner_text("body")[:5000]
        finally:
            page.close()

    def _parse_card(self, card) -> ScrapedJob | None:
        title_el = card.query_selector("[class*='title'], h3, a[class*='title']")
        if not title_el:
            return None
        title = title_el.inner_text().strip()
        if not title or len(title) < 5:
            return None

        link_el = card.query_selector("a[href*='/jobs/view/'], a[href*='/jobs/']")
        href = ""
        if link_el:
            href = link_el.get_attribute("href") or ""
        if href.startswith("/"):
            href = "https://www.linkedin.com" + href
        # Clean tracking params
        if "?" in href:
            href = href.split("?")[0]
        if not href:
            return None

        external_id = href.rstrip("/").split("/")[-1]

        company = ""
        comp_el = card.query_selector("[class*='company'], [class*='subtitle']")
        if comp_el:
            company = comp_el.inner_text().strip()

        location = ""
        loc_el = card.query_selector("[class*='location'], [class*='bullet']")
        if loc_el:
            location = loc_el.inner_text().strip()

        text = card.inner_text().lower()
        remote = "remote" in text or "télétravail" in text
        lang = "en" if any(w in title.lower() for w in ["engineer", "developer", "manager"]) else "fr"

        return ScrapedJob(
            platform=self.platform_name, external_id=external_id, title=title,
            company=company, location=location, remote=remote, skills=[],
            url=href, language=lang,
        )
