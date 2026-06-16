class GeminiProvider:
    """Future Gemini adapter for fast routing, search, and multimodal workers."""

    name = "gemini"

    def complete(self, prompt: str, model: str) -> str:
        raise NotImplementedError("Gemini live calls are intentionally disabled in the MVP.")

