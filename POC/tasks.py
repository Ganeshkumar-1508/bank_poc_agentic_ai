# tasks.py
from crewai import Task
from datetime import datetime
import hashlib

_CURRENT_YEAR = datetime.now().year

DB_SCHEMA_INFO = """\
Tables in 'bank_poc.db':
- users: user_id, first_name, last_name, account_number, email, is_account_active
- address: address_id, user_id, user_address, pin_number, mobile_number, mobile_verified
- kyc_verification: kyc_id, user_id, address_id, account_number, kyc_details_1, kyc_details_2,
  kyc_status, verified_at, created_at, updated_at  (kyc_details format: 'TYPE-VALUE', e.g. 'PAN-ABCDE1234F')
- accounts: account_id, user_id, account_number, account_type, balance, email, created_at
- fixed_deposit: fd_id, user_id, initial_amount, bank_name, tenure_months, interest_rate,
  maturity_date, premature_penalty_percent, fd_status, product_type, monthly_installment, compounding_freq"""

_MD_RULES = (
    "OUTPUT: valid Streamlit-renderable Markdown only — no JSON, no code fences, no HTML, "
    "no escaped characters. Every table cell must have a value (N/A if unknown). "
    "Links: [text](url). Bold key values with **. Use --- for section dividers."
)


_PRODUCT_META = {
    # code: (display_name, regions_list_or_"ALL", default_tenure_months, notes)
    "FD":           ("Fixed Deposit",                   "ALL",   12,  ""),
    "TD":           ("Term Deposit",                    "ALL",   12,  ""),
    "RD":           ("Recurring Deposit",               "SA",    12,  "monthly installment"),
    "MF":           ("Mutual Fund / SIP",               "ALL",   36,  "market-linked; SIP or lump-sum"),
    "BOND":         ("Bond (coupon)",                   "ALL",   60,  "semi-annual coupon"),
    "MMARKET":      ("Money Market Account",            "ALL",   12,  ""),
    "PPF":          ("Public Provident Fund",           "IN",   180,  "annual deposit; EEE tax; lock-in 15 yr"),
    "NSC":          ("National Savings Certificate",    "IN",    60,  "lump-sum; 80C deduction"),
    "KVP":          ("Kisan Vikas Patra",               "IN",   115,  "doubles money"),
    "SSY":          ("Sukanya Samriddhi Yojana",        "IN",   252,  "girl-child; annual deposit; EEE"),
    "SCSS":         ("Senior Citizens Savings Scheme",  "IN",    60,  "quarterly payout; age ≥60"),
    "SGB":          ("Sovereign Gold Bond",             "IN",    96,  "2.5% coupon + gold price gains"),
    "NPS":          ("National Pension System",         "IN",   240,  "monthly SIP; 60% lump / 40% annuity"),
    "CD":           ("Certificate of Deposit",          "US",    12,  "FDIC insured"),
    "T-BILL":       ("Treasury Bill",                   "US",     6,  "discount; 4–52 weeks"),
    "T-NOTE":       ("Treasury Note",                   "US",    60,  "semi-annual coupon; 2–10 yr"),
    "T-BOND":       ("Treasury Bond",                   "US",   360,  "semi-annual coupon; 20–30 yr"),
    "I-BOND":       ("I Bond (Inflation-Protected)",    "US",    12,  "composite = fixed + 2×CPI-U"),
    "ISA":          ("Individual Savings Account",      "GB",    12,  "tax-free; £20k/yr allowance"),
    "PREMIUM_BOND": ("Premium Bond (NS&I)",             "GB",    12,  "prize draws; no guaranteed return"),
    "GIC":          ("Guaranteed Investment Certificate","CA",   12,  "CDIC insured; C$100k"),
    "SSB":          ("Singapore Savings Bond",          "SG",   120,  "step-up interest; 10 yr"),
    "MURABAHA":     ("Murabaha / Islamic Term Deposit", "GCC",   12,  "Sharia-compliant profit rate"),
}

_REGION_PRODUCTS = {
    "IN":  ["FD", "RD", "PPF", "NSC", "KVP", "SSY", "SCSS", "SGB", "NPS", "MF", "BOND"],
    "US":  ["FD", "CD", "T-BILL", "T-NOTE", "T-BOND", "I-BOND", "MMARKET", "MF", "BOND"],
    "GB":  ["FD", "TD", "ISA", "PREMIUM_BOND", "MMARKET", "MF", "BOND"],
    "AU":  ["FD", "TD", "MMARKET", "MF", "BOND"],
    "CA":  ["FD", "GIC", "MMARKET", "MF", "BOND"],
    "SG":  ["FD", "TD", "SSB", "MF", "BOND"],
    "AE":  ["FD", "TD", "MURABAHA", "MF", "BOND"],
    "MY":  ["FD", "RD", "MURABAHA", "MF", "BOND"],
}

_REGION_NAMES = {
    "INDIA": "IN", "UNITED STATES": "US", "USA": "US", "AMERICA": "US",
    "UK": "GB", "UNITED KINGDOM": "GB", "BRITAIN": "GB",
    "AUSTRALIA": "AU", "CANADA": "CA", "SINGAPORE": "SG",
    "UAE": "AE", "MALAYSIA": "MY",
}


def _region_code(region: str) -> str:
    return _REGION_NAMES.get(region.upper(), region.upper()[:2] if len(region) >= 2 else "IN")


def _get_region_products_str(region: str) -> str:
    """Return a formatted bullet list of product codes + names for a region (used in prompts)."""
    code = _region_code(region)
    codes = _REGION_PRODUCTS.get(code, ["FD", "TD", "RD", "MF", "BOND"])
    lines = []
    for c in codes:
        meta = _PRODUCT_META.get(c, (c, "ALL", 12, ""))
        note = f" — {meta[3]}" if meta[3] else ""
        lines.append(f"  - **{c}**: {meta[0]}{note}")
    return "\n".join(lines)


def _get_product_name(code: str) -> str:
    return _PRODUCT_META.get(code.upper(), (code,))[0]


def _product_synonyms_str() -> str:
    return (
        "'fixed deposit'/'FD'→FD, 'term deposit'/'TD'→TD, 'recurring deposit'/'RD'→RD, "
        "'mutual fund'/'SIP'/'MF'→MF, 'provident fund'/'PPF'→PPF, "
        "'savings certificate'/'NSC'→NSC, 'kisan vikas'/'KVP'→KVP, "
        "'sukanya'/'girl child'/'SSY'→SSY, 'senior citizen scheme'/'SCSS'→SCSS, "
        "'gold bond'/'SGB'→SGB, 'pension'/'NPS'→NPS, "
        "'certificate of deposit'/'CD'→CD, 'treasury bill'/'T-BILL'→T-BILL, "
        "'treasury note'/'T-NOTE'→T-NOTE, 'treasury bond'/'T-BOND'→T-BOND, "
        "'i bond'/'inflation bond'/'I-BOND'→I-BOND, "
        "'ISA'/'individual savings'→ISA, 'premium bond'→PREMIUM_BOND, "
        "'GIC'/'guaranteed investment'→GIC, 'savings bond'/'SSB'→SSB, "
        "'murabaha'/'islamic deposit'→MURABAHA, 'money market'/'MMARKET'→MMARKET, "
        "'bond'→BOND."
    )


def _get_provider_diversity_rule(region: str, count: int = 5) -> str:
    """Return a region-appropriate provider diversity rule."""
    return (
        f"Select {count} providers meeting ALL of these diversity requirements:\n"
        f"- ≥1 government/public sector bank (e.g. national or state-owned banks in {region})\n"
        f"- ≥1 non-banking financial institution (NBFC or equivalent in {region})\n"
        "- ≥1 regional/specialized bank (e.g. community bank, cooperative bank, digital bank, or small finance bank)\n"
        f"- Remaining slots: top private/commercial banks by rate in {region}\n"
        "If the user names specific providers, include them first, then fill remaining slots."
    )


# SQL cache query template — shared between analysis & research pipelines
_RATES_CACHE_SQL_TEMPLATE = (
    "SELECT general_rate, senior_rate, effective_date FROM interest_rates_catalog\n"
    "WHERE lower(bank_name)=lower('<PROVIDER>') AND product_type='<PRODUCT_TYPE>'\n"
    "AND tenure_min_months<=<TENURE> AND tenure_max_months>=<TENURE>\n"
    "AND is_active=1 AND effective_date>=datetime('now','-6 hours')\n"
    "ORDER BY effective_date DESC LIMIT 1;"
)

# Deposit insurance / protection by region
_DEPOSIT_INSURANCE = {
    "IN": "DICGC ₹5 lakh per depositor per bank",
    "US": "FDIC $250,000 per depositor per insured bank",
    "GB": "FSCS £85,000 per depositor per institution",
    "AU": "FCS AU$250,000 per depositor per institution",
    "CA": "CDIC C$100,000 per depositor per category",
    "SG": "SDIC S$100,000 per depositor per DI member",
    "AE": "No universal deposit insurance scheme (UAE)",
}


def _get_insurance_note(region: str) -> str:
    code = _region_code(region)
    return _DEPOSIT_INSURANCE.get(code, f"Check local deposit protection scheme for {region}")


def _report_id() -> str:
    return hashlib.md5(str(datetime.now().timestamp()).encode()).hexdigest()[:6].upper()


# ---------------------------------------------------------------------------
# Analysis pipeline
# ---------------------------------------------------------------------------

def create_analysis_tasks(agents, user_query: str, region: str = "India"):

    _products_list = _get_region_products_str(region)
    _insurance_note = _get_insurance_note(region)

    parse_task = Task(
        description=(
            f"Parse '{user_query}' for region: {region}.\n\n"
            f"Step 1 — Identify product type from the list available for {region}:\n"
            f"{_products_list}\n\n"
            f"Synonym map: {_product_synonyms_str()}\n"
            "Default to FD if product is ambiguous.\n\n"
            "Step 2 — Extract:\n"
            "1. Type: [product code — e.g. FD, RD, PPF, CD, ISA, BOND…]\n"
            "2. Amount: integer (K/k→×1000, M/m→×1000000; "
            "also handle L→×100000, Cr→×10000000 for India)\n"
            "3. Tenure: integer months (years→×12; "
            "PPF default=180, NSC=60, KVP=115, SSY=252, SCSS=60, SGB=96, NPS=240)\n"
            "4. Compounding: monthly/quarterly/half_yearly/yearly "
            "(default quarterly for FD/RD/CD; yearly for PPF/NSC/SSY; N/A for SCSS/BOND/SGB)\n"
            "5. Payment_Freq: annual/semi_annual/quarterly "
            "(for BOND/SGB/SCSS/T-NOTE/T-BOND; default semi_annual)\n"
            "6. Is_SIP: true/false (true if user says 'SIP' or 'monthly investment' for MF/NPS)\n"
            "7. Is_Senior: true/false (user mentions senior citizen, age 60+, or pensioner)\n\n"
            "Output format (strict — exactly 7 lines, nothing else):\n"
            "Type: FD\nAmount: 100000\nTenure: 12\nCompounding: quarterly\n"
            "Payment_Freq: semi_annual\nIs_SIP: false\nIs_Senior: false"
        ),
        expected_output="7-line format: Type, Amount, Tenure, Compounding, Payment_Freq, Is_SIP, Is_Senior",
        agent=agents["query_parser_agent"],
    )

    search_task = Task(
        description=(
            "Read product Type and Is_Senior from parse_task context.\n\n"
            f"Search for the TOP 5 {region} providers offering the parsed product type "
            f"with the best rates/returns for the parsed tenure.\n\n"
            "Search 1 (rates): "
            f"'best [PRODUCT_TYPE] interest rates/returns {region} {_CURRENT_YEAR} top providers'\n"
            "Search 2 (senior rates if Is_Senior=true OR product has senior variant): "
            f"'senior citizen [PRODUCT_TYPE] rate extra benefit {region} {_CURRENT_YEAR}'\n\n"
            + _get_provider_diversity_rule(region, 5) + "\n\n"
            "For EACH provider find:\n"
            "  - General Rate/Return: standard rate for all customers\n"
            "  - Senior Citizen Rate: rate for age 60+. If not published, add 0.50% to General.\n"
            "    (For market-linked products like MF/NPS, record expected CAGR range instead.)\n\n"
            "Products that do NOT have a 'senior citizen rate' (MF, NPS, BOND, T-BILL, etc.):\n"
            "  - Set both columns to the same rate (e.g. the expected return or yield).\n\n"
            "Output EXACTLY 5 lines — no headers, no extra text:\n"
            "[Provider1],[GeneralRate%],[SeniorRate%]\n"
            "Example: SBI,6.80,7.30  |  Vanguard_SP500,12.00,12.00"
        ),
        expected_output="Exactly 5 lines: Provider,GeneralRate%,SeniorRate%",
        agent=agents["search_agent"],
        context=[parse_task],
    )

    projection_task = Task(
        description=(
            "From parse_task context: Type, Amount, Tenure, Compounding, Payment_Freq, Is_SIP.\n"
            "From search_task context: 5 providers with General and Senior rates.\n\n"
            "For each provider call 'Deposit_Calculator' ONCE — pass deposit_type=Type, "
            "amount=Amount, rate=GeneralRate, senior_rate=SeniorRate, "
            "tenure_months=Tenure, compounding_freq=Compounding, "
            "payment_freq=Payment_Freq, is_sip=Is_SIP.\n"
            "It returns both General and Senior results in one call.\n\n"
            "IMPORTANT — for products with PAYOUT structure (SCSS, BOND, SGB, T-NOTE, T-BOND):\n"
            "  'Maturity' = principal returned. 'Interest' = total periodic payouts over tenure.\n"
            "For market-linked products (MF, NPS): label projections as 'Projected' (not guaranteed).\n\n"
            "Output CSV with header:\n"
            "Provider,GeneralRate,SeniorRate,GeneralMaturity,SeniorMaturity,GeneralInterest,SeniorInterest\n"
            "Rules: numbers only, no currency symbols, no commas in numbers, exactly 5 data rows."
        ),
        expected_output="CSV header + 5 data rows, all numbers, no symbols.",
        agent=agents["projection_agent"],
        context=[parse_task, search_task],
    )

    research_task = Task(
        description=(
            "For each of the 5 providers from search_task context — "
            "read the product Type from parse_task context.\n\n"
            "STEP 1 — ONE batched credit-rating search:\n"
            f"'[P1] [P2] [P3] [P4] [P5] credit rating {region} {_CURRENT_YEAR}'\n\n"
            "STEP 2 — ONE batched product-specific news search:\n"
            f"'[P1] [P2] [P3] [P4] [P5] [PRODUCT_TYPE] interest rate offer {region} {_CURRENT_YEAR}'\n"
            "URL RULES (strict):\n"
            "  ✓ Only include URLs returned directly by the search tool.\n"
            "  ✓ Each URL must be from the provider's official domain OR a recognized financial news source.\n"
            "  ✗ Do NOT fabricate, guess, or reconstruct any URL.\n"
            "  ✗ If no verifiable URL: write URL: N/A — never substitute a made-up link.\n\n"
            "STEP 3 — ONE batched product features search:\n"
            f"'[P1] [P2] [P3] [P4] [P5] [PRODUCT_TYPE] senior benefit withdrawal penalty {region} {_CURRENT_YEAR}'\n"
            f"Note the regional deposit insurance: {_insurance_note}. "
            "Mark NBFCs / market-linked products as 'N/A' for deposit insurance.\n\n"
            "STEP 4 — ONE batched provider type search:\n"
            f"'[P1] [P2] [P3] [P4] [P5] bank type public private NBFC digital {region} {_CURRENT_YEAR}'\n"
            "Classify each: Government/Public Sector, Private Sector, NBFC, Small Finance Bank, "
            "Asset Manager, Brokerage, Cooperative, Government Scheme.\n\n"
            + _MD_RULES + "\n\n"
            "For EACH provider output a Markdown section:\n"
            "---\n"
            "### [Provider Name]\n\n"
            "| Field | Details |\n"
            "|---|---|\n"
            "| **Provider Type** | [Government/Public / Private / NBFC / Asset Manager / Gov. Scheme / etc.] |\n"
            "| **Product** | [Product name as marketed by this provider] |\n"
            "| **General Rate / Return** | [X% p.a. or Expected CAGR X%] |\n"
            "| **Senior Citizen Rate** | [X% or Same as General for non-senior products] |\n"
            "| **Senior Benefit** | [describe extra benefit or 'Standard +0.50%' or 'N/A'] |\n"
            "| **Credit Rating** | [Agency-Grade or Not Rated or N/A for Gov. Schemes] |\n"
            "| **Withdrawal Penalty / Exit Load** | [X% or conditions] |\n"
            "| **Deposit / Investor Insurance** | [coverage + scheme name, or N/A] |\n"
            "| **Loan / Pledging Against Product** | [X% of corpus or N/A] |\n"
            "| **Minimum Investment** | [amount or N/A] |\n"
            "| **Online / Digital Opening** | [Yes/No] |\n"
            "| **Auto-Renewal / SIP Mandate** | [Yes/No] |\n"
            "| **Nomination Facility** | [Yes/No] |\n"
            "| **Flexible Tenure Options** | [Yes/No] |\n\n"
            "**Recent News:**\n"
            "| # | Headline | Source |\n"
            "|---|---|---|\n"
            "| 1 | [Headline relevant to this product/provider] | [URL or N/A] |\n"
            "| 2 | [Headline 2] | [URL or N/A] |\n"
            "| 3 | [Headline 3] | [URL or N/A] |"
        ),
        expected_output=(
            "5 provider sections in Streamlit-renderable Markdown, each with a fields table and news table. "
            "All cells filled with real data. No JSON, no code fences, no fabricated URLs."
        ),
        agent=agents["research_agent"],
        context=[parse_task, search_task],
    )

    safety_task = Task(
        description=(
            "Classify each provider's safety from research data. "
            "Read product Type from parse_task context.\n\n"
            "Classification Rules:\n"
            "- **SAFE**: government/public sector bank OR government scheme (PPF/NSC/SCSS/SSY/KVP/SGB/SSB) "
            "OR investment-grade rating (AAA/AA+/AA/AA-) AND deposit/investor insurance AND NPA<5%\n"
            "- **MODERATE**: private bank with AA- or lower, or regional/specialized bank with AA, "
            "or regulated NBFC, or market-linked product with SEBI/FCA/SEC oversight\n"
            "- **RISKY**: NBFC/non-bank without AAA, Not Rated, negative news, NPA>10%, "
            "no deposit insurance, or unregulated product\n\n"
            "For market-linked products (MF, NPS, SGB price component): "
            "note 'Market Risk' as a separate column — Low/Medium/High based on asset allocation.\n\n"
            "For each provider score risk factors (1=Low, 2=Medium, 3=High):\n"
            "- Credit Rating Risk\n"
            "- Deposit / Investor Insurance Coverage\n"
            "- NPA / Asset Quality (N/A for non-lending institutions)\n"
            "- News / Sentiment Risk\n"
            "- Institution Stability\n"
            "- Market / Price Risk (for MF/NPS/SGB/BOND/T-BILL)\n\n"
            + _MD_RULES + "\n\n"
            "### Safety & Risk Assessment\n\n"
            "| # | Provider | Product | Overall Safety | Rating | Insurance | NPA | "
            "News Sentiment | Market Risk | Cr.Rating Risk | Insurance Risk | "
            "NPA Risk | Sentiment Risk | Stability Risk | Market Risk Score | Reason |\n"
            "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|\n"
            "| 1 | [Name] | [Product] | **[Safe/Moderate/Risky]** | [Grade] | [coverage] | [X% or N/A] | "
            "[Positive/Mixed/Negative] | [Low/Med/High/N/A] | [1/2/3] | [1/2/3] | [1/2/3] | "
            "[1/2/3] | [1/2/3] | [1/2/3] | [1-2 sentence rationale] |"
        ),
        expected_output=(
            "Streamlit-renderable Markdown safety table with 5 providers, overall safety classification, "
            "market risk column, individual risk factor scores (1-3), and detailed reasoning. "
            "No JSON, no code fences."
        ),
        agent=agents["safety_agent"],
        context=[research_task],
    )

    _report_sections = (
        "## 1. Executive Summary\n"
        "3-4 sentences: market/rate environment for [PRODUCT_TYPE], rate/return range, top recommendation.\n\n"
        "## 2. Key Metrics\n"
        "Table: highest/lowest/avg General rates, highest/lowest Senior rates (if applicable), "
        "max maturity/corpus, safest provider, best risk-adjusted return.\n\n"
        "## 3. Provider Comparison\n"
        "Table: #, Provider, Product, Gen.Rate/Return, Sr.Rate, Sr.Benefit, Gen.Maturity/Corpus, "
        "Sr.Maturity, Gen.Interest/Gain, Sr.Interest/Gain, Rating, Safety.\n"
        "For market-linked products: label maturity columns as 'Projected Value'.\n\n"
        "## 4. Top 3 Recommendations\n"
        "Table: Rank, Provider, Product, Gen.Rate, Sr.Rate, Projected Value, Safety, Reason.\n\n"
        "## 5. Senior Citizen Guide\n"
        "Table: Provider, Senior Rate / Return, Extra Benefit over General, "
        "Special Scheme Details, Insurance Coverage.\n"
        "If product has no senior variant (MF, NPS, BOND, T-BILL etc.), note: "
        "'This product does not carry a dedicated senior citizen rate. Standard rates apply to all investors.'\n"
        "Add a 2-sentence note on eligibility and how to claim senior benefits where applicable.\n\n"
        "## 6. Risk & Safety Assessment\n"
        "Table: Provider, Safety, Rating, Market Risk, Exit Penalty/Load, Insurance, Pledging/Loan.\n\n"
        "## 7. Strategy Recommendations\n"
        "Sub-sections: **Conservative / Capital Preservation** | **Growth / Yield-Maximising** | "
        "**Balanced** | **Senior Citizen / Income-Focused** (if relevant).\n"
        "Each: provider, allocation, projected value, rationale.\n\n"
        "## 8. Recent News\n"
        "Table: Provider, Headline, URL (only real URLs from research context; N/A if unavailable).\n\n"
        "## 9. Disclaimers\n"
        "- AI-generated analysis — verify rates with providers before investing.\n"
        "- Rates/returns subject to change without notice.\n"
    )

    summary_task = Task(
        description=(
            "Write a professional investment analysis report using all context data.\n\n"
            "Extract from context: Type (product), Amount, Tenure, Compounding, Is_SIP, Is_Senior, "
            "5 providers with rates/returns, maturity/corpus projections, credit ratings, "
            "news, safety classifications, penalty/insurance/loan data (from research_task).\n\n"
            f"# Investment Analysis Report — [PRODUCT_TYPE]\n"
            f"**Region:** {region} | **Product:** [Type — full name] | "
            f"**Principal / Deposit:** [Amount in local currency] | "
            f"**Tenure:** [Tenure] months | **Date:** {datetime.now().strftime('%B %d, %Y')} | "
            f"**ID:** INV-{_report_id()}\n\n"
            "⚠ For MARKET-LINKED products (MF, NPS, SGB, BOND, T-BILL, I-BOND): "
            "label all projected values as 'Projected (not guaranteed)' and add a risk disclaimer "
            "in the Executive Summary.\n\n"
            "Required sections (all tables filled with real data from context):\n"
            + _report_sections + "\n\n"
            + _MD_RULES + "\n\n"
            f"**Report Generated:** Investment Advisor AI | "
            f"**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        ),
        expected_output=(
            "Complete Streamlit-renderable Markdown report with 9 sections and all tables "
            "filled with real data from context. No JSON, no code fences, no HTML."
        ),
        agent=agents["summary_agent"],
        context=[parse_task, search_task, projection_task, research_task, safety_task],
    )

    return [parse_task, search_task, projection_task, research_task, safety_task, summary_task]


# ---------------------------------------------------------------------------
# Research pipeline
# ---------------------------------------------------------------------------

def create_research_tasks(agents, user_query: str, region: str = "India"):

    _today = datetime.now().strftime("%B %d, %Y")
    _products_list = _get_region_products_str(region)
    _insurance_note = _get_insurance_note(region)

    identify_providers_task = Task(
        description=(
            f"Request: '{user_query}'\n\n"
            "STEP 1 — Determine:\n"
            "- Product type (use synonyms and context; default FD)\n"
            "- Tenure in months (default 12; years→×12)\n"
            "- Any specifically named providers in the query\n"
            "- User intent: RATES (returns-focused), SAFETY (risk/rating), "
            "COMPARISON (side-by-side), GENERAL (overview)\n\n"
            f"Available products for {region}:\n{_products_list}\n\n"
            f"Synonym map: {_product_synonyms_str()}\n\n"
            f"STEP 2 — Search (run both):\n"
            f"  Search A: 'top [PRODUCT_TYPE] interest rates/returns {region} {_CURRENT_YEAR} highest'\n"
            f"  Search B: 'senior citizen [PRODUCT_TYPE] rate benefit {region} {_CURRENT_YEAR}'\n\n"
            + _get_provider_diversity_rule(region, 10) + "\n\n"
            "For EACH provider record:\n"
            "  - General Rate / Return: standard customer rate or expected CAGR\n"
            "  - Senior Rate: age 60+ rate (General+0.50% if not found; same as General for market-linked)\n\n"
            + _MD_RULES + "\n\n"
            "### Query Analysis\n\n"
            "| Field | Value |\n"
            "|---|---|\n"
            "| **Product Type** | [code — e.g. FD, PPF, CD, ISA, MF] |\n"
            "| **Product Name** | [full name] |\n"
            "| **Tenure** | [months] |\n"
            "| **Intent** | [RATES / SAFETY / COMPARISON / GENERAL] |\n"
            f"| **Region** | {region} |\n\n"
            "### Identified Providers\n\n"
            "| # | Provider | Type | General Rate/Return (%) | Senior Rate (%) | Insurance / Protection |\n"
            "|---|---|---|---|---|---|\n"
            "| 1 | [Name] | [Gov/Private/NBFC/AssetMgr/GovScheme] | [X%] | [X%] | "
            f"[{_insurance_note} or N/A] |\n"
            "(List all 10 providers as rows.)"
        ),
        expected_output=(
            "Streamlit-renderable Markdown with Query Analysis table and Identified Providers table "
            "listing 10 providers. No JSON, no code fences."
        ),
        agent=agents["provider_search_agent"],
    )

    deep_research_task = Task(
        description=(
            "From context: TENURE, PRODUCT_TYPE, INTENT, all PROVIDERS with General and Senior rates.\n\n"
            "For EACH provider gather: credit ratings, product-specific news with verified URLs, "
            "senior citizen rate details, key financials, and liquidity/exit terms.\n\n"
            "STEP 1 — International credit-rating search:\n"
            f"'[P1]…[P5] credit rating Moodys S&P Fitch {_CURRENT_YEAR}'\n\n"
            "STEP 2 — Local/domestic credit-rating search:\n"
            f"'[P1]…[P5] ICRA CRISIL CARE rating {region} {_CURRENT_YEAR}'\n"
            "(Adapt agencies: ICRA/CRISIL/CARE India; DBRS/Kroll US; "
            "Capital Intelligence UAE; RAM/MARC Malaysia; ACRA Singapore; etc.)\n\n"
            "STEP 3 — Financial health search:\n"
            f"'[P1]…[P5] quarterly results NPA CAR capital adequacy AUM {_CURRENT_YEAR}'\n\n"
            "STEP 4 — Product-specific news search (P1–P5):\n"
            f"'[P1]…[P5] [PRODUCT_TYPE] rate offer return {region} {_CURRENT_YEAR}'\n"
            "URL RULES — READ CAREFULLY:\n"
            "  ✓ Record ONLY the exact URL the search tool returns.\n"
            "  ✓ URL must be from provider's official site OR recognized financial news source.\n"
            "  ✗ Do NOT fabricate, guess, or reconstruct any URL.\n"
            "  ✗ If no verifiable URL: write 'URL: N/A'.\n\n"
            "STEP 5 — Product-specific news for remaining providers (P6–P10): same rules.\n\n"
            "STEP 6 — Senior citizen & exit/liquidity search:\n"
            f"'[P1]…[P5] senior citizen rate scheme premature withdrawal exit load {region} {_CURRENT_YEAR}'\n"
            f"Deposit insurance: {_insurance_note}. Mark NBFCs / market-linked as N/A.\n\n"
            + _MD_RULES + "\n\n"
            "For EACH provider output a section:\n\n"
            "---\n"
            "### [Provider Name]\n\n"
            "| Field | Details |\n"
            "|---|---|\n"
            "| **General Rate / Return** | [X% or Expected CAGR X%] |\n"
            "| **Senior Citizen Rate** | [X% or Same as General] |\n"
            "| **Safety Classification** | **[Safe / Moderate / Risky]** |\n"
            "| **Senior Citizen Scheme** | [scheme name / 'Standard +0.50%' / 'N/A'] |\n"
            "| **Provider Type** | [Government / Private / NBFC / Asset Manager / Gov. Scheme / etc.] |\n"
            "| **Established** | [year or N/A] |\n"
            "| **AUM / Customer Base** | [AUM or approx. depositors or N/A] |\n\n"
            "#### Credit Ratings\n\n"
            "| Agency | Rating | Outlook |\n"
            "|---|---|---|\n"
            "| **Moody's** | [Rating or Not Rated] | [Outlook or N/A] |\n"
            "| **S&P Global** | [Rating or Not Rated] | [Outlook or N/A] |\n"
            "| **Fitch** | [Rating or Not Rated] | [Outlook or N/A] |\n"
            "| **Domestic ([Agency])** | [Rating or Not Rated] | [Outlook or N/A] |\n\n"
            "#### Financial Health\n\n"
            "| Metric | Value |\n"
            "|---|---|\n"
            "| **Capital Adequacy Ratio (CAR)** | [X% or N/A] |\n"
            "| **Gross NPA** | [X% or N/A for non-lending] |\n"
            "| **Net NPA** | [X% or N/A] |\n"
            "| **Net Profit (Latest)** | [Amount or N/A] |\n"
            "| **Net Interest Margin (NIM)** | [X% or N/A] |\n"
            "| **CASA Ratio** | [X% or N/A] |\n"
            "| **AUM** | [Amount or N/A] |\n\n"
            "#### Product Features & Liquidity\n\n"
            "| Feature | Details |\n"
            "|---|---|\n"
            "| **Early Exit Penalty / Exit Load** | [X% or conditions] |\n"
            "| **Deposit / Investor Insurance** | [coverage + scheme or N/A] |\n"
            "| **Loan / Pledge Against Product** | [X% or N/A] |\n"
            "| **Minimum Investment** | [amount or N/A] |\n"
            "| **Digital / Online Access** | [Yes/No] |\n"
            "| **Auto-Renewal / SIP Mandate** | [Yes/No] |\n"
            "| **Nomination Facility** | [Yes/No] |\n"
            "| **Flexible Tenure Options** | [Yes/No] |\n\n"
            "#### Recent News\n\n"
            "| # | Headline | URL |\n"
            "|---|---|---|\n"
            "| 1 | [Headline] | [exact URL or N/A] |\n"
            "| 2 | [Headline 2] | [exact URL or N/A] |\n"
            "| 3 | [Headline 3] | [exact URL or N/A] |\n\n"
            "**Safety Rationale:** [2-3 sentences referencing credit ratings, NPA, insurance, provider type]\n\n"
            "**Market Context:** [2-3 sentences on recent product-related developments]"
        ),
        expected_output=(
            "Per-provider Streamlit-renderable Markdown sections with all tables. "
            "All cells filled. Real URLs only (N/A if unavailable). No JSON, no code fences."
        ),
        agent=agents["deep_research_agent"],
        context=[identify_providers_task],
    )

    _research_report_sections = (
        "## 1. Executive Summary\n"
        "3-4 sentences: market rate/return environment, safety landscape, and the single strongest "
        "recommendation with its General rate/return, Senior rate, and projected value on a standard "
        "100,000 principal (or 10,000 monthly SIP for installment products).\n"
        "⚠ If product is market-linked (MF, NPS, SGB, BOND, T-BILL), add: "
        "'Projected returns are illustrative and not guaranteed.'\n\n"
        "## 2. Market Overview & Provider Analysis\n"
        "Per-provider sub-section:\n"
        "### [Provider Name]\n"
        "- **General Rate / Return:** [X%] | **Senior Rate:** [X%]\n"
        "- **Senior Citizen Scheme:** [scheme name or 'Standard +0.50%' or 'N/A']\n"
        "- **Safety Profile:** [Safe / Moderate / Risky]\n"
        "  - **Reason:** [1-2 sentence rationale]\n"
        "- **Market Context:** [2-3 sentences. Each news fact MUST be [Headline](URL) with real URL. "
        "If no verified URL: cite as plain text — never fabricate a URL.]\n\n"
        "## 3. Financial Projections\n"
        "Standard principal = 100,000 in local currency (or 10,000/month SIP for installment products). "
        "Tenure from context.\n"
        "| Provider | Product | Gen.Rate/Return (%) | Sr.Rate (%) | Gen.Value | Sr.Value | "
        "Gen.Gain | Sr.Gain | Safety |\n"
        "|---|---|---|---|---|---|---|---|---|\n"
        "| [Name] | [Product] | [X%] | [X%] | [amount¹] | [amount¹] | [amount] | [amount] | [Safe/Mod/Risky] |\n"
        "¹ Label as 'Projected' for market-linked products.\n"
        "Key Observations: 3-4 bullet points.\n\n"
        "## 4. Senior Citizen Guide\n"
        "| Provider | Gen.Rate | Senior Rate | Extra Benefit | Special Scheme | Insurance |\n"
        "|---|---|---|---|---|---|\n"
        "2-sentence note on eligibility and claiming the benefit.\n"
        "If product has no senior variant: note this clearly.\n\n"
        "## 5. Risk vs. Reward Assessment\n"
        "**Maximum Safety** / **High Yield** / **Balanced Choice** sub-sections.\n"
        "Include **Market / Price Risk** assessment for MF / NPS / BOND / SGB / T-BILL.\n\n"
        "## 6. Strategic Recommendations\n"
        "**Option A (Conservative)** | **Option B (Aggressive)** | **Option C (Balanced)**\n\n"
        "## 7. Conclusion\n"
        "2-3 sentences naming the best overall choice, referencing safety + return.\n\n"
        "_Disclaimer: AI-generated for informational purposes only. "
        "Market-linked products carry principal risk. Not financial advice. "
        "Verify rates/returns with providers before investing._"
    )

    compile_report_task = Task(
        description=(
            f"Request: '{user_query}'\n"
            f"Report Date: {_today}\n\n"
            "From context extract: PRODUCT_TYPE, TENURE, INTENT, all PROVIDERS with General and Senior "
            "rates/returns, senior citizen scheme details, research data (ratings, news with URLs, "
            "financials, liquidity, safety rationale, market context).\n\n"
            "Compile into a comprehensive Streamlit-renderable Markdown report.\n\n"
            + _MD_RULES + "\n\n"
            "SENIOR CITIZEN RULE: Every provider section MUST show BOTH General rate AND Senior rate. "
            "Projections table must have separate General and Senior columns. "
            "Section 4 (Senior Citizen Guide) is mandatory; if product has no senior variant, state so.\n\n"
            "MARKET-LINKED RULE: For MF, NPS, SGB, BOND, T-BILL, I-BOND — "
            "label all projected values as 'Projected (not guaranteed)' everywhere they appear.\n\n"
            "URL RULE — STRICTLY ENFORCED:\n"
            "  ✓ Markdown hyperlinks [text](url) ONLY for URLs explicitly in research context.\n"
            "  ✗ Do NOT write any URL not returned by the search tool.\n"
            "  ✗ If context says 'URL: N/A', cite as plain text — no hyperlink.\n\n"
            "PROJECTION RULE: Use compound interest for FD/TD/NSC/CD/GIC/MMARKET; "
            "recurring deposit formula for RD; SIP formula for MF/NPS; "
            "quarterly payout + principal for SCSS; coupon + face for BOND/SGB/T-NOTE/T-BOND. "
            "Use 100,000 as principal (or 10,000/month for SIP products). "
            "Compute General and Senior separately.\n\n"
            "REQUIRED SECTIONS:\n\n"
            + _research_report_sections + "\n\n"
            "After the Conclusion, append this machine-readable block:\n\n"
            "---\n"
            "**_STRUCTURED_SUMMARY_BEGIN_**\n"
            "PRODUCT_TYPE: [code]\nPRODUCT_NAME: [full name]\n"
            "PROVIDERS: [comma-separated in general-rate-descending order]\n"
            "GENERAL_RATES: [comma-separated matching PROVIDERS order]\n"
            "SENIOR_RATES: [comma-separated matching PROVIDERS order]\n"
            "GENERAL_VALUE: [comma-separated General projected values]\n"
            "SENIOR_VALUE: [comma-separated Senior projected values]\n"
            "GENERAL_GAIN: [comma-separated General gains]\n"
            "SENIOR_GAIN: [comma-separated Senior gains]\n"
            "SAFETY: [comma-separated Safe/Moderate/Risky]\n"
            "SAFEST: [provider with best ratings]\n"
            "HIGHEST_GENERAL_RATE: [provider]\nHIGHEST_SENIOR_RATE: [provider]\n"
            "LOWEST_NPA: [provider or N/A]\nINTENT: [RATES|SAFETY|COMPARISON|GENERAL]\n"
            "TENURE_MONTHS: [number]\nPRINCIPAL: 100000\nIS_MARKET_LINKED: [true/false]\n"
            "**_STRUCTURED_SUMMARY_END_**"
        ),
        expected_output=(
            "Full Streamlit-renderable Markdown report with all 7 sections, "
            "product-appropriate projections, real URLs only, and STRUCTURED_SUMMARY block."
        ),
        agent=agents["research_compilation_agent"],
        context=[identify_providers_task, deep_research_task],
    )

    return [identify_providers_task, deep_research_task, compile_report_task]


# ---------------------------------------------------------------------------
# Database pipeline
# ---------------------------------------------------------------------------

def create_database_tasks(agents, user_query: str):
    return [Task(
        description=(
            f"Request: '{user_query}'.\n"
            f"Schema:\n{DB_SCHEMA_INFO}\n"
            "Use 'Bank Database Query Tool' to write and run SQL. "
            "Start with SELECT * FROM ... LIMIT 5 if unsure of structure.\n"
            "The product_type column may contain: FD, TD, RD, PPF, NSC, KVP, SSY, SCSS, SGB, NPS, "
            "MF, BOND, CD, T-BILL, T-NOTE, T-BOND, I-BOND, ISA, GIC, MURABAHA, MMARKET, PREMIUM_BOND, SSB.\n\n"
            "OUTPUT FORMAT: Valid Streamlit-renderable Markdown. "
            "Use tables with | delimiters for tabular data. Bold key values with **. "
            "Use bullet points (-) for lists. No JSON, no code fences."
        ),
        expected_output="Clear Markdown-formatted answer based on SQL query results.",
        agent=agents["db_agent"],
    )]


# ---------------------------------------------------------------------------
# Onboarding pipeline
# ---------------------------------------------------------------------------

def create_data_collection_task(agents, conversation_history: str,
                                 country_name: str = "India",
                                 kyc_doc1: str = "", kyc_doc2: str = ""):
    if kyc_doc1 and kyc_doc2:
        kyc_instructions = (
            f"KYC documents for {country_name} are already known: '{kyc_doc1}' and '{kyc_doc2}'. "
            "Skip KYC search. Go to STEP 2."
        )
    else:
        kyc_instructions = (
            f"STEP 1: Search 'primary KYC documents for bank account opening in {country_name}'. "
            "Identify TOP 2 mandatory government IDs."
        )

    doc1_label = kyc_doc1 or "KYC Doc 1"
    doc2_label = kyc_doc2 or "KYC Doc 2"

    # Get available products for this country
    _code = _region_code(country_name)
    _products = _REGION_PRODUCTS.get(_code, ["FD", "TD", "RD", "MF", "BOND"])
    _products_inline = " / ".join(_products)

    return Task(
        description=(
            f"Conversation History:\n{conversation_history}\n\n"
            f"User Country: {country_name}\n\n"
            f"{kyc_instructions}\n\n"
            f"STEP 2: Check all fields collected: Name, Email, Address, PIN, Mobile, Bank/Provider Name, "
            f"Product Type ({_products_inline}), Amount, Tenure, Compounding, {doc1_label}, {doc2_label}.\n\n"
            "STEP 3: If anything missing, ask ONE question: 'QUESTION: [your question]'\n\n"
            "STEP 4: If ALL present, output:\n"
            'DATA_READY: {"first_name":"...","last_name":"...","email":"...","user_address":"...",'
            '"pin_number":"...","mobile_number":"...","bank_name":"...","product_type":"FD",'
            '"initial_amount":0,"tenure_months":0,"compounding_freq":"quarterly",'
            '"kyc_details_1":"DOC_NAME-DOC_VALUE","kyc_details_2":"DOC_NAME-DOC_VALUE"}'
        ),
        expected_output="Either 'QUESTION: ...' or 'DATA_READY: {...}'",
        agent=agents["onboarding_data_agent"],
    )


# ---------------------------------------------------------------------------
# AML execution pipeline
# ---------------------------------------------------------------------------

def create_aml_execution_tasks(agents, client_data_json: str):

    neo4j_search_task = Task(
        description=(
            f"Client Data:\n{client_data_json}\n\n"
            "STEP 1 — Extract first_name and last_name from the client data above.\n"
            "If only a 'name' field exists, split on space: first word = first_name, rest = last_name.\n\n"
            "STEP 2 — Call 'Neo4j Entity Name Search' with the extracted first_name and last_name.\n"
            "Use default max_hops=4, limit_nodes=20, limit_results=50.\n\n"
            "The tool executes this Cypher query internally (example with first_name='Alaa', last_name='Mubarak'):\n\n"
            "// Phase 1: Identify the starting node based on name variations\n"
            "MATCH (p)\n"
            "WHERE any(label IN labels(p) WHERE label IN ['Officer','Entity','Intermediary','Other'])\n"
            "  AND (\n"
            "    toLower(p.name) CONTAINS toLower('Alaa Mubarak')\n"
            "    OR toLower(p.name) CONTAINS toLower('Mubarak, Alaa')\n"
            "    OR toLower(p.name) CONTAINS toLower('Mubarak Alaa')\n"
            "    OR toLower(p.original_name) CONTAINS toLower('Alaa Mubarak')\n"
            "    OR toLower(p.translit_name) CONTAINS toLower('Alaa Mubarak')\n"
            "    OR (toLower(p.name) CONTAINS toLower('Alaa') AND toLower(p.name) CONTAINS toLower('Mubarak'))\n"
            "  )\n"
            "WITH p LIMIT 20\n\n"
            "// Phase 2: Expand the network to find related entities\n"
            "MATCH (p)-[r*1..4]-(connected)\n"
            "RETURN p, r, connected\n"
            "LIMIT 50\n\n"
            "If the primary search returns no results, the tool automatically retries with a broader query.\n\n"
            "STEP 3 — Report all nodes/relationships, the exact GRAPH_IMAGE_PATH line verbatim, "
            "and a short network summary."
        ),
        expected_output="Graph findings with node/relationship details and exact GRAPH_IMAGE_PATH.",
        agent=agents["neo4j_agent"],
    )

    sanctions_task = Task(
        description=(
            f"Client Data:\n{client_data_json}\n\n"
            'Build JSON: {"schema":"Person","name":"<full_name>","birth_date":"<dob>","nationality":"<nationality>"}\n'
            "Add any extra available fields. Pass to 'Deep Entity Enrichment (Yente/OpenSanctions)'. "
            "Trust score > 0.5 only.\n"
            "Report ALL fields verbatim: risk_flags, topics, sanctions_programs, related_entities, "
            "match_score, positions, aliases, nationalities, sources. Preserve the 'ENTITY_NAME:' line."
        ),
        expected_output="Yente sanctions/PEP report with all fields including verbatim ENTITY_NAME line.",
        agent=agents["sanctions_agent"],
    )

    osint_task = Task(
        description=(
            "From Yente context:\n"
            "STEP 1 — Pass full Yente output (including ENTITY_NAME: line) to 'Wikidata Subject Image Fetcher'. "
            "Record: WIKIDATA_IMAGE_PATH, Wikipedia description, organisations, positions, social media URLs.\n"
            "STEP 2 — Adverse media: use 'NewsAPI Entity Search' first "
            "(entity_name='[Client Full Name]', context='sanctions fraud crime'). "
            "Fall back to 'DuckDuckGo News Search' if unavailable. Also search each related_entity.\n"
            "Output Markdown:\n"
            "1. Wikidata Profile (image path, biography, organisations).\n"
            "2. Social Media and Web Presence.\n"
            "3. Adverse Media (headlines + exact URLs — never invent)."
        ),
        expected_output="OSINT report with WIKIDATA_IMAGE_PATH, biography, social URLs, adverse media links.",
        agent=agents["osint_agent"],
        context=[sanctions_task],
    )

    ubo_task = Task(
        description=(
            f"Client Data:\n{client_data_json}\n\n"
            "Review Neo4j graph and Yente sanctions from context.\n"
            "COMPANY client: search directors/shareholders via Yente; check if sanctioned.\n"
            "PERSON client: find companies they are 'officer_of' from Neo4j. "
            "Use 'NewsAPI Entity Search' first (entity_name='[Company]', context='ownership shareholders directors'); "
            "fall back to DuckDuckGo.\n"
            "For each UBO: Name | Role | Yente Match Score | Sanctions/PEP Status | Source"
        ),
        expected_output="Table of UBOs with individual risk assessments and sources.",
        agent=agents["ubo_investigator_agent"],
        context=[neo4j_search_task, sanctions_task],
    )

    live_enrichment_task = Task(
        description=(
            f"Client Data:\n{client_data_json}\n\n"
            "STEP 1 — Re-run 'Deep Entity Enrichment (Yente)' for: a) primary client, "
            "b) every flagged related_entity, c) every UBO. Append new sanctions/aliases/positions.\n"
            "STEP 2 — Pass latest Yente output to 'Wikidata Subject Image Fetcher' for each flagged entity. "
            "Record exact WIKIDATA_IMAGE_PATH.\n"
            "Output: Entity | New Sanctions Found | New Aliases | WIKIDATA_IMAGE_PATH"
        ),
        expected_output="Enrichment table: updated sanctions data and WIKIDATA_IMAGE_PATH per entity.",
        agent=agents["live_enrichment_agent"],
        context=[sanctions_task, osint_task, ubo_task],
    )

    risk_scoring_task = Task(
        description=(
            "Synthesise ALL context into a court-ready AML compliance report.\n\n"
            f"Client Data:\n{client_data_json}\n\n"
            "Rules:\n"
            "1. HEADER: client full name + current datetime (YYYY-MM-DD HH:MM:SS).\n"
            "2. VERBATIM: every figure, score, flag, entity, sanction ID, relationship, match score, graph path.\n"
            "3. NEWS URLs: search '[Entity] sanctions fraud investigation' via DuckDuckGo. "
            "Embed as Markdown hyperlinks. Never invent URLs.\n"
            "4. SCORE TABLE: Risk Factor | Points | Rationale | Evidence Link. Bold total row.\n"
            "5. GRAPH: re-state exact GRAPH_IMAGE_PATH from neo4j context.\n\n"
            "Required sections:\n"
            "# AML Compliance Report — [Client Full Name]\n"
            "**Generated:** [datetime] | **Prepared by:** Chief Risk Officer | **Classification:** CONFIDENTIAL\n\n"
            "## Executive Summary\nDECISION: [PASS or FAIL]\nSCORE: [N]\nREASONING: [1 sentence]\n\n"
            "## 1. Subject Identity Profile\n"
            "## 2. Sanctions and PEP Status\n"
            "## 3. Neo4j Graph Analysis (GRAPH_IMAGE_PATH: [exact path])\n"
            "## 4. UBO Analysis\n"
            "## 5. OSINT and Media Intelligence\n"
            "## 6. Risk Score Breakdown (4-column table)\n"
            "## 7. Recommendations (numbered, with FATF references)\n"
            "## 8. Data Sources and Tool Audit\n\n"
            "---\n*Auto-generated by Compliance AI. Internal use only.*"
        ),
        expected_output=(
            "Court-ready Markdown AML report with timestamp header, all risk data verbatim, "
            "DDG hyperlinks, 4-column score table, FATF recommendations, GRAPH_IMAGE_PATH preserved, "
            "DECISION/SCORE/REASONING clearly stated."
        ),
        agent=agents["risk_scoring_agent"],
        context=[neo4j_search_task, sanctions_task, osint_task, ubo_task, live_enrichment_task],
    )

    create_deposit_task = Task(
        description=(
            "Check the DECISION line in the compliance report from context.\n"
            "If 'DECISION: FAIL': output exactly 'STOP: Application Rejected.' — do nothing else.\n"
            "If 'DECISION: PASS':\n"
            "  1. Search current interest/return rate for the provider and product type.\n"
            "  2. Use 'Deposit Creator' to create the investment record.\n"
            "  3. Output: Deposit ID, Product Type, Interest/Return Rate Used, Maturity Date.\n\n"
            f"Client Data:\n{client_data_json}"
        ),
        expected_output="Deposit ID + Product Type + Maturity Date on PASS, or 'STOP: Application Rejected.' on FAIL.",
        agent=agents["fd_processor_agent"],
        context=[risk_scoring_task],
    )

    pdf_task = Task(
        description=(
            "Use the full Markdown compliance report from risk_scoring context as 'markdown_content'.\n\n"
            "Extract from context (search ALL task outputs carefully):\n"
            "  - GRAPH_IMAGE_PATH (from neo4j task) → 'graph_image_path' argument\n"
            "  - WIKIDATA_IMAGE_PATH (from osint or live_enrichment task) → 'subject_image_path' argument\n"
            "  - SOCIAL_MEDIA_SECTION (from osint task) → 'social_media_section'\n"
            "  - RELATIVES_SECTION (from osint task) → 'relatives_section'\n"
            "  - BIOGRAPHY_SECTION (from osint task) → 'biography_section'\n"
            "  - DECISION: PASS or FAIL\n"
            f"  - first_name, last_name from: {client_data_json}\n\n"
            "Pass FULL raw text of each section verbatim — do NOT summarize.\n\n"
            "Filename: {first_name}_{last_name}_{DECISION}  (e.g. John_Doe_PASS)\n"
            "Title: 'Application Rejection Report' (FAIL) or 'Application Approval and Compliance Report' (PASS).\n\n"
            "Call 'Markdown Report Generator' with ALL arguments. Output the exact PDF path returned. "
            "Also output: PDF_PATH: <exact path>"
        ),
        expected_output="Exact PDF file path from Markdown Report Generator. Must include a line: PDF_PATH: <path>",
        agent=agents["pdf_generator_agent"],
        context=[risk_scoring_task, create_deposit_task, neo4j_search_task, live_enrichment_task, osint_task],
    )

    email_task = Task(
        description=(
            f"Recipient email from client data:\n{client_data_json}\n\n"
            "Get DECISION from risk_scoring context. "
            "Get PDF path from pdf_task context (line starting 'PDF_PATH:').\n\n"
            "FAIL — Subject: 'Application Update'\n"
            "Body: 'We regret to inform you that we are unable to proceed with your application "
            "due to compliance requirements. Please find the detailed report attached.'\n\n"
            "PASS — Subject: 'Investment Created — Compliance Report Attached'\n"
            "Body: 'Your investment has been successfully created. "
            "Please find your personalised compliance report attached.'\n\n"
            "Call 'Email Sender' with to_email, subject, body, attachment_paths=[PDF_PATH]. "
            "Send EXACTLY ONE email.\n\n"
            "CRITICAL: Your final output MUST be the PDF file path (the line starting 'PDF_PATH:'). "
            "Do NOT output the email confirmation as your final answer."
        ),
        expected_output="The exact PDF_PATH: <path> line from pdf_task context.",
        agent=agents["email_sender_agent"],
        context=[pdf_task, risk_scoring_task],
    )

    return [
        neo4j_search_task, sanctions_task, osint_task,
        ubo_task, live_enrichment_task, risk_scoring_task,
        create_deposit_task, pdf_task, email_task,
    ]


# ---------------------------------------------------------------------------
# Visualization
# ---------------------------------------------------------------------------

def create_visualization_task(agents, user_query: str, data_context: str):
    has_context = bool(data_context and data_context != "null" and len(data_context) > 50)
    data_instruction = (
        "Use the DataFrame JSON context primarily. Only search web if user asks for external data."
        if has_context
        else "No data context. Use DuckDuckGo to fetch necessary data first."
    )

    return Task(
        description=(
            f"Query: '{user_query}'\n"
            f"Data Context: {data_context if has_context else 'None'}\n\n"
            f"1. {data_instruction}\n"
            "2. Create an Apache ECharts JSON configuration.\n"
            "3. Match chart type: 'bar'→type bar, 'line'→type line, 'pie'→type pie.\n\n"
            'Schema: {"title":{"text":"Title","left":"center"},"tooltip":{"trigger":"axis"},'
            '"legend":{"data":["S1"],"bottom":0},"xAxis":{"type":"category","data":["L1","L2"]},'
            '"yAxis":{"type":"value","name":"Label"},"series":[{"name":"S1","type":"bar","data":[10,20]}]}\n\n'
            "Rules: output ONLY raw JSON object or list, no fences, no 'options' wrapper. "
            "xAxis data and series data MUST have same length. Multiple metrics → return list."
        ),
        expected_output="Valid JSON object or list configuring an EChart. No fences, no wrapper keys.",
        agent=agents["data_visualizer_agent"],
    )


# ---------------------------------------------------------------------------
# Credit risk
# ---------------------------------------------------------------------------

def create_credit_risk_tasks(agents, borrower_json: str = "{}"):

    collect_task = Task(
        description=(
            f"Borrower data so far:\n{borrower_json}\n\n"
            "Check if ALL required fields present: loan_amnt, term, int_rate, annual_inc, dti, "
            "fico_score, home_ownership, delinq_2yrs, inq_last_6mths, pub_rec, earliest_cr_line, "
            "revol_util, revol_bal, purpose, emp_length.\n\n"
            "If missing: ask ONE question: 'QUESTION: [your question]'\n"
            "If complete: output: DATA_READY: {full JSON}"
        ),
        expected_output="Either 'QUESTION: ...' or 'DATA_READY: {...}'",
        agent=agents["credit_risk_collector_agent"],
    )

    analysis_task = Task(
        description=(
            "Pass borrower JSON from context to 'US Credit Risk Scorer'.\n"
            "Write a professional credit-risk memo:\n\n"
            "# Credit Risk Assessment Memo\n"
            "**Grade:** [grade] | **Default Probability:** [pct] | **Risk:** [level]\n\n"
            "## Borrower Profile Summary — one paragraph: income, debt burden, credit history.\n\n"
            "## Key Risk Drivers\n"
            "Table: Feature | Value | Importance | Interpretation (use top_features from tool).\n\n"
            "## Credit Committee Recommendation — 2-3 sentences: approve/decline/conditional.\n\n"
            "## Caveats\n"
            "- Model trained on US Lending Club data (2007-2018); current-vintage performance unvalidated.\n"
            "- Survivorship bias: only approved loans in training set.\n"
            "- XGBoost may produce non-monotonic predictions; verify edge cases for regulatory use."
        ),
        expected_output="Credit-risk memo in Markdown with grade, probability, risk-driver table, recommendation.",
        agent=agents["credit_risk_analyst_agent"],
        context=[collect_task],
    )

    return [collect_task, analysis_task]


# ---------------------------------------------------------------------------
# Routing
# ---------------------------------------------------------------------------

# Extended product keyword list for routing
_PRODUCT_KEYWORDS = (
    "fd", "fixed deposit", "rd", "recurring deposit", "td", "term deposit",
    "ppf", "provident fund", "nsc", "savings certificate", "kvp", "kisan vikas",
    "ssy", "sukanya", "scss", "senior citizen scheme", "sgb", "gold bond",
    "nps", "pension", "mutual fund", "sip", "mf", "bond", "debenture",
    "cd", "certificate of deposit", "t-bill", "treasury bill", "treasury note",
    "treasury bond", "i-bond", "inflation bond", "isa", "individual savings",
    "premium bond", "gic", "guaranteed investment", "singapore savings bond",
    "ssb", "murabaha", "islamic deposit", "money market"
)

_ANALYSIS_SIGNALS = (
    "amount", "tenure", "invest", "maturity", "options", "rates", "compare",
    "returns", "calculate", "projection", "yield", "profit", "earn", "best rate",
    "how much will i get", "what will i earn", "interest on", "return on"
) + _PRODUCT_KEYWORDS


def create_routing_task(agents, user_query: str):
    return Task(
        description=(
            f"Classify into ONE label: ANALYSIS, RESEARCH, DATABASE, or ONBOARDING.\n"
            f"QUERY: \"{user_query}\"\n\n"
            "ANALYSIS: compare/calculate returns for any investment product. "
            "Signals: amount+tenure, options/rates/compare/returns/maturity/calculate, "
            "or any product name (FD, RD, PPF, NSC, KVP, SSY, SCSS, SGB, NPS, MF, BOND, "
            "CD, T-BILL, T-NOTE, T-BOND, I-BOND, ISA, GIC, MURABAHA, MMARKET).\n"
            "RESEARCH: general info about products, no calculation. "
            "Signals: explain/tell me/what is/how does/difference between.\n"
            "DATABASE: existing system records. "
            "Signals: my account/my FD/my PPF/my investment/show/list/check/account number.\n"
            "ONBOARDING: open/create/apply RIGHT NOW. "
            "Signals: open account/create FD/apply for RD/start PPF/invest in/register me.\n"
            "Note: 'I have 500k to deposit' = ANALYSIS. When in doubt → ANALYSIS.\n\n"
            "Respond with ONLY one word: ANALYSIS, RESEARCH, DATABASE, or ONBOARDING."
        ),
        expected_output="Single word: ANALYSIS, RESEARCH, DATABASE, or ONBOARDING",
        agent=agents["manager_agent"],
    )