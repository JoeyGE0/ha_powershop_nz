from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

from bs4 import BeautifulSoup
from dateutil import parser as date_parser


_MONEY_RE = re.compile(r"\$\s*([0-9][0-9,]*)(?:\.(\d{2}))?")


def _to_float(s: str) -> Optional[float]:
    s = (s or "").strip()
    if not s:
        return None
    s = s.replace(",", "")
    s = s.replace("$", "")
    s = s.replace("NZD", "").strip()
    # common unit suffixes
    s = re.sub(r"\bkwh\b", "", s, flags=re.I).strip()
    s = re.sub(r"\bkw\s*h\b", "", s, flags=re.I).strip()
    try:
        return float(s)
    except ValueError:
        return None


def parse_customer_id_from_url(url: str) -> Optional[str]:
    m = re.search(r"/customers/(\d+)(?:/|$)", url)
    return m.group(1) if m else None


def parse_consumer_ids_from_usage_html(html: str) -> List[str]:
    return sorted(set(re.findall(r"selected_consumer_id=(\d+)", html)))


def parse_balance_nzd_from_balance_html(html: str) -> Optional[float]:
    soup = BeautifulSoup(html, "lxml")
    container = soup.find(id="unit-balance-container")
    text = container.get_text(" ", strip=True) if container else soup.get_text(" ", strip=True)
    m = _MONEY_RE.search(text)
    if not m:
        return None
    whole = m.group(1).replace(",", "")
    cents = m.group(2) or "00"
    try:
        return float(f"{whole}.{cents}")
    except ValueError:
        return None


@dataclass(frozen=True)
class UsageRecord:
    when: date
    kwh: Optional[float] = None
    cost_nzd: Optional[float] = None
    raw: Dict[str, Any] | None = None


def _guess_columns(headers: List[str]) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    lowered = [h.strip().lower() for h in headers]
    date_col = None
    kwh_col = None
    cost_col = None

    for h, lh in zip(headers, lowered):
        if lh in ("date", "day", "period", "start") or "date" in lh:
            date_col = h
            break
    # If no explicit date, accept end as fallback
    if date_col is None:
        for h, lh in zip(headers, lowered):
            if lh == "end":
                date_col = h
                break

    for h, lh in zip(headers, lowered):
        if "kwh" in lh or lh in ("usage", "energy", "consumption"):
            kwh_col = h
            break
    # Powershop CSV can use "Average daily use" without 'kWh' in the header
    if kwh_col is None:
        for h, lh in zip(headers, lowered):
            if "use" in lh and "estimate" not in lh and "cost" not in lh:
                kwh_col = h
                break

    for h, lh in zip(headers, lowered):
        if "cost" in lh or "price" in lh or "$" in lh or "nzd" in lh:
            cost_col = h
            break
    # Some exports label cost column as "Estimate"
    if cost_col is None:
        for h, lh in zip(headers, lowered):
            if lh == "estimate":
                cost_col = h
                break

    if headers and date_col is None:
        date_col = headers[0]

    return date_col, kwh_col, cost_col


def parse_usage_csv(csv_text: str) -> List[UsageRecord]:
    csv_text = (csv_text or "").lstrip("\ufeff")
    f = io.StringIO(csv_text)
    sample = csv_text[:4096]

    try:
        dialect = csv.Sniffer().sniff(sample)
    except Exception:
        dialect = csv.excel

    reader = csv.DictReader(f, dialect=dialect)
    if not reader.fieldnames:
        return []

    date_col, kwh_col, cost_col = _guess_columns(reader.fieldnames)
    out: List[UsageRecord] = []

    for row in reader:
        if not row:
            continue
        raw_date = (row.get(date_col) or "").strip() if date_col else ""
        if not raw_date:
            continue
        try:
            d = date_parser.parse(raw_date).date()
        except Exception:
            continue
        kwh = _to_float(row.get(kwh_col, "")) if kwh_col else None
        cost = _to_float(row.get(cost_col, "")) if cost_col else None
        out.append(UsageRecord(when=d, kwh=kwh, cost_nzd=cost, raw=row))

    out.sort(key=lambda r: r.when)
    return out

