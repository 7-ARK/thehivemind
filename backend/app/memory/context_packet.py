from __future__ import annotations

from app.core.config import Settings, get_settings
from app.memory.memory_policies import redact_secrets
from app.memory.memory_retriever import constraints_for_packet, default_retrieval_request, now_iso
from app.memory.memory_store import MemoryStore
from app.memory.memory_retriever import MemoryRetriever
from app.memory.schemas import ContextPacket


def build_context_packet(
    *,
    agent_id: str,
    project_id: str | None,
    run_id: str | None,
    run_type: str,
    task: str,
    current_command: str,
    settings: Settings | None = None,
) -> ContextPacket:
    active_settings = settings or get_settings()
    request = default_retrieval_request(
        project_id=project_id,
        query=task,
        agent_id=agent_id,
        run_type=run_type,
        current_command=current_command,
        settings=active_settings,
    )
    results = MemoryRetriever(active_settings, MemoryStore(active_settings)).retrieve(request)
    packet = ContextPacket(
        agent_id=agent_id,
        project_id=project_id,
        run_id=run_id,
        run_type=run_type,
        task=task,
        current_command=current_command,
        retrieved_memory_items=results,
        project_state_summary=_first_summary(results, "project_state"),
        active_constraints=constraints_for_packet(current_command, run_type),
        relevant_sources=_source_notes(results),
        relevant_qa_warnings=[result.item.summary or result.item.content for result in results if result.item.memory_type == "qa_warning"],
        model_routing_notes=[result.item.summary or result.item.content for result in results if result.item.memory_type == "model_selection"],
        token_budget=active_settings.memory_max_tokens_per_agent,
        omitted_memory_count=max(0, len(results) - active_settings.memory_top_k),
        created_at=now_iso(),
    )
    return _redacted_packet(packet)


def format_context_packet(packet: ContextPacket) -> str:
    lines = ["## Relevant Memory"]
    if not packet.retrieved_memory_items:
        lines.append("- No relevant memory retrieved.")
    for result in packet.retrieved_memory_items:
        item = result.item
        lines.append(f"- [{item.memory_type}] {item.summary or item.content[:240]} (why: {', '.join(result.why_selected)})")
    lines.append("\n## Active Constraints")
    lines.extend(f"- {constraint}" for constraint in packet.active_constraints)
    if packet.relevant_sources:
        lines.append("\n## Source Notes")
        lines.extend(f"- {source}" for source in packet.relevant_sources)
    if packet.relevant_qa_warnings:
        lines.append("\n## QA Warnings")
        lines.extend(f"- {warning}" for warning in packet.relevant_qa_warnings)
    return "\n".join(lines)


def _first_summary(results, memory_type: str) -> str:
    for result in results:
        if result.item.memory_type == memory_type:
            return result.item.summary or result.item.content
    return ""


def _source_notes(results) -> list[str]:
    notes = []
    for result in results:
        item = result.item
        if item.memory_type != "research_source_summary":
            continue
        urls = ", ".join(item.source_urls[:3])
        suffix = f" URLs: {urls}" if urls else ""
        notes.append(f"{item.summary or item.content}{suffix}")
    return notes


def _redacted_packet(packet: ContextPacket) -> ContextPacket:
    data = packet.model_dump()
    text, _ = redact_secrets(format_context_packet(packet))
    data["metadata"] = {"redacted_preview": text[:1000]}
    return ContextPacket.model_validate(data)
