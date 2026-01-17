# core/normalize.py
"""
Stable, public normalization API.

Everything is implemented in core/normalize_mod/.
This file exists so the rest of the app can do:
  from core.normalize import normalize_orders, ...
"""

from core.normalize_mod import (
    SHOPIFY_COLUMN_MAP,
    detect_shopify_orders,
    normalize_orders,
    normalize_shipments,
    normalize_tracking,
)

__all__ = [
    "SHOPIFY_COLUMN_MAP",
    "detect_shopify_orders",
    "normalize_orders",
    "normalize_shipments",
    "normalize_tracking",
]
