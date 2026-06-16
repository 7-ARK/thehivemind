from app.core.models import TaskEdge, TaskGraph, TaskNode


def build_default_task_graph() -> TaskGraph:
    nodes = [
        TaskNode(id="command", label="Command", status="completed"),
        TaskNode(id="ceo-plan", label="CEO Plan", status="completed"),
        TaskNode(id="worker-tasks", label="Worker Tasks", status="completed"),
        TaskNode(id="agent-outputs", label="Agent Outputs", status="completed"),
        TaskNode(id="qa-review", label="QA Review", status="completed"),
        TaskNode(id="final-answer", label="Final Answer", status="completed"),
    ]
    edges = [
        TaskEdge(source="command", target="ceo-plan"),
        TaskEdge(source="ceo-plan", target="worker-tasks"),
        TaskEdge(source="worker-tasks", target="agent-outputs"),
        TaskEdge(source="agent-outputs", target="qa-review"),
        TaskEdge(source="qa-review", target="final-answer"),
    ]
    return TaskGraph(nodes=nodes, edges=edges)

