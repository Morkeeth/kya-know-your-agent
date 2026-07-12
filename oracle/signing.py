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
_DEFAULT_TTL = int(os.environ.get("ORACLE_VERDICT_TTL", "300"))  # seconds
ALG = "ed25519"


def _message(digest_hex: str, issued_at: int, ttl: int) -> bytes:
    """The exact bytes we sign — binds the verdict to a freshness window so a
    SAFE verdict can't be replayed after it expires."""
    return f"{digest_hex}.{issued_at}.{ttl}".encode()


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

    def sign_digest(self, digest_hex: str, ttl: int | None = None) -> dict:
        """Sign a verdict digest + freshness window; return an attachable envelope."""
        issued_at = int(time.time())
        ttl = _DEFAULT_TTL if ttl is None else ttl
        sig = self._key.sign(_message(digest_hex, issued_at, ttl)).hex()
        return {
            "alg": ALG,
            "pubkey": self._pub_hex,
            "signature": sig,
            "signed_at": issued_at,
            "ttl": ttl,
            "expires_at": issued_at + ttl,
        }


def verify_envelope(digest_hex: str, env: dict, at: int | None = None) -> bool:
    """Verify a signed verdict envelope: signature valid AND not expired."""
    now = int(time.time()) if at is None else at
    if now > env.get("expires_at", 0):
        return False
    return verify(_message(digest_hex, env["signed_at"], env["ttl"]),
                  env["signature"], env["pubkey"])


def verify(message: bytes | str, signature_hex: str, pubkey_hex: str) -> bool:
    """Low-level Ed25519 verify over raw message bytes."""
    if isinstance(message, str):
        message = message.encode()
    try:
        pub = Ed25519PublicKey.from_public_bytes(bytes.fromhex(pubkey_hex))
        pub.verify(bytes.fromhex(signature_hex), message)
        return True
    except Exception:  # noqa: BLE001 — any failure = invalid
        return False
