from dataclasses import dataclass, field
from loguru import logger
from playwright.sync_api import Page

from src.applicator.base import PlatformApplicator
from src.config import settings
from src.models import ApplicationRecord, JobRecord
from src.utils.browser import browser_manager, human_delay


@dataclass
class ApplyResult:
    success: bool = False
    application_result: str = ""  # "submitted", "external_redirect", "no_apply_button", "error"
    external_url: str = ""


class FreeWorkApplicator(PlatformApplicator):
    """Auto-apply on free-work.com using Playwright.

    Free-Work has two apply flows:
    1. Direct apply: clicking "Postuler" reveals a message textarea + "Je postule" submit button.
    2. External redirect: clicking "Postuler" shows a link to the recruiter's external site.
    Only flow 1 is automated; flow 2 is logged and skipped.
    """

    platform_name = "freework"
    last_apply_result: ApplyResult = None
    LOGIN_URL = "https://www.free-work.com/fr/tech-it/login"

    def _is_logged_in(self, page: Page) -> bool:
        """Check if the current page shows a logged-in state."""
        # If we see a login/signup prompt or no "Postuler" button, we're likely not logged in
        body = page.inner_text("body").lower()
        not_logged_signals = ["créer un compte", "se connecter", "trouvez votre prochaine mission"]
        for signal in not_logged_signals:
            if signal in body:
                return False
        return True

    def _auto_login(self, page: Page) -> bool:
        """Automatically log in to Free-Work using credentials from .env."""
        if not settings.freework_email or not settings.freework_password:
            logger.warning("Freework credentials not set in .env — cannot auto-login")
            return False

        try:
            logger.info("Session expired — auto-logging in to Free-Work...")
            page.goto(self.LOGIN_URL, wait_until="domcontentloaded", timeout=30000)
            human_delay(2.0, 3.0)
            self._dismiss_popups(page)

            # Fill email
            email_input = page.query_selector("input[type='email'], input[name='email'], #email")
            if not email_input:
                email_input = page.query_selector("input[type='text']")
            if not email_input:
                logger.error("Could not find email input on login page")
                return False

            email_input.click()
            human_delay(0.3, 0.5)
            email_input.fill(settings.freework_email)
            human_delay(0.5, 1.0)

            # Fill password
            password_input = page.query_selector("input[type='password']")
            if not password_input:
                logger.error("Could not find password input on login page")
                return False

            password_input.click()
            human_delay(0.3, 0.5)
            password_input.fill(settings.freework_password)
            human_delay(0.5, 1.0)

            # Click login button
            login_btn = page.query_selector("button[type='submit']")
            if not login_btn:
                login_btn = page.query_selector("button:has-text('Connexion')")
            if not login_btn:
                logger.error("Could not find login button")
                return False

            login_btn.click()
            human_delay(4.0, 6.0)

            # Verify login succeeded
            body = page.inner_text("body").lower()
            if "mot de passe incorrect" in body or "identifiants invalides" in body:
                logger.error("Freework login failed — invalid credentials")
                return False

            logger.info("Auto-login to Free-Work successful")
            return True

        except Exception as e:
            logger.error(f"Auto-login failed: {e}")
            return False

    def submit_application(self, job: JobRecord, application: ApplicationRecord) -> bool:
        self.last_apply_result = ApplyResult()
        page = browser_manager.new_page(self.platform_name)

        try:
            logger.info(f"Applying to '{job.title}' on Free-Work: {job.url}")
            page.goto(job.url, wait_until="domcontentloaded", timeout=30000)
            human_delay(3.0, 5.0)

            self._dismiss_popups(page)

            # Auto-login if session expired
            if not self._is_logged_in(page):
                if not self._auto_login(page):
                    self.last_apply_result = ApplyResult(
                        success=False, application_result="login_failed"
                    )
                    return False
                # Navigate back to the job page after login
                page.goto(job.url, wait_until="domcontentloaded", timeout=30000)
                human_delay(3.0, 5.0)
                self._dismiss_popups(page)

            # Click the "Postuler" button to reveal the apply form
            postuler = page.query_selector("button:has-text('Postuler')")
            if not postuler or not postuler.is_visible():
                logger.warning(f"No Postuler button found for '{job.title}'")
                self.last_apply_result = ApplyResult(
                    success=False, application_result="no_apply_button"
                )
                return False

            postuler.click()
            human_delay(3.0, 4.0)

            # Check if already applied
            body_text = page.inner_text("body").lower()
            if "vous avez postulé" in body_text:
                logger.info(f"Already applied to '{job.title}' — skipping")
                self.last_apply_result = ApplyResult(
                    success=False, application_result="already_applied"
                )
                return False

            # Check which flow we got
            textarea = page.query_selector("#job-application-message")
            if not textarea or not textarea.is_visible():
                # Maybe session expired mid-page — try auto-login and retry
                page.screenshot(path=str(settings.project_root / "logs" / "debug_after_postuler.png"))
                if self._auto_login(page):
                    page.goto(job.url, wait_until="domcontentloaded", timeout=30000)
                    human_delay(3.0, 5.0)
                    self._dismiss_popups(page)
                    postuler = page.query_selector("button:has-text('Postuler')")
                    if postuler and postuler.is_visible():
                        postuler.click()
                        human_delay(3.0, 4.0)
                    textarea = page.query_selector("#job-application-message")

            if not textarea or not textarea.is_visible():
                # Flow 2: external redirect
                ext_url = ""
                external_link = page.query_selector("a:has-text('Je postule')")
                if external_link:
                    ext_url = external_link.get_attribute("href") or ""
                    logger.info(f"External apply for '{job.title}': {ext_url[:100]}")
                logger.warning(f"No direct apply form for '{job.title}' — external redirect")
                self.last_apply_result = ApplyResult(
                    success=False, application_result="external_redirect", external_url=ext_url
                )
                return False

            # Flow 1: Direct apply — scroll to form, fill, and submit
            textarea.scroll_into_view_if_needed()
            human_delay(0.5, 1.0)

            message = application.proposal_message or application.cover_letter
            if message:
                textarea.click()
                human_delay(0.5, 1.0)
                textarea.fill(message)
                human_delay(1.0, 2.0)
                logger.debug(f"Filled message textarea ({len(message)} chars)")

            human_delay(1.0, 2.0)

            # Click "Je postule" submit button
            submit_btn = page.query_selector("button[type='submit']:has-text('Je postule')")
            if not submit_btn:
                submit_btn = page.query_selector("button:has-text('Je postule')")
            if not submit_btn or not submit_btn.is_visible():
                logger.warning(f"Could not find 'Je postule' submit button for '{job.title}'")
                return False

            submit_btn.scroll_into_view_if_needed()
            human_delay(0.5, 1.0)
            submit_btn.click()
            human_delay(3.0, 4.0)

            # Handle status confirmation popup ("Vérifiez votre statut")
            confirm_btn = page.query_selector("button:has-text('Confirmer candidature')")
            if confirm_btn and confirm_btn.is_visible():
                logger.debug("Status confirmation popup detected — clicking 'Confirmer candidature'")
                confirm_btn.click()
                human_delay(4.0, 6.0)
            else:
                human_delay(2.0, 3.0)

            # Verify submission succeeded
            if self._verify_submission(page):
                logger.info(f"Application CONFIRMED for '{job.title}' on Free-Work")
                self.last_apply_result = ApplyResult(
                    success=True, application_result="submitted"
                )
                return True

            logger.warning(f"Application may not have submitted for '{job.title}' — no confirmation detected")
            page.screenshot(path=str(settings.project_root / "logs" / f"unconfirmed_freework_{job.id[:8]}.png"))
            self.last_apply_result = ApplyResult(
                success=False, application_result="unconfirmed"
            )
            return False

        except Exception as e:
            logger.error(f"Failed to apply to '{job.title}' on Free-Work: {e}")
            self.last_apply_result = ApplyResult(
                success=False, application_result=f"error: {e}"
            )
            try:
                page.screenshot(path=str(settings.project_root / "logs" / f"error_freework_{job.id[:8]}.png"))
            except Exception:
                pass
            return False
        finally:
            page.close()

    def _verify_submission(self, page: Page) -> bool:
        """Check for confirmation signals after clicking 'Je postule'."""
        try:
            body = page.inner_text("body")
            body_lower = body.lower()

            # Success indicators on Free-Work
            success_signals = [
                "votre candidature a été envoyée",
                "candidature envoyée",
                "cv envoyé",
                "suivre mes candidatures",
                "envoyé",
            ]
            for signal in success_signals:
                if signal in body_lower:
                    logger.debug(f"Submission confirmed: found '{signal}'")
                    return True

            # Also check: the textarea should be gone after successful submit
            textarea = page.query_selector("#job-application-message")
            if textarea is None or not textarea.is_visible():
                logger.debug("Submission confirmed: textarea no longer visible")
                return True

        except Exception as e:
            logger.debug(f"Verification check failed: {e}")

        return False

    def _dismiss_popups(self, page: Page):
        for sel in [
            "button:has-text('Accepter')",
            "button:has-text('Tout accepter')",
            "#didomi-notice-agree-button",
            "button:has-text('Fermer')",
            "[aria-label='Close']",
        ]:
            try:
                btn = page.query_selector(sel)
                if btn and btn.is_visible():
                    btn.click()
                    human_delay(0.3, 0.8)
            except Exception:
                pass
