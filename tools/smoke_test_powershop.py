#!/usr/bin/env python3
"""
Local smoke test for Powershop NZ scraping (no Home Assistant runtime needed).

This script:
- Uses a logged-in cookie (recommended) OR extracts cookies/customer_id from a HAR
- Fetches Balance HTML and parses balance
- Fetches Usage CSV and parses kWh/cost records

It does NOT print cookies/tokens.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import asdict
from datetime import date, timedelta
from pathlib import Path
from typing import Dict, Optional, Tuple
from urllib.parse import urlparse

import requests

BASE_URL = "https://secure.powershop.co.nz"


def load_parsers_module():
    """Load parsers.py by filepath without importing Home Assistant."""
    import importlib.util
    import types

    root = Path(__file__).resolve().parents[1] / "custom_components"
    pkg_dir = root / "powershop_nz"

    # Fake packages for relative imports if needed later
    cc = types.ModuleType("custom_components")
    cc.__path__ = [str(root)]
    sys.modules["custom_components"] = cc

    ps = types.ModuleType("custom_components.powershop_nz")
    ps.__path__ = [str(pkg_dir)]
    sys.modules["custom_components.powershop_nz"] = ps

    spec = importlib.util.spec_from_file_location("custom_components.powershop_nz.parsers", str(pkg_dir / "parsers.py"))
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules["custom_components.powershop_nz.parsers"] = mod
    spec.loader.exec_module(mod)  # type: ignore
    return mod


PARSERS = load_parsers_module()


def _cookies_from_har(har_path: Path) -> Dict[str, str]:
    har = json.loads(har_path.read_text(encoding="utf-8"))
    entries = har.get("log", {}).get("entries", [])
    cookies: Dict[str, str] = {}

    for e in entries:
        req = e.get("request", {})
        url = req.get("url", "")
        if urlparse(url).netloc != "secure.powershop.co.nz":
            continue
        for c in req.get("cookies", []) or []:
            name = c.get("name")
            val = c.get("value")
            if name and val:
                cookies[name] = val

    return cookies


def _customer_id_from_har(har_path: Path) -> Optional[str]:
    har = json.loads(har_path.read_text(encoding="utf-8"))
    # look at page titles first (they contain /customers/<id>/...)
    for p in har.get("log", {}).get("pages", []) or []:
        title = p.get("title", "") or ""
        m = re.search(r"/customers/(\d+)", title)
        if m:
            return m.group(1)
    # fallback: look in requests
    for e in har.get("log", {}).get("entries", []) or []:
        url = (e.get("request", {}) or {}).get("url", "")
        m = re.search(r"/customers/(\d+)", url)
        if m:
            return m.group(1)
    return None


def cookie_header_from_dict(cookies: Dict[str, str]) -> str:
    # DO NOT print this.
    return "; ".join([f"{k}={v}" for k, v in cookies.items()])


def get(session: requests.Session, path: str, *, params: dict | None = None, referer: str | None = None) -> requests.Response:
    url = path if path.startswith("http") else f"{BASE_URL}{path}"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-NZ,en;q=0.9",
    }
    if referer:
        headers["Referer"] = referer
    return session.get(url, params=params, headers=headers, allow_redirects=True, timeout=30)


def assert_logged_in(resp: requests.Response) -> None:
    # heuristic: redirected to login or got login page content
    if resp.url.rstrip("/") == BASE_URL.rstrip("/"):
        # could be either homepage or login. check for obvious login markers
        if "Powershop Login" in resp.text or "<title>Powershop Login</title>" in resp.text:
            raise RuntimeError("Not logged in (got login page). Cookie likely missing/expired.")


def _looks_like_login_html(html: str) -> bool:
    h = (html or "").lower()
    return "powershop login" in h and ("csrf-token" in h or "authenticity_token" in h)


def _find_login_form_fields(html: str) -> tuple[str, dict, str, str]:
    """
    Parse login page HTML (best-effort) without external deps.
    Returns (action_url, hidden_fields, email_field, password_field).
    """
    forms = list(re.finditer(r"<form\b[^>]*>([\s\S]*?)</form>", html, flags=re.I))
    if not forms:
        raise RuntimeError("No <form> found in login HTML.")

    def score(form_html: str) -> int:
        fh = form_html.lower()
        s = 0
        if "password" in fh:
            s += 10
        if "email" in fh:
            s += 5
        if "authenticity_token" in fh:
            s += 2
        return s

    best = max(forms, key=lambda m: score(m.group(0))).group(0)

    m_action = re.search(r"<form\b[^>]*\baction=[\"']([^\"']+)[\"']", best, flags=re.I)
    action = m_action.group(1).strip() if m_action else "/"
    action_url = action if action.startswith("http") else (BASE_URL.rstrip("/") + "/" + action.lstrip("/"))

    hidden: dict = {}
    for m in re.finditer(r"<input\b[^>]*\btype=[\"']hidden[\"'][^>]*>", best, flags=re.I):
        tag = m.group(0)
        n = re.search(r"\bname=[\"']([^\"']+)[\"']", tag, flags=re.I)
        v = re.search(r"\bvalue=[\"']([^\"']*)[\"']", tag, flags=re.I)
        if n:
            hidden[n.group(1)] = v.group(1) if v else ""

    email_field = None
    pass_field = None
    for m in re.finditer(r"<input\b[^>]*>", best, flags=re.I):
        tag = m.group(0)
        name = re.search(r"\bname=[\"']([^\"']+)[\"']", tag, flags=re.I)
        _id = re.search(r"\bid=[\"']([^\"']+)[\"']", tag, flags=re.I)
        typ = re.search(r"\btype=[\"']([^\"']+)[\"']", tag, flags=re.I)
        ident = (name.group(1) if name else (_id.group(1) if _id else "")).strip()
        if not ident:
            continue
        lident = ident.lower()
        ltyp = (typ.group(1).lower() if typ else "")

        if email_field is None and (ltyp == "email" or "email" in lident):
            email_field = ident
        if pass_field is None and (ltyp == "password" or "password" in lident or lident == "pass"):
            pass_field = ident

    if not email_field or not pass_field:
        raise RuntimeError("Could not identify email/password fields in login form HTML.")

    return action_url, hidden, email_field, pass_field


def login_with_email_password(session: requests.Session, email: str, password: str) -> None:
    r = get(session, "/", referer=None)
    if r.status_code >= 400:
        raise RuntimeError(f"Login page fetch failed: HTTP {r.status_code}")
    if not _looks_like_login_html(r.text):
        raise RuntimeError("Login page HTML did not look like the expected Powershop login page.")

    action_url, hidden, email_field, pass_field = _find_login_form_fields(r.text)
    payload = dict(hidden)
    payload[email_field] = email
    payload[pass_field] = password

    headers = {
        "Referer": BASE_URL + "/",
        "Content-Type": "application/x-www-form-urlencoded",
    }
    resp = session.post(action_url, data=payload, headers=headers, allow_redirects=True, timeout=30)
    if _looks_like_login_html(resp.text):
        raise RuntimeError("Login POST returned login page again (credentials/captcha/2FA/bot protection).")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cookie", help="Full Cookie header value from a logged-in browser session.")
    ap.add_argument("--email", help="Email (or set POWERSHOP_EMAIL).")
    ap.add_argument("--password", help="Password (or set POWERSHOP_PASSWORD).")
    ap.add_argument("--har", help="Path to a .har file to extract cookies/customer_id from.")
    ap.add_argument("--customer-id", help="Customer ID (optional; can be inferred from HAR).")
    ap.add_argument("--scale", default="day", choices=["day", "week", "month", "billing"])
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--show-values", action="store_true", help="Print parsed values (may be sensitive).")
    args = ap.parse_args()

    cookie = args.cookie
    customer_id = args.customer_id
    email = args.email or os.environ.get("POWERSHOP_EMAIL")
    password = args.password or os.environ.get("POWERSHOP_PASSWORD")

    if args.har:
        har_path = Path(args.har).expanduser()
        if not har_path.exists():
            raise SystemExit(f"HAR not found: {har_path}")
        if not cookie:
            cookies = _cookies_from_har(har_path)
            if not cookies:
                raise SystemExit("Could not extract cookies from HAR.")
            cookie = cookie_header_from_dict(cookies)
        if not customer_id:
            customer_id = _customer_id_from_har(har_path)

    if not cookie and not (email and password):
        raise SystemExit("Provide --cookie/--har or --email/--password (or POWERSHOP_EMAIL/POWERSHOP_PASSWORD)")
    if not customer_id:
        raise SystemExit("Provide --customer-id or a HAR containing /customers/<id>/ URLs")

    s = requests.Session()
    if cookie:
        s.headers.update({"Cookie": cookie})
    elif email and password:
        # Establish session via email/password login
        login_with_email_password(s, email=email, password=password)

    # Balance
    bal_resp = get(s, f"/customers/{customer_id}/balance", referer=BASE_URL + "/")
    print("balance status:", bal_resp.status_code, "url:", bal_resp.url)
    assert_logged_in(bal_resp)
    balance = PARSERS.parse_balance_nzd_from_balance_html(bal_resp.text)
    if balance is None:
        raise RuntimeError("Could not parse balance from HTML (parser returned None).")

    # Usage page (prime selected consumer state + find consumer ids)
    usage_page = get(
        s,
        f"/customers/{customer_id}/usage",
        referer=BASE_URL + f"/customers/{customer_id}/balance",
    )
    print("usage page status:", usage_page.status_code, "url:", usage_page.url)
    assert_logged_in(usage_page)
    consumer_ids = PARSERS.parse_consumer_ids_from_usage_html(usage_page.text)
    consumer_id = consumer_ids[0] if consumer_ids else None
    if not consumer_id:
        raise RuntimeError("Could not discover consumer_id from usage page HTML.")

    # Prime server-side selected_consumer_id
    _ = get(
        s,
        f"/customers/{customer_id}/usage",
        referer=BASE_URL + f"/customers/{customer_id}/balance",
        params={"selected_consumer_id": consumer_id},
    )

    end = date.today()
    start = end - timedelta(days=max(1, int(args.days)))

    csv_resp = get(
        s,
        "/usage/data.csv",
        referer=BASE_URL + f"/customers/{customer_id}/usage",
        params={"start": start.isoformat(), "end": end.isoformat(), "scale": args.scale},
    )
    print("usage csv status:", csv_resp.status_code, "bytes:", len(csv_resp.text))
    assert_logged_in(csv_resp)

    records = PARSERS.parse_usage_csv(csv_resp.text)
    if not records:
        raise RuntimeError("Parsed 0 usage records from CSV.")

    sum_kwh = sum([r.kwh for r in records if getattr(r, "kwh", None) is not None])
    sum_cost = sum([r.cost_nzd for r in records if getattr(r, "cost_nzd", None) is not None])

    print("\\nOK: scraped values")
    print("  balance_parsed:", balance is not None)
    print("  customer_id:", customer_id)
    print("  consumer_id:", consumer_id)
    print("  window:", start.isoformat(), "→", end.isoformat(), "scale:", args.scale)
    print("  records:", len(records))
    print("  sum_kwh:", sum_kwh)
    if sum_cost and args.show_values:
        print("  sum_cost_nzd:", sum_cost)
    if args.show_values:
        print("  balance_nzd:", balance)
        print("  first_record:", asdict(records[0]))
        print("  last_record:", asdict(records[-1]))

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as e:
        print("FAIL:", e)
        raise

