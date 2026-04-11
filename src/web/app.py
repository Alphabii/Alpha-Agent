import html
import json
import re
import threading
from datetime import datetime, timezone
from pathlib import Path

from flask import Flask, jsonify, render_template, request, redirect, url_for, flash
from markupsafe import Markup, escape
from loguru import logger

from src.config import settings
from src.db import (
    get_jobs,
    get_job,
    get_stats,
    get_chart_data,
    get_application_for_job,
    init_db,
    update_job_status,
)

app = Flask(
    __name__,
    template_folder=str(Path(__file__).parent / "templates"),
    static_folder=str(Path(__file__).parent / "static"),
)
app.secret_key = "job-agent-secret-key"


@app.template_filter("format_profile")
def format_profile(text):
    """Format profile.md markdown into a polished CV-style HTML layout."""
    if not text:
        return ""
    lines = text.strip().split("\n")
    html_parts = []
    in_list = False

    for line in lines:
        stripped = line.strip()
        if not stripped:
            if in_list:
                html_parts.append("</ul>")
                in_list = False
            continue

        # H1 — name/title header
        m = re.match(r'^# (.+)$', stripped)
        if m:
            if in_list:
                html_parts.append("</ul>")
                in_list = False
            parts = m.group(1).split(" — ", 1)
            name = str(escape(parts[0]))
            title = str(escape(parts[1])) if len(parts) > 1 else ""
            html_parts.append(f'<div class="profile-header"><h2 class="profile-name">{name}</h2>')
            if title:
                html_parts.append(f'<div class="profile-title">{title}</div>')
            html_parts.append("</div>")
            continue

        # H2 — section header
        m = re.match(r'^## (.+)$', stripped)
        if m:
            if in_list:
                html_parts.append("</ul>")
                in_list = False
            heading = str(escape(m.group(1)))
            html_parts.append(f'<div class="profile-section"><h3 class="profile-section-title">{heading}</h3>')
            html_parts.append("</div>")
            continue

        # H3 — subsection (job title)
        m = re.match(r'^### (.+)$', stripped)
        if m:
            if in_list:
                html_parts.append("</ul>")
                in_list = False
            content = m.group(1)
            # Split "Role — Company, Location (Dates)"
            parts = content.split(" — ", 1)
            role = str(escape(parts[0]))
            detail = str(escape(parts[1])) if len(parts) > 1 else ""
            html_parts.append(f'<div class="profile-job"><span class="profile-role">{role}</span>')
            if detail:
                html_parts.append(f'<span class="profile-detail">{detail}</span>')
            html_parts.append("</div>")
            continue

        # List item
        m = re.match(r'^- (.+)$', stripped)
        if m:
            if not in_list:
                html_parts.append('<ul class="profile-list">')
                in_list = True
            item = str(escape(m.group(1)))
            # Highlight "Tech:" prefix
            item = re.sub(r'^(Tech:)', r'<span class="profile-tech-label">\1</span>', item)
            html_parts.append(f"<li>{item}</li>")
            continue

        # Plain text paragraph
        if in_list:
            html_parts.append("</ul>")
            in_list = False
        html_parts.append(f"<p>{str(escape(stripped))}</p>")

    if in_list:
        html_parts.append("</ul>")

    return Markup("\n".join(html_parts))


@app.template_filter("format_description")
def format_description(text):
    """Format plain-text job descriptions into readable HTML."""
    if not text:
        return ""
    # 1. Decode HTML entities (&#039; -> ', &amp; -> &, etc.)
    text = html.unescape(text)
    # 2. Escape for XSS safety
    text = str(escape(text))
    # 3. Line breaks before ALL-CAPS headers (3+ uppercase words)
    text = re.sub(
        r'\s*(?=(?:MISSIONS?|R[EÉ]SULTATS?|PR[EÉ]-REQUIS|CONDITIONS|CALENDRIER|COMP[EÉ]TENCES?|'
        r'PROFIL|CONTEXTE|LIVRABLES?|ENVIRONNEMENT|DESCRIPTION|RESPONSABILIT[EÉ]S?|'
        r'R[EÉ]ALISATIONS?|ATTENDUS?|TECHNIQUES?|PRESTATION|AVANTAGES))',
        r'<br><br><strong>\g<0></strong>', text,
    )
    # 4. Line breaks before numbered sections (1/, 2/, 1., 2.)
    text = re.sub(r'\s*(?=\d+[/.)]\s)', '<br><br>', text)
    # 5. Line breaks before list items (- or •)
    text = re.sub(r'\s*([-•])\s+', r'<br>&bull; ', text)
    # 6. Clean up multiple breaks
    text = re.sub(r'(<br>\s*){3,}', '<br><br>', text)
    text = text.strip().lstrip('<br>')
    return Markup(text)

# Global scanner reference
_scanner = None
_scanner_thread = None


def get_scanner():
    return _scanner


# ── Pages ─────────────────────────────────────────────────────────────────

@app.route("/")
def dashboard():
    """Main dashboard with stats and recent activity."""
    stats = get_stats()
    recent_jobs = get_jobs(limit=10)
    return render_template("dashboard.html", stats=stats, recent_jobs=recent_jobs)


@app.route("/jobs")
def jobs_list():
    """Job listings with filtering."""
    status_filter = request.args.get("status", "")
    platform_filter = request.args.get("platform", "")
    page = int(request.args.get("page", 1))
    per_page = 20

    jobs = get_jobs(
        status=status_filter or None,
        platform=platform_filter or None,
        limit=per_page * page,
    )

    # Simple pagination
    start = (page - 1) * per_page
    paginated = jobs[start : start + per_page]
    has_more = len(jobs) > start + per_page

    return render_template(
        "jobs.html",
        jobs=paginated,
        status_filter=status_filter,
        platform_filter=platform_filter,
        page=page,
        has_more=has_more,
    )


@app.route("/jobs/<job_id>")
def job_detail(job_id):
    """Job detail with application content."""
    job = get_job(job_id)
    if not job:
        flash("Job not found", "error")
        return redirect(url_for("jobs_list"))

    application = get_application_for_job(job_id)
    return render_template("job_detail.html", job=job, application=application)


@app.route("/settings", methods=["GET"])
def settings_page():
    """Profile page: current configuration summary + read-only CV."""
    profile_text = settings.get_profile_text()
    return render_template("settings.html", settings=settings, profile_text=profile_text)


# ── API Endpoints ─────────────────────────────────────────────────────────

@app.route("/api/charts")
def api_charts():
    """Get aggregated chart data for the dashboard."""
    return jsonify(get_chart_data())


@app.route("/api/stats")
def api_stats():
    """Get current stats as JSON."""
    stats = get_stats()
    scanner = get_scanner()
    return jsonify({
        "stats": stats.model_dump(),
        "scanner": {
            "running": scanner is not None and not scanner.is_paused if scanner else False,
            "paused": scanner.is_paused if scanner else False,
        },
    })


@app.route("/api/scanner/start", methods=["POST"])
def api_scanner_start():
    """Start or resume the scanner."""
    global _scanner, _scanner_thread

    if _scanner and _scanner.is_paused:
        _scanner.resume()
        return jsonify({"status": "resumed"})

    if _scanner_thread and _scanner_thread.is_alive():
        return jsonify({"status": "already_running"})

    # Start fresh scanner
    from src.pipeline import Pipeline
    import src.scrapers  # noqa: F401
    import src.applicator  # noqa: F401
    from src.scheduler.runner import Scanner

    pipeline = Pipeline()
    _scanner = Scanner(pipeline)

    _scanner_thread = threading.Thread(
        target=_scanner.run_forever,
        args=(settings.scan_interval_minutes,),
        daemon=True,
    )
    _scanner_thread.start()
    logger.info("Scanner started from web UI")
    return jsonify({"status": "started"})


@app.route("/api/scanner/pause", methods=["POST"])
def api_scanner_pause():
    """Pause the scanner."""
    if _scanner:
        _scanner.pause()
        return jsonify({"status": "paused"})
    return jsonify({"status": "not_running"})


@app.route("/api/scanner/scan", methods=["POST"])
def api_scanner_scan_now():
    """Run a single scan cycle immediately."""
    def run_scan():
        from src.pipeline import Pipeline
        import src.scrapers  # noqa: F401
        import src.applicator  # noqa: F401

        pipeline = Pipeline()
        results = pipeline.run_cycle()
        logger.info(f"Manual scan: {results['new_jobs']} new, {results['applied']} applied")

    thread = threading.Thread(target=run_scan, daemon=True)
    thread.start()
    return jsonify({"status": "scan_started"})


@app.route("/api/jobs/<job_id>/status", methods=["POST"])
def api_update_job_status(job_id):
    """Update a job's status (skip, approve, etc.)."""
    data = request.get_json()
    new_status = data.get("status")
    if new_status not in ("new", "applied", "skipped", "failed"):
        return jsonify({"error": "Invalid status"}), 400

    update_job_status(job_id, new_status)
    return jsonify({"status": "updated", "new_status": new_status})


@app.route("/api/profile", methods=["POST"])
def api_save_profile():
    """Save the profile.md content."""
    data = request.get_json()
    content = data.get("content", "")
    profile_path = settings.project_root / "profile.md"
    profile_path.write_text(content, encoding="utf-8")
    return jsonify({"status": "saved"})


@app.route("/api/env", methods=["POST"])
def api_save_env():
    """Save .env file content."""
    data = request.get_json()
    content = data.get("content", "")
    env_path = settings.project_root / ".env"
    env_path.write_text(content, encoding="utf-8")
    return jsonify({"status": "saved", "message": "Restart the app to apply changes."})


# ── Platform Login ────────────────────────────────────────────────────────

PLATFORM_URLS = {
    "freework": {"name": "Free-Work", "login_url": "https://www.free-work.com/fr/tech-it/login"},
}

# Track active login sessions
_login_sessions: dict[str, dict] = {}


@app.route("/api/platforms/status")
def api_platforms_status():
    """Get login status for all platforms."""
    statuses = {}
    for key, info in PLATFORM_URLS.items():
        profile_dir = settings.profiles_dir / key
        has_session = profile_dir.exists() and any(profile_dir.iterdir()) if profile_dir.exists() else False
        is_logging_in = key in _login_sessions
        statuses[key] = {
            "name": info["name"],
            "logged_in": has_session,
            "logging_in": is_logging_in,
        }
    return jsonify(statuses)


@app.route("/api/platforms/<platform>/login", methods=["POST"])
def api_platform_login(platform):
    """Open a browser window for the user to log in to a platform."""
    if platform not in PLATFORM_URLS:
        return jsonify({"error": "Unknown platform"}), 400

    if platform in _login_sessions:
        return jsonify({"status": "already_logging_in"})

    def open_login_browser():
        from src.utils.browser import BrowserManager
        try:
            manager = BrowserManager()
            manager.start()
            page = manager.get_context(platform, headless=False).new_page()
            page.goto(PLATFORM_URLS[platform]["login_url"])

            _login_sessions[platform] = {
                "manager": manager,
                "page": page,
                "started_at": datetime.now(timezone.utc).isoformat(),
            }
            logger.info(f"Login browser opened for {platform}")
        except Exception as e:
            logger.error(f"Failed to open login browser for {platform}: {e}")
            _login_sessions.pop(platform, None)

    thread = threading.Thread(target=open_login_browser, daemon=True)
    thread.start()
    return jsonify({"status": "browser_opening"})


@app.route("/api/platforms/<platform>/login/done", methods=["POST"])
def api_platform_login_done(platform):
    """Confirm login is complete — close browser and save session."""
    if platform not in _login_sessions:
        return jsonify({"error": "No active login session"}), 400

    session = _login_sessions.pop(platform)
    try:
        page = session["page"]
        manager = session["manager"]
        page.close()
        manager.stop()
        logger.info(f"Login session saved for {platform}")
        return jsonify({"status": "saved"})
    except Exception as e:
        logger.error(f"Error closing login session for {platform}: {e}")
        return jsonify({"status": "saved_with_warning", "warning": str(e)})


@app.route("/api/platforms/<platform>/login/cancel", methods=["POST"])
def api_platform_login_cancel(platform):
    """Cancel an active login session."""
    if platform not in _login_sessions:
        return jsonify({"error": "No active login session"}), 400

    session = _login_sessions.pop(platform)
    try:
        session["page"].close()
        session["manager"].stop()
    except Exception:
        pass
    return jsonify({"status": "cancelled"})


# ── Launch ────────────────────────────────────────────────────────────────

def start_web(host: str = "127.0.0.1", port: int = 5050, debug: bool = False):
    """Start the web application."""
    init_db()
    logger.info(f"Web dashboard starting at http://{host}:{port}")
    app.run(host=host, port=port, debug=debug)
