from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import List, Optional
from urllib.parse import urljoin

from aiohttp import ClientResponseError, ClientSession
from bs4 import BeautifulSoup

from .parsers import (
    UsageRecord,
    parse_balance_nzd_from_balance_html,
    parse_consumer_ids_from_usage_html,
    parse_customer_id_from_url,
    parse_usage_csv,
)


BASE_URL = "https://secure.powershop.co.nz"


class PowershopError(RuntimeError):
    pass


class PowershopAuthError(PowershopError):
    pass


def _cookie_header_value(cookie_header: str) -> str:
    # HA stores string; we pass through as-is
    return cookie_header.strip()


def _extract_csrf_token(html: str) -> Optional[str]:
    soup = BeautifulSoup(html, "lxml")
    tag = soup.find("meta", attrs={"name": "csrf-token"})
    return tag.get("content") if tag else None


@dataclass
class PowershopClient:
    session: ClientSession
    cookie: Optional[str] = None
    email: Optional[str] = None
    password: Optional[str] = None

    customer_id: Optional[str] = None
    consumer_id: Optional[str] = None

    def _url(self, path: str) -> str:
        return path if path.startswith("http") else urljoin(BASE_URL, path)

    async def _get_text(self, path: str, *, referer: Optional[str] = None, params: Optional[dict] = None) -> str:
        headers = {}
        if referer:
            headers["Referer"] = referer
        if self.cookie:
            headers["Cookie"] = _cookie_header_value(self.cookie)
        async with self.session.get(self._url(path), headers=headers, params=params, timeout=30) as resp:
            resp.raise_for_status()
            return await resp.text()

    async def _post_text(self, url: str, data: dict, *, referer: Optional[str] = None, csrf: Optional[str] = None) -> str:
        headers = {}
        if referer:
            headers["Referer"] = referer
        if csrf:
            headers["X-CSRF-Token"] = csrf
        if self.cookie:
            headers["Cookie"] = _cookie_header_value(self.cookie)
        async with self.session.post(url, data=data, headers=headers, timeout=30) as resp:
            resp.raise_for_status()
            return await resp.text()

    async def login_if_needed(self) -> None:
        # Cookie auth is the primary path; if no cookie, try email/password.
        if self.cookie:
            return
        if not (self.email and self.password):
            raise PowershopAuthError("Provide either cookie auth or email/password.")

        login_html = await self._get_text("/", referer=None)
        csrf = _extract_csrf_token(login_html)

        # Best-effort login form detection: find first form with password input
        soup = BeautifulSoup(login_html, "lxml")
        form = None
        for f in soup.find_all("form"):
            if f.find("input", attrs={"type": "password"}):
                form = f
                break
        if not form:
            raise PowershopAuthError("Could not locate login form.")

        action = form.get("action") or "/"
        action_url = self._url(action)

        hidden = {}
        email_name = None
        pass_name = None
        for inp in form.find_all("input"):
            name = inp.get("name")
            if not name:
                continue
            typ = (inp.get("type") or "").lower()
            if typ == "hidden":
                hidden[name] = inp.get("value") or ""
            elif typ == "email" or "email" in name.lower():
                email_name = name
            elif typ == "password" or "pass" in name.lower():
                pass_name = name

        if not email_name or not pass_name:
            raise PowershopAuthError("Could not identify email/password fields.")

        payload = dict(hidden)
        payload[email_name] = self.email
        payload[pass_name] = self.password

        _ = await self._post_text(action_url, payload, referer=BASE_URL + "/", csrf=csrf)

    async def ensure_customer_id(self) -> str:
        if self.customer_id:
            return self.customer_id

        # Try /properties to find /customers/<id>/ links
        html = await self._get_text("/properties", referer=BASE_URL + "/")
        soup = BeautifulSoup(html, "lxml")
        for a in soup.find_all("a", href=True):
            cid = parse_customer_id_from_url(a["href"])
            if cid:
                self.customer_id = cid
                return cid

        # Fallback: try home page
        html2 = await self._get_text("/", referer=None)
        soup2 = BeautifulSoup(html2, "lxml")
        for a in soup2.find_all("a", href=True):
            cid = parse_customer_id_from_url(a["href"])
            if cid:
                self.customer_id = cid
                return cid

        raise PowershopAuthError("Could not discover customer_id (invalid session cookie?).")

    async def ensure_consumer_id(self) -> str:
        if self.consumer_id:
            return self.consumer_id

        cid = await self.ensure_customer_id()
        usage_html = await self._get_text(f"/customers/{cid}/usage", referer=BASE_URL + f"/customers/{cid}/balance")
        consumer_ids = parse_consumer_ids_from_usage_html(usage_html)
        if not consumer_ids:
            raise PowershopError("Could not discover consumer_id from usage page.")
        self.consumer_id = consumer_ids[0]
        return self.consumer_id

    async def fetch_balance_nzd(self, *, customer_id: Optional[str] = None) -> float:
        cid = customer_id or await self.ensure_customer_id()
        html = await self._get_text(f"/customers/{cid}/balance", referer=BASE_URL + "/")
        bal = parse_balance_nzd_from_balance_html(html)
        if bal is None:
            raise PowershopError("Could not parse balance from balance HTML.")
        return bal

    async def fetch_usage_records(
        self,
        *,
        customer_id: Optional[str] = None,
        consumer_id: Optional[str] = None,
        scale: str = "day",
        days: int = 7,
    ) -> List[UsageRecord]:
        if scale not in ("day", "week", "month", "billing"):
            raise ValueError("scale must be one of: day, week, month, billing")

        cid = customer_id or await self.ensure_customer_id()
        consumer = consumer_id or await self.ensure_consumer_id()

        # Visit usage page with selected consumer to prime server-side state.
        await self._get_text(
            f"/customers/{cid}/usage",
            referer=BASE_URL + f"/customers/{cid}/balance",
            params={"selected_consumer_id": consumer},
        )

        end = date.today()
        start = end - timedelta(days=max(1, int(days)))

        csv_text = await self._get_text(
            "/usage/data.csv",
            referer=BASE_URL + f"/customers/{cid}/usage",
            params={
                "start": start.isoformat(),
                "end": end.isoformat(),
                "scale": scale,
            },
        )

        return parse_usage_csv(csv_text)

