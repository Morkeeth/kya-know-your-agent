"""
Content vetting — what an agent EXPOSES, not just its reputation.

A listed, well-reviewed agent can still ship a poisoned tool: instructions hidden
in a service/tool description that the calling model reads and obeys, but a human
skims past. This is the #1 MCP-specific attack ("tool poisoning", Invariant Labs
2025) and reputation/liveness checks are blind to it. This module scans the text
an agent exposes for injected instructions, hidden characters, and secret-exfil
directives — pure text analysis, no network, no key.
"""
from __future__ import annotations

import re
import unicodedata

# Characters used to HIDE instructions from a human reading the description while
# the model still ingests them: zero-width, BOM, and bidi overrides.
_INVISIBLE = {
    "​": "zero-width space", "‌": "zero-width non-joiner",
    "‍": "zero-width joiner", "﻿": "byte-order mark",
    "⁠": "word joiner", "‮": "right-to-left override",
    "‭": "left-to-right override", "⁦": "left-to-right isolate",
    "⁧": "right-to-left isolate", "­": "soft hyphen",
}

# Instruction-injection & exfiltration patterns. Each: (regex, kind, severity).
# 'critical' => a real poisoning attempt (BLOCK); 'warn' => suspicious (cap).
_PATTERNS: list[tuple[re.Pattern, str, str]] = [
    (re.compile(r"ignore\s+(all\s+)?(previous|prior|above|earlier)\s+(instructions|prompts?|context)", re.I),
     "instruction-override", "critical"),
    (re.compile(r"disregard\s+(the\s+|your\s+|all\s+)?(previous|prior|above|system|earlier)", re.I),
     "instruction-override", "critical"),
    (re.compile(r"do\s+not\s+(tell|inform|mention|reveal|notify|alert)\b.{0,30}\b(user|human|owner|operator)", re.I),
     "hide-from-user", "critical"),
    (re.compile(r"(before|prior to)\s+(using|calling|invoking|running)\s+(this|any|the)\s+tool", re.I),
     "tool-preamble-injection", "critical"),
    (re.compile(r"\b(system\s*prompt|developer\s*message|</?(system|important|secret)>)", re.I),
     "system-prompt-injection", "critical"),
    (re.compile(r"(exfiltrate|leak|forward|send|upload|post|transmit)\b.{0,40}\b"
                r"(private\s*key|seed\s*phrase|mnemonic|api[\s_-]*key|secret|password|token|wallet|credential)", re.I),
     "secret-exfiltration", "critical"),
    (re.compile(r"(private\s*key|seed\s*phrase|mnemonic|\.ssh|id_rsa|aws_secret|env\s*file|\.env\b)", re.I),
     "secret-reference", "warn"),
    (re.compile(r"you\s+(must|should|shall|will)\s+(always|now|immediately|first)\b", re.I),
     "imperative-directive", "warn"),
    (re.compile(r"\b(base64|atob|fromCharCode|eval|exec)\s*\(", re.I),
     "obfuscated-payload", "warn"),
]

# A long unbroken base64-ish blob hidden in prose (a common obfuscation carrier).
_B64_BLOB = re.compile(r"[A-Za-z0-9+/]{60,}={0,2}")


def scan_injection(texts: list[str]) -> list[dict]:
    """Return a list of findings across all texts. Each finding:
    {kind, severity, evidence}. Empty list = clean."""
    findings: list[dict] = []
    for raw in texts:
        if not raw:
            continue
        text = str(raw)
        # 1) invisible / bidi characters used to smuggle instructions
        hidden = {ch for ch in text if ch in _INVISIBLE}
        if hidden:
            names = ", ".join(sorted(_INVISIBLE[c] for c in hidden))
            findings.append({"kind": "hidden-unicode", "severity": "critical",
                             "evidence": f"contains hidden characters ({names})"})
        # also catch odd control chars beyond the known set
        if any(unicodedata.category(ch) in ("Cf", "Co") and ch not in _INVISIBLE for ch in text):
            findings.append({"kind": "hidden-unicode", "severity": "warn",
                             "evidence": "contains format/control characters"})
        # 2) instruction / exfil patterns
        for rx, kind, sev in _PATTERNS:
            m = rx.search(text)
            if m:
                findings.append({"kind": kind, "severity": sev,
                                 "evidence": _snippet(text, m.start(), m.end())})
        # 3) long obfuscated blob
        b = _B64_BLOB.search(text)
        if b and " " not in text[b.start():b.end()]:
            findings.append({"kind": "obfuscated-payload", "severity": "warn",
                             "evidence": f"long opaque blob ({b.end()-b.start()} chars)"})
    return _dedupe(findings)


def gather_texts(agent_info: dict | None, services: list[dict]) -> list[str]:
    """All human/model-facing text an agent exposes via the marketplace record."""
    out = [(agent_info or {}).get("profileDescription") or "",
           (agent_info or {}).get("name") or ""]
    for s in services or []:
        out.append(s.get("serviceName") or "")
        out.append(s.get("serviceDescription") or "")
    return [t for t in out if t]


def _snippet(text: str, start: int, end: int, pad: int = 24) -> str:
    a, b = max(0, start - pad), min(len(text), end + pad)
    return ("…" if a else "") + text[a:b].replace("\n", " ").strip() + ("…" if b < len(text) else "")


def _dedupe(findings: list[dict]) -> list[dict]:
    seen, out = set(), []
    for f in findings:
        key = (f["kind"], f["evidence"])
        if key not in seen:
            seen.add(key)
            out.append(f)
    return out
