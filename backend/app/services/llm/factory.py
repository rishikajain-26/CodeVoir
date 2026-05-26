from app.core.config import settings
from app.services.llm.gemini_provider import GeminiProvider


def get_llm_provider():
    if settings.ANTHROPIC_API_KEY:
        from app.services.llm.claude_provider import ClaudeProvider
        return ClaudeProvider()
    return GeminiProvider()
