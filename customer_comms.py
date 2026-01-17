# core/customer_comms.py
def build_customer_email_draft(order_id: str, customer_email: str, reason: str = "") -> dict:
    order_id = (order_id or "").strip()
    customer_email = (customer_email or "").strip()
    reason = (reason or "").strip()

    subject = f"Update on your order {order_id}".strip() if order_id else "Update on your order"

    body_lines = [
        "Hi there,",
        "",
        f"We’re reaching out with an update on your order {order_id}." if order_id else "We’re reaching out with an update on your order.",
    ]
    if reason:
        body_lines += ["", f"Update: {reason}"]

    body_lines += [
        "",
        "What we’re doing next:",
        "• We’ve contacted the supplier/carrier and requested an immediate status update.",
        "• We’re monitoring the shipment and will keep you updated as soon as we have confirmed details.",
        "• If we cannot confirm progress quickly, we will offer next steps (replacement, refund, or alternative).",
        "",
        "Thank you for your patience — we’ll follow up again soon.",
        "",
        "Best,",
    ]

    return {"to": customer_email, "subject": subject, "body": "\n".join(body_lines)}
