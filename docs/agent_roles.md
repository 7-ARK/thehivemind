# Agent Roles

## CEO Agent

The CEO Agent receives the command, clarifies the objective, builds the plan, and delegates work. It is the top-level reasoning and coordination agent.

## Model Selector Agent

The Model Selector Agent chooses the best model tier for each task. In the MVP it returns deterministic mock routing, but the interface is designed for future cost, latency, and capability-aware routing.

## Research Agent

The Research Agent handles search-heavy, market, competitive, and contextual work. It is planned to use cheaper fast search-capable models when live mode is added.

## Coding Agent

The Coding Agent turns plans into technical implementation tasks, system designs, automation steps, and later code changes. Future routing may use Codex or a specialized coder model.

## Content Agent

The Content Agent drafts reports, launch copy, messaging, documentation, and user-facing summaries.

## QA Agent

The QA Agent reviews worker outputs for completeness, contradictions, quality, and readiness before final assembly.

