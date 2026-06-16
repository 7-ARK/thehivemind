from app.agents.base_agent import BaseAgent


class ModelSelectorAgent(BaseAgent):
    def route_models(self) -> str:
        return "CEO stays on flex reasoning; search-heavy work uses Gemini; production workers use nano."

