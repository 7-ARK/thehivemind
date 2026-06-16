class MockProvider:
    """Deterministic provider used by default for local demos and interviews."""

    name = "mock"

    def complete(self, prompt: str, model: str) -> str:
        return f"Mock response from {model}: {prompt[:160]}"

