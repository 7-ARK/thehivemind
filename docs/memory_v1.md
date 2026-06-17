# Memory v1

TheHiveMind currently uses local memory only. No paid embedding APIs are called.

## Layers

- Core memory: durable identity and operating principles.
- Current state: latest project/run summary.
- Vector memory placeholder: JSON text chunks with lexical scoring.
- Embedding memory interface: provider-independent metadata-aware search with deterministic local scoring.

## New Interface

`backend/app/memory/embedding_memory.py` exposes:

```python
add_memory(text, metadata)
search_memory(query, top_k=5, filters=None)
```

Metadata includes:

- `project_id`
- `run_id`
- `agent_name`
- `artifact_id`
- `memory_type`
- `created_at`
- `tags`

## Retrieval Discipline

Agents receive only task-specific memory in their task packets. Full artifacts and huge outputs are not dumped into core memory. Sandboxed Autonomy stores summaries, paths, command results, and agent decisions.

## Upgrade Path

The interface can later use real embeddings, pgvector, Chroma, or provider embedding APIs behind explicit configuration. For now it is deterministic and local.
