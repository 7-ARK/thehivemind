# Model Routing

TheHiveMind separates planning, routing, worker execution, and QA so each task can use a model that fits its cost and capability profile.

## Planned Defaults

- CEO: GPT-5.5 Flex
- Model selector/search: Gemini 3.5 Flash
- Cheap non-search worker: GPT-5.4 nano
- Cheap search/multimodal worker: Gemini 3.1 Flash-Lite
- Coding later: Codex or Qwen Coder style specialized coding worker

## MVP Behavior

Mock mode is enabled by default. The model names are displayed, logged, and cost-estimated, but no paid API calls are made.

## Future Routing Signals

Future live routing can consider:

- task type
- required context size
- search or multimodal needs
- expected output size
- cost budget
- latency target
- historical model quality

The `ModelSelectorAgent` and provider interfaces are the extension points for this work.

