"""The paid tier must EARN its price.

Why this file exists (2026-07-17): `/audit` shipped charging 0.10 USDT while returning a
strict SUBSET of the free `/verify` — it even dropped `digest`, `name` and `pronouncement`.
The code comment claimed `signals` was "the full breakdown the free tier withholds"; the
free tier had been returning `signals` all along. Nobody caught it because audit_paid.py
had zero tests. A buyer diffing the two payloads would have found it in seconds — on a
product whose entire thesis is "published != true".

The invariant these tests pin: PAID must be a strict superset of FREE, and the extra keys
must carry real data the free tier cannot answer (timeline / uptime / fleet), not
relabelled fields.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from oracle import audit_paid  # noqa: E402
from oracle.engine import score_agent  # noqa: E402


def _healthy(url): return {url: {"reachable": True, "status": 402, "healthy": True, "category": "x402"}}


def _asp(**over):
    base = dict(agentId="999", name="Test Provider", approvalStatus=4,
                onlineStatus=1, status=1, salesCount=169, securityRate="4.75",
                profileDescription="does a thing")
    base.update(over)
    return base


def _svc(endpoint="https://svc.example.com/api", fee="0.10"):
    return [{"endpoint": endpoint, "fee": fee, "serviceType": "A2MCP", "serviceName": "Thing"}]


def _verdict():
    ep = "https://svc.example.com/api"
    return score_agent(_asp(), _svc(ep), _healthy(ep))


_ENV = {"pubkey": "ab" * 32, "signature": "cd" * 64, "signed_at": 0, "expires_at": 1}


def _free_payload(v) -> dict:
    """The shape /verify serves — app.py builds this from the same verdict object."""
    return {
        "agent_id": v.agent_id, "name": v.name, "verdict": v.verdict, "score": v.score,
        "confidence": v.confidence, "max_safe_usd": v.max_safe_usd, "reasons": v.reasons,
        "signals": v.signals, "evidence": v.evidence, "digest": v.digest,
        "pronouncement": "…", "signature": _ENV,
    }


def test_paid_audit_is_a_strict_superset_of_the_free_verdict(tmp_path):
    """Every field a caller gets free must also be in the paid payload. Paying must never
    return LESS — which is exactly what shipped before this test existed."""
    v = _verdict()
    free = _free_payload(v)
    paid = audit_paid.full_audit(v.agent_id, v, _ENV)

    # `name`/`pronouncement` are presentation, not audit depth; everything else must carry over.
    missing = [k for k in free if k not in paid and k not in ("name", "pronouncement")]
    assert not missing, f"paid /audit is missing free-tier fields: {missing}"


def test_paid_audit_adds_depth_the_free_tier_cannot_answer():
    """The premium delta must be REAL: the free tier is a snapshot, the paid tier is a
    timeline. If these keys vanish, /audit is a relabelled /verify and the price is a lie."""
    v = _verdict()
    paid = audit_paid.full_audit(v.agent_id, v, _ENV)

    for key in ("timeline", "uptime", "fleet"):
        assert key in paid, f"paid tier lost its differentiator: {key}"

    assert paid["tier"] == "full-audit (paid)"
    assert isinstance(paid["timeline"], list)


def test_paid_audit_never_charges_for_nothing():
    """Guard the actual regression: paid must have strictly MORE than free."""
    v = _verdict()
    free = _free_payload(v)
    paid = audit_paid.full_audit(v.agent_id, v, _ENV)

    extra = set(paid) - set(free)
    assert extra, "paid /audit returns nothing the free tier does not — do not charge for it"
    assert {"timeline", "uptime", "fleet"} <= extra, (
        f"the premium delta must be depth, not relabels. Got: {sorted(extra)}"
    )


def test_payto_never_defaults_to_the_buyer_wallet():
    """A self-payment is the exact wash pattern KYA flags on other agents. This used to
    DEFAULT to the buyer wallet, so any deploy missing KYA_AUDIT_PAYTO would have settled
    money to itself. It must now be unset (refuse to mount) or a distinct payee."""
    payto = audit_paid.AUDIT_PAYTO
    assert payto is None or payto.lower() != audit_paid.BUYER_WALLET.lower(), (
        "KYA_AUDIT_PAYTO is the buyer wallet — a real settle would be a self-payment, "
        "the wash pattern KYA itself penalises."
    )


def test_paid_tier_refuses_to_mount_without_a_distinct_payee(monkeypatch):
    """The guard must actually fire: creds present but payTo unset/self => no /audit.
    Taking money with no distinct payee is worse than having no paid tier."""
    monkeypatch.setenv("OKX_API_KEY", "k")
    monkeypatch.setenv("OKX_SECRET_KEY", "s")
    monkeypatch.setenv("OKX_PASSPHRASE", "p")

    monkeypatch.setattr(audit_paid, "AUDIT_PAYTO", None)
    mw, reason = audit_paid.build_paid_middleware()
    assert mw is None and "KYA_AUDIT_PAYTO unset" in reason

    monkeypatch.setattr(audit_paid, "AUDIT_PAYTO", audit_paid.BUYER_WALLET)
    mw, reason = audit_paid.build_paid_middleware()
    assert mw is None and "self-payment" in reason
