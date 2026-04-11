from loguru import logger
from playwright.sync_api import Page

from src.applicator.base import PlatformApplicator
from src.config import settings
from src.models import ApplicationRecord, JobRecord
from src.utils.browser import browser_manager, human_delay


class CollectiveApplicator(PlatformApplicator):
    """Auto-apply on collective.work using Playwright."""

    platform_name = "collective"

    def submit_application(self, job: JobRecord, application: ApplicationRecord) -> bool:
        """Navigate to job page, click apply, fill form, submit."""
        page = browser_manager.new_page(self.platform_name)

        try:
            logger.info(f"Applying to '{job.title}' on Collective: {job.url}")
            page.goto(job.url, wait_until="domcontentloaded", timeout=30000)
            human_delay(2.0, 4.0)

            self._dismiss_popups(page)

            # Step 1: Click apply
            if not self._click_apply_button(page):
                logger.warning(f"No apply button found for '{job.title}'")
                return False

            human_delay(2.0, 4.0)
            self._dismiss_popups(page)

            # Step 2: Fill form
            self._fill_form(page, job, application)

            # Step 3: Upload CV
            self._upload_resume(page, job.language)

            human_delay(1.0, 2.0)

            # Step 4: Submit
            if self._click_submit(page):
                human_delay(2.0, 4.0)
                logger.info(f"Application submitted for '{job.title}' on Collective")
                return True
            else:
                logger.warning(f"Could not find submit button for '{job.title}'")
                return False

        except Exception as e:
            logger.error(f"Failed to apply to '{job.title}' on Collective: {e}")
            try:
                page.screenshot(path=str(settings.project_root / "logs" / f"error_collective_{job.id[:8]}.png"))
            except Exception:
                pass
            return False
        finally:
            page.close()

    def _dismiss_popups(self, page: Page):
        """Close cookie banners, modals, etc."""
        for sel in [
            "button:has-text('Accepter')", "button:has-text('Accept')",
            "button:has-text('OK')", "button:has-text('Fermer')",
            "[aria-label='Close']", "[class*='cookie'] button",
        ]:
            try:
                btn = page.query_selector(sel)
                if btn and btn.is_visible():
                    btn.click()
                    human_delay(0.3, 0.8)
            except Exception:
                pass

    def _click_apply_button(self, page: Page) -> bool:
        """Find and click the apply button."""
        for sel in [
            "button:has-text('Postuler')", "a:has-text('Postuler')",
            "button:has-text('Candidater')", "a:has-text('Candidater')",
            "button:has-text('Apply')", "a:has-text('Apply')",
            "button:has-text('Je suis int')",
            "[data-testid*='apply']", "[class*='apply']",
        ]:
            try:
                btn = page.query_selector(sel)
                if btn and btn.is_visible():
                    btn.click()
                    logger.debug(f"Clicked apply: {sel}")
                    return True
            except Exception:
                continue
        return False

    def _fill_form(self, page: Page, job: JobRecord, application: ApplicationRecord):
        """Fill the application form."""
        message = application.proposal_message or application.cover_letter

        # Fill message textarea
        for sel in [
            "textarea[name*='message']", "textarea[name*='motivation']",
            "textarea[name*='cover']", "textarea[placeholder*='message']",
            "textarea[placeholder*='motivation']", "textarea",
        ]:
            try:
                el = page.query_selector(sel)
                if el and el.is_visible():
                    el.fill(message)
                    human_delay(0.5, 1.0)
                    break
            except Exception:
                continue

        # Fill contact fields
        self._fill_if_empty(page, ["input[name*='email']", "input[type='email']"], settings.freelancer_email)
        self._fill_if_empty(page, ["input[name*='phone']", "input[type='tel']"], settings.freelancer_phone)
        self._fill_if_empty(page, ["input[name*='first']", "input[name*='prenom']"], settings.freelancer_first_name)
        self._fill_if_empty(page, ["input[name*='last']", "input[name*='nom']"], settings.freelancer_last_name)
        self._fill_if_empty(page, ["input[name*='linkedin']"], settings.freelancer_linkedin)

        # Try to fill TJM/rate if asked
        for sel in ["input[name*='tjm']", "input[name*='rate']", "input[name*='tarif']", "input[placeholder*='TJM']"]:
            try:
                el = page.query_selector(sel)
                if el and el.is_visible() and not el.input_value():
                    el.fill(str(settings.daily_rate_min))
                    human_delay(0.2, 0.5)
                    break
            except Exception:
                continue

    def _fill_if_empty(self, page: Page, selectors: list[str], value: str):
        """Fill a field only if it's empty and visible."""
        if not value:
            return
        for sel in selectors:
            try:
                el = page.query_selector(sel)
                if el and el.is_visible() and not el.input_value():
                    el.fill(value)
                    human_delay(0.2, 0.5)
                    break
            except Exception:
                continue

    def _upload_resume(self, page: Page, language: str = "fr"):
        """Upload CV if file input exists."""
        resume_path = settings.get_resume_path(language)
        if not resume_path:
            return

        for sel in ["input[type='file']", "input[accept*='pdf']", "input[name*='cv']", "input[name*='file']"]:
            try:
                el = page.query_selector(sel)
                if el:
                    el.set_input_files(str(resume_path))
                    logger.info(f"Uploaded resume: {resume_path.name}")
                    human_delay(1.0, 2.0)
                    return
            except Exception:
                continue

        # Try file chooser approach
        for sel in ["button:has-text('CV')", "button:has-text('Upload')", "label:has-text('CV')", "[class*='upload']"]:
            try:
                btn = page.query_selector(sel)
                if btn and btn.is_visible():
                    with page.expect_file_chooser() as fc:
                        btn.click()
                    fc.value.set_files(str(resume_path))
                    logger.info(f"Uploaded resume via chooser: {resume_path.name}")
                    human_delay(1.0, 2.0)
                    return
            except Exception:
                continue

    def _click_submit(self, page: Page) -> bool:
        """Find and click submit."""
        for sel in [
            "button[type='submit']", "button:has-text('Envoyer')",
            "button:has-text('Postuler')", "button:has-text('Valider')",
            "button:has-text('Confirmer')", "button:has-text('Submit')",
            "input[type='submit']",
        ]:
            try:
                btn = page.query_selector(sel)
                if btn and btn.is_visible():
                    btn.click()
                    return True
            except Exception:
                continue
        return False
