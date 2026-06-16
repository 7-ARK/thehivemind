class OpenAIProvider:
    """Future OpenAI adapter. Kept thin so orchestration code stays provider-agnostic."""

    name = "openai"

    def complete(self, prompt: str, model: str) -> str:
        raise NotImplementedError("OpenAI live calls are intentionally disabled in the MVP.")

