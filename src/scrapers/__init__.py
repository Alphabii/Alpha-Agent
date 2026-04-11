from src.registry import register_scraper
from src.scrapers.freework import FreeWorkScraper
from src.scrapers.collective import CollectiveScraper
from src.scrapers.hellowork import HelloWorkScraper
from src.scrapers.linkedin import LinkedInScraper

register_scraper("freework", FreeWorkScraper)
register_scraper("collective", CollectiveScraper)
register_scraper("hellowork", HelloWorkScraper)
register_scraper("linkedin", LinkedInScraper)
