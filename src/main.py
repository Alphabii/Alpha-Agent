import typer
from loguru import logger

from src.db import get_stats, init_db
from src.config import settings

app = typer.Typer(name="job-agent", help="AI-powered freelance job application agent")


@app.command()
def status():
    """Show database stats and current configuration."""
    init_db()
    stats = get_stats()

    typer.echo("=== Job Agent Status ===\n")
    typer.echo(f"Jobs:         {stats.total_jobs} total")
    typer.echo(f"  New:        {stats.new_jobs}")
    typer.echo(f"  Applied:    {stats.applied_jobs}")
    typer.echo(f"  Skipped:    {stats.skipped_jobs}")
    typer.echo(f"  Failed:     {stats.failed_jobs}")
    typer.echo(f"\nApplications: {stats.total_applications} total")
    typer.echo(f"  Submitted:  {stats.submitted_applications}")
    typer.echo(f"\nConfig:")
    typer.echo(f"  Name:       {settings.freelancer_name}")
    typer.echo(f"  Skills:     {', '.join(settings.freelancer_skills)}")
    typer.echo(f"  Rate:       €{settings.daily_rate_min}+/day")
    typer.echo(f"  Locations:  {', '.join(settings.preferred_locations)}")
    typer.echo(f"  Interval:   {settings.scan_interval_minutes} min")
    typer.echo(f"  Threshold:  {settings.relevance_threshold}/100")


@app.command()
def scan(
    platform: str = typer.Option(
        None, "--platform", "-p", help="Scan a specific platform only"
    ),
    query: str = typer.Option(None, "--query", "-q", help="Search keywords"),
    contracts: str = typer.Option(
        None, "--contracts", "-c",
        help="Contract type(s), comma-separated: freelance,cdi,cdd"
    ),
    freshness: str = typer.Option(
        None, "--freshness", "-f",
        help="Publication date filter: 24h, 7d, 14d, 30d"
    ),
    remote: str = typer.Option(
        None, "--remote", "-r",
        help="Remote filter: full, partial, no"
    ),
    location: str = typer.Option(
        None, "--location", "-l", help="Location filter"
    ),
    max_pages: int = typer.Option(
        3, "--max-pages", help="Max pages to scrape per query"
    ),
):
    """Run a single scan cycle across all (or one) platform(s)."""
    init_db()
    from src.pipeline import Pipeline
    import src.scrapers  # noqa: F401 — register scrapers
    import src.applicator  # noqa: F401 — register applicators

    # Build filters from CLI options
    filters = {
        "skills": settings.freelancer_skills,
        "location": settings.preferred_locations,
        "remote": settings.remote_only,
        "min_rate": settings.daily_rate_min,
        "max_pages": max_pages,
    }
    if query:
        filters["query"] = query
    filters["contracts"] = [c.strip() for c in contracts.split(",")] if contracts else ["freelance"]
    if freshness:
        filters["freshness"] = freshness
    if remote:
        filters["remote"] = remote
    if location:
        filters["location"] = location

    pipeline = Pipeline()
    platforms = [platform] if platform else None
    results = pipeline.run_cycle(platforms=platforms, filters=filters)
    typer.echo(f"\nScan complete: {results['new_jobs']} new jobs, {results['applied']} applications submitted")


@app.command()
def watch():
    """Continuously scan platforms on an interval."""
    init_db()
    from src.scheduler.runner import Scanner
    from src.pipeline import Pipeline
    import src.scrapers  # noqa: F401
    import src.applicator  # noqa: F401

    pipeline = Pipeline()
    scanner = Scanner(pipeline)

    typer.echo(f"Watching for jobs every {settings.scan_interval_minutes} min. Press Ctrl+C to stop.")
    try:
        scanner.run_forever(settings.scan_interval_minutes)
    except KeyboardInterrupt:
        typer.echo("\nStopped.")


@app.command()
def start():
    """Run scanner + WhatsApp bot together."""
    init_db()
    import threading
    from src.scheduler.runner import Scanner
    from src.pipeline import Pipeline
    import src.scrapers  # noqa: F401
    import src.applicator  # noqa: F401

    pipeline = Pipeline()
    scanner = Scanner(pipeline)

    # Start scanner in background thread
    scan_thread = threading.Thread(
        target=scanner.run_forever,
        args=(settings.scan_interval_minutes,),
        daemon=True,
    )
    scan_thread.start()
    logger.info("Scanner started in background thread")

    # Start WhatsApp bot in main thread
    try:
        from src.whatsapp.bot import start_bot
        start_bot(scanner)
    except KeyboardInterrupt:
        typer.echo("\nStopped.")


@app.command()
def web(
    port: int = typer.Option(5050, "--port", "-p", help="Port to run on"),
    debug: bool = typer.Option(False, "--debug", help="Enable debug mode"),
):
    """Launch the web dashboard."""
    init_db()
    from src.web.app import start_web
    start_web(port=port, debug=debug)


@app.command()
def dashboard():
    """Generate the Dashboard sheet in Google Sheets."""
    from src.sheets import build_dashboard
    typer.echo("Building dashboard...")
    build_dashboard()
    typer.echo("Dashboard built successfully.")


@app.command()
def login(
    platform: str = typer.Argument(help="Platform to login to: freework, collective, hellowork, linkedin"),
):
    """Interactively login to a platform to save the browser session."""
    from src.utils.browser import browser_manager

    typer.echo(f"Opening {platform} login page. Please log in manually...")
    typer.echo("Press Enter in this terminal when done.\n")

    browser_manager.start()
    page = browser_manager.new_page(platform, headless=False)

    urls = {
        "freework": "https://www.free-work.com/fr/tech-it/login",
        "collective": "https://app.collective.work/login",
        "hellowork": "https://www.hellowork.com/mon-compte/connexion",
        "linkedin": "https://www.linkedin.com/login",
    }

    url = urls.get(platform)
    if not url:
        typer.echo(f"Unknown platform: {platform}")
        raise typer.Exit(1)

    page.goto(url)
    typer.echo("Log in, then close the browser window when done.")
    page.pause()  # Opens Playwright inspector — keeps browser alive
    page.close()
    browser_manager.stop()
    typer.echo(f"Session saved for {platform}.")


@app.command()
def extract_cookies(
    platform: str = typer.Argument(default="freework", help="Platform to extract cookies from"),
):
    """Extract auth cookies from a saved browser session for .env injection."""
    from src.utils.browser import browser_manager

    browser_manager.start()
    ctx = browser_manager.get_context(platform, headless=True)

    cookie_names = {
        "freework": ["jwt_hp", "jwt_s", "refresh_token"],
    }
    target_cookies = cookie_names.get(platform, [])
    urls = {"freework": "https://www.free-work.com"}
    all_cookies = ctx.cookies([urls.get(platform, "")])

    typer.echo(f"\n=== {platform} auth cookies ===")
    found = False
    for c in all_cookies:
        if c["name"] in target_cookies:
            env_key = f"{platform.upper()}_{c['name'].upper()}"
            typer.echo(f"{env_key}={c['value']}")
            found = True

    if not found:
        typer.echo("No auth cookies found. Run 'login' first to create a session.")
    else:
        typer.echo("\nCopy the values above into your .env file.")

    browser_manager.stop()


if __name__ == "__main__":
    app()
