# normalize.py
"""
Backwards-compatible normalization API (root-level import).

Keeps old imports working:
  from normalize import normalize_orders, ...
"""

from core.normalize import (
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
