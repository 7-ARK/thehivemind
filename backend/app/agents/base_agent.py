from dataclasses import dataclass, field


@dataclass
class BaseAgent:
    name: str
    role: str
    assigned_model: str
    status: str = "idle"
    latest_action: str = "Waiting for a run"
    completed_work: list[str] = field(default_factory=list)

    def mark_complete(self, action: str, work_item: str) -> None:
        self.status = "completed"
        self.latest_action = action
        self.completed_work.append(work_item)

