# Memory Design

TheHiveMind uses layered memory so agents get the right context without flooding every prompt.

## Core Memory

Core memory contains durable identity and operating principles. It is always safe to include because it is short and stable.

## Current State

Current state stores the latest truth about the active project or run. It helps agents avoid stale assumptions and gives the dashboard a concise project status.

## Vector Memory Placeholder

The MVP uses a local JSON text-chunk store with simple lexical scoring. It is intentionally shaped like a vector store interface:

- add a text chunk
- search by query
- return ranked snippets

This can later be replaced by pgvector, Chroma, or another embedding-backed store.

## Retrieval

Retrieval combines core memory, current state, and relevant snippets into a `MemorySummary`. Agents should receive relevant snippets, not the entire memory store.

## Why Agents Do Not Read All Memory

Loading all memory into every agent wastes tokens, increases cost, and raises the chance of irrelevant context influencing the output. Retrieval keeps the working context smaller, cheaper, and easier to audit.

