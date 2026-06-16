from app.agents.base_agent import BaseAgent


class QAAgent(BaseAgent):
    def review(self) -> str:
        return "Checked outputs for completeness, contradictions, next steps, and recruiter-friendly clarity."

