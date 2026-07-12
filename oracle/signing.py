"""
Ed25519 signing for verdicts.

A calling agent should be able to prove a verdict genuinely came from the Oracle
and wasn't altered. The engine produces a sha256 `digest` of the verdict's
canonical core; here we sign that digest with an Ed25519 key the Oracle controls
and publish the public key at /pubkey so anyone can verify offline.

Key resolution (first that works):
  1. ORACLE_SIGNING_KEY env var  — 64 hex chars (32-byte Ed25519 seed). Production.
  2. ./keys/oracle_ed25519.seed  — local dev key file (gitignored), auto-created.
  3. ephemeral in-memory key      — last resort; logs a warning (verdicts won't
                                    verify across restarts).
"""
from __future__ import annotations

import os
import time
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey, Ed25519PublicKey,
)
from cryptography.hazmat.primitives import serialization

_KEY_FILE = Path(os.environ.get("ORACLE_KEY_FILE", "keys/oracle_ed25519.seed"))
ALG = "ed25519"


def _load_or_create_key() -> tuple[Ed25519PrivateKey, str]:
    env = os.environ.get("ORACLE_SIGNING_KEY", "").strip()
    if env:
        seed = bytes.fromhex(env)
        if len(seed) != 32:
            raise ValueError("ORACLE_SIGNING_KEY must be 64 hex chars (32-byte seed)")
        return Ed25519PrivateKey.from_private_bytes(seed), "env"

    if _KEY_FILE.exists():
        seed = bytes.fromhex(_KEY_FILE.read_text().strip())
        return Ed25519PrivateKey.from_private_bytes(seed), "file"

    key = Ed25519PrivateKey.generate()
    seed = key.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    )
    try:
        _KEY_FILE.parent.mkdir(parents=True, exist_ok=True)
        _KEY_FILE.write_text(seed.hex())
        _KEY_FILE.chmod(0o600)
        return key, "file-new"
    except OSError:
        return key, "ephemeral"


class Signer:
    """Holds the Oracle's Ed25519 key and signs verdict digests."""

    def __init__(self) -> None:
        self._key, self.source = _load_or_create_key()
        self._pub_hex = self._key.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        ).hex()

    @property
    def public_key_hex(self) -> str:
        return self._pub_hex

    def sign_digest(self, digest_hex: str) -> dict:
        """Sign a verdict's sha256 digest; return an attachable signature envelope."""
        sig = self._key.sign(bytes.fromhex(digest_hex)).hex()
        return {
            "alg": ALG,
            "pubkey": self._pub_hex,
            "signature": sig,
            "signed_at": int(time.time()),
        }


def verify(digest_hex: str, signature_hex: str, pubkey_hex: str) -> bool:
    """Offline verification helper — anyone can call this with the published pubkey."""
    try:
        pub = Ed25519PublicKey.from_public_bytes(bytes.fromhex(pubkey_hex))
        pub.verify(bytes.fromhex(signature_hex), bytes.fromhex(digest_hex))
        return True
    except Exception:  # noqa: BLE001 — any failure = invalid
        return False
