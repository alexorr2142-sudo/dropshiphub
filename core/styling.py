# core/styling.py
from __future__ import annotations

import pandas as pd
import streamlit.components.v1 as components


def copy_button(text: str, label: str, key: str):
    safe_text = (
        str(text)
        .replace("\\", "\\\\")
        .replace("`", "\\`")
        .replace("${", "\\${")
    )
    html = f"""
    <div style="margin: 0.25rem 0;">
      <button
        id="btn-{key}"
        style="
          padding: 0.45rem 0.75rem;
          border-radius: 0.5rem;
          border: 1px solid rgba(49, 51, 63, 0.2);
          background: white;
          cursor: pointer;
          font-size: 0.9rem;
        "
        onclick="navigator.clipboard.writeText(`{safe_text}`)
          .then(() => {{
            const b = document.getElementById('btn-{key}');
            const old = b.innerText;
            b.innerText = 'Copied ✅';
            setTimeout(() => b.innerText = old, 1200);
          }})
          .catch(() => alert('Copy failed. Your browser may block clipboard access.'));">

        {label}
      </button>
    </div>
    """
    components.html(html, height=55)


def add_urgency_column(exceptions_df: pd.DataFrame) -> pd.DataFrame:
    """
    Adds an ordered categorical Urgency column:
      Critical > High > Medium > Low
    """
    if exceptions_df is None or exceptions_df.empty:
        return exceptions_df if isinstance(exceptions_df, pd.DataFrame) else pd.DataFrame()

    df = exceptions_df.copy()

    def classify_row(row) -> str:
        issue_type = str(row.get("issue_type", "")).lower()
        explanation = str(row.get("explanation", "")).lower()
        next_action = str(row.get("next_action", "")).lower()
        risk = str(row.get("customer_risk", "")).lower()
        line_status = str(row.get("line_status", "")).lower()
        blob = " ".join([issue_type, explanation, next_action, risk, line_status])

        critical_terms = [
            "late", "past due", "overdue", "late unshipped",
            "missing tracking", "no tracking", "tracking missing",
            "carrier exception", "exception", "lost", "stuck", "seized",
            "returned to sender", "address missing", "missing address",
        ]
        if any(t in blob for t in critical_terms):
            return "Critical"

        high_terms = [
            "partial", "partial shipment",
            "mismatch", "quantity mismatch",
            "invalid tracking", "tracking invalid",
            "carrier unknown", "unknown carrier",
        ]
        if any(t in blob for t in high_terms):
            return "High"

        medium_terms = ["verify", "check", "confirm", "format", "invalid", "missing", "contact"]
        if any(t in blob for t in medium_terms):
            return "Medium"

        return "Low"

    df["Urgency"] = df.apply(classify_row, axis=1)
    df["Urgency"] = pd.Categorical(
        df["Urgency"],
        categories=["Critical", "High", "Medium", "Low"],
        ordered=True,
    )
    return df


def style_exceptions_table(df: pd.DataFrame):
    """
    Row-highlights exceptions by Urgency.
    """
    if df is None or df.empty or "Urgency" not in df.columns:
        return df.style if isinstance(df, pd.DataFrame) else pd.DataFrame().style

    colors = {
        "Critical": "background-color: #ffd6d6;",
        "High": "background-color: #fff1cc;",
        "Medium": "background-color: #f3f3f3;",
        "Low": ""
    }

    def row_style(row):
        u = str(row.get("Urgency", "Low"))
        return [colors.get(u, "")] * len(row)

    return df.style.apply(row_style, axis=1)


def style_supplier_table(df: pd.DataFrame):
    """
    Highlights supplier rows missing supplier_email.
    """
    if df is None or df.empty or "supplier_email" not in df.columns:
        return df.style if isinstance(df, pd.DataFrame) else pd.DataFrame().style

    def _row_style(row):
        email = str(row.get("supplier_email", "")).strip()
        if email == "" or email.lower() in ["nan", "none"]:
            return ["background-color: #fff1cc;"] * len(row)
        return [""] * len(row)

    return df.style.apply(_row_style, axis=1)
