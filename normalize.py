"""Backwards-compatible normalization API.

Keep this file small (<300 lines). Real implementations live in core/normalize_mod/.
"""

from __future__ import annotations

from core.normalize_mod.orders import SHOPIFY_COLUMN_MAP, detect_shopify_orders, normalize_orders
from core.normalize_mod.shipments import normalize_shipments
from core.normalize_mod.tracking import normalize_tracking
