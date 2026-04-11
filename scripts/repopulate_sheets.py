"""One-off script to repopulate Google Sheets from the SQLite database.

Use after clearing the sheets to restore them from the authoritative DB.
"""
import json
import sqlite3
from pathlib import Path

from src.config import settings
from src.sheets import track_application, track_job_found


def repopulate():
    conn = sqlite3.connect(str(settings.db_path))
    conn.row_factory = sqlite3.Row

    # --- Job Offers Found sheet ---
    jobs = conn.execute(
        "SELECT * FROM jobs ORDER BY discovered_at ASC"
    ).fetchall()
    print(f"Repopulating 'Job Offers Found' with {len(jobs)} jobs...")

    for job in jobs:
        skills = json.loads(job["skills"]) if job["skills"] else []
        matching_skills = json.loads(job["matching_skills"]) if job["matching_skills"] else []
        concerns = json.loads(job["concerns"]) if job["concerns"] else []
        status = "qualified" if job["relevance_score"] >= settings.relevance_threshold else "skipped"
        if job["status"] == "applied":
            status = "qualified"

        track_job_found(
            date=job["discovered_at"],
            platform=job["platform"],
            title=job["title"],
            company=job["company"],
            location=job["location"],
            remote=bool(job["remote"]),
            contract_type=job["contract_type"] or "contractor",
            duration=job["duration"] or "",
            daily_rate_min=job["daily_rate_min"],
            daily_rate_max=job["daily_rate_max"],
            skills=skills,
            score=job["relevance_score"],
            reasoning=job["relevance_reason"],
            matching_skills=matching_skills,
            concerns=concerns,
            status=status,
            language=job["language"],
            url=job["url"],
        )

    # --- Free-Work applications sheet ---
    apps = conn.execute(
        """SELECT a.*, j.platform, j.title, j.company, j.location, j.remote,
                  j.daily_rate_min, j.daily_rate_max, j.relevance_score, j.url
           FROM applications a
           JOIN jobs j ON a.job_id = j.id
           ORDER BY a.generated_at ASC"""
    ).fetchall()
    print(f"Repopulating 'Free-Work' with {len(apps)} applications...")

    for app in apps:
        status_map = {
            "submitted": "submitted",
            "failed": "failed",
            "draft": "draft",
        }
        status = status_map.get(app["submission_status"], app["submission_status"])
        track_application(
            date=app["submitted_at"] or app["generated_at"],
            platform=app["platform"],
            title=app["title"],
            company=app["company"],
            location=app["location"],
            remote=bool(app["remote"]),
            daily_rate_min=app["daily_rate_min"],
            daily_rate_max=app["daily_rate_max"],
            score=app["relevance_score"],
            status=status,
            application_result=app["error_message"] or ("submitted" if status == "submitted" else ""),
            external_url="",
            url=app["url"],
            proposal=app["proposal_message"],
        )

    conn.close()
    print("Done.")


if __name__ == "__main__":
    repopulate()
