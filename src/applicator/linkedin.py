from loguru import logger
from playwright.sync_api import Page

from src.applicator.base import PlatformApplicator
from src.config import settings
from src.models import ApplicationRecord, JobRecord
from src.utils.browser import browser_manager, human_delay


class LinkedInApplicator(PlatformApplicator):
    """LinkedIn Easy Apply automation (draft mode — saves but can also submit)."""

    platform_name = "linkedin"

    def submit_application(self, job: JobRecord, application: ApplicationRecord) -> bool:
        """Navigate to job, attempt Easy Apply if available."""
        page = browser_manager.new_page(self.platform_name)

        try:
            logger.info(f"Applying to '{job.title}' on LinkedIn: {job.url}")
            page.goto(job.url, wait_until="domcontentloaded", timeout=30000)
            human_delay(3.0, 5.0)

            self._dismiss_popups(page)

            # Check if Easy Apply is available
            easy_apply_btn = self._find_easy_apply(page)
            if not easy_apply_btn:
                logger.info(f"No Easy Apply for '{job.title}' — external apply only")
                return False

            easy_apply_btn.click()
            human_delay(2.0, 4.0)

            # Fill the multi-step Easy Apply form
            max_steps = 10
            for step in range(max_steps):
                self._dismiss_popups(page)
                self._fill_current_step(page, job, application)
                human_delay(1.0, 2.0)

                # Check if we're on the review/submit page
                submit_btn = page.query_selector("button:has-text('Submit application')")
                if not submit_btn:
                    submit_btn = page.query_selector("button:has-text('Soumettre la candidature')")
                if not submit_btn:
                    submit_btn = page.query_selector("button:has-text('Envoyer la candidature')")

                if submit_btn and submit_btn.is_visible():
                    submit_btn.click()
                    human_delay(2.0, 4.0)
                    logger.info(f"LinkedIn Easy Apply submitted for '{job.title}'")
                    return True

                # Click Next/Continue
                next_btn = self._find_next_button(page)
                if next_btn:
                    next_btn.click()
                    human_delay(1.5, 3.0)
                else:
                    break

            logger.warning(f"Could not complete Easy Apply for '{job.title}'")
            return False

        except Exception as e:
            logger.error(f"Failed LinkedIn Easy Apply for '{job.title}': {e}")
            try:
                page.screenshot(path=str(settings.project_root / "logs" / f"error_linkedin_{job.id[:8]}.png"))
            except Exception:
                pass
            # Try to close the modal to avoid leaving it open
            try:
                dismiss = page.query_selector("button[aria-label='Dismiss']")
                if dismiss:
                    dismiss.click()
                    # Discard the draft
                    discard = page.query_selector("button:has-text('Discard')")
                    if discard:
                        discard.click()
            except Exception:
                pass
            return False
        finally:
            page.close()

    def _dismiss_popups(self, page: Page):
        """Dismiss LinkedIn popups and overlays."""
        for sel in [
            "button:has-text('Accepter')", "button:has-text('Accept')",
            "button[aria-label='Dismiss']",
            "[class*='msg-overlay-bubble-header'] button",
        ]:
            try:
                btn = page.query_selector(sel)
                if btn and btn.is_visible():
                    btn.click()
                    human_delay(0.3, 0.5)
            except Exception:
                pass

    def _find_easy_apply(self, page: Page):
        """Find the Easy Apply button."""
        for sel in [
            "button:has-text('Easy Apply')",
            "button:has-text('Candidature simplifi')",
            "button:has-text('Postuler')",
            "[class*='jobs-apply-button']",
        ]:
            try:
                btn = page.query_selector(sel)
                if btn and btn.is_visible():
                    text = btn.inner_text().lower()
                    # Exclude external apply buttons
                    if "easy" in text or "simplifi" in text or "postuler" in text:
                        return btn
            except Exception:
                continue
        return None

    def _fill_current_step(self, page: Page, job: JobRecord, application: ApplicationRecord):
        """Fill whatever fields are visible on the current Easy Apply step."""
        # Phone
        self._fill_if_empty(page, [
            "input[name*='phone']", "input[id*='phone']",
        ], settings.freelancer_phone)

        # Email
        self._fill_if_empty(page, [
            "input[name*='email']", "input[id*='email']",
        ], settings.freelancer_email)

        # Upload resume if file input visible
        resume_path = settings.get_resume_path(job.language)
        if resume_path:
            try:
                file_input = page.query_selector("input[type='file']")
                if file_input:
                    file_input.set_input_files(str(resume_path))
                    logger.info(f"Uploaded resume on LinkedIn")
                    human_delay(1.0, 2.0)
            except Exception:
                pass

        # Fill text areas (additional questions, cover letter)
        message = application.proposal_message or application.cover_letter
        textareas = page.query_selector_all("textarea:visible")
        for ta in textareas:
            try:
                if ta.is_visible() and not ta.input_value():
                    ta.fill(message[:500])  # LinkedIn limits text
                    human_delay(0.5, 1.0)
            except Exception:
                continue

        # Handle dropdowns (years of experience, education, etc.)
        selects = page.query_selector_all("select:visible")
        for sel_el in selects:
            try:
                if sel_el.is_visible():
                    options = sel_el.query_selector_all("option")
                    if len(options) > 1:
                        # Select the second option (first is usually placeholder)
                        sel_el.select_option(index=1)
                        human_delay(0.3, 0.5)
            except Exception:
                continue

        # Handle radio buttons (Yes/No questions — default to Yes)
        radios = page.query_selector_all("input[type='radio'][value='Yes']:visible, input[type='radio'][value='Oui']:visible")
        for radio in radios:
            try:
                if radio.is_visible() and not radio.is_checked():
                    radio.check()
                    human_delay(0.2, 0.4)
            except Exception:
                continue

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

    def _find_next_button(self, page: Page):
        """Find the Next/Continue button in multi-step form."""
        for sel in [
            "button:has-text('Next')", "button:has-text('Suivant')",
            "button:has-text('Continue')", "button:has-text('Continuer')",
            "button:has-text('Review')", "button:has-text('V')",
            "button[aria-label='Continue to next step']",
        ]:
            try:
                btn = page.query_selector(sel)
                if btn and btn.is_visible():
                    return btn
            except Exception:
                continue
        return None
