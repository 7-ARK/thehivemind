# Business Builder v1 Architecture

## Purpose
Business Builder v1 adds a bounded Phase 1 planning workflow to TheHiveMind. It turns a structured business intake into auditable planning artifacts and a future Phase 2 build handoff.

## Phase 1 Scope
- Intake validation
- Business strategy planning
- Target customer planning
- Offer and pricing framework
- Brand direction planning
- Website/app requirements planning
- MVP scope
- Build handoff
- Planning QA
- Final planning report

## Explicit Phase 1 Exclusions
Phase 1 does not build websites, apps, HTML, React components, brand assets, logos, images, screenshots, deployments, payment flows, integrations, ads, social posts, emails, outreach, supplier contact, customer contact, package installs, cloud resources, or external actions.

## Intake Schema
`business_builder` accepts `business_intake` on the existing run API.

Required:
- `idea`

Optional:
- `business_type`
- `market_location`
- `target_customer`
- `primary_goal`
- `budget`
- `style_preferences`
- `product_or_service_details`
- `required_features`
- `constraints`
- `forbidden_actions`

Existing run types do not require `business_intake`.

## Workflow Stages
Default mock workflow:
- Business Planner
- Planning QA

Optional research may be selected only when web search is explicitly allowed and the command contains a positive research need. The Real Coding Agent is never selected for Phase 1.

## Phase 1.1 Strategic Decision Contract
Phase 1.1 keeps the same `business_builder` workflow and Phase 1 boundary, but the planner output is now a compact `strategic_decisions` contract. Mock mode creates the same contract deterministically. Live mode requests one bounded standard OpenAI GPT-5.5 planning call, validates the returned contract, and then uses the backend renderer to create artifacts.

The contract includes:
- customer wedge and primary launch segment
- positioning and safe promise
- validation plan and decision rules
- offer/pricing status with unknowns separated from facts
- brand direction and claim-safety rules
- website section contracts
- local-only inquiry flow
- local prototype readiness
- public launch readiness

Invalid live output is rejected instead of falling back to mock or coding behavior.

## Artifact Contract
Each successful run creates:
- `strategic_decisions.json`
- `business_brief.json`
- `business_brief.md`
- `business_strategy.md`
- `target_customer.md`
- `offer_and_pricing.md`
- `brand_direction.md`
- `website_app_requirements.md`
- `mvp_scope.md`
- `build_handoff.json`
- `planning_qa.md`
- `final_planning_report.md`
- `business_builder_state.json`

Generic run artifacts such as `agent_plan.json`, `model_selection.json`, `project_manifest.json`, and `project_state.md` may also appear through existing infrastructure.

## State Contract
The latest Phase 1 state is also persisted in the project workspace as `business_builder_state.json`.

Required state concepts:
- `phase: 1`
- `phase_status: planning_complete`
- `build_started: false`
- `build_allowed: false`
- `external_actions_taken: []`
- blocked external actions
- approvals needed
- deferred Phase 2 work

## Search and Memory Behavior
Search is off by default. With `allow_web_search=false`, Business Builder reports `search_needed=false`, selects no Research Agent, and does not fabricate sources.

With `use_memory=false`, historical memory retrieval is disabled. Post-run ingestion remains separate and is labelled by the existing run summary.

## Model and Cost Behavior
Business Builder uses the existing model registry and usage reporting. Mock mode is deterministic and logs simulated estimates only. GPT-5.5 is not required by the default Phase 1 path.

Live Phase 1 planning is intentionally blocked until an explicit compatible live route is approved.

## Safety Boundaries
Business Builder always blocks Phase 2 build work and external actions in Phase 1. Forbidden actions supplied by the user are preserved in the planning artifacts and state.

## Phase 2 Handoff Boundary
`build_handoff.json` is the only Phase 1 output intended for a later controlled Phase 2 build. It contains no code, package list, deployment plan, or claim that anything was built.

Phase 1.1 separates local prototype readiness from public launch readiness. A local prototype may be conditionally ready for a bounded, non-deployed build handoff while public launch remains `not_ready` until pricing, claims, operations, compliance, delivery, and external approvals are resolved.

## Planning QA
Planning QA now includes semantic checks for:
- primary customer specificity
- secondary audience separation
- safe promise and unsupported-claim avoidance
- offer status clarity
- validation questions, signals, and decision rules
- website handoff completeness
- local-only inquiry behavior
- local readiness versus public launch readiness
- no Phase 2 build or external action

## Testing and Manual Verification
Backend tests cover:
- mock success and artifact contract
- Phase 1.1 strategic decision contract
- broad-audience primary/secondary segmentation
- claim safety when search is off
- local prototype readiness versus public launch readiness
- build-ready website handoff without building
- required idea validation
- search-off behavior
- memory-off behavior
- no Real Coding Agent or website file changes
- compatibility with existing run types

Manual verification should run a mock `business_builder` intake with memory and web search off, then inspect Run Detail for Phase 1 status, no build, no search, no memory retrieval, required artifacts, and persisted `business_builder_state.json`.
