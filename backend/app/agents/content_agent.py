from app.agents.base_agent import BaseAgent


class ContentAgent(BaseAgent):
    def draft(self, command: str) -> str:
        return f"Drafted user-facing messaging, launch narrative, and deliverable structure for: {command}."

