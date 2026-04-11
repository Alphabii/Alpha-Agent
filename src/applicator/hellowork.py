from loguru import logger
from playwright.sync_api import Page

from src.applicator.base import PlatformApplicator
from src.config import settings
from src.models import ApplicationRecord, JobRecord
from src.utils.browser import browser_manager, human_delay


class HelloWorkApplicator(PlatformApplicator):
    """Auto-apply on hellowork.com using Playwright."""

    platform_name = "hellowork"

    def submit_application(self, job: JobRecord, application: ApplicationRecord) -> bool:
        """Navigate to job page, fill form, submit."""
        page = browser_manager.new_page(self.platform_name)

        try:
            logger.info(f"Applying to '{job.title}' on HelloWork: {job.url}")
            page.goto(job.url, wait_until="domcontentloaded", timeout=30000)
            human_delay(2.0, 4.0)

            self._dismiss_popups(page)

            # Step 1: Click apply
            if not self._click_apply_button(page):
                logger.warning(f"No apply button found for '{job.title}'")
                return False

            human_delay(2.0, 4.0)
            self._dismiss_popups(page)

            # Step 2: Fill full form (HelloWork typically asks for more fields)
            self._fill_form(page, job, application)

            # Step 3: Upload CV
            self._upload_resume(page, job.language)

            human_delay(1.0, 2.0)

            # Step 4: Accept terms if checkbox exists
            self._check_terms(page)

            # Step 5: Submit
            if self._click_submit(page):
                human_delay(2.0, 4.0)
                logger.info(f"Application submitted for '{job.title}' on HelloWork")
                return True
            else:
                logger.warning(f"Could not find submit button for '{job.title}'")
                return False

        except Exception as e:
            logger.error(f"Failed to apply to '{job.title}' on HelloWork: {e}")
            try:
                page.screenshot(path=str(settings.project_root / "logs" / f"error_hellowork_{job.id[:8]}.png"))
            except Exception:
                pass
            return False
        finally:
            page.close()

    def _dismiss_popups(self, page: Page):
        """Close cookie banners, modals, etc."""
        for sel in [
            "button:has-text('Accepter')", "button:has-text('Tout accepter')",
            "button:has-text('Accept')", "button:has-text('Continuer')",
            "#didomi-notice-agree-button",
            "button:has-text('OK')", "[aria-label='Close']",
            "[class*='cookie'] button", "[class*='consent'] button",
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
            "button:has-text('postuler')", "a:has-text('postuler')",
            "button:has-text('Je postule')", "a:has-text('Je postule')",
            "button:has-text('Candidater')",
            "button:has-text('Postuler en 1 clic')",
            "[data-testid*='apply']",
            "[class*='apply'] button", "[class*='postuler']",
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
        """Fill all form fields. HelloWork asks for full contact details."""
        message = application.proposal_message or application.cover_letter

        # Fill name fields
        self._fill_if_empty(page, [
            "input[name*='firstname']", "input[name*='first_name']",
            "input[name*='prenom']", "input[id*='prenom']",
            "input[placeholder*='Pr']",
        ], settings.freelancer_first_name)

        self._fill_if_empty(page, [
            "input[name*='lastname']", "input[name*='last_name']",
            "input[name*='nom']", "input[id*='nom']",
            "input[placeholder*='Nom']",
        ], settings.freelancer_last_name)

        # Email
        self._fill_if_empty(page, [
            "input[name*='email']", "input[type='email']",
            "input[id*='email']", "input[placeholder*='email']",
        ], settings.freelancer_email)

        # Phone
        self._fill_if_empty(page, [
            "input[name*='phone']", "input[name*='tel']",
            "input[type='tel']", "input[id*='phone']",
            "input[placeholder*='phone']", "input[placeholder*='tel']",
        ], settings.freelancer_phone)

        # Message/motivation
        for sel in [
            "textarea[name*='message']", "textarea[name*='motivation']",
            "textarea[name*='lettre']", "textarea[name*='cover']",
            "textarea[id*='message']", "textarea[placeholder*='message']",
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

        # Title/current position
        self._fill_if_empty(page, [
            "input[name*='title']", "input[name*='poste']",
            "input[name*='fonction']", "input[placeholder*='poste']",
        ], settings.freelancer_title)

    def _fill_if_empty(self, page: Page, selectors: list[str], value: str):
        """Fill a field only if visible and empty."""
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
        """Upload CV."""
        resume_path = settings.get_resume_path(language)
        if not resume_path:
            return

        for sel in ["input[type='file']", "input[accept*='pdf']", "input[name*='cv']", "input[name*='resume']"]:
            try:
                el = page.query_selector(sel)
                if el:
                    el.set_input_files(str(resume_path))
                    logger.info(f"Uploaded resume: {resume_path.name}")
                    human_delay(1.0, 2.0)
                    return
            except Exception:
                continue

        for sel in ["button:has-text('CV')", "button:has-text('Importer')", "label:has-text('CV')", "[class*='upload']"]:
            try:
                btn = page.query_selector(sel)
                if btn and btn.is_visible():
                    with page.expect_file_chooser() as fc:
                        btn.click()
                    fc.value.set_files(str(resume_path))
                    logger.info(f"Uploaded resume via chooser")
                    human_delay(1.0, 2.0)
                    return
            except Exception:
                continue

    def _check_terms(self, page: Page):
        """Check terms/conditions checkbox if present."""
        for sel in [
            "input[type='checkbox'][name*='terms']",
            "input[type='checkbox'][name*='cgu']",
            "input[type='checkbox'][name*='consent']",
            "input[type='checkbox'][name*='accept']",
            "input[type='checkbox'][id*='terms']",
            "input[type='checkbox'][id*='cgu']",
        ]:
            try:
                el = page.query_selector(sel)
                if el and el.is_visible() and not el.is_checked():
                    el.check()
                    human_delay(0.3, 0.5)
            except Exception:
                continue

    def _click_submit(self, page: Page) -> bool:
        """Find and click submit."""
        for sel in [
            "button[type='submit']",
            "button:has-text('Envoyer')", "button:has-text('envoyer')",
            "button:has-text('Postuler')", "button:has-text('Valider')",
            "button:has-text('Confirmer')", "button:has-text('Envoyer ma candidature')",
            "button:has-text('Submit')", "input[type='submit']",
        ]:
            try:
                btn = page.query_selector(sel)
                if btn and btn.is_visible():
                    btn.click()
                    return True
            except Exception:
                continue
        return False
