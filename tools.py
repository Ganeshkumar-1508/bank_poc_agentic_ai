import csv
import os
import re
from io import StringIO
from typing import List, Optional, Tuple
from dotenv import load_dotenv
import pandas as pd
import requests
from bs4 import BeautifulSoup
from crewai_tools import WebsiteSearchTool

from config import (
    CSV_PATH,
    FALLBACK_SOURCE_NAME,
    FALLBACK_SOURCE_URL,
    SOURCE_NAME,
    SOURCE_URL,
    TOP_PROVIDERS,
    WEBSITE_SEARCH_API_KEY,
    WEBSITE_SEARCH_BASE_URL,
    WEBSITE_SEARCH_MODEL,
)
from models import RateRow, UserQuery

load_dotenv()

AMOUNT_RE = re.compile(r"(\d+(?:,\d{2,3})*(?:\.\d+)?)")
TENURE_RE = re.compile(
    r"(\d+)\s*(day|days|d|month|months|mo|mos|year|years|yr|yrs)",
    re.IGNORECASE,
)
AGE_RE = re.compile(r"(\d{2})\s*(?:years|yrs|year|yr)", re.IGNORECASE)
RATE_RE = re.compile(r"(\d+(?:\.\d+)?)\s*%")
TENURE_BAND_RE = re.compile(
    r"(one|two|three|four|five|six|seven|eight|nine|ten|\d+)\s*(day|days|month|months|year|years)",
    re.IGNORECASE,
)
WORD_TO_NUM = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
}


def parse_user_query(text: str) -> UserQuery:
    lowered = text.lower()
    product_type = (
        "fd"
        if "fd" in lowered or "fixed deposit" in lowered
        else "td"
        if "td" in lowered or "term deposit" in lowered
        else "fd"
    )

    amount = None
    amount_match = AMOUNT_RE.search(text.replace(",", ""))
    if amount_match:
        try:
            amount = float(amount_match.group(1))
        except ValueError:
            amount = None

    tenure_months = None
    tenure_days = None
    tenure_match = TENURE_RE.search(lowered)
    if tenure_match:
        value = int(tenure_match.group(1))
        unit = tenure_match.group(2).lower()
        if unit.startswith("y"):
            tenure_months = value * 12
            tenure_days = value * 365
        elif unit.startswith("m"):
            tenure_months = value
            tenure_days = value * 30
        else:
            tenure_days = value
            tenure_months = max(1, round(value / 30))

    age = None
    age_match = AGE_RE.search(lowered)
    if age_match:
        try:
            age = int(age_match.group(1))
        except ValueError:
            age = None

    return UserQuery(
        raw=text,
        product_type=product_type,
        amount=amount,
        tenure_months=tenure_months,
        tenure_days=tenure_days,
        age=age,
    )


def website_search_tool(query: str, websites: List[str]) -> str:
    urls = [u for u in websites if u]
    if not urls:
        return "No website URL provided for website search."

    if not WEBSITE_SEARCH_API_KEY:
        return (
            "Website search requires WEBSITE_SEARCH_API_KEY (or NVIDIA_API_KEY) in your environment."
        )

    nvidia_llm_cfg = {
        "provider": "nvidia",
        "config": {
            "model": WEBSITE_SEARCH_MODEL,
            "api_key": WEBSITE_SEARCH_API_KEY,
            "base_url": WEBSITE_SEARCH_BASE_URL,
        },
    }

    # crewai_tools API has changed across versions (website_url vs website_urls).
    init_attempts = [
        {
            "website_url": urls[0],
            "config": {"llm": nvidia_llm_cfg},
        },
        {
            "website_urls": urls,
            "config": {"llm": nvidia_llm_cfg},
        },
        {
            "website_url": urls[0],
            "llm": nvidia_llm_cfg,
        },
        {
            "website_urls": urls,
            "llm": nvidia_llm_cfg,
        },
        {"website_url": urls[0]},
        {"website_urls": urls},
        {"config": {"llm": nvidia_llm_cfg}},
        {"llm": nvidia_llm_cfg},
        {},
    ]

    last_error: Optional[Exception] = None
    for kwargs in init_attempts:
        try:
            tool = WebsiteSearchTool(**kwargs)
            try:
                return str(tool.run(query, website_url=urls[0]))
            except TypeError:
                return str(tool.run(query))
        except Exception as exc:
            last_error = exc

    return f"Website search failed: {last_error}"


def _normalize_col(col) -> str:
    if isinstance(col, tuple):
        return " ".join(str(c) for c in col if c and str(c) != "nan").strip().lower()
    return str(col).strip().lower()


def _rate_bounds(rate_text: str) -> Tuple[Optional[float], Optional[float]]:
    values = [float(v) for v in RATE_RE.findall(str(rate_text))]
    if not values:
        return None, None
    return min(values), max(values)


def _token_to_int(token: str) -> Optional[int]:
    token_l = token.lower().strip()
    if token_l.isdigit():
        return int(token_l)
    return WORD_TO_NUM.get(token_l)


def _unit_to_days(value: int, unit: str) -> int:
    unit_l = unit.lower()
    if unit_l.startswith("year"):
        return value * 365
    if unit_l.startswith("month"):
        return value * 30
    return value


def _extract_tenure_band_days(context_text: str) -> Tuple[Optional[int], Optional[int]]:
    matches = TENURE_BAND_RE.findall(context_text or "")
    if not matches:
        return None, None

    bounds: List[int] = []
    for token, unit in matches[:2]:
        value = _token_to_int(token)
        if value is None:
            continue
        bounds.append(_unit_to_days(value, unit))

    if not bounds:
        return None, None
    if len(bounds) == 1:
        return bounds[0], None
    return min(bounds), max(bounds)


def _best_per_provider(rows: List[RateRow], top_n: int) -> List[RateRow]:
    best_rows = {}
    for row in rows:
        key = row.provider.lower().strip()
        existing = best_rows.get(key)
        score = row.rate_max if row.rate_max is not None else -1.0
        existing_score = existing.rate_max if existing and existing.rate_max is not None else -1.0
        if existing is None or score > existing_score:
            best_rows[key] = row

    ranked = sorted(
        best_rows.values(),
        key=lambda r: (r.rate_max if r.rate_max is not None else -1.0),
        reverse=True,
    )
    return ranked[: max(1, top_n)]


def _scrape_market_rates(amount: Optional[float], senior: Optional[bool], tenure_days: Optional[int]) -> List[RateRow]:
    resp = requests.get(SOURCE_URL, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")
    tables = soup.find_all("table")
    dfs = pd.read_html(StringIO(resp.text))
    rows: List[RateRow] = []
    table_entries = []

    for idx, df in enumerate(dfs):
        context_text = ""
        if idx < len(tables):
            context = tables[idx].find_previous("p")
            if context:
                context_text = context.get_text(" ", strip=True)
        band_min_days, band_max_days = _extract_tenure_band_days(context_text)
        table_entries.append((df, context_text, band_min_days, band_max_days))

    allowed_width = None
    if tenure_days is not None:
        widths = []
        for _, _, band_min_days, band_max_days in table_entries:
            if band_min_days is None or band_max_days is None:
                continue
            if band_min_days <= tenure_days <= band_max_days:
                widths.append(band_max_days - band_min_days)
        if widths:
            allowed_width = min(widths)

    for df, context_text, band_min_days, band_max_days in table_entries:
        if tenure_days is not None and band_min_days is not None and band_max_days is not None:
            if tenure_days < band_min_days or tenure_days > band_max_days:
                continue
            if allowed_width is not None and (band_max_days - band_min_days) > allowed_width:
                continue

        cols = [_normalize_col(c) for c in df.columns]
        provider_idx = next((i for i, c in enumerate(cols) if "bank" in c or "provider" in c), None)
        general_idx = next((i for i, c in enumerate(cols) if "general" in c), None)
        senior_idx = next((i for i, c in enumerate(cols) if "senior" in c), None)

        if provider_idx is None or (general_idx is None and senior_idx is None):
            continue

        rate_idx = senior_idx if senior else general_idx
        if rate_idx is None:
            continue

        for _, row in df.iterrows():
            provider = str(row.iloc[provider_idx]).strip()
            rate_text = str(row.iloc[rate_idx]).strip()
            if not provider or provider.lower() == "nan" or not rate_text or rate_text.lower() == "nan":
                continue

            rate_min, rate_max = _rate_bounds(rate_text)
            rows.append(
                RateRow(
                    provider=provider,
                    tenure=context_text or "FD rates",
                    interest_rate=rate_text,
                    amount=str(amount) if amount is not None else "",
                    senior_citizen="Yes" if senior else "No",
                    source_url=SOURCE_URL,
                    source_name=SOURCE_NAME,
                    rate_min=rate_min,
                    rate_max=rate_max,
                )
            )

    return rows


def _scrape_hdfc_fallback(amount: Optional[float], senior: Optional[bool]) -> List[RateRow]:
    resp = requests.get(FALLBACK_SOURCE_URL, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
    resp.raise_for_status()

    dfs = pd.read_html(StringIO(resp.text))
    rows: List[RateRow] = []

    for df in dfs:
        cols = [_normalize_col(c) for c in df.columns]
        tenor_idx = next((i for i, c in enumerate(cols) if "tenor" in c), None)
        if tenor_idx is None:
            continue

        regular_idx = next((i for i, c in enumerate(cols) if "interest rate" in c or "regular" in c or "general" in c), None)
        senior_idx = next((i for i, c in enumerate(cols) if "senior" in c), None)

        if regular_idx is None and senior_idx is None:
            continue

        for _, row in df.iterrows():
            tenor_val = str(row.iloc[tenor_idx]).strip()
            if not tenor_val or tenor_val.lower() == "nan":
                continue

            if regular_idx is not None:
                rate_regular = str(row.iloc[regular_idx]).strip()
                rate_min, rate_max = _rate_bounds(rate_regular)
                rows.append(
                    RateRow(
                        provider=FALLBACK_SOURCE_NAME,
                        tenure=tenor_val,
                        interest_rate=rate_regular,
                        amount=str(amount) if amount is not None else "",
                        senior_citizen="No",
                        source_url=FALLBACK_SOURCE_URL,
                        source_name=FALLBACK_SOURCE_NAME,
                        rate_min=rate_min,
                        rate_max=rate_max,
                    )
                )

            if senior_idx is not None:
                rate_senior = str(row.iloc[senior_idx]).strip()
                rate_min, rate_max = _rate_bounds(rate_senior)
                rows.append(
                    RateRow(
                        provider=FALLBACK_SOURCE_NAME,
                        tenure=tenor_val,
                        interest_rate=rate_senior,
                        amount=str(amount) if amount is not None else "",
                        senior_citizen="Yes",
                        source_url=FALLBACK_SOURCE_URL,
                        source_name=FALLBACK_SOURCE_NAME,
                        rate_min=rate_min,
                        rate_max=rate_max,
                    )
                )

    if senior is not None:
        rows = [r for r in rows if (r.senior_citizen == "Yes") == bool(senior)]

    return _best_per_provider(rows, TOP_PROVIDERS)


def scrape_fd_rates(
    amount: Optional[float],
    senior: Optional[bool],
    tenure_days: Optional[int] = None,
    top_n: Optional[int] = None,
) -> List[RateRow]:
    limit = top_n if top_n is not None else TOP_PROVIDERS
    try:
        market_rows = _scrape_market_rates(amount=amount, senior=senior, tenure_days=tenure_days)
        if market_rows:
            return _best_per_provider(market_rows, limit)
    except Exception:
        pass

    return _scrape_hdfc_fallback(amount=amount, senior=senior)


def save_rates_to_csv(rows: List[RateRow], path: str = CSV_PATH) -> str:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "provider",
                "tenure",
                "interest_rate",
                "amount",
                "senior_citizen",
                "source_name",
                "source_url",
                "rate_min",
                "rate_max",
            ]
        )
        for r in rows:
            writer.writerow(
                [
                    r.provider,
                    r.tenure,
                    r.interest_rate,
                    r.amount,
                    r.senior_citizen,
                    r.source_name,
                    r.source_url,
                    r.rate_min if r.rate_min is not None else "",
                    r.rate_max if r.rate_max is not None else "",
                ]
            )
    return path
