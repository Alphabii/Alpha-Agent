import json
import re
from urllib.parse import urlencode

from loguru import logger
from playwright.sync_api import Page

from src.models import ScrapedJob
from src.scrapers.base import PlatformScraper
from src.utils.browser import browser_manager, human_delay


# Free-Work API filter parameter mappings
CONTRACT_MAP = {
    "freelance": "contractor",
    "cdi": "permanent",
    "cdd": "fixed_term",
    "internship": "internship",
    "apprenticeship": "apprenticeship",
}

FRESHNESS_MAP = {
    "24h": "less_than_24_hours",
    "yesterday": "less_than_24_hours",
    "1d": "less_than_24_hours",
    "7d": "less_than_7_days",
    "last_week": "less_than_7_days",
    "1w": "less_than_7_days",
    "14d": "less_than_14_days",
    "2w": "less_than_14_days",
    "30d": "less_than_30_days",
    "last_month": "less_than_30_days",
    "1m": "less_than_30_days",
}

REMOTE_MAP = {
    "full": "full",
    "partial": "partial",
    "no": "no",
    "hybrid": "partial",
    True: "full",
    False: "no",
}

LOCATION_MAP = {
    "france": "fr~~~",
    "paris": "fr~ile-de-france~paris~paris",
    "ile-de-france": "fr~ile-de-france~~",
    "île-de-france": "fr~ile-de-france~~",
    "lyon": "fr~auvergne-rhone-alpes~rhone~lyon",
    "toulouse": "fr~occitanie~haute-garonne~toulouse",
    "marseille": "fr~provence-alpes-cote-dazur~bouches-du-rhone~marseille",
    "nantes": "fr~pays-de-la-loire~loire-atlantique~nantes",
    "remote": "fr~~~",
}


class FreeWorkScraper(PlatformScraper):
    """Scraper for free-work.com using the internal API."""

    platform_name = "freework"
    API_URL = "https://www.free-work.com/api/job_postings"
    SITE_URL = "https://www.free-work.com"

    def _build_api_params(self, filters: dict) -> dict:
        """Build API query parameters from user-facing filters."""
        params = {"itemsPerPage": 20, "page": 1}

        # Search query
        query = filters.get("query")
        if not query and filters.get("skills"):
            skills = filters["skills"]
            query = " ".join(skills[:3]) if isinstance(skills, list) else skills
        if query:
            params["searchKeywords"] = query

        # Contract type
        contracts = filters.get("contracts")
        if contracts:
            if isinstance(contracts, str):
                contracts = [contracts]
            mapped = []
            for c in contracts:
                key = c.lower().strip()
                mapped.append(CONTRACT_MAP.get(key, key))
            params["contracts"] = ",".join(mapped)

        # Publication date
        freshness = filters.get("freshness")
        if freshness:
            key = str(freshness).lower().strip()
            params["publishedSince"] = FRESHNESS_MAP.get(key, key)

        # Remote work
        remote = filters.get("remote")
        if remote is not None:
            mapped = REMOTE_MAP.get(remote, str(remote).lower())
            if mapped and mapped != "no":
                params["remote"] = mapped

        # Location
        location = filters.get("location")
        if location:
            loc = location[0] if isinstance(location, list) else location
            loc_key = LOCATION_MAP.get(loc.lower(), None)
            if loc_key:
                params["locationKeys"] = loc_key
            else:
                params["locationKeys"] = loc

        # Daily rate range
        min_rate = filters.get("min_rate")
        if min_rate and int(min_rate) > 0:
            params["minDailySalary"] = int(min_rate)
        max_rate = filters.get("max_rate")
        if max_rate and int(max_rate) > 0:
            params["maxDailySalary"] = int(max_rate)

        return params

    def scrape_jobs(self, filters: dict) -> list[ScrapedJob]:
        page = browser_manager.new_page(self.platform_name)
        jobs: list[ScrapedJob] = []
        max_pages = filters.get("max_pages", 3)

        try:
            # Load the site first to have session cookies
            page.goto(self.SITE_URL, wait_until="domcontentloaded", timeout=30000)
            human_delay(2.0, 3.0)

            api_params = self._build_api_params(filters)
            logger.info(f"Free-Work API filters: {api_params}")

            for page_num in range(1, max_pages + 1):
                api_params["page"] = page_num
                api_url = self.API_URL + "?" + urlencode(api_params)

                # Fetch API via browser context (keeps session/cookies)
                raw = page.evaluate("""async (url) => {
                    const res = await fetch(url, { credentials: "include" });
                    return await res.text();
                }""", api_url)

                data = json.loads(raw)
                members = data.get("hydra:member", [])
                total = data.get("hydra:totalItems", 0)

                if page_num == 1:
                    logger.info(f"Free-Work API: {total} total results")

                if not members:
                    break

                for item in members:
                    try:
                        job = self._parse_api_item(item)
                        if job:
                            jobs.append(job)
                    except Exception as e:
                        logger.debug(f"Failed to parse API item: {e}")

                # Stop if we've fetched all results
                if len(jobs) >= total:
                    break

                human_delay(0.5, 1.0)

        except Exception as e:
            logger.error(f"Free-Work scraping failed: {e}")
        finally:
            page.close()

        logger.info(f"Free-Work: scraped {len(jobs)} jobs total")
        return jobs

    def _parse_api_item(self, item: dict) -> ScrapedJob | None:
        title = item.get("title", "").strip()
        slug = item.get("slug", "")
        if not title or not slug:
            return None

        # Build URL from job category and slug
        job_info = item.get("job", {})
        job_slug = job_info.get("slug", "")
        url = f"{self.SITE_URL}/fr/tech-it/{job_slug}/job-mission/{slug}"

        # Company
        company_info = item.get("company", {})
        company = company_info.get("name", "")

        # Location
        loc = item.get("location", {}) or {}
        location_parts = []
        if loc.get("locality"):
            location_parts.append(loc["locality"])
        if loc.get("adminLevel1"):
            location_parts.append(loc["adminLevel1"])
        if loc.get("country"):
            location_parts.append(loc["country"])
        location = ", ".join(location_parts)

        # Rate
        daily_rate_min = item.get("minDailySalary") or 0
        daily_rate_max = item.get("maxDailySalary") or 0
        # Try parsing from dailySalary string (e.g. "400-600 €")
        if not daily_rate_min:
            salary_str = item.get("dailySalary") or ""
            rate_match = re.search(r"(\d{3,})\s*[-–à]\s*(\d{3,})", str(salary_str))
            if rate_match:
                daily_rate_min = int(rate_match.group(1))
                daily_rate_max = int(rate_match.group(2))

        # Remote
        remote_mode = item.get("remoteMode") or ""
        remote = remote_mode in ("full", "partial")

        # Description (HTML stripped to plain text)
        desc_html = item.get("description", "") or ""
        desc_text = re.sub(r"<[^>]+>", " ", desc_html)
        desc_text = re.sub(r"\s+", " ", desc_text).strip()

        # Skills
        skills = []
        for skill in item.get("skills", []):
            if isinstance(skill, dict):
                skills.append(skill.get("name", ""))
            elif isinstance(skill, str):
                skills.append(skill)
        skills = [s for s in skills if s]

        # Fallback: extract skills from description if API returns none
        if not skills:
            skills = self._extract_skills_from_text(desc_text)

        # Contracts
        contracts = item.get("contracts", [])
        contract_type = ", ".join(contracts) if contracts else ""

        # Duration
        duration_val = item.get("durationValue") or ""
        duration_period = item.get("durationPeriod") or ""
        duration = f"{duration_val} {duration_period}".strip() if duration_val else ""

        # Application type
        app_type = item.get("applicationType", "")

        # Language detection
        locale = item.get("locale", "fr_FR")
        lang = "en" if "en" in locale.lower() else "fr"

        # Published date
        posted_at = item.get("publishedAt", "")

        return ScrapedJob(
            platform=self.platform_name,
            external_id=slug,
            title=title,
            company=company,
            location=location,
            remote=remote,
            daily_rate_min=daily_rate_min,
            daily_rate_max=daily_rate_max,
            skills=skills,
            url=url,
            language=lang,
            description=desc_text,
            posted_at=posted_at,
            contract_type=contract_type,
            duration=duration,
        )

    KNOWN_SKILLS = [
        "Python", "Java", "JavaScript", "TypeScript", "SQL", "R", "Scala", "C\\+\\+", "C#",
        "TensorFlow", "PyTorch", "Keras", "Scikit-learn", "Pandas", "NumPy", "Spark", "PySpark",
        "Hadoop", "Kafka", "Airflow", "dbt", "Docker", "Kubernetes", "AWS", "Azure", "GCP",
        "Snowflake", "BigQuery", "Redshift", "Databricks", "Tableau", "Power BI", "Looker",
        "Machine Learning", "Deep Learning", "NLP", "Computer Vision", "LLM", "GenAI",
        "MLOps", "MLflow", "CI/CD", "Git", "Linux", "Terraform", "FastAPI", "Flask", "Django",
        "React", "Node\\.js", "PostgreSQL", "MongoDB", "MySQL", "Redis", "Elasticsearch",
        "LangChain", "RAG", "OpenCV", "YOLO", "Transformers", "HuggingFace",
        "Dataiku", "SAS", "SPSS", "Excel", "Qlik", "Grafana",
        "ETL", "NoSQL", "REST", "API", "Agile", "Scrum", "JIRA",
    ]

    def _extract_skills_from_text(self, text: str) -> list[str]:
        """Extract known tech skills from job description text."""
        found = []
        for skill in self.KNOWN_SKILLS:
            if re.search(rf"\b{skill}\b", text, re.IGNORECASE):
                # Use clean name (unescape regex chars)
                clean = skill.replace("\\", "")
                if clean not in found:
                    found.append(clean)
        return found

    def get_job_details(self, job_url: str) -> str:
        """Fetch full job description from the job page."""
        page = browser_manager.new_page(self.platform_name)
        try:
            page.goto(job_url, wait_until="domcontentloaded", timeout=30000)
            human_delay(1.5, 3.0)
            for selector in ["[class*='description']", "[class*='content']", "[class*='detail']", "main"]:
                el = page.query_selector(selector)
                if el:
                    text = el.inner_text()
                    if len(text) > 100:
                        return text.strip()
            return page.inner_text("body")[:5000]
        finally:
            page.close()
