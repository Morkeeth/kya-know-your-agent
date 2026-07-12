"""Ed25519 signing tests — sign a digest, verify it, and prove tampering fails."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from oracle.signing import Signer, verify  # noqa: E402


def test_sign_and_verify_roundtrip():
    s = Signer()
    digest = "a" * 64
    env = s.sign_digest(digest)
    assert env["alg"] == "ed25519"
    assert verify(digest, env["signature"], env["pubkey"]) is True


def test_tampered_digest_fails_verification():
    s = Signer()
    env = s.sign_digest("a" * 64)
    assert verify("b" * 64, env["signature"], env["pubkey"]) is False


def test_wrong_pubkey_fails():
    s1, s2 = Signer(), Signer()
    digest = "c" * 64
    env = s1.sign_digest(digest)
    # s2 has the same key file (dev), so forge a clearly-wrong pubkey instead.
    assert verify(digest, env["signature"], "00" * 32) is False


def test_envelope_has_timestamp():
    env = Signer().sign_digest("d" * 64)
    assert isinstance(env["signed_at"], int) and env["signed_at"] > 0
