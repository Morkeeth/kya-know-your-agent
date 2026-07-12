"""Ed25519 signing tests — sign a digest, verify the envelope, prove tampering
and expiry both fail."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from oracle.signing import Signer, verify_envelope  # noqa: E402


def test_sign_and_verify_roundtrip():
    s = Signer()
    digest = "a" * 64
    env = s.sign_digest(digest)
    assert env["alg"] == "ed25519"
    assert verify_envelope(digest, env) is True


def test_tampered_digest_fails():
    s = Signer()
    env = s.sign_digest("a" * 64)
    assert verify_envelope("b" * 64, env) is False


def test_tampered_score_window_fails():
    # Flipping signed_at/ttl invalidates the signature (they're signed).
    s = Signer()
    env = s.sign_digest("c" * 64)
    env["signed_at"] += 1
    assert verify_envelope("c" * 64, env) is False


def test_expired_verdict_rejected():
    s = Signer()
    env = s.sign_digest("d" * 64, ttl=300)
    # Evaluate far in the future -> past expiry -> rejected even if sig is valid.
    assert verify_envelope("d" * 64, env, at=env["expires_at"] + 1) is False
    assert verify_envelope("d" * 64, env, at=env["expires_at"] - 1) is True


def test_envelope_shape():
    env = Signer().sign_digest("e" * 64)
    for k in ("alg", "pubkey", "signature", "signed_at", "ttl", "expires_at"):
        assert k in env
