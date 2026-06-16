from app.agents.base_agent import BaseAgent


class ResearchAgent(BaseAgent):
    def research(self, command: str) -> str:
        return f"Created a market/context research brief for: {command}."

