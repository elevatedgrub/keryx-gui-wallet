"""
config.py — tiny persistent settings for the Keryx wallet GUI.

Stores non-sensitive UI preferences (currently just the last node address
connected to) in ~/.keryx-wallet-gui.json. Never stores passwords, keys, or
mnemonics.
"""

from __future__ import annotations

import os
import json
from typing import Any, Dict

_CONFIG_PATH = os.path.expanduser("~/.keryx-wallet-gui.json")


def load() -> Dict[str, Any]:
    try:
        with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save(data: Dict[str, Any]) -> None:
    try:
        with open(_CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f)
    except Exception:
        pass  # settings are best-effort; never block the app on a write failure


def get_last_node() -> str:
    return str(load().get("last_node", "") or "")


def set_last_node(address: str) -> None:
    data = load()
    data["last_node"] = (address or "").strip()
    save(data)


def get_language() -> str:
    return str(load().get("language", "") or "")


def set_language(lang: str) -> None:
    data = load()
    data["language"] = (lang or "").strip()
    save(data)


# ── Account display order (per wallet, keyed by wallet id) ───────────────────
# keryx-cli has no stable account index — `list`/`select` order changes when an
# account is renamed (it re-appends). We persist a stable display order per
# wallet so the account dropdown doesn't jump around.
def get_account_order(wallet_id: str) -> list:
    if not wallet_id:
        return []
    orders = load().get("account_order", {}) or {}
    val = orders.get(wallet_id, [])
    return list(val) if isinstance(val, list) else []


def set_account_order(wallet_id: str, ids: list) -> None:
    if not wallet_id:
        return
    data = load()
    orders = data.get("account_order", {})
    if not isinstance(orders, dict):
        orders = {}
    orders[wallet_id] = list(ids)
    data["account_order"] = orders
    save(data)


def get_has_passphrase(wallet_id: str) -> bool:
    """Whether this wallet is known to use a BIP39 passphrase (learned the first
    time an operation hits the 'Enter payment password' prompt)."""
    if not wallet_id:
        return False
    d = load().get("has_passphrase", {}) or {}
    return bool(d.get(wallet_id, False))


def set_has_passphrase(wallet_id: str, value: bool = True) -> None:
    if not wallet_id:
        return
    data = load()
    d = data.get("has_passphrase", {})
    if not isinstance(d, dict):
        d = {}
    d[wallet_id] = bool(value)
    data["has_passphrase"] = d
    save(data)


def get_order_locked(wallet_id: str) -> bool:
    """True once the user has manually reordered this wallet's accounts. A manual
    order is respected as-is (the automatic main-account pin is not applied)."""
    if not wallet_id:
        return False
    locks = load().get("account_order_locked", {}) or {}
    return bool(locks.get(wallet_id, False))


def set_order_locked(wallet_id: str, locked: bool = True) -> None:
    if not wallet_id:
        return
    data = load()
    locks = data.get("account_order_locked", {})
    if not isinstance(locks, dict):
        locks = {}
    locks[wallet_id] = bool(locked)
    data["account_order_locked"] = locks
    save(data)


def get_main_account(wallet_id: str) -> str:
    """The hex id of the wallet's main account (derivation index 0), if known.

    keryx-cli exposes no stable account index, but a wallet seen with exactly one
    account must be showing its main account — we record that id so it can be
    pinned first in the switcher even after it's renamed (which reorders keryx).
    """
    if not wallet_id:
        return ""
    mains = load().get("main_account", {}) or {}
    return str(mains.get(wallet_id, "") or "")


def set_main_account(wallet_id: str, account_id: str) -> None:
    if not wallet_id or not account_id:
        return
    data = load()
    mains = data.get("main_account", {})
    if not isinstance(mains, dict):
        mains = {}
    if mains.get(wallet_id) == account_id:
        return
    mains[wallet_id] = account_id
    data["main_account"] = mains
    save(data)


# ── Address book ─────────────────────────────────────────────────────────
def get_address_book() -> list:
    """Return saved addresses as a list of {"label": str, "address": str}."""
    data = load()
    book = data.get("address_book", [])
    return book if isinstance(book, list) else []


def save_address_book(entries: list) -> None:
    data = load()
    data["address_book"] = entries
    save(data)


def add_address(label: str, address: str) -> None:
    label = (label or "").strip()
    address = (address or "").strip()
    if not address:
        return
    book = get_address_book()
    # Update if the address already exists, else append.
    for e in book:
        if e.get("address") == address:
            e["label"] = label
            save_address_book(book)
            return
    book.append({"label": label, "address": address})
    save_address_book(book)


def remove_address(address: str) -> None:
    book = [e for e in get_address_book() if e.get("address") != address]
    save_address_book(book)
