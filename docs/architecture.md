# Architecture

TheHiveMind is structured around a visible orchestration loop:

`User Command -> CEO Agent -> Model Selector -> Worker Agents -> QA Agent -> Memory Updates -> Final Output`

## Flow

1. The user submits a command through the dashboard.
2. The FastAPI backend creates a run record and retrieves relevant memory.
3. The CEO Agent turns the command into a practical execution plan.
4. The Model Selector Agent chooses model tiers for each task.
5. Worker agents produce specialized outputs:
   - Research Agent handles search and context.
   - Coding Agent handles technical task planning.
   - Content Agent handles narrative and deliverables.
6. The QA Agent reviews outputs for gaps and contradictions.
7. The final output is assembled and stored with structured events.
8. The frontend renders the timeline, agent cards, task graph, metrics, memory, and final answer.

## Recruiter-Friendly Design

The system avoids hidden chain-of-thought. Instead, it shows practical work logs: what each agent did, what it used, what it produced, which model was assigned, and the estimated cost.

## Extensibility

Provider adapters, memory modules, cost estimation, and agent roles are separated so each part can evolve independently. The mock provider keeps the MVP useful before live model calls are enabled.

