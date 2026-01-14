# explain.py
from __future__ import annotations

import json
import os
import time
from typing import Any, Dict, Optional

import pandas as pd
import requests

# -------------------------------
# LLM config (optional)
# -------------------------------
LLM_MODEL = os.getenv("DSH_LLM_MODEL", "gpt-4o-mini")
LLM_BASE_URL = os.getenv("DSH_LLM_BASE_URL", "https://api.openai.com/v1")
LLM_API_KEY = os.getenv("DSH_LLM_API_KEY", "")
LLM_TIMEOUT_SEC = int(os.getenv("DSH_LLM_TIMEOUT_SEC", "30"))
LLM_MAX_ROWS = int(os.getenv("DSH_LLM_MAX_ROWS", "40"))  # cost control


def _has_llm() -> bool:
    return bool(LLM_API_KEY.strip()) and bool(LLM_BASE_URL.strip())


# -------------------------------
# Rule-based fallbacks (always available)
# -------------------------------
ISSUE_TO_RISK = {
    "CARRIER_EXCEPTION": "High",
    "LATE_UNSHIPPED": "High",
    "MISSING_TRACKING": "Medium",
    "PARTIAL_SHIPMENT": "Medium",
    "UNSHIPPED": "Medium",
    "OVER_SHIPPED": "Low",
}

ISSUE_TO_ACTION = {
    "CARRIER_EXCEPTION": "Contact carrier + supplier; decide reship/refund.",
    "LATE_UNSHIPPED": "Escalate to supplier; request tracking within 24h.",
    "MISSING_TRACKING": "Request tracking number + carrier today.",
    "PARTIAL_SHIPMENT": "Request remainder ETA + tracking.",
    "UNSHIPPED": "Confirm order accepted; request estimated ship date.",
    "OVER_SHIPPED": "Verify duplicates; stop further shipments; decide return/keep policy.",
}


def _rule_explanation(row: Dict[str, Any]) -> str:
    issue = str(row.get("issue_type", "") or "")
    order_id = row.get("order_id", "")
    sku = row.get("sku", "")
    supplier = row.get("supplier_name", "") or "supplier"
    days = row.get("days_since_order", None)
    promised = row.get("promised_ship_days", None)

    if issue == "LATE_UNSHIPPED":
        if pd.notna(days) and pd.notna(promised):
            return f"Order {order_id} (SKU {sku}) is {int(days)} day(s) old and still not shipped (SLA {int(promised)} days)."
        return f"Order {order_id} (SKU {sku}) is late and still not shipped."

    if issue == "MISSING_TRACKING":
        return f"Order {order_id} (SKU {sku}) appears shipped but tracking is missing or invalid. Request carrier + tracking from {supplier}."

    if issue == "PARTIAL_SHIPMENT":
        q_shipped = row.get("quantity_shipped", None)
        q_ordered = row.get("quantity_ordered", None)
        if pd.notna(q_shipped) and pd.notna(q_ordered):
            return f"Order {order_id} (SKU {sku}) is partially shipped ({int(q_shipped)}/{int(q_ordered)})."
        return f"Order {order_id} (SKU {sku}) is partially shipped."

    if issue == "CARRIER_EXCEPTION":
        tracking = row.get("tracking_number", "")
        carrier = row.get("carrier", "")
        return f"Order {order_id} (SKU {sku}) has a carrier exception. Carrier: {carrier or '—'} Tracking: {tracking or '—'}."

    if issue == "UNSHIPPED":
        return f"Order {order_id} (SKU {sku}) is unshipped. Confirm acceptance and ship date with {supplier}."

    if issue == "OVER_SHIPPED":
        return f"Order {order_id} (SKU {sku}) may have excess shipment vs ordered quantity. Verify duplicates before further action."

    # Default
    return f"Order {order_id} (SKU {sku}) needs review."


# -------------------------------
# LLM prompt + call (OpenAI-compatible)
# -------------------------------
def _build_prompt(row: Dict[str, Any]) -> str:
    return f"""
You are an operations copilot for a dropshipping business.

Write a concise explanation and a recommended next action for the ops team.
Return STRICT JSON with keys:
- explanation: string (1–2 sentences, plain English)
- next_action: string (one clear action)
- customer_risk: one of ["Low","Medium","High"]
- confidence: integer 0–100

Context:
order_id: {row.get("order_id")}
sku: {row.get("sku")}
issue_type: {row.get("issue_type")}
supplier_name: {row.get("supplier_name")}
customer_country: {row.get("customer_country")}
quantity_ordered: {row.get("quantity_ordered")}
quantity_shipped: {row.get("quantity_shipped")}
days_since_order: {row.get("days_since_order")}
promised_ship_days: {row.get("promised_ship_days")}
carrier: {row.get("carrier")}
tracking_number: {row.get("tracking_number")}

Rule_based_explanation:
{row.get("explanation_rule_based")}
""".strip()


def _call_chat(prompt: str) -> Optional[Dict[str, Any]]:
    """
    Calls an OpenAI-compatible Chat Completions endpoint.
    If it fails for any reason, returns None.
    """
    if not _has_llm():
        return None

    url = LLM_BASE_URL.rstrip("/") + "/chat/completions"
    headers = {"Authorization": f"Bearer {LLM_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": LLM_MODEL,
        "temperature": 0.2,
        "messages": [
            {"role": "system", "content": "Output only valid JSON."},
            {"role": "user", "content": prompt},
        ],
        # Many providers support this (OpenAI does); if not supported it may error and we fall back.
        "response_format": {"type": "json_object"},
    }

    try:
        r = requests.post(url, headers=headers, json=payload, timeout=LLM_TIMEOUT_SEC)
        if r.status_code != 200:
            return None
        data = r.json()
        content = data["choices"][0]["message"]["content"]
        return json.loads(content)
    except Exception:
        return None


# -------------------------------
# Public function used by app.py
# -------------------------------
def enhance_explanations(exceptions_df: pd.DataFrame) -> pd.DataFrame:
    """
    Adds/overwrites:
      - explanation_rule_based (created if missing)
      - customer_risk
      - next_action
      - explanation (final combined)
      - llm_used (bool)
      - llm_confidence

    Safe: never raises due to LLM issues.
    """
    if exceptions_df is None or exceptions_df.empty:
        return exceptions_df

    df = exceptions_df.copy()

    # Ensure these columns exist
    if "issue_type" not in df.columns:
        df["issue_type"] = ""
    if "supplier_name" not in df.columns:
        df["supplier_name"] = ""
    if "order_id" not in df.columns:
        df["order_id"] = ""
    if "sku" not in df.columns:
        df["sku"] = ""

    # Rule-based baseline
    df["explanation_rule_based"] = df.apply(lambda r: _rule_explanation(r.to_dict()), axis=1)
    df["customer_risk"] = df["issue_type"].map(ISSUE_TO_RISK).fillna("Low")
    df["next_action"] = df["issue_type"].map(ISSUE_TO_ACTION).fillna("Review and take action.")
    df["llm_used"] = False
    df["llm_confidence"] = pd.NA

    # If no LLM configured, produce final explanation immediately
    if not _has_llm():
        df["explanation"] = df.apply(
            lambda r: f"{r['explanation_rule_based']}\nRisk: {r['customer_risk']}. Next: {r['next_action']}",
            axis=1,
        )
        return df

    # Choose rows to send to LLM (cap for cost)
    work = df.head(LLM_MAX_ROWS).copy()

    for idx, row in work.iterrows():
        prompt = _build_prompt(row.to_dict())
        result = _call_chat(prompt)

        if isinstance(result, dict) and result.get("explanation"):
            df.at[idx, "explanation_rule_based"] = str(result.get("explanation")).strip()
            df.at[idx, "next_action"] = str(result.get("next_action") or df.at[idx, "next_action"]).strip()
            df.at[idx, "customer_risk"] = str(result.get("customer_risk") or df.at[idx, "customer_risk"]).strip()
            df.at[idx, "llm_confidence"] = result.get("confidence")
            df.at[idx, "llm_used"] = True

        # tiny pause helps avoid rate-limit bursts
        time.sleep(0.05)

    # Final user-facing explanation block
    df["explanation"] = df.apply(
        lambda r: f"{r['explanation_rule_based']}\nRisk: {r['customer_risk']}. Next: {r['next_action']}",
        axis=1,
    )

    return df
