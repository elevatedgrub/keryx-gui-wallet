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
