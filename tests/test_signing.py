"""Ed25519 signing tests — verify against a PINNED key, and prove the red-team's
forgery and replay attacks fail."""
import sys
import time
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from oracle.signing import Signer, verify_envelope, _message  # noqa: E402


def _pub(s: Signer) -> str:
    return s.public_key_hex


def test_sign_and_verify_roundtrip():
    s = Signer()
    digest = "a" * 64
    env = s.sign_digest(digest)
    assert env["alg"] == "ed25519"
    assert verify_envelope(digest, env, expected_pubkey=_pub(s)) is True


def test_tampered_digest_fails():
    s = Signer()
    env = s.sign_digest("a" * 64)
    assert verify_envelope("b" * 64, env, expected_pubkey=_pub(s)) is False


def test_forged_self_signed_verdict_fails():
    """Red-team #2: attacker self-signs SAFE with THEIR key and ships their pubkey.
    Must fail because we pin the Oracle's key."""
    real = Signer()
    attacker = Ed25519PrivateKey.generate()
    digest = "c" * 64
    issued, ttl = int(time.time()), 300
    forged = {
        "alg": "ed25519",
        "pubkey": attacker.public_key().public_bytes(
            encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw).hex(),
        "signature": attacker.sign(_message(digest, issued, ttl)).hex(),
        "signed_at": issued, "ttl": ttl, "expires_at": issued + ttl,
    }
    # Self-consistent, but not the Oracle's key -> rejected.
    assert verify_envelope(digest, forged, expected_pubkey=_pub(real)) is False


def test_replay_via_tampered_expires_at_fails():
    """Red-team #3: bump the UNSIGNED expires_at on an old verdict to replay it.
    Must fail because expiry is recomputed from the signed signed_at+ttl."""
    s = Signer()
    env = s.sign_digest("d" * 64, ttl=300)
    env["expires_at"] = 9_999_999_999  # attacker lies about expiry
    # Evaluate well past the real (signed) window -> still rejected.
    assert verify_envelope("d" * 64, env, expected_pubkey=_pub(s),
                           at=env["signed_at"] + 10_000) is False


def test_expiry_boundary():
    s = Signer()
    env = s.sign_digest("e" * 64, ttl=300)
    assert verify_envelope("e" * 64, env, expected_pubkey=_pub(s), at=env["signed_at"] + 299) is True
    assert verify_envelope("e" * 64, env, expected_pubkey=_pub(s), at=env["signed_at"] + 301) is False


def test_envelope_shape():
    env = Signer().sign_digest("f" * 64)
    for k in ("alg", "pubkey", "signature", "signed_at", "ttl", "expires_at"):
        assert k in env
