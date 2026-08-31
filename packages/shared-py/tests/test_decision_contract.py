"""Contract tests for fintra_decision — the canonical Decision seam.

Proves: (1) the three existing native vocabularies collapse to one canonical
verdict; (2) the trust band boundaries; (3) the registry routes one request shape
to the right domain engine; (4) the response seal is deterministic and covers the
verdict; (5) an unhandled action fails closed (NoEngineError, never a silent allow).
"""
import sys
from pathlib import Path

# Make the package importable whether pytest's rootdir is packages/shared-py or repo root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fintra_decision import (  # noqa: E402
    Action,
    Actor,
    Band,
    DecisionContext,
    DecisionRequest,
    DecisionRegistry,
    NoEngineError,
    Target,
    Verdict,
    band_from_score,
    default_registry,
    idempotency_key_for,
    normalize_verdict,
    persist_decision,
)


# ── 1 · verdict unification across the three real vocabularies ───────────────
def test_normalize_aegis_vocabulary():
    # The Aegis PDP's full native vocabulary, mapped to canonical.
    assert normalize_verdict("allow") == Verdict.ALLOW
    assert normalize_verdict("allow_with_logging") == Verdict.ALLOW
    assert normalize_verdict("require_step_up") == Verdict.STEP_UP
    assert normalize_verdict("human_review_required") == Verdict.HOLD
    assert normalize_verdict("deny_recommended") == Verdict.BLOCK


def test_normalize_finance_signals_vocabulary():
    assert normalize_verdict("allow") == Verdict.ALLOW
    assert normalize_verdict("challenge") == Verdict.STEP_UP
    assert normalize_verdict("require_approval") == Verdict.HOLD
    assert normalize_verdict("block") == Verdict.BLOCK


def test_normalize_billpay_vocabulary():
    assert normalize_verdict("step_up") == Verdict.STEP_UP
    assert normalize_verdict("hold") == Verdict.HOLD


def test_normalize_is_case_and_space_insensitive():
    assert normalize_verdict("  ALLOW ") == Verdict.ALLOW
    assert normalize_verdict("Deny") == Verdict.BLOCK


def test_normalize_unknown_fails_safe_to_hold():
    # Fail-safe: an unrecognized verdict must NOT release the action.
    assert normalize_verdict("banana") == Verdict.HOLD
    assert normalize_verdict("") == Verdict.HOLD
    assert normalize_verdict(None) == Verdict.HOLD  # type: ignore[arg-type]


# ── 2 · trust band boundaries ────────────────────────────────────────────────
def test_band_boundaries():
    assert band_from_score(100) == Band.TRUSTED
    assert band_from_score(80) == Band.TRUSTED
    assert band_from_score(79.9) == Band.GUARDED
    assert band_from_score(60) == Band.GUARDED
    assert band_from_score(40) == Band.ELEVATED
    assert band_from_score(39) == Band.CRITICAL
    assert band_from_score(0) == Band.CRITICAL


# ── helpers ──────────────────────────────────────────────────────────────────
def _finance_request(action_type, amount, envelope=None, signals=None, org_id="org-1"):
    return DecisionRequest(
        request_id="req-fin-1",
        actor=Actor(id="agent://ap-bot", type="agent"),
        action=Action(type=action_type),
        target=Target(id="inv-1", kind="invoice"),
        context=DecisionContext(
            domain="finance",
            amount=amount,
            envelope=envelope or {},
            signals=signals or [],
        ),
        org_id=org_id,
        now_iso="2026-07-16T00:00:00Z",
    )


def _security_request(privileged, reversible, environment="prod", blast="enterprise"):
    return DecisionRequest(
        request_id="req-sec-1",
        actor=Actor(id="agent://deploy-bot", type="agent", privileged=privileged),
        action=Action(type="delete_iam_policy", reversible=reversible),
        target=Target(id="policy-1", kind="iam_policy", environment=environment, blast_radius=blast),
        context=DecisionContext(domain="security"),
    )


# ── 3 · the registry routes one shape to the right engine ────────────────────
def test_registry_routes_finance():
    reg = default_registry()
    resp = reg.decide(_finance_request("pay_invoice", 75_000))
    assert resp.domain == "finance"
    assert resp.engine == "finance.reference"
    assert resp.verdict == Verdict.HOLD  # >= 50k fallback


def test_registry_routes_security_high_risk_blocks():
    reg = default_registry()
    resp = reg.decide(_security_request(privileged=True, reversible=False))
    assert resp.domain == "security"
    assert resp.verdict == Verdict.BLOCK  # prod + privileged + irreversible + enterprise
    assert resp.band == Band.CRITICAL
    assert "restore_previous_state" in resp.compensating_actions


def test_security_low_risk_allows():
    reg = default_registry()
    resp = reg.decide(_security_request(privileged=False, reversible=True, environment="dev", blast="user"))
    assert resp.verdict == Verdict.ALLOW


# ── native envelope preferred over the fallback ──────────────────────────────
def test_finance_uses_native_recommended_action():
    reg = default_registry()
    # A small-dollar action the fallback would ALLOW, but the engine said block.
    resp = reg.decide(_finance_request("pay_invoice", 500, envelope={"recommended_action": "block", "risk": 90}))
    assert resp.verdict == Verdict.BLOCK
    assert resp.band == Band.CRITICAL
    assert resp.compensating_actions  # block => compensating actions present


def test_finance_signals_become_drivers():
    reg = default_registry()
    resp = reg.decide(
        _finance_request(
            "pay_invoice", 12_000,
            signals=[{"type": "new_payee", "score": 0.8}, {"type": "amount_spike", "score": 0.3}],
        )
    )
    labels = {d["label"] for d in resp.drivers}
    assert labels == {"new_payee", "amount_spike"}
    tones = {d["label"]: d["tone"] for d in resp.drivers}
    assert tones["new_payee"] == "danger"
    assert tones["amount_spike"] == "neutral"


# ── 4 · the seal is deterministic and covers the verdict ─────────────────────
def test_seal_is_deterministic():
    reg = default_registry()
    a = reg.decide(_finance_request("pay_invoice", 75_000))
    b = reg.decide(_finance_request("pay_invoice", 75_000))
    assert a.evidence_ref == b.evidence_ref
    assert a.evidence_ref.startswith("sha256:")


def test_seal_changes_with_verdict():
    reg = default_registry()
    allow = reg.decide(_finance_request("pay_invoice", 500))
    hold = reg.decide(_finance_request("pay_invoice", 75_000))
    assert allow.verdict != hold.verdict
    assert allow.evidence_ref != hold.evidence_ref


# ── 4b · the ledger row is the request⋈response join, tenant-stamped ─────────
def test_ledger_row_joins_request_and_response():
    reg = default_registry()
    req = _finance_request("pay_invoice", 75_000, org_id="org-acme")
    resp = reg.decide(req)
    row = resp.to_ledger_row(req)
    assert row["org_id"] == "org-acme"                     # tenant stamped
    assert row["actor_identifier"] == "agent://ap-bot"
    assert row["action_intent_signature"] == "pay_invoice"
    assert row["functional_domain"] == "finance"
    assert row["enforced_decision"] == "hold"              # verdict value, not enum
    assert row["evidence_ref"] == resp.evidence_ref        # proof carried into the ledger
    assert row["created_at"] == "2026-07-16T00:00:00Z"
    assert row["calculated_blast_radius"] == "team"


def test_ledger_row_is_json_serializable():
    import json
    reg = default_registry()
    req = _finance_request("pay_invoice", 12_000, signals=[{"type": "new_payee", "score": 0.8}])
    resp = reg.decide(req)
    # Must serialize cleanly for an append-only store (no enums leaking through).
    dumped = json.dumps(resp.to_ledger_row(req))
    assert "new_payee" in dumped


# ── 4c · persistence seam (pure sink, fail-soft, content-addressed idempotency) ─
class _FakeSink:
    def __init__(self):
        self.rows = []

    def write(self, row):
        # emulate an upsert de-duped on idempotency_key
        self.rows = [r for r in self.rows if r["idempotency_key"] != row["idempotency_key"]]
        self.rows.append(row)


class _BrokenSink:
    def write(self, row):
        raise RuntimeError("db down")


def test_persist_writes_one_row_with_key():
    reg = default_registry()
    req = _finance_request("pay_invoice", 75_000, org_id="org-acme")
    resp = reg.decide(req)
    sink = _FakeSink()
    key = persist_decision(req, resp, sink=sink)
    assert key == idempotency_key_for(req, resp)
    assert key.startswith("decision:org-acme:req-fin-1:")
    assert len(sink.rows) == 1
    assert sink.rows[0]["evidence_ref"] == resp.evidence_ref


def test_persist_is_idempotent_on_retry():
    reg = default_registry()
    req = _finance_request("pay_invoice", 75_000)
    resp = reg.decide(req)
    sink = _FakeSink()
    persist_decision(req, resp, sink=sink)
    persist_decision(req, resp, sink=sink)  # retry, identical content
    assert len(sink.rows) == 1              # de-duped, not doubled


def test_persist_new_row_when_decision_changes():
    reg = default_registry()
    sink = _FakeSink()
    req_allow = _finance_request("pay_invoice", 500)      # ALLOW
    req_block = _finance_request("pay_invoice", 500, envelope={"recommended_action": "block", "risk": 90})
    persist_decision(req_allow, reg.decide(req_allow), sink=sink)
    persist_decision(req_block, reg.decide(req_block), sink=sink)
    # same request_id, but different decision content => two distinct ledger rows
    assert len(sink.rows) == 2
    assert {r["enforced_decision"] for r in sink.rows} == {"allow", "block"}


def test_persist_is_fail_soft():
    reg = default_registry()
    req = _finance_request("pay_invoice", 75_000)
    resp = reg.decide(req)
    # A sink outage must NOT raise and must still return the key.
    key = persist_decision(req, resp, sink=_BrokenSink())
    assert key == idempotency_key_for(req, resp)


# ── 5 · unhandled action fails closed ────────────────────────────────────────
def test_unhandled_action_raises_no_engine():
    reg = DecisionRegistry()  # empty registry
    req = _finance_request("pay_invoice", 100)
    try:
        reg.decide(req)
        assert False, "expected NoEngineError"
    except NoEngineError:
        pass


def test_unknown_domain_and_action_raises():
    reg = default_registry()
    req = DecisionRequest(
        request_id="req-x",
        actor=Actor(id="agent://x"),
        action=Action(type="brew_coffee"),
        target=Target(id="mug-1"),
        context=DecisionContext(domain="kitchen"),
    )
    try:
        reg.decide(req)
        assert False, "expected NoEngineError"
    except NoEngineError:
        pass
