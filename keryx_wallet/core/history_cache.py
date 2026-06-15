"""
history_cache.py — persist an address's fetched transaction history between
runs so the wallet shows it instantly on startup, then only fetches the few
new transactions that arrived since last time.

Cache lives in ~/.keryx-wallet-history.json as:
    { "<address>": { "txs": [ <tx dict>, ... ] }, ... }

Transactions are stored newest-first (the same order the UI renders). Only
non-sensitive public chain data is cached — never keys or passwords.
"""

from __future__ import annotations

import os
import json
from typing import List, Dict, Any

_CACHE_PATH = os.path.expanduser("~/.keryx-wallet-history.json")

# Safety cap so a runaway address can't bloat the cache file without bound.
_MAX_CACHED_PER_ADDRESS = 50_000


def _load_all() -> Dict[str, Any]:
    try:
        with open(_CACHE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_all(data: Dict[str, Any]) -> None:
    try:
        # Write atomically-ish: temp then replace, so a crash mid-write doesn't
        # corrupt the cache.
        tmp = _CACHE_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f)
        os.replace(tmp, _CACHE_PATH)
    except Exception:
        pass


def get_cached(address: str) -> List[Dict[str, Any]]:
    """Return the cached tx list for an address (newest-first), or []."""
    address = (address or "").strip()
    if not address:
        return []
    entry = _load_all().get(address)
    if isinstance(entry, dict) and isinstance(entry.get("txs"), list):
        return entry["txs"]
    return []


def set_cached(address: str, txs: List[Dict[str, Any]]) -> None:
    """Replace the cached tx list for an address (expects newest-first)."""
    address = (address or "").strip()
    if not address:
        return
    data = _load_all()
    data[address] = {"txs": txs[:_MAX_CACHED_PER_ADDRESS]}
    _save_all(data)


def known_tx_ids(address: str) -> set:
    """Set of tx_ids already cached for this address (for incremental fetch)."""
    return {t.get("tx_id") for t in get_cached(address) if t.get("tx_id")}


def merge_new(address: str, new_txs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Prepend genuinely-new txs (by tx_id) to the cached list, persist, and
    return the merged newest-first list. `new_txs` should be newest-first."""
    address = (address or "").strip()
    if not address:
        return new_txs or []
    cached = get_cached(address)
    seen = {t.get("tx_id") for t in cached if t.get("tx_id")}
    fresh = [t for t in (new_txs or []) if t.get("tx_id") and t["tx_id"] not in seen]
    merged = fresh + cached if fresh else cached
    if fresh:
        set_cached(address, merged)
    return merged
