"""
On-chain settlement reader — the Sybil killer's data source.

OKX's marketplace API hides `buyerCount` (it's null), so a wash-trader can post N
sub-cent sales from a couple of wallets and the count-based gate can't see it. But
x402 sales settle as REAL on-chain stablecoin transfers into the agent's wallet, so
the distinct SENDERS are the distinct buyers. This reads them from OKLink's X Layer
`token-transaction-list` endpoint and hands the engine {distinct_payers, volume,
per-payer totals, per-tx amounts} for concentration / wash analysis.

DEFAULT-OFF. Activated only when BOTH are set:
  - KYA_SETTLEMENT=1
  - an OKLink key in OKLINK_API_KEY (or OKX_API_KEY)

⚠️ UNVERIFIED ASSUMPTION (must be checked on a real settled tx before trusting the
distinct-payer count): that the inbound transfer's `from` is the BUYER, not an OKX
facilitator/settlement contract. If OKX routes buyer -> facilitator -> agent, every
inbound `from` is the facilitator and distinct_payers collapses to 1. Until verified,
keep this OFF. See docs/V2-RESEARCH.md and the slice-1 spike.
"""
from __future__ import annotations

import os

import httpx

_OKLINK_BASE = "https://www.oklink.com"
_TOKENS = {  # X Layer stablecoin contracts (resolved live in the slice-1 spike)
    "USDC": "0x74b7f16337b8972027f6196a17a631ac6de26d22",
    "USDT": "0x1e4a5963abfd975d8c9021ce480b42188849d41d",
}


def enabled() -> bool:
    return os.environ.get("KYA_SETTLEMENT") == "1" and bool(_api_key())


def _api_key() -> str | None:
    return os.environ.get("OKLINK_API_KEY") or os.environ.get("OKX_API_KEY") or None


def _default_get(path: str, params: dict) -> dict:
    r = httpx.get(_OKLINK_BASE + path, params=params, timeout=10.0,
                  headers={"OK-ACCESS-KEY": _api_key() or ""})
    r.raise_for_status()
    return r.json()


def fetch_settlements(wallet: str, *, get=None, max_pages: int = 5) -> dict | None:
    """Reconstruct settled volume + distinct payers for an agent wallet from inbound
    stablecoin transfers. `get(path, params) -> json` is injectable for testing.
    Returns None on no key / error, else:
      {onchain_volume, distinct_payers, payers:{addr:total}, amounts:[per-tx], tx_count}.
    """
    if get is None:
        if not enabled():
            return None
        get = _default_get
    wallet = str(wallet).strip().lower()
    if not wallet:
        return None
    payers: dict[str, float] = {}
    amounts: list[float] = []
    try:
        for contract in _TOKENS.values():
            page = 1
            while page <= max_pages:
                payload = get("/api/v5/explorer/address/token-transaction-list", {
                    "chainShortName": "XLAYER", "address": wallet, "protocolType": "token_20",
                    "tokenContractAddress": contract, "limit": 100, "page": page,
                })
                txs = _extract_txs(payload)
                if not txs:
                    break
                for tx in txs:
                    frm = str(tx.get("from") or "").strip().lower()
                    to = str(tx.get("to") or "").strip().lower()
                    amt = _to_float(tx.get("amount"))
                    if to == wallet and frm and amt and amt > 0:  # inbound only
                        payers[frm] = payers.get(frm, 0.0) + amt
                        amounts.append(amt)
                if len(txs) < 100:
                    break
                page += 1
    except (httpx.HTTPError, ValueError, KeyError):
        return None
    return {
        "onchain_volume": round(sum(amounts), 6),
        "distinct_payers": len(payers),
        "payers": payers,
        "amounts": amounts,
        "tx_count": len(amounts),
    }


def _extract_txs(payload: dict) -> list[dict]:
    """OKLink v5 nests as data[].transactionLists[] — tolerate a couple of shapes."""
    data = payload.get("data")
    if isinstance(data, list) and data:
        first = data[0]
        if isinstance(first, dict):
            return first.get("transactionLists") or first.get("transactionList") or []
    if isinstance(data, dict):
        return data.get("transactionLists") or data.get("transactionList") or []
    return []


def _to_float(x) -> float | None:
    try:
        return float(x) if x not in (None, "") else None
    except (TypeError, ValueError):
        return None
