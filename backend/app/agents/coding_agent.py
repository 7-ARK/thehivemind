from app.agents.base_agent import BaseAgent


class CodingAgent(BaseAgent):
    def produce_task(self, command: str) -> str:
        return f"Outlined technical systems, automation steps, and implementation tasks for: {command}."

