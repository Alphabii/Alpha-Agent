from loguru import logger

from src.ai.prompts import (
    COVER_LETTER_SYSTEM,
    COVER_LETTER_USER,
    PROPOSAL_MESSAGE_SYSTEM,
    PROPOSAL_MESSAGE_USER,
)
from src.config import settings
from src.models import JobRecord
from src.utils.retry import retry


def _init_vertex():
    import vertexai

    credentials = settings.get_google_credentials()
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
        return None
    else:
        import google.generativeai as genai
        genai.configure(api_key=settings.gemini_api_key)
        return None


class ApplicationGenerator:
    """Generates cover letters and proposals using LLM."""

    def __init__(self):
        self._client = _create_client()
        self._profile = settings.get_profile_text()

        if settings.ai_provider == "vertex":
            from vertexai.generative_models import GenerativeModel
            self._cover_model = GenerativeModel(
                model_name=settings.content_model,
                system_instruction=COVER_LETTER_SYSTEM,
            )
            self._proposal_model = GenerativeModel(
                model_name=settings.content_model,
                system_instruction=PROPOSAL_MESSAGE_SYSTEM,
            )
        elif settings.ai_provider == "gemini":
            import google.generativeai as genai
            self._cover_model = genai.GenerativeModel(
                model_name=settings.content_model,
                system_instruction=COVER_LETTER_SYSTEM,
            )
            self._proposal_model = genai.GenerativeModel(
                model_name=settings.content_model,
                system_instruction=PROPOSAL_MESSAGE_SYSTEM,
            )

    def _generate(self, system: str, user_prompt: str) -> str:
        if settings.ai_provider == "openai":
            response = self._client.chat.completions.create(
                model=settings.content_model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user_prompt},
                ],
            )
            return response.choices[0].message.content.strip()
        else:
            # Works for both "gemini" and "vertex" providers
            model = self._cover_model if system == COVER_LETTER_SYSTEM else self._proposal_model
            response = model.generate_content(user_prompt)
            return response.text.strip()

    @retry(max_attempts=2)
    def generate_cover_letter(self, job: JobRecord) -> str:
        user_prompt = COVER_LETTER_USER.format(
            profile=self._profile,
            title=job.title,
            company=job.company,
            location=job.location,
            skills=", ".join(job.skills),
            description=job.description[:3000],
        )
        text = self._generate(COVER_LETTER_SYSTEM, user_prompt)
        logger.info(f"Generated cover letter for '{job.title}' ({len(text)} chars)")
        return text

    @retry(max_attempts=2)
    def generate_proposal(self, job: JobRecord) -> str:
        user_prompt = PROPOSAL_MESSAGE_USER.format(
            profile=self._profile,
            title=job.title,
            company=job.company,
            skills=", ".join(job.skills),
            description=job.description[:3000],
        )
        text = self._generate(PROPOSAL_MESSAGE_SYSTEM, user_prompt)
        logger.info(f"Generated proposal for '{job.title}' ({len(text)} chars)")
        return text
