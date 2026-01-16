# ui/onboarding_ui.py
from __future__ import annotations

import streamlit as st


def render_onboarding_checklist(
    *,
    title: str = "ClearOps onboarding checklist (14 steps)",
    expanded: bool = True,
) -> None:
    with st.expander(title, expanded=expanded):
        st.markdown(
            """
### What is ClearOps?

**ClearOps** gives you operational clarity by turning messy order, shipment,
and tracking data into **clear exceptions, follow-ups, and actions**.

It helps teams:
- See what’s broken (and why)
- Prioritize Critical and High-risk issues
- Track supplier follow-ups
- Communicate proactively with customers
- Build trend history over time

You can explore everything instantly using **ClearOps Demo**, or upload
your own CSVs to run against real data.
            """.strip()
        )

        st.divider()

        st.markdown(
            """
1. Enter **Early Access Code**  
2. Verify your **work email** (allowlist gate)  
3. Set **Tenant**: `account_id`, `store_id`, `platform_hint`  
4. Set **Defaults**: currency + promised ship days (SLA)  
5. (Optional) Turn on **ClearOps Demo (Sticky)** to explore instantly  
6. (Demo) Use **Edit demo data** to simulate real scenarios  
7. Upload **Orders CSV** (required if not using demo)  
8. Upload **Shipments CSV** (required if not using demo)  
9. Upload **Tracking CSV** (optional but recommended)  
10. Download **Templates** if you need the correct format  
11. Upload **suppliers.csv** to auto-fill supplier follow-ups  
12. Review **Ops Triage** (start with Critical + High)  
13. Work the **Exceptions Queue** (filter by supplier, country, urgency)  
14. Use **Ops Outreach (Comms)**, then **Save Run** to build trends and history
            """.strip()
        )
