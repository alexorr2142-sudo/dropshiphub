# core/email_utils.py
import urllib.parse

def mailto_link(to: str, subject: str, body: str) -> str:
    to = (to or "").strip()
    params = {"subject": subject or "", "body": body or ""}
    q = urllib.parse.urlencode(params, quote_via=urllib.parse.quote)
    return f"mailto:{to}?{q}"
