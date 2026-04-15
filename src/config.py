import json
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # AI
    gemini_api_key: str = ""
    openai_api_key: str = ""
    content_model: str = "gpt-4.1-mini"
    ai_provider: str = "openai"  # "openai", "gemini", or "vertex"

    # Vertex AI (Google Cloud)
    vertex_project_id: str = ""
    vertex_location: str = ""
    google_service_account_path: str = ""

    # WhatsApp (Twilio)
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_whatsapp_from: str = "whatsapp:+14155238886"
    whatsapp_to: str = ""

    # Freework
    freework_email: str = ""
    freework_password: str = ""
    freework_jwt_hp: str = ""
    freework_jwt_s: str = ""
    freework_refresh_token: str = ""

    # Freelancer profile
    freelancer_name: str = ""
    freelancer_first_name: str = ""
    freelancer_last_name: str = ""
    freelancer_title: str = ""
    freelancer_email: str = ""
    freelancer_phone: str = ""
    freelancer_linkedin: str = ""
    freelancer_github: str = ""
    freelancer_skills: list[str] = []
    daily_rate_min: int = 0
    preferred_locations: list[str] = []
    remote_only: bool = False
    languages: list[str] = ["French", "English"]
    search_queries: list[str] = []

    # Resumes
    resume_fr: str = ""
    resume_en: str = ""

    # Database
    sqlite_cloud_url: str = ""

    # Scanning
    scan_interval_minutes: int = 30
    relevance_threshold: int = 70

    # Paths
    project_root: Path = Path(__file__).parent.parent
    db_path: Path = Path(__file__).parent.parent / "data" / "jobs.db"
    profiles_dir: Path = Path(__file__).parent.parent / "profiles"
    profile_file: Path = Path(__file__).parent.parent / "profile.md"

    @field_validator("freelancer_skills", "preferred_locations", "languages", "search_queries", mode="before")
    @classmethod
    def parse_json_list(cls, v):
        if isinstance(v, str):
            return json.loads(v)
        return v

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }

    def get_profile_text(self) -> str:
        """Read the user's profile.md for AI context."""
        if self.profile_file.exists():
            return self.profile_file.read_text(encoding="utf-8")
        return ""

    def get_resume_path(self, language: str = "fr") -> Path | None:
        """Get the resume PDF path for a given language."""
        path_str = self.resume_fr if language == "fr" else self.resume_en
        if path_str:
            p = Path(path_str)
            if p.exists():
                return p
        return None


settings = Settings()
