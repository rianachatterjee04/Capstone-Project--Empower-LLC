# fintra_decision — the canonical Decision contract

**The seam that makes "one core, many engines" real.**

Fintra already makes consequential decisions in three different places, each with
its own verdict vocabulary:

| Engine | Where | Native verdicts |
| --- | --- | --- |
| Aegis PDP | `packages/aegis` (`/pdp/decide`) | `allow`, `deny_recommended` |
| Finance signals | `packages/api` (`evaluate_payment` / `internal_finance`) | `allow`, `challenge`, `require_approval`, `block` |
| Bill Pay | `packages/api/lib/addons/billpay` | `allow`, `step_up`, `hold`, `block` |

Three vocabularies, three request shapes, three response shapes — so the trust
ledger, the Verified-Autonomy console, and assurance receipts each special-case
who answered. `fintra_decision` collapses that into **one** request, **one**
response, **one** verdict vocabulary, and a registry that routes to domain engines.

Adding a domain (HR, procurement, deploy-gating) becomes *registering an engine* —
not reshaping the contract.

## The contract

```
DecisionRequest  =  Actor  ->  Action  ->  Target  ->  Context
DecisionResponse =  Verdict + Trust (score/band) + Proof (sealed evidence_ref)
```

- **Verdict** — canonical `{ALLOW, STEP_UP, HOLD, BLOCK}`. Every engine's native
  verdict maps in via `normalize_verdict()`. Unknown ⇒ `HOLD` (fail-safe: never
  silently release a consequential action).
- **Trust** — `trust_score` (0–100, the Action Trust Score = 100 − risk) and a
  `Band` (`trusted / guarded / elevated / critical`).
- **Proof** — `evidence_ref` is a deterministic `sha256:` seal over the decision
  (canonical JSON), matching the Verified-Autonomy assurance seal, so a decision
  can be pinned into the trust ledger tamper-evidently.

## Registering the real engines (adapters)

The two engines in `reference.py` are runnable proof. In production each is a thin
adapter that translates a *native* output into a canonical `DecisionResponse`:

```python
from fintra_decision import DecisionRegistry, DecisionResponse, band_from_score, normalize_verdict

class AegisAdapter:
    domain = "security"
    def handles(self, req): return req.context.domain == "security"
    def decide(self, req):
        native = aegis_client.decide(req)                 # POST /pdp/decide
        v = normalize_verdict(native["verdict"])          # allow | deny_recommended -> canonical
        score = native["action_trust_score"]
        return DecisionResponse(
            request_id=req.request_id, domain="security", engine="aegis.pdp",
            verdict=v, trust_score=score, band=band_from_score(score),
            drivers=native.get("drivers", []),
        ).sealed()

class FinanceAdapter:
    domain = "finance"
    def handles(self, req): return req.context.domain == "finance"
    def decide(self, req):
        env = evaluate_payment(req.context.business)      # existing finance engine
        v = normalize_verdict(env["recommended_action"])  # allow|challenge|require_approval|block
        ...

registry = DecisionRegistry()
registry.register(FinanceAdapter())
registry.register(AegisAdapter())
verdict = registry.decide(request)   # routed by domain/action, one shape out
```

Nothing downstream needs to know which engine answered.

## Design rules

- **Pure & dependency-free.** `fintra_decision` imports only the stdlib. It can be
  imported by any backend without pulling `supabase`/`fastapi` (it is co-shipped in
  the `fintra-entitlements` distribution purely for install convenience).
- **Fail closed.** Unknown verdict ⇒ `HOLD`; no registered engine ⇒
  `NoEngineError` (never a silent allow); a throwing engine is skipped by the
  router, not fatal.
- **Deterministic seal.** Same decision ⇒ same `evidence_ref`.

## Tests

```
cd packages/shared-py
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest tests/test_decision_contract.py -q
```

> **Cross-references.** Paths under `packages/api`, `packages/payroll`, `packages/sentri-api`
> and similar refer to services in the wider Fintra platform that are **not part of this
> build**. They are named so the seam is visible, not because the code ships here.
