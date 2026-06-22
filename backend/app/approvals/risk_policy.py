import uuid
from datetime import UTC, datetime

from app.approvals.schemas import ApprovalRequest
from app.core.config import Settings, get_settings
from app.core.models import RunCreate


def evaluate_approval_needs(payload: RunCreate, run_id: str | None = None, settings: Settings | None = None) -> list[ApprovalRequest]:
    active_settings = settings or get_settings()
    command = payload.command.lower()
    approvals: list[ApprovalRequest] = []

    if payload.mode == "live":
        approvals.append(
            _approval(
                payload,
                run_id,
                approval_type="live_mode",
                risk_level="high",
                title="Approval required: Live mode",
                reason="Live mode may use real provider API credits. Approval does not bypass ALLOW_LIVE_CALLS or provider key checks.",
                requested_action="Run workflow in live provider mode.",
                estimated_cost_usd=payload.max_cost_usd,
            )
        )

    if payload.allow_ceo_live or _contains_positive_any(command, ["use gpt-5.5", "gpt-5.5", "best ceo model", "most powerful model"], ["do not use gpt-5.5", "don't use gpt-5.5", "no gpt-5.5"]):
        approvals.append(
            _approval(
                payload,
                run_id,
                approval_type="expensive_ceo_model",
                risk_level="high",
                title="Approval required: GPT-5.5 CEO",
                reason="The GPT-5.5 CEO path may be expensive and must be explicitly approved through an approval card.",
                requested_action="Allow the expensive CEO model for this run.",
                estimated_cost_usd=payload.max_cost_usd,
                model=active_settings.ceo_model,
                provider="openai",
            )
        )

    if payload.max_cost_usd > active_settings.max_cost_per_run_usd:
        approvals.append(
            _approval(
                payload,
                run_id,
                approval_type="run_cost_limit",
                risk_level="medium",
                title="Approval required: Higher run estimate",
                reason=f"Requested max_cost_usd ${payload.max_cost_usd:.2f} is above the configured default ${active_settings.max_cost_per_run_usd:.2f}.",
                requested_action="Allow a higher per-run cost ceiling.",
                estimated_cost_usd=payload.max_cost_usd,
            )
        )

    if payload.allow_live_coding_model_call:
        approvals.append(
            _approval(
                payload,
                run_id,
                approval_type="live_coding_model",
                risk_level="high",
                title="Approval required: Live coding model",
                reason="Real Coding Agent live mode can send selected project file context to OpenRouter and spend provider credits.",
                requested_action="Allow a live OpenRouter coding model call for this run.",
                estimated_cost_usd=payload.max_cost_usd,
                model=active_settings.real_coding_agent_model,
                provider="openrouter",
            )
        )

    keyword_rules = [
        (
            "package_install",
            "high",
            "Approval required: Package installation",
            "Package installation can change the local environment and is not part of the safe command allowlist.",
            "Install or modify project dependencies.",
            ["pip install", "npm install", "install package", "install dependency", "add dependency", "yarn add", "pnpm add"],
        ),
        (
            "deployment",
            "critical",
            "Approval required: Deployment",
            "Deployment can publish code or affect production systems. TheHiveMind does not deploy automatically in this v1.",
            "Deploy, publish, host, or release the project.",
            ["deploy", "publish live", "production deploy", "deploy to production", "production hosting", "hosting", "release this website", "go live"],
        ),
        (
            "external_api",
            "high",
            "Approval required: External API action",
            "External API calls can affect third-party systems or expose data.",
            "Call or integrate an external API.",
            ["call external api", "external api", "webhook", "third-party api"],
        ),
        (
            "web_search",
            "medium",
            "Approval required: Web search",
            "Web search or grounding can contact external services and may add provider cost.",
            "Use web search, grounding, or browsing.",
            ["web search", "grounding", "browse the web", "search the web", "google search"],
        ),
        (
            "customer_messaging",
            "critical",
            "Approval required: Customer messaging",
            "Sending messages to customers must stay behind explicit human approval.",
            "Send email, WhatsApp, SMS, or customer messages.",
            ["send email", "email customers", "send whatsapp", "whatsapp", "sms", "message customers"],
        ),
        (
            "social_posting",
            "high",
            "Approval required: Social posting",
            "Posting publicly to social platforms requires human approval.",
            "Post to social media.",
            ["post on instagram", "post on facebook", "post on linkedin", "social media post", "tweet", "post to x"],
        ),
        (
            "payment_integration",
            "critical",
            "Approval required: Payment integration",
            "Payment providers and real money flows require explicit approval and extra hard safety checks.",
            "Add or connect payment processing.",
            ["payment integration", "stripe", "jazzcash", "easypaisa", "checkout", "real payment"],
        ),
        (
            "sensitive_file",
            "critical",
            "Approval required: Sensitive file change",
            "Sensitive files such as .env, keys, and secrets must not be modified without explicit approval. Existing safety rules still block unsafe writes.",
            "Write or modify sensitive files.",
            [".env", "secret", "api key", "private key", "credentials"],
        ),
        (
            "dangerous_command",
            "critical",
            "Approval required: Dangerous command",
            "Dangerous shell commands are blocked by policy and also require approval before any safe alternative is considered.",
            "Run a risky shell command.",
            ["rm -rf", "delete everything", "format disk", "sudo", "chmod 777", "drop database"],
        ),
        (
            "large_overwrite",
            "medium",
            "Approval required: Large overwrite",
            "Large rewrites or overwrites can destroy useful project state.",
            "Overwrite many files or perform a large rewrite.",
            ["overwrite all", "rewrite entire", "replace everything", "large overwrite"],
        ),
        (
            "human_approval_marker",
            "medium",
            "Approval required: Marked human approval",
            "The requested action is explicitly marked as requiring human approval.",
            "Perform an action marked requires_human_approval.",
            ["requires_human_approval", "requires human approval"],
        ),
        (
            "unknown_model",
            "medium",
            "Approval required: Unknown model request",
            "The command mentions a model outside the configured registry.",
            "Use an unknown or new model.",
            ["claude", "llama", "mistral", "unknown model", "new model"],
        ),
    ]

    for approval_type, risk_level, title, reason, requested_action, keywords in keyword_rules:
        if _contains_positive_any(command, keywords, _negative_phrases_for(approval_type)):
            approvals.append(
                _approval(
                    payload,
                    run_id,
                    approval_type=approval_type,
                    risk_level=risk_level,
                    title=title,
                    reason=reason,
                    requested_action=requested_action,
                )
            )

    return _dedupe(approvals)


def _approval(
    payload: RunCreate,
    run_id: str | None,
    *,
    approval_type: str,
    risk_level: str,
    title: str,
    reason: str,
    requested_action: str,
    estimated_cost_usd: float | None = None,
    model: str | None = None,
    provider: str | None = None,
) -> ApprovalRequest:
    return ApprovalRequest(
        id=str(uuid.uuid4()),
        run_id=run_id,
        project_id=payload.project_id,
        command=payload.command,
        status="pending",
        risk_level=risk_level,
        approval_type=approval_type,
        title=title,
        reason=reason,
        requested_action=requested_action,
        estimated_cost_usd=estimated_cost_usd,
        model=model,
        provider=provider,
        created_at=datetime.now(UTC).isoformat(),
        metadata={"run_type": payload.run_type, "mode": payload.mode},
    )


def _contains_any(value: str, keywords: list[str]) -> bool:
    return any(keyword in value for keyword in keywords)


def _contains_positive_any(value: str, keywords: list[str], negative_phrases: list[str]) -> bool:
    if any(phrase in value for phrase in negative_phrases):
        return False
    return _contains_any(value, keywords)


def _negative_phrases_for(approval_type: str) -> list[str]:
    phrases = {
        "package_install": ["do not install packages", "don't install packages", "no package installs", "do not install dependencies"],
        "deployment": ["do not deploy", "don't deploy", "no deploy", "no deployment"],
        "external_api": ["no external actions", "do not call external api", "don't call external api", "do not use external actions"],
        "web_search": ["do not search", "don't search", "no web search", "do not browse", "don't browse", "do not run live web search"],
        "customer_messaging": ["do not send email", "don't send email", "do not send whatsapp", "don't send whatsapp", "no emails", "no whatsapp"],
        "social_posting": ["do not post", "don't post", "no social posting"],
        "payment_integration": ["do not add payment", "don't add payment", "no payment integration"],
        "sensitive_file": ["do not edit .env", "don't edit .env", "do not expose secrets"],
        "dangerous_command": ["do not run dangerous commands", "no dangerous commands"],
        "large_overwrite": ["do not overwrite all", "don't overwrite all"],
    }
    return phrases.get(approval_type, [])


def _dedupe(approvals: list[ApprovalRequest]) -> list[ApprovalRequest]:
    by_type = {}
    for approval in approvals:
        by_type.setdefault(approval.approval_type, approval)
    return list(by_type.values())
