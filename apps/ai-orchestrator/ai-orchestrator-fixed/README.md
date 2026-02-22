# AI Orchestrator (stub)

This service runs privileged HR automations:
- Case inactivity scans + auto-escalation ticks
- Resume screening batches
- Performance calibration + discrepancy detection
- Policy-to-action enforcement (SLAs, workflows)

It calls backend internal routes using `X-Internal-AI-Secret`.

Implementation intentionally stubbed here; backend already exposes `/api/internal/ai/tick/escalations`.
