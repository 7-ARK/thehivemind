from app.agents.base_agent import BaseAgent


class CEOAgent(BaseAgent):
    def build_plan(self, command: str) -> str:
        return (
            f"Clarify the objective, split '{command}' into research, technical, "
            "content, and QA tasks, then assemble one final answer."
        )

