class OpenRouterProvider:
    """Future OpenRouter adapter for flexible worker model routing."""

    name = "openrouter"

    def complete(self, prompt: str, model: str) -> str:
        raise NotImplementedError("OpenRouter live calls are intentionally disabled in the MVP.")

