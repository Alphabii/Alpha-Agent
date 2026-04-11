import json

from loguru import logger

from src.ai.prompts import RELEVANCE_SCORING_SYSTEM, RELEVANCE_SCORING_USER
from src.config import settings
from src.models import JobRecord, RelevanceResult
from src.utils.retry import retry


def _init_vertex():
    import vertexai
    from google.oauth2 import service_account

    credentials = service_account.Credentials.from_service_account_file(
        settings.google_service_account_path
    )
    vertexai.init(
        project=settings.vertex_project_id,
        location=settings.vertex_location,
        credentials=credentials,
    )


def _create_client():
    if settings.ai_provider == "openai":
        from openai import OpenAI
        return OpenAI(api_key=settings.openai_api_key)
    elif settings.ai_provider == "vertex":
        _init_vertex()
        from vertexai.generative_models import GenerativeModel
        return GenerativeModel(
            model_name=settings.content_model,
            system_instruction=RELEVANCE_SCORING_SYSTEM,
        )
    else:
        import google.generativeai as genai
        genai.configure(api_key=settings.gemini_api_key)
        return genai.GenerativeModel(
            model_name=settings.content_model,
            system_instruction=RELEVANCE_SCORING_SYSTEM,
        )


class JobAnalyzer:
    """Scores job relevance using LLM."""

    def __init__(self):
        self._client = _create_client()
        self._profile = settings.get_profile_text()

    @retry(max_attempts=2)
    def score_relevance(self, job: JobRecord) -> RelevanceResult:
        user_prompt = RELEVANCE_SCORING_USER.format(
            profile=self._profile,
            title=job.title,
            company=job.company,
            location=job.location,
            remote="Yes" if job.remote else "No",
            rate_min=job.daily_rate_min,
            rate_max=job.daily_rate_max,
            skills=", ".join(job.skills),
            description=job.description[:3000],
        )

        if settings.ai_provider == "openai":
            response = self._client.chat.completions.create(
                model=settings.content_model,
                messages=[
                    {"role": "system", "content": RELEVANCE_SCORING_SYSTEM},
                    {"role": "user", "content": user_prompt},
                ],
            )
            text = response.choices[0].message.content.strip()
        else:
            # Works for both "gemini" and "vertex" providers
            response = self._client.generate_content(user_prompt)
            text = response.text.strip()

        # Extract JSON from response (handle markdown code blocks)
        if "```" in text:
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
            text = text.strip()

        data = json.loads(text)
        result = RelevanceResult(**data)
        logger.info(f"Job '{job.title}' scored {result.score}/100")
        return result
