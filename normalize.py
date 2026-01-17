"""
Thin compatibility wrapper.
Real implementations live in core/normalize/.
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
