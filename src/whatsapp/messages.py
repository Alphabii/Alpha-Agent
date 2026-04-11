from src.models import JobRecord, ScanStats


def format_job_applied(job: JobRecord) -> str:
    """Format a notification for a submitted application."""
    rate = ""
    if job.daily_rate_min or job.daily_rate_max:
        rate = f"\n💰 €{job.daily_rate_min}-{job.daily_rate_max}/j"

    location = f"\n📍 {job.location}" if job.location else ""
    remote = " (Remote)" if job.remote else ""
    skills = f"\n🛠 {', '.join(job.skills[:5])}" if job.skills else ""

    return (
        f"✅ *Application Submitted*\n\n"
        f"*{job.title}*\n"
        f"🏢 {job.company or 'N/A'}"
        f"{location}{remote}"
        f"{rate}"
        f"{skills}\n\n"
        f"🔗 {job.url}"
    )


def format_job_skipped(job: JobRecord, score: int, reason: str) -> str:
    """Format a notification for a skipped job."""
    return (
        f"⏭ *Job Skipped* (score: {score}/100)\n\n"
        f"*{job.title}*\n"
        f"🏢 {job.company or 'N/A'}\n"
        f"📝 {reason}"
    )


def format_status(stats: ScanStats) -> str:
    """Format a status summary."""
    return (
        f"📊 *Agent Status*\n\n"
        f"Jobs: {stats.total_jobs} total\n"
        f"  • New: {stats.new_jobs}\n"
        f"  • Applied: {stats.applied_jobs}\n"
        f"  • Skipped: {stats.skipped_jobs}\n"
        f"  • Failed: {stats.failed_jobs}\n\n"
        f"Applications: {stats.total_applications} total\n"
        f"  • Submitted: {stats.submitted_applications}"
    )


def format_help() -> str:
    """Format the help message."""
    return (
        "🤖 *Job Agent Commands*\n\n"
        "• *status* — Show stats\n"
        "• *start* — Resume scanning\n"
        "• *stop* / *pause* — Pause scanning\n"
        "• *summary* — Daily summary\n"
        "• *help* — Show this message"
    )
