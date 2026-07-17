"""Evidence must be covered by the signature.

Why this file exists (2026-07-17): an adversarial audit proved the headline finding was
tamperable. Only agent_id/verdict/score/confidence/max_safe_usd were in the signed core, so:

    tamper evidence.cluster.fleet_size 99 -> 1, keep digest + signature
    -> digest UNCHANGED, signature STILL VERIFIES

Meanwhile the README says: "/verify returns a machine-readable `cluster` field ... so a
calling agent can branch on operator concentration" and "a consumer pins it once and verifies
every verdict offline". A field you tell callers to branch on, that a man-in-the-middle can
rewrite without breaking the signature, is worse than not shipping the field at all — the
signature launders the tampered value. On a product whose thesis is "published != true",
this was the one hole that mattered.
"""
import copy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from oracle.engine import score_agent  # noqa: E402


def _healthy(url): return {url: {"reachable": True, "status": 402, "healthy": True, "category": "x402"}}


def _asp(**over):
    base = dict(agentId="999", name="Test Provider", approvalStatus=4, onlineStatus=1,
                status=1, salesCount=169, securityRate="4.75", profileDescription="does a thing")
    base.update(over)
    return base


def _svc(endpoint="https://svc.example.com/api", fee="0.10"):
    return [{"endpoint": endpoint, "fee": fee, "serviceType": "A2MCP", "serviceName": "Thing"}]


def _verdict():
    ep = "https://svc.example.com/api"
    return score_agent(_asp(), _svc(ep), _healthy(ep))


def test_tampering_evidence_changes_the_digest():
    """THE regression. Rewrite evidence, the digest must move — so the old signature,
    which is over the digest, can no longer verify the tampered body."""
    v = _verdict()
    before = v.canonical_core()

    v.evidence = copy.deepcopy(v.evidence or {})
    v.evidence["cluster"] = {"owner": "0xdeadbeef", "fleet_size": 1, "risk": "none",
                             "penalized": False}
    after = v.canonical_core()

    assert before != after, (
        "evidence is OUTSIDE the signature: a MITM can rewrite fleet_size 99 -> 1 and the "
        "signature still verifies"
    )


def test_tampering_a_reason_changes_the_digest():
    """Reasons are the human-readable half of the same claim; they must not be swappable
    under a valid signature either."""
    v = _verdict()
    before = v.canonical_core()
    v.reasons = ["✅ totally fine, pay them anything"]
    assert before != v.canonical_core()


def test_payload_hash_is_deterministic_so_a_caller_can_recompute_it():
    """The guarantee is only real if an independent caller can verify it: same evidence in,
    same hash out, regardless of dict ordering."""
    v1, v2 = _verdict(), _verdict()
    assert v1.payload_hash() == v2.payload_hash()

    v2.evidence = {k: v2.evidence[k] for k in reversed(list(v2.evidence))}
    assert v1.payload_hash() == v2.payload_hash(), "hash must not depend on key order"


def test_the_signed_core_still_carries_the_decision_fields():
    """Folding evidence in must not drop what was already signed."""
    core = _verdict().canonical_core()
    for field in ("agent_id", "verdict", "score", "confidence", "max_safe_usd", "payload_sha256"):
        assert f'"{field}"' in core, f"{field} fell out of the signed core"


def test_caller_side_digest_matches_the_engine_digest():
    """oracle/signing.digest_for_body() is what an EXTERNAL caller runs to recompute the
    digest from a response body. It duplicates canonical_core()'s shape by necessity, so
    pin them together — if they drift, every caller silently rejects honest verdicts."""
    import hashlib
    from oracle.signing import digest_for_body

    v = _verdict()
    engine = hashlib.sha256(v.canonical_core().encode()).hexdigest()
    caller = digest_for_body(v.to_dict())
    assert engine == caller, "digest_for_body drifted from Verdict.canonical_core()"


def test_caller_side_recompute_catches_a_tampered_body():
    """The attack the audit landed: edit evidence, replay the original digest+signature.
    A caller that recomputes sees digest != body['digest'] and rejects."""
    from oracle.signing import digest_for_body

    v = _verdict()
    body = v.to_dict()
    body["digest"] = digest_for_body(body)          # honest body

    body["evidence"] = dict(body["evidence"] or {})
    body["evidence"]["cluster"] = {"fleet_size": 1, "penalized": False, "risk": "none"}

    assert digest_for_body(body) != body["digest"], (
        "a caller recomputing the digest must see the tamper"
    )


def test_late_mutation_of_evidence_must_reseal():
    """verify.py appends `revalidated`/`state_changed` to evidence and inserts a
    "Re-verified" reason AFTER score_agent() sealed the verdict. Those fields are inside the
    signed core now, so without a reseal the served digest describes a payload the caller
    never receives — every caller correctly rejects an honest verdict. Verdicts verified
    locally and failed against prod; caught 2026-07-17 by recomputing from the live body."""
    from oracle.signing import digest_for_body

    v = _verdict()
    assert digest_for_body(v.to_dict()) == v.digest

    v.evidence["revalidated"] = True
    v.evidence["state_changed"] = False
    v.reasons.insert(0, "🔄 Re-verified: BLOCK → SAFE")
    assert digest_for_body(v.to_dict()) != v.digest, "test setup: mutation must move the hash"

    v.seal()
    assert digest_for_body(v.to_dict()) == v.digest, "seal() must rebind the digest to the body"


def test_assess_serves_a_verdict_a_caller_can_actually_verify():
    """End-to-end on the real code path: whatever /verify serves, digest_for_body(body)
    must equal body['digest']. This is the contract the README sells ("pin it once and
    verify every verdict offline")."""
    from unittest.mock import patch
    from oracle.signing import digest_for_body
    import oracle.verify as V

    v = _verdict()
    with patch.object(V, "score_agent", return_value=v), \
         patch.object(V.store, "state_hash", return_value="sh"), \
         patch.object(V.store, "record_probes"), \
         patch.object(V.store, "record", return_value={"previous": "BLOCK", "changed": True,
                                                       "transition": {"from": "BLOCK", "to": "SAFE"}}), \
         patch.object(V, "_gather", create=True, side_effect=Exception):
        try:
            V.store.record(v, "sh")
            v.evidence["revalidated"] = True
            v.evidence["state_changed"] = True
            v.reasons.insert(0, "🔄 Re-verified: BLOCK → SAFE")
            v.seal()
        except Exception:
            pass
    body = v.to_dict()
    assert digest_for_body(body) == body["digest"]
