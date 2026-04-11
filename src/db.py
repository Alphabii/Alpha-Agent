import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from src.config import settings
from src.models import ApplicationRecord, JobRecord, ScanStats, ScrapedJob


SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    platform TEXT NOT NULL,
    external_id TEXT NOT NULL,
    title TEXT NOT NULL,
    company TEXT DEFAULT '',
    description TEXT DEFAULT '',
    location TEXT DEFAULT '',
    remote BOOLEAN DEFAULT 0,
    daily_rate_min INTEGER DEFAULT 0,
    daily_rate_max INTEGER DEFAULT 0,
    skills TEXT DEFAULT '[]',
    url TEXT NOT NULL,
    language TEXT DEFAULT 'fr',
    posted_at TEXT DEFAULT '',
    discovered_at TEXT NOT NULL,
    relevance_score INTEGER DEFAULT 0,
    relevance_reason TEXT DEFAULT '',
    contract_type TEXT DEFAULT '',
    duration TEXT DEFAULT '',
    status TEXT DEFAULT 'new',
    matching_skills TEXT DEFAULT '[]',
    concerns TEXT DEFAULT '[]',
    UNIQUE(platform, external_id)
);

CREATE TABLE IF NOT EXISTS applications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT NOT NULL REFERENCES jobs(id),
    cover_letter TEXT DEFAULT '',
    proposal_message TEXT DEFAULT '',
    generated_at TEXT NOT NULL,
    submitted_at TEXT DEFAULT '',
    submission_status TEXT DEFAULT 'draft',
    error_message TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS scan_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    platform TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT DEFAULT '',
    jobs_found INTEGER DEFAULT 0,
    new_jobs INTEGER DEFAULT 0,
    status TEXT DEFAULT 'running'
);
"""


@contextmanager
def get_db():
    """Get a database connection with WAL mode."""
    settings.db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(settings.db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    """Create tables if they don't exist."""
    with get_db() as conn:
        conn.executescript(SCHEMA)


def save_job(job: ScrapedJob) -> bool:
    """Save a scraped job. Returns True if it was new (inserted)."""
    record = JobRecord.from_scraped(job)
    with get_db() as conn:
        cursor = conn.execute(
            """INSERT OR IGNORE INTO jobs
            (id, platform, external_id, title, company, description, location,
             remote, daily_rate_min, daily_rate_max, skills, url, language,
             posted_at, discovered_at, relevance_score, relevance_reason,
             contract_type, duration, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                record.id,
                record.platform,
                record.external_id,
                record.title,
                record.company,
                record.description,
                record.location,
                record.remote,
                record.daily_rate_min,
                record.daily_rate_max,
                json.dumps(record.skills),
                record.url,
                record.language,
                record.posted_at,
                record.discovered_at,
                record.relevance_score,
                record.relevance_reason,
                record.contract_type,
                record.duration,
                record.status,
            ),
        )
        return cursor.rowcount > 0


def get_jobs(
    status: str | None = None, platform: str | None = None, limit: int = 50
) -> list[JobRecord]:
    """Get jobs filtered by status and/or platform."""
    query = "SELECT * FROM jobs WHERE 1=1"
    params: list = []
    if status:
        query += " AND status = ?"
        params.append(status)
    if platform:
        query += " AND platform = ?"
        params.append(platform)
    query += " ORDER BY discovered_at DESC LIMIT ?"
    params.append(limit)

    with get_db() as conn:
        rows = conn.execute(query, params).fetchall()
        return [_row_to_job(row) for row in rows]


def get_job(job_id: str) -> JobRecord | None:
    """Get a single job by ID."""
    with get_db() as conn:
        row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return _row_to_job(row) if row else None


def update_job_status(job_id: str, status: str):
    """Update a job's status."""
    with get_db() as conn:
        conn.execute("UPDATE jobs SET status = ? WHERE id = ?", (status, job_id))


def update_job_relevance(
    job_id: str,
    score: int,
    reason: str,
    matching_skills: list[str] | None = None,
    concerns: list[str] | None = None,
):
    """Update a job's relevance score, reason, matching skills, and concerns."""
    with get_db() as conn:
        conn.execute(
            """UPDATE jobs SET relevance_score = ?, relevance_reason = ?,
               matching_skills = ?, concerns = ? WHERE id = ?""",
            (
                score,
                reason,
                json.dumps(matching_skills or []),
                json.dumps(concerns or []),
                job_id,
            ),
        )


def save_application(app: ApplicationRecord) -> int:
    """Save an application record. Returns the application ID."""
    with get_db() as conn:
        cursor = conn.execute(
            """INSERT INTO applications
            (job_id, cover_letter, proposal_message, generated_at,
             submitted_at, submission_status, error_message)
            VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                app.job_id,
                app.cover_letter,
                app.proposal_message,
                app.generated_at,
                app.submitted_at,
                app.submission_status,
                app.error_message,
            ),
        )
        return cursor.lastrowid


def update_application_status(
    app_id: int, status: str, submitted_at: str = "", error: str = ""
):
    """Update an application's submission status."""
    with get_db() as conn:
        conn.execute(
            """UPDATE applications
            SET submission_status = ?, submitted_at = ?, error_message = ?
            WHERE id = ?""",
            (status, submitted_at, error, app_id),
        )


def get_application_for_job(job_id: str) -> ApplicationRecord | None:
    """Get the latest application for a job."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM applications WHERE job_id = ? ORDER BY id DESC LIMIT 1",
            (job_id,),
        ).fetchone()
        if not row:
            return None
        return ApplicationRecord(
            id=row["id"],
            job_id=row["job_id"],
            cover_letter=row["cover_letter"],
            proposal_message=row["proposal_message"],
            generated_at=row["generated_at"],
            submitted_at=row["submitted_at"],
            submission_status=row["submission_status"],
            error_message=row["error_message"],
        )


def log_scan_start(platform: str, started_at: str) -> int:
    """Log the start of a scan. Returns log ID."""
    with get_db() as conn:
        cursor = conn.execute(
            "INSERT INTO scan_log (platform, started_at) VALUES (?, ?)",
            (platform, started_at),
        )
        return cursor.lastrowid


def log_scan_finish(
    log_id: int, finished_at: str, jobs_found: int, new_jobs: int, status: str = "done"
):
    """Log the completion of a scan."""
    with get_db() as conn:
        conn.execute(
            """UPDATE scan_log
            SET finished_at = ?, jobs_found = ?, new_jobs = ?, status = ?
            WHERE id = ?""",
            (finished_at, jobs_found, new_jobs, status, log_id),
        )


def get_stats() -> ScanStats:
    """Get summary statistics."""
    with get_db() as conn:
        jobs = conn.execute(
            """SELECT
                COUNT(*) as total,
                SUM(CASE WHEN status = 'new' THEN 1 ELSE 0 END) as new_count,
                SUM(CASE WHEN status = 'applied' THEN 1 ELSE 0 END) as applied_count,
                SUM(CASE WHEN status = 'skipped' THEN 1 ELSE 0 END) as skipped_count,
                SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed_count
            FROM jobs"""
        ).fetchone()

        apps = conn.execute(
            """SELECT
                COUNT(*) as total,
                SUM(CASE WHEN submission_status = 'submitted' THEN 1 ELSE 0 END) as submitted
            FROM applications"""
        ).fetchone()

        return ScanStats(
            total_jobs=jobs["total"],
            new_jobs=jobs["new_count"] or 0,
            applied_jobs=jobs["applied_count"] or 0,
            skipped_jobs=jobs["skipped_count"] or 0,
            failed_jobs=jobs["failed_count"] or 0,
            total_applications=apps["total"],
            submitted_applications=apps["submitted"] or 0,
        )


def get_chart_data() -> dict:
    """Get aggregated data for dashboard charts."""
    contract_map = {
        "contractor": "Freelance", "permanent": "CDI", "fixed_term": "CDD",
        "internship": "Stage", "apprenticeship": "Alternance",
    }
    with get_db() as conn:
        jobs_status = {r["status"]: r["cnt"] for r in conn.execute(
            "SELECT status, COUNT(*) as cnt FROM jobs WHERE status != 'new' GROUP BY status"
        ).fetchall()}

        score_dist = {}
        for label, lo, hi in [("0-29", 0, 29), ("30-49", 30, 49), ("50-69", 50, 69), ("70-84", 70, 84), ("85-100", 85, 100)]:
            score_dist[label] = conn.execute(
                "SELECT COUNT(*) FROM jobs WHERE relevance_score BETWEEN ? AND ?", (lo, hi)
            ).fetchone()[0]

        apps_status = {r["submission_status"]: r["cnt"] for r in conn.execute(
            "SELECT submission_status, COUNT(*) as cnt FROM applications GROUP BY submission_status"
        ).fetchall()}

        skill_counts: dict[str, int] = {}
        for row in conn.execute("SELECT skills FROM jobs").fetchall():
            for skill in json.loads(row["skills"]):
                skill_counts[skill] = skill_counts.get(skill, 0) + 1
        top_skills = dict(sorted(skill_counts.items(), key=lambda x: x[1], reverse=True)[:10])

        contract_types: dict[str, int] = {}
        for r in conn.execute("SELECT contract_type, COUNT(*) as cnt FROM jobs GROUP BY contract_type").fetchall():
            raw = r["contract_type"] or "unknown"
            parts = [p.strip() for p in raw.split(",")]
            for part in parts:
                display = contract_map.get(part, part.capitalize() if part else "Unknown")
                contract_types[display] = contract_types.get(display, 0) + r["cnt"]

        remote: dict[str, int] = {}
        for r in conn.execute("SELECT remote, COUNT(*) as cnt FROM jobs GROUP BY remote").fetchall():
            remote["Remote" if r["remote"] else "On-site"] = r["cnt"]

        return {
            "jobs_by_status": jobs_status,
            "score_distribution": score_dist,
            "apps_by_status": apps_status,
            "top_skills": top_skills,
            "contract_types": contract_types,
            "remote": remote,
        }


def _row_to_job(row: sqlite3.Row) -> JobRecord:
    """Convert a database row to a JobRecord."""
    return JobRecord(
        id=row["id"],
        platform=row["platform"],
        external_id=row["external_id"],
        title=row["title"],
        company=row["company"],
        description=row["description"],
        location=row["location"],
        remote=bool(row["remote"]),
        daily_rate_min=row["daily_rate_min"],
        daily_rate_max=row["daily_rate_max"],
        skills=json.loads(row["skills"]),
        url=row["url"],
        language=row["language"],
        posted_at=row["posted_at"],
        discovered_at=row["discovered_at"],
        relevance_score=row["relevance_score"],
        relevance_reason=row["relevance_reason"],
        contract_type=row["contract_type"] or "",
        duration=row["duration"] or "",
        status=row["status"],
    )
