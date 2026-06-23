"""
price.py — fetch the KRX/USDT price from the NonKYC public API.

NonKYC's public REST API exposes market tickers. The exact ticker path can vary
by deployment; we try the documented forms in order and return the first that
yields a usable last price. No API key is required for public market data.

If the network is unavailable or the symbol isn't found, get_krx_usdt_price()
returns None and the caller simply omits the USD value — the wallet still works
fully offline.
"""

from __future__ import annotations

import json
import time
import urllib.request
import urllib.error
from typing import Optional

# Market symbol on NonKYC. KRX quoted in USDT.
SYMBOL = "KRX_USDT"
SYMBOL_SLASH = "KRX/USDT"

# Candidate endpoints (tried in order). NonKYC's public market data lives under
# api.nonkyc.io/api/v2. Different builds expose the ticker as getbysymbol or via
# the markets list; we try the specific lookup first, then fall back to scanning
# the full market list for the KRX/USDT pair.
_GETBYSYMBOL_URLS = [
    f"https://api.nonkyc.io/api/v2/market/getbysymbol/{SYMBOL}",
    f"https://api.nonkyc.io/api/v2/ticker/{SYMBOL}",
]
_MARKETS_URL = "https://api.nonkyc.io/api/v2/market/getlist"

_TIMEOUT = 6
_MAX_BYTES = 8 * 1024 * 1024  # cap response size (memory-exhaustion guard)


def _http_get_json(url: str):
    if not url.lower().startswith("https://"):
        raise ValueError("Refusing non-HTTPS URL.")
    req = urllib.request.Request(url, headers={"User-Agent": "keryx-wallet/1.0"})
    with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
        data = resp.read(_MAX_BYTES + 1)
        if len(data) > _MAX_BYTES:
            raise ValueError("Price response too large.")
        return json.loads(data.decode("utf-8", "replace"))


def _extract_last_price(obj) -> Optional[float]:
    """Pull a last-price float from a ticker-like dict, trying common keys."""
    if not isinstance(obj, dict):
        return None
    for key in ("lastPrice", "last_price", "last", "lastPriceNumber",
                "price", "lastTradePrice"):
        if key in obj and obj[key] not in (None, "", "0"):
            try:
                val = float(obj[key])
                if val > 0:
                    return val
            except (TypeError, ValueError):
                continue
    return None


# Cache the last good price so the periodic balance refresh (every ~10s) doesn't
# hit the price API on every tick — the price barely moves between ticks and
# hammering the public endpoint risks rate-limiting.
_CACHE_TTL = 60.0  # seconds
_cache_price: Optional[float] = None
_cache_ts: float = 0.0


def get_krx_usdt_price() -> Optional[float]:
    """
    Return the current KRX price in USDT (≈ USD), or None if unavailable.
    Cached for up to _CACHE_TTL seconds; on a miss it refetches and, on success,
    refreshes the cache. A failed refetch returns the last cached value if any.
    """
    global _cache_price, _cache_ts
    now = time.monotonic()
    if _cache_price is not None and (now - _cache_ts) < _CACHE_TTL:
        return _cache_price
    price = _fetch_krx_usdt_price()
    if price is not None:
        _cache_price = price
        _cache_ts = now
        return price
    # Refetch failed — fall back to the last known price rather than flicker to
    # "no value" on a transient network blip.
    return _cache_price


def _fetch_krx_usdt_price() -> Optional[float]:
    """
    Return the current KRX price in USDT (≈ USD), or None if unavailable.
    Tries the direct symbol lookup, then falls back to scanning the market list.
    """
    # 1) Direct symbol lookup.
    for url in _GETBYSYMBOL_URLS:
        try:
            data = _http_get_json(url)
        except Exception:
            continue
        price = _extract_last_price(data)
        if price is not None:
            return price
        # Some APIs wrap the ticker in {"data": {...}} or a list.
        if isinstance(data, dict) and isinstance(data.get("data"), dict):
            price = _extract_last_price(data["data"])
            if price is not None:
                return price

    # 2) Fall back to the full market list, find KRX/USDT.
    try:
        markets = _http_get_json(_MARKETS_URL)
    except Exception:
        return None
    items = markets
    if isinstance(markets, dict):
        items = markets.get("data") or markets.get("markets") or []
    if not isinstance(items, list):
        return None
    for m in items:
        if not isinstance(m, dict):
            continue
        sym = str(m.get("symbol") or m.get("market") or m.get("pair") or "")
        sym_norm = sym.replace("-", "/").replace("_", "/").upper()
        if sym_norm == SYMBOL_SLASH:
            price = _extract_last_price(m)
            if price is not None:
                return price
    return None
