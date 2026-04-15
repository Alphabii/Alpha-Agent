from dataclasses import dataclass, field

import requests
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
    _cookies_injected: bool = False

    def _inject_cookies(self, context) -> bool:
        """Inject Freework auth cookies from config into the browser context.

        Returns True if cookies were injected, False if not configured.
        """
        if not settings.freework_jwt_hp or not settings.freework_jwt_s:
            return False

        cookies = [
            {
                "name": "jwt_hp",
                "value": settings.freework_jwt_hp,
                "domain": "www.free-work.com",
                "path": "/",
                "secure": True,
                "httpOnly": False,
            },
            {
                "name": "jwt_s",
                "value": settings.freework_jwt_s,
                "domain": "www.free-work.com",
                "path": "/",
                "secure": True,
                "httpOnly": True,
            },
        ]
        if settings.freework_refresh_token:
            cookies.append({
                "name": "refresh_token",
                "value": settings.freework_refresh_token,
                "domain": "www.free-work.com",
                "path": "/",
                "secure": True,
                "httpOnly": True,
            })

        context.add_cookies(cookies)
        logger.info("Injected Freework auth cookies from config")
        return True

    def _is_logged_in(self, page: Page) -> bool:
        """Check if the current page shows a logged-in state."""
        # If we see a login/signup prompt or no "Postuler" button, we're likely not logged in
        body = page.inner_text("body").lower()
        not_logged_signals = ["créer un compte", "se connecter", "trouvez votre prochaine mission"]
        for signal in not_logged_signals:
            if signal in body:
                return False
        return True

    def _auto_login(self, page) -> bool:
        """Log in to Free-Work via the REST API and inject cookies into the browser.

        Freework blocks Playwright from rendering the login form (even in
        visible mode), so we call the login API directly with requests,
        then inject the returned auth cookies into the browser context.
        """
        if not settings.freework_email or not settings.freework_password:
            logger.warning("Freework credentials not set in .env — cannot auto-login")
            return False

        try:
            logger.info("Logging in to Free-Work via API...")

            resp = requests.post(
                "https://www.free-work.com/api/login",
                json={
                    "email": settings.freework_email,
                    "password": settings.freework_password,
                },
                headers={
                    "Content-Type": "application/json",
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/131.0.0.0 Safari/537.36"
                    ),
                    "Accept": "application/json",
                    "Origin": "https://www.free-work.com",
                    "Referer": "https://www.free-work.com/fr/tech-it/login",
                },
                timeout=15,
            )

            if resp.status_code not in (200, 204):
                logger.error(f"Freework API login failed: HTTP {resp.status_code}")
                return False

            # Extract auth cookies from response
            cookies = resp.cookies
            jwt_hp = cookies.get("jwt_hp", "")
            jwt_s = cookies.get("jwt_s", "")
            refresh_token = cookies.get("refresh_token", "")

            if not jwt_hp or not jwt_s:
                logger.error("Freework API login returned no auth cookies")
                return False

            logger.info("Freework API login successful — injecting cookies into browser")

            # Inject cookies into the browser context
            ctx = browser_manager.get_context(self.platform_name)
            cookie_list = [
                {"name": "jwt_hp", "value": jwt_hp, "domain": "www.free-work.com", "path": "/", "secure": True, "httpOnly": False},
                {"name": "jwt_s", "value": jwt_s, "domain": "www.free-work.com", "path": "/", "secure": True, "httpOnly": True},
            ]
            if refresh_token:
                cookie_list.append({"name": "refresh_token", "value": refresh_token, "domain": "www.free-work.com", "path": "/", "secure": True, "httpOnly": True})

            ctx.add_cookies(cookie_list)
            self._cookies_injected = True

            # Log cookies for .env backup
            logger.info("=== Copy these to .env for cookie injection backup ===")
            logger.info(f"FREEWORK_JWT_HP={jwt_hp}")
            logger.info(f"FREEWORK_JWT_S={jwt_s}")
            if refresh_token:
                logger.info(f"FREEWORK_REFRESH_TOKEN={refresh_token}")
            logger.info("=== End of cookie values ===")

            return True

        except Exception as e:
            logger.error(f"Auto-login via API failed: {e}")
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
                logger.info("Not logged in — attempting authentication")
                page.close()
                logged_in = False

                # Try 1: inject cookies from .env config
                if not self._cookies_injected and settings.freework_jwt_hp and settings.freework_jwt_s:
                    ctx = browser_manager.get_context(self.platform_name)
                    self._inject_cookies(ctx)
                    self._cookies_injected = True
                    page = browser_manager.new_page(self.platform_name)
                    page.goto(job.url, wait_until="domcontentloaded", timeout=30000)
                    human_delay(3.0, 5.0)
                    self._dismiss_popups(page)
                    if self._is_logged_in(page):
                        logger.info("Cookie injection login successful")
                        logged_in = True
                    else:
                        logger.warning("Injected cookies expired — falling back to API login")
                        page.close()

                # Try 2: API login (get fresh cookies via HTTP)
                if not logged_in:
                    if not self._auto_login(None):
                        self.last_apply_result = ApplyResult(
                            success=False, application_result="login_failed"
                        )
                        return False
                    page = browser_manager.new_page(self.platform_name)
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
                # Maybe session expired mid-page — try API login and retry
                page.screenshot(path=str(settings.project_root / "logs" / "debug_after_postuler.png"))
                if self._auto_login(None):
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

    def _log_session_cookies(self):
        """After a successful login, log the auth cookies so the user can copy them to .env."""
        try:
            ctx = browser_manager.get_context(self.platform_name)
            cookies = ctx.cookies(["https://www.free-work.com"])
            auth_cookies = {c["name"]: c["value"] for c in cookies if c["name"] in ("jwt_hp", "jwt_s", "refresh_token")}
            if auth_cookies:
                logger.info("=== Copy these to .env for headless cookie injection ===")
                for name, value in auth_cookies.items():
                    env_key = f"FREEWORK_{name.upper()}"
                    logger.info(f"{env_key}={value}")
                logger.info("=== End of cookie values ===")
        except Exception as e:
            logger.debug(f"Could not extract session cookies: {e}")

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
