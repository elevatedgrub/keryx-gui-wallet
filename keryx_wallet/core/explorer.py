"""
explorer.py — fetch an address's full transaction history from the Keryx
explorer API.

Keryx is a full Kaspa fork ("Full Kaspa -> Keryx rebrand") with an "Explorer +
API (real-time, PostgreSQL indexed)". The Kaspa-lineage explorer REST API
exposes address history at:

    GET /addresses/{address}/full-transactions?limit=N&offset=M

Querying by ADDRESS returns the true, complete on-chain history regardless of
which local wallet instance is open — unlike the CLI's per-instance history.

The API base URL is configurable (set KERYX_EXPLORER_API or pass base_url). We
try a few likely bases. If none respond, get_address_transactions() returns
None and the caller can fall back to the CLI history.
"""

from __future__ import annotations

import os
import json
import urllib.request
import urllib.parse
import urllib.error
from typing import Optional, List, Dict, Any

# Confirmed Keryx explorer API: GET /api/v1/addresses/{address}
# returns {"address","total_received_sompi","total_tx_count","transactions":[
#   {"address","amount_sompi","block_hash","daa_score","is_spend","tx_id"}, ...]}
# amount_sompi is the SIGNED net effect on this address (negative = outgoing).
_DEFAULT_BASES = [
    "https://keryx-labs.com/api/v1",
]

# The address resource itself carries the transaction list.
_TX_PATHS = [
    "/addresses/{addr}",
]

_TIMEOUT = 8
# Cap how much we read so a malicious/compromised endpoint can't exhaust memory
# with an unbounded response. Real explorer responses are tiny.
_MAX_BYTES = 8 * 1024 * 1024  # 8 MB


def _bases() -> List[str]:
    # The KERYX_EXPLORER_API override is honoured ONLY if it is HTTPS. A non-TLS
    # (or otherwise malformed) override is ignored and we fall back to the
    # built-in default, so the override can never downgrade the connection to
    # plaintext or point at a non-HTTPS scheme.
    env = os.environ.get("KERYX_EXPLORER_API", "").strip()
    if env and env.lower().startswith("https://"):
        return [env.rstrip("/")]
    return [b.rstrip("/") for b in _DEFAULT_BASES]


def _http_get_json(url: str):
    # Defense in depth: only HTTPS reaches the network here.
    if not url.lower().startswith("https://"):
        raise ValueError("Refusing non-HTTPS explorer URL.")
    req = urllib.request.Request(url, headers={"User-Agent": "keryx-wallet/1.0"})
    with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
        data = resp.read(_MAX_BYTES + 1)
        if len(data) > _MAX_BYTES:
            raise ValueError("Explorer response too large.")
        return json.loads(data.decode("utf-8", "replace"))


def get_address_transactions(address: str, limit: int = 1_000_000,
                             base_url: str = "",
                             stop_at_ids: set = None
                             ) -> Optional[List[Dict[str, Any]]]:
    """
    Return a list of normalized transaction dicts for the given address, newest
    first, or None if the explorer can't be reached.

    Each dict: {
        "tx_id": str,
        "amount": float,     # net effect on this address in KRX (+in / -out)
        "direction": str,    # "incoming" | "outgoing"
        "block_time": int,   # ms epoch (0 if unknown)
        "accepting_daa": int # DAA score (0 if unknown)
    }
    """
    address = (address or "").strip()
    if not address:
        return None

    bases = [base_url.rstrip("/")] if base_url else _bases()
    enc_addr = urllib.parse.quote(address, safe="")

    # Find a working base/path and KEEP its first page (avoids a throwaway probe
    # followed by a duplicate offset=0 fetch).
    PAGE = 100
    working = None
    first_raw = None
    for base in bases:
        for tmpl in _TX_PATHS:
            path = tmpl.format(addr=enc_addr)
            url = f"{base}{path}?{urllib.parse.urlencode({'limit': PAGE, 'offset': 0})}"
            try:
                first_raw = _http_get_json(url)
                if first_raw is not None:
                    working = (base, tmpl)
                    break
            except Exception:
                continue
        if working:
            break
    if not working:
        return None

    base, tmpl = working
    path = tmpl.format(addr=enc_addr)

    # Page through with limit+offset until a short/empty page or the cap. The
    # first page is already fetched above, so start the loop using it.
    collected = []
    seen_ids = set()
    offset = 0
    raw = first_raw
    while len(collected) < limit:
        if raw is None:
            q = urllib.parse.urlencode({"limit": PAGE, "offset": offset})
            url = f"{base}{path}?{q}"
            try:
                raw = _http_get_json(url)
            except Exception:
                break
        page_txs = raw.get("transactions") if isinstance(raw, dict) else raw
        if not isinstance(page_txs, list) or not page_txs:
            break
        new_count = 0
        hit_known = False
        for tx in page_txs:
            if not isinstance(tx, dict):
                continue
            tid = tx.get("tx_id") or tx.get("transaction_id") or ""
            # Incremental mode: if we reach a tx we already have cached, we've
            # caught up — collect the rest of THIS page then stop paging.
            if stop_at_ids and tid and tid in stop_at_ids:
                hit_known = True
                continue
            if tid and tid in seen_ids:
                continue
            if tid:
                seen_ids.add(tid)
            collected.append(tx)
            new_count += 1
        if hit_known:
            break
        # End of history: a partial page, or this page added nothing new (which
        # would mean the API ignored offset and repeated — a safety stop).
        if new_count == 0 or len(page_txs) < PAGE:
            break
        offset += PAGE
        raw = None  # force a fresh fetch for the next page

    txs = collected
    if not isinstance(txs, list):
        return None

    out = []
    for tx in txs:
        if not isinstance(tx, dict):
            continue
        tx_id = tx.get("tx_id") or tx.get("transaction_id") or tx.get("hash") or ""
        amt_sompi = tx.get("amount_sompi")
        if amt_sompi is None:
            # Fallback: derive from total_out / is_spend if amount missing.
            amt_sompi = tx.get("total_out_sompi") or 0
            if tx.get("is_spend"):
                amt_sompi = -abs(int(amt_sompi))
        try:
            amt_sompi = int(amt_sompi)
        except (TypeError, ValueError):
            amt_sompi = 0
        amount_krx = amt_sompi / 1e8  # 1 KRX = 1e8 sompi
        daa = tx.get("daa_score") or tx.get("accepting_daa_score") or 0
        is_spend = bool(tx.get("is_spend"))
        direction = "outgoing" if (is_spend or amt_sompi < 0) else "incoming"

        out.append({
            "tx_id": tx_id,
            "amount": amount_krx,
            "direction": direction,
            "block_time": 0,          # not provided by this endpoint
            "accepting_daa": int(daa) if daa else 0,
            "block_hash": tx.get("block_hash", ""),
        })

    # Newest first by DAA score (higher = more recent).
    out.sort(key=lambda t: t["accepting_daa"], reverse=True)
    return out


def get_utxo_count(address: str, base_url: str = "") -> Optional[int]:
    """
    Return the number of UTXOs currently held by the address, or None if the
    explorer can't be reached. Uses the confirmed /addresses/<addr>/utxos
    endpoint (returns a JSON list of UTXO entries).
    """
    address = (address or "").strip()
    if not address:
        return None
    bases = [base_url.rstrip("/")] if base_url else _bases()
    enc_addr = urllib.parse.quote(address, safe="")
    for base in bases:
        url = f"{base}/addresses/{enc_addr}/utxos"
        try:
            data = _http_get_json(url)
        except Exception:
            continue
        if isinstance(data, list):
            return len(data)
        if isinstance(data, dict):
            # Some deployments wrap as {"utxos": [...]} or {"data": [...]}.
            for key in ("utxos", "data", "entries"):
                if isinstance(data.get(key), list):
                    return len(data[key])
            # Or report a count field directly.
            for key in ("count", "utxo_count", "total"):
                if isinstance(data.get(key), int):
                    return data[key]
    return None

