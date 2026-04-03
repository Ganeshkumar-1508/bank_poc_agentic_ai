# tools/calculator_tool.py
# ---------------------------------------------------------------------------
# Universal Investment Product Calculator
#
# Supports: FD, TD, CD, RD, PPF, NSC, KVP, SSY, SCSS, SGB, NPS, MF,
#           BOND, T-BILL, T-NOTE, T-BOND, I-BOND, ISA, GIC, MURABAHA,
#           MMARKET — with region-awareness.
# ---------------------------------------------------------------------------

import math
from typing import Type, Optional, List, Dict

from crewai.tools import BaseTool
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Product Registry — central source of truth
# ---------------------------------------------------------------------------

PRODUCT_REGISTRY: Dict[str, Dict] = {
    # ── Global / widely available ───────────────────────────────────────────
    "FD":           {"name": "Fixed Deposit",                    "regions": "ALL"},
    "TD":           {"name": "Term Deposit",                     "regions": "ALL"},
    "RD":           {"name": "Recurring Deposit",                "regions": ["IN", "PK", "BD", "LK", "NP", "MY"]},
    "MF":           {"name": "Mutual Fund / SIP",                "regions": "ALL"},
    "BOND":         {"name": "Corporate / Government Bond",      "regions": "ALL"},
    "MMARKET":      {"name": "Money Market Account",             "regions": "ALL"},

    # ── India ───────────────────────────────────────────────────────────────
    "PPF":          {"name": "Public Provident Fund",            "regions": ["IN"]},
    "NSC":          {"name": "National Savings Certificate",     "regions": ["IN"]},
    "KVP":          {"name": "Kisan Vikas Patra",                "regions": ["IN"]},
    "SSY":          {"name": "Sukanya Samriddhi Yojana",         "regions": ["IN"]},
    "SCSS":         {"name": "Senior Citizens Savings Scheme",   "regions": ["IN"]},
    "SGB":          {"name": "Sovereign Gold Bond",              "regions": ["IN"]},
    "NPS":          {"name": "National Pension System",          "regions": ["IN"]},

    # ── United States ───────────────────────────────────────────────────────
    "CD":           {"name": "Certificate of Deposit",          "regions": ["US"]},
    "T-BILL":       {"name": "Treasury Bill",                   "regions": ["US"]},
    "T-NOTE":       {"name": "Treasury Note",                   "regions": ["US"]},
    "T-BOND":       {"name": "Treasury Bond",                   "regions": ["US"]},
    "I-BOND":       {"name": "I Bond (Inflation-Protected)",    "regions": ["US"]},

    # ── United Kingdom ──────────────────────────────────────────────────────
    "ISA":          {"name": "Individual Savings Account",      "regions": ["GB", "UK"]},
    "PREMIUM_BOND": {"name": "Premium Bond (NS&I)",             "regions": ["GB", "UK"]},

    # ── Canada ──────────────────────────────────────────────────────────────
    "GIC":          {"name": "Guaranteed Investment Certificate","regions": ["CA"]},

    # ── Singapore ───────────────────────────────────────────────────────────
    "SSB":          {"name": "Singapore Savings Bond",          "regions": ["SG"]},

    # ── Gulf / Islamic finance ──────────────────────────────────────────────
    "MURABAHA":     {"name": "Murabaha / Islamic Term Deposit",  "regions": ["AE", "SA", "KW", "BH", "OM", "QA", "MY"]},
}

# Region-name → ISO-2 code lookup (for human-readable region strings)
_REGION_NAME_TO_CODE: Dict[str, str] = {
    "INDIA": "IN", "UNITED STATES": "US", "USA": "US", "AMERICA": "US",
    "UK": "GB", "UNITED KINGDOM": "GB", "BRITAIN": "GB", "ENGLAND": "GB",
    "AUSTRALIA": "AU", "CANADA": "CA", "SINGAPORE": "SG",
    "UAE": "AE", "DUBAI": "AE", "GULF": "AE", "MALAYSIA": "MY",
    "PAKISTAN": "PK", "BANGLADESH": "BD", "SRI LANKA": "LK", "NEPAL": "NP",
    "SAUDI ARABIA": "SA", "KUWAIT": "KW", "BAHRAIN": "BH", "OMAN": "OM", "QATAR": "QA",
    "WORLDWIDE": "WW", "GLOBAL": "WW",
}

# Ordered product lists per region (shown in prompts / Streamlit UI)
_REGION_PRODUCT_LISTS: Dict[str, List[str]] = {
    "IN": ["FD", "RD", "PPF", "NSC", "KVP", "SSY", "SCSS", "SGB", "NPS", "MF", "BOND"],
    "US": ["FD", "CD", "T-BILL", "T-NOTE", "T-BOND", "I-BOND", "MMARKET", "MF", "BOND"],
    "GB": ["FD", "TD", "ISA", "PREMIUM_BOND", "MMARKET", "MF", "BOND"],
    "AU": ["FD", "TD", "MMARKET", "MF", "BOND"],
    "CA": ["FD", "GIC", "MMARKET", "MF", "BOND"],
    "SG": ["FD", "TD", "SSB", "MF", "BOND"],
    "AE": ["FD", "TD", "MURABAHA", "MF", "BOND"],
    "MY": ["FD", "RD", "MURABAHA", "MF", "BOND"],
    "PK": ["FD", "RD", "MF", "BOND"],
    "BD": ["FD", "RD", "MF", "BOND"],
    "LK": ["FD", "RD", "MF", "BOND"],
    "DEFAULT": ["FD", "TD", "RD", "MF", "BOND"],
}


def get_available_products(region: str) -> List[str]:
    """Return ordered list of product codes available in *region*.

    *region* may be a country name (e.g. 'India') or ISO-2 code (e.g. 'IN').
    """
    code = _REGION_NAME_TO_CODE.get(region.upper(), region.upper()[:2] if len(region) >= 2 else "IN")
    return _REGION_PRODUCT_LISTS.get(code, _REGION_PRODUCT_LISTS["DEFAULT"])


def get_products_display_str(region: str) -> str:
    """Human-readable bullet list of available products for *region* (used in prompts)."""
    codes = get_available_products(region)
    lines = [f"  - {c}: {PRODUCT_REGISTRY.get(c, {}).get('name', c)}" for c in codes]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Per-product calculation helpers
# ---------------------------------------------------------------------------

def _freq_n(compounding_freq: str) -> int:
    return {"monthly": 12, "quarterly": 4, "half_yearly": 2, "yearly": 1}.get(
        compounding_freq.lower().replace("-", "_").replace(" ", "_"), 4
    )


def _pay_n(payment_freq: str) -> int:
    """Periods per year for coupon / interest payouts."""
    return {"monthly": 12, "quarterly": 4, "semi_annual": 2, "half_yearly": 2, "annual": 1, "yearly": 1}.get(
        payment_freq.lower().replace("-", "_").replace(" ", "_"), 2
    )


def _calc_compound(principal: float, rate: float, tenure_months: float, n: int):
    """Standard compound interest — used for FD / TD / CD / GIC / NSC / ISA / MMARKET / Murabaha."""
    r = rate / 100
    t = tenure_months / 12
    maturity = principal * (1 + r / n) ** (n * t)
    return round(maturity, 2), round(maturity - principal, 2)


def _calc_rd(monthly: float, rate: float, tenure_months: float, n: int):
    """Recurring Deposit — post-paid installments, compounded n times/year."""
    r = rate / 100
    t = tenure_months / 12
    rate_per_period = r / n
    total_periods = n * t
    periods_per_month = n / 12
    if periods_per_month == 0:
        raise ValueError(f"Compounding frequency yields 0 periods/month.")
    growth_factor = (1 + rate_per_period) ** total_periods
    maturity = monthly * (growth_factor - 1) / (1 - (1 + rate_per_period) ** (-periods_per_month))
    invested = monthly * tenure_months
    return round(maturity, 2), round(maturity - invested, 2), round(invested, 2)


def _calc_ppf(annual_deposit: float, rate: float, tenure_years: int = 15):
    """PPF — annual deposits compounded yearly; interest exempt under 80C."""
    r = rate / 100
    maturity = sum(annual_deposit * (1 + r) ** (tenure_years - y + 1) for y in range(1, tenure_years + 1))
    invested = annual_deposit * tenure_years
    return round(maturity, 2), round(maturity - invested, 2), round(invested, 2)


def _calc_nsc(principal: float, rate: float, years: int = 5):
    """NSC — lump sum, annually compounded, paid at maturity."""
    r = rate / 100
    maturity = principal * (1 + r) ** years
    return round(maturity, 2), round(maturity - principal, 2)


def _calc_kvp(principal: float, rate: float):
    """KVP — doubles money at given annual rate.  Returns (doubled_amount, months_to_double)."""
    r = rate / 100
    months_to_double = math.ceil(math.log(2) / math.log(1 + r) * 12)
    return round(principal * 2, 2), round(principal, 2), months_to_double


def _calc_scss(principal: float, rate: float, tenure_years: int = 5):
    """SCSS — quarterly interest PAYOUT (not compounded); principal returned at maturity."""
    quarterly_payout = round(principal * rate / 100 / 4, 2)
    total_interest = round(principal * rate / 100 * tenure_years, 2)
    return principal, total_interest, quarterly_payout


def _calc_ssy(annual_deposit: float, rate: float, deposit_years: int = 15, total_years: int = 21):
    """SSY — deposits for first *deposit_years*; corpus grows until *total_years*."""
    r = rate / 100
    maturity = sum(annual_deposit * (1 + r) ** (total_years - y + 1) for y in range(1, deposit_years + 1))
    invested = annual_deposit * deposit_years
    return round(maturity, 2), round(maturity - invested, 2), round(invested, 2)


def _calc_sgb(principal: float, coupon_rate: float = 2.5, tenure_years: int = 8):
    """SGB — fixed 2.5% p.a. coupon paid semi-annually.
    Gold-price appreciation is NOT modelled (marked as variable)."""
    total_coupon = round(principal * coupon_rate / 100 * tenure_years, 2)
    semi_annual_coupon = round(principal * coupon_rate / 100 / 2, 2)
    return principal + total_coupon, total_coupon, semi_annual_coupon


def _calc_nps(monthly: float, expected_return: float, tenure_years: int):
    """NPS — SIP-style monthly contributions; projected corpus split 60% lump / 40% annuity."""
    r = expected_return / 100 / 12
    n = tenure_years * 12
    corpus = monthly * ((1 + r) ** n - 1) / r * (1 + r) if r > 0 else monthly * n
    invested = monthly * n
    lump = round(corpus * 0.6, 2)
    annuity_corpus = round(corpus * 0.4, 2)
    return round(corpus, 2), round(corpus - invested, 2), round(invested, 2), lump, annuity_corpus


def _calc_mf_sip(monthly: float, expected_return: float, tenure_months: float):
    """MF SIP — monthly installment compounded monthly at expected CAGR."""
    r = expected_return / 100 / 12
    n = tenure_months
    maturity = monthly * ((1 + r) ** n - 1) / r * (1 + r) if r > 0 else monthly * n
    invested = monthly * tenure_months
    return round(maturity, 2), round(maturity - invested, 2), round(invested, 2)


def _calc_bond(face_value: float, coupon_rate: float, tenure_years: float, payment_freq: str = "semi_annual"):
    """Bond — periodic coupon payments + face value returned at maturity."""
    n = _pay_n(payment_freq)
    coupon_per_period = face_value * coupon_rate / 100 / n
    total_periods = n * tenure_years
    total_coupon = round(coupon_per_period * total_periods, 2)
    coupon_str = f"{coupon_per_period:,.2f} per period ({payment_freq.replace('_', '-')} × {int(total_periods)})"
    return face_value + total_coupon, total_coupon, coupon_str


def _calc_tbill(face_value: float, discount_rate: float, weeks: int = 26):
    """T-Bill — discount instrument; purchase price = face value discounted at given rate."""
    purchase_price = face_value * (1 - discount_rate / 100 * weeks / 52)
    gain = face_value - purchase_price
    return round(face_value, 2), round(gain, 2), round(purchase_price, 2)


def _calc_ibond(principal: float, fixed_rate: float, inflation_rate: float, tenure_years: int = 1):
    """I-Bond (US) — composite rate ≈ fixed_rate + 2*inflation_rate + fixed_rate*inflation_rate."""
    f = fixed_rate / 100
    i = inflation_rate / 100
    composite = f + 2 * i + f * i
    maturity = principal * (1 + composite / 2) ** (2 * tenure_years)  # semi-annual compounding
    return round(maturity, 2), round(maturity - principal, 2), round(composite * 100, 4)


def _calc_premium_bond(principal: float, prize_rate: float = 4.4):
    """Premium Bond (UK NS&I) — no guaranteed interest; prize fund rate used as expected return."""
    expected_gain = round(principal * prize_rate / 100, 2)
    return round(principal + expected_gain, 2), expected_gain


# ---------------------------------------------------------------------------
# Input schema
# ---------------------------------------------------------------------------

class UniversalDepositCalculatorInput(BaseModel):
    deposit_type: str = Field(
        ...,
        description=(
            "Investment product code. Global: FD, TD, RD, MF, BOND, MMARKET. "
            "India: PPF, NSC, KVP, SSY, SCSS, SGB, NPS. "
            "US: CD, T-BILL, T-NOTE, T-BOND, I-BOND. "
            "UK: ISA, PREMIUM_BOND. Canada: GIC. Singapore: SSB. Gulf: MURABAHA."
        ),
    )
    amount: float = Field(..., description="Principal (FD/NSC/BOND/SGB/…), monthly installment (RD/MF-SIP/NPS), or annual deposit (PPF/SSY).")
    rate: float = Field(..., description="Annual interest / coupon / expected-return rate (%). For I-BOND: fixed-rate component.")
    tenure_months: int = Field(..., description="Tenure in months. PPF default=180, NSC=60, KVP=115, SSY=252, SCSS=60, SGB=96.")
    compounding_freq: str = Field(default="quarterly", description="monthly / quarterly / half_yearly / yearly (ignored for payout products like SCSS, BOND).")
    senior_rate: Optional[float] = Field(default=None, description="Senior citizen rate — when set, returns both General and Senior projections.")
    payment_freq: Optional[str] = Field(default="semi_annual", description="Coupon / interest payout frequency for BOND, SGB, SCSS: annual / semi_annual / quarterly.")
    inflation_rate: Optional[float] = Field(default=None, description="Inflation rate (%) — required for I-BOND composite calculation.")
    is_sip: Optional[bool] = Field(default=False, description="Set True for MF/NPS when amount is a monthly SIP installment.")


# ---------------------------------------------------------------------------
# Tool
# ---------------------------------------------------------------------------

class UniversalDepositCalculatorTool(BaseTool):
    name: str = "Deposit_Calculator"
    description: str = (
        "Calculate maturity / projected corpus for any investment product: "
        "FD, TD, CD, RD, PPF, NSC, KVP, SSY, SCSS, SGB, NPS, MF (lump-sum or SIP), "
        "BOND, T-BILL, T-NOTE, T-BOND, I-BOND, ISA, GIC, MURABAHA, MMARKET, PREMIUM_BOND. "
        "Set senior_rate to get both General + Senior projections in one call."
    )
    args_schema: Type[BaseModel] = UniversalDepositCalculatorInput
    cache: bool = True

    def _run(  # noqa: C901  (complexity acceptable for dispatcher)
        self,
        deposit_type: str,
        amount: float,
        rate: float,
        tenure_months: int,
        compounding_freq: str = "quarterly",
        senior_rate: Optional[float] = None,
        payment_freq: Optional[str] = "semi_annual",
        inflation_rate: Optional[float] = None,
        is_sip: Optional[bool] = False,
    ) -> str:
        try:
            dtype = deposit_type.upper().replace("-", "_").replace(" ", "_")
            n = _freq_n(compounding_freq)
            tenure_years = tenure_months / 12
            pf = payment_freq or "semi_annual"

            # ── Dispatch ─────────────────────────────────────────────────────

            # FD / TD / CD / GIC / MMARKET / MURABAHA / SSB / ISA (lump-sum) / T-NOTE / T-BOND
            if dtype in ("FD", "TD", "CD", "GIC", "MMARKET", "MURABAHA", "SSB",
                         "T_NOTE", "T_BOND"):
                product_label = PRODUCT_REGISTRY.get(
                    deposit_type.upper().replace("_", "-"), {}
                ).get("name", deposit_type.upper())
                if senior_rate is not None:
                    g_mat, g_int = _calc_compound(amount, rate, tenure_months, n)
                    s_mat, s_int = _calc_compound(amount, senior_rate, tenure_months, n)
                    return self._dual_rate_output(product_label, amount, tenure_months, compounding_freq,
                                                  rate, senior_rate, g_mat, g_int, s_mat, s_int,
                                                  f"Principal: {amount:,.2f}")
                mat, interest = _calc_compound(amount, rate, tenure_months, n)
                return (
                    f"Product: {product_label}\nPrincipal: {amount:,.2f}\n"
                    f"Rate: {rate}% | Tenure: {tenure_months} months | Compounding: {compounding_freq.capitalize()}\n"
                    f"Maturity Amount: {mat:,.2f}\nInterest Earned: {interest:,.2f}"
                )

            # RD
            if dtype == "RD":
                if senior_rate is not None:
                    g_mat, g_int, g_inv = _calc_rd(amount, rate, tenure_months, n)
                    s_mat, s_int, _ = _calc_rd(amount, senior_rate, tenure_months, n)
                    return self._dual_rate_output("Recurring Deposit", amount, tenure_months, compounding_freq,
                                                  rate, senior_rate, g_mat, g_int, s_mat, s_int,
                                                  f"Monthly Installment: {amount:,.2f} | Total Invested: {g_inv:,.2f}")
                mat, interest, invested = _calc_rd(amount, rate, tenure_months, n)
                return (
                    f"Product: Recurring Deposit\nMonthly Installment: {amount:,.2f}\n"
                    f"Total Invested: {invested:,.2f}\n"
                    f"Rate: {rate}% | Tenure: {tenure_months} months | Compounding: {compounding_freq.capitalize()}\n"
                    f"Maturity Amount: {mat:,.2f}\nInterest Earned: {interest:,.2f}"
                )

            # PPF
            if dtype == "PPF":
                yrs = max(1, round(tenure_years))
                mat, interest, invested = _calc_ppf(amount, rate, yrs)
                return (
                    f"Product: Public Provident Fund (PPF)\nAnnual Deposit: {amount:,.2f}\n"
                    f"Rate: {rate}% p.a. | Tenure: {yrs} years (annually compounded)\n"
                    f"Total Invested: {invested:,.2f}\n"
                    f"Maturity Corpus: {mat:,.2f}\nWealth Gained: {interest:,.2f}\n"
                    f"Tax Status: EEE — Exempt under Section 80C (India)\n"
                    f"Note: Minimum lock-in 15 years; partial withdrawal from year 7."
                )

            # NSC
            if dtype == "NSC":
                yrs = max(1, round(tenure_years))
                mat, interest = _calc_nsc(amount, rate, yrs)
                return (
                    f"Product: National Savings Certificate (NSC)\nPrincipal: {amount:,.2f}\n"
                    f"Rate: {rate}% p.a. | Tenure: {yrs} years (annually compounded, paid at maturity)\n"
                    f"Maturity Amount: {mat:,.2f}\nInterest Earned: {interest:,.2f}\n"
                    f"Tax: 80C deduction on principal (India). Interest taxable."
                )

            # KVP
            if dtype == "KVP":
                mat, interest, months_double = _calc_kvp(amount, rate)
                return (
                    f"Product: Kisan Vikas Patra (KVP)\nPrincipal: {amount:,.2f}\n"
                    f"Rate: {rate}% p.a. (annually compounded)\n"
                    f"Maturity Amount: {mat:,.2f} (doubles investment)\n"
                    f"Interest Earned: {interest:,.2f}\n"
                    f"Approximate Time to Double: {months_double} months ({months_double/12:.1f} years)\n"
                    f"Note: No tax deduction; interest fully taxable."
                )

            # SCSS
            if dtype == "SCSS":
                yrs = max(1, round(tenure_years))
                principal, total_int, qtrly = _calc_scss(amount, rate, yrs)
                return (
                    f"Product: Senior Citizens Savings Scheme (SCSS)\nPrincipal: {amount:,.2f}\n"
                    f"Rate: {rate}% p.a. | Tenure: {yrs} years\n"
                    f"Interest Payout: Quarterly (NOT compounded)\n"
                    f"Quarterly Payout: {qtrly:,.2f}\nTotal Interest Paid Out: {total_int:,.2f}\n"
                    f"Principal Returned at Maturity: {principal:,.2f}\n"
                    f"Tax: 80C deduction on principal (India). TDS on interest > ₹50,000/year.\n"
                    f"Eligibility: Age ≥ 60; max deposit ₹30 lakh."
                )

            # SSY
            if dtype == "SSY":
                d_yrs = min(15, max(1, round(tenure_years)))
                mat, interest, invested = _calc_ssy(amount, rate, d_yrs, 21)
                return (
                    f"Product: Sukanya Samriddhi Yojana (SSY)\nAnnual Deposit: {amount:,.2f}\n"
                    f"Rate: {rate}% p.a. | Deposit Period: {d_yrs} years | Maturity: 21 years from opening\n"
                    f"Total Invested: {invested:,.2f}\n"
                    f"Maturity Corpus (at 21 years): {mat:,.2f}\nWealth Gained: {interest:,.2f}\n"
                    f"Tax Status: EEE — Fully exempt under 80C (India)\n"
                    f"Eligibility: Girl child < 10 years old. Min ₹250/year, Max ₹1.5L/year."
                )

            # SGB
            if dtype == "SGB":
                yrs = max(1, round(tenure_years)) if tenure_months else 8
                mat, total_coupon, semi_coupon = _calc_sgb(amount, rate, yrs)
                return (
                    f"Product: Sovereign Gold Bond (SGB)\nPrincipal (Face Value): {amount:,.2f}\n"
                    f"Fixed Coupon: {rate}% p.a. (paid semi-annually) | Tenure: {yrs} years\n"
                    f"Semi-Annual Coupon: {semi_coupon:,.2f}\n"
                    f"Total Coupon Income: {total_coupon:,.2f}\n"
                    f"Capital Value at Maturity: {mat:,.2f} (fixed coupon component only)\n"
                    f"IMPORTANT: Actual maturity value also includes gold price appreciation / depreciation,\n"
                    f"which cannot be projected. Capital gains on redemption at maturity are tax-exempt (India)."
                )

            # NPS
            if dtype == "NPS":
                yrs = max(1, round(tenure_years))
                corpus, gain, invested, lump, annuity = _calc_nps(amount, rate, yrs)
                return (
                    f"Product: National Pension System (NPS) — Projected\nMonthly Contribution: {amount:,.2f}\n"
                    f"Expected Return: {rate}% p.a. | Tenure: {yrs} years\n"
                    f"Total Invested: {invested:,.2f}\n"
                    f"Projected Corpus at 60: {corpus:,.2f} | Projected Gain: {gain:,.2f}\n"
                    f"  → 60% Lump Sum (tax-free): {lump:,.2f}\n"
                    f"  → 40% Annuity Corpus (mandatory): {annuity:,.2f}\n"
                    f"DISCLAIMER: NPS returns are market-linked (equity + bonds + govt securities).\n"
                    f"Projection uses {rate}% assumed CAGR — actual returns will vary.\n"
                    f"Tax: 80CCD(1B) additional ₹50,000 deduction over 80C limit."
                )

            # MF (Lump Sum or SIP)
            if dtype == "MF":
                if is_sip:
                    mat, gain, invested = _calc_mf_sip(amount, rate, tenure_months)
                    return (
                        f"Product: Mutual Fund SIP (Projected)\nMonthly SIP: {amount:,.2f}\n"
                        f"Expected CAGR: {rate}% | Tenure: {tenure_months} months\n"
                        f"Total Invested: {invested:,.2f}\n"
                        f"Projected Corpus: {mat:,.2f} | Projected Gains: {gain:,.2f}\n"
                        f"DISCLAIMER: MF returns are market-linked. Projection uses {rate}% assumed CAGR.\n"
                        f"Actual returns may be higher or lower. Not a guaranteed return product."
                    )
                else:
                    mat, interest = _calc_compound(amount, rate, tenure_months, n)
                    return (
                        f"Product: Mutual Fund Lump Sum (Projected)\nInvestment: {amount:,.2f}\n"
                        f"Expected CAGR: {rate}% | Tenure: {tenure_months} months\n"
                        f"Projected Value: {mat:,.2f} | Projected Gains: {interest:,.2f}\n"
                        f"DISCLAIMER: MF returns are market-linked. Not a guaranteed return product."
                    )

            # BOND (coupon)
            if dtype == "BOND":
                yrs = tenure_years
                mat, total_coupon, coupon_str = _calc_bond(amount, rate, yrs, pf)
                return (
                    f"Product: Bond\nFace Value: {amount:,.2f}\n"
                    f"Coupon Rate: {rate}% p.a. | Tenure: {yrs:.1f} years | Payment: {pf.replace('_','-')}\n"
                    f"Coupon: {coupon_str}\nTotal Coupon Income: {total_coupon:,.2f}\n"
                    f"Total Return (coupons + principal): {mat:,.2f}\n"
                    f"Note: Assumes bond held to maturity at par (no capital gain/loss)."
                )

            # T-BILL
            if dtype == "T_BILL":
                weeks_map = {1: 4, 2: 8, 3: 13, 4: 17, 5: 26, 6: 52}
                weeks = int(tenure_months / 12 * 52)
                face, gain, purchase = _calc_tbill(amount, rate, weeks)
                return (
                    f"Product: U.S. Treasury Bill\nFace Value: {face:,.2f}\n"
                    f"Discount Rate: {rate}% | Term: {weeks} weeks (~{tenure_months} months)\n"
                    f"Purchase Price: {purchase:,.2f}\nDiscount Gain: {gain:,.2f}\n"
                    f"Effective Yield: {(gain / purchase * 52 / weeks * 100):.4f}% annualized\n"
                    f"Note: T-Bills are discount instruments — no coupon; gain = face - purchase price."
                )

            # I-BOND
            if dtype == "I_BOND":
                infl = inflation_rate or 3.0
                yrs = max(1, round(tenure_years))
                mat, interest, composite = _calc_ibond(amount, rate, infl, yrs)
                return (
                    f"Product: U.S. I Bond (Inflation-Protected)\nPrincipal: {amount:,.2f}\n"
                    f"Fixed Rate: {rate}% | Inflation Rate (6-month): {infl}% | Composite: {composite}% p.a.\n"
                    f"Tenure: {yrs} years (semi-annually compounded)\n"
                    f"Projected Value: {mat:,.2f} | Interest Earned: {interest:,.2f}\n"
                    f"Note: I-Bond composite rate adjusts every 6 months based on CPI-U.\n"
                    f"Must hold ≥ 12 months; 3-month interest penalty if redeemed < 5 years."
                )

            # ISA (UK)
            if dtype == "ISA":
                if is_sip:
                    mat, gain, invested = _calc_mf_sip(amount, rate, tenure_months)
                    return (
                        f"Product: Stocks & Shares ISA (Projected)\nMonthly Contribution: {amount:,.2f}\n"
                        f"Expected Return: {rate}% | Tenure: {tenure_months} months\n"
                        f"Total Invested: {invested:,.2f}\nProjected Value: {mat:,.2f} | Gain: {gain:,.2f}\n"
                        f"Annual ISA Allowance: £20,000 (2024/25). All returns tax-free (UK)."
                    )
                mat, interest = _calc_compound(amount, rate, tenure_months, n)
                return (
                    f"Product: Cash ISA\nPrincipal: {amount:,.2f}\n"
                    f"Rate: {rate}% | Tenure: {tenure_months} months | Compounding: {compounding_freq.capitalize()}\n"
                    f"Maturity: {mat:,.2f} | Interest (tax-free): {interest:,.2f}\n"
                    f"Annual ISA Allowance: £20,000 (2024/25). All interest tax-free (UK)."
                )

            # PREMIUM_BOND
            if dtype == "PREMIUM_BOND":
                mat, expected_gain = _calc_premium_bond(amount, rate)
                return (
                    f"Product: Premium Bond (NS&I, UK)\nHolding: {amount:,.2f}\n"
                    f"Prize Fund Rate: {rate}% (used as expected return proxy)\n"
                    f"Expected Prize Winnings over 1 year: {expected_gain:,.2f}\n"
                    f"Note: Premium Bonds do NOT pay guaranteed interest. Returns are via monthly prize draws.\n"
                    f"All prizes are tax-free. Capital is 100% government-backed. Max holding: £50,000."
                )

            # GIC (Canada)
            if dtype == "GIC":
                if senior_rate is not None:
                    g_mat, g_int = _calc_compound(amount, rate, tenure_months, n)
                    s_mat, s_int = _calc_compound(amount, senior_rate, tenure_months, n)
                    return self._dual_rate_output("Guaranteed Investment Certificate (GIC)",
                                                  amount, tenure_months, compounding_freq,
                                                  rate, senior_rate, g_mat, g_int, s_mat, s_int,
                                                  f"Principal: {amount:,.2f}")
                mat, interest = _calc_compound(amount, rate, tenure_months, n)
                return (
                    f"Product: Guaranteed Investment Certificate (GIC)\nPrincipal: {amount:,.2f}\n"
                    f"Rate: {rate}% | Tenure: {tenure_months} months | Compounding: {compounding_freq.capitalize()}\n"
                    f"Maturity Amount: {mat:,.2f}\nInterest Earned: {interest:,.2f}\n"
                    f"CDIC insured up to C$100,000 per depositor per insured category."
                )

            # MURABAHA (Islamic)
            if dtype == "MURABAHA":
                mat, profit = _calc_compound(amount, rate, tenure_months, 1)  # annual for simplicity
                return (
                    f"Product: Murabaha / Islamic Term Deposit\nPrincipal: {amount:,.2f}\n"
                    f"Profit Rate: {rate}% p.a. | Tenure: {tenure_months} months\n"
                    f"Maturity Amount: {mat:,.2f}\nProfit Earned: {profit:,.2f}\n"
                    f"Note: Sharia-compliant. Returns are pre-agreed profit, not 'interest'."
                )

            # Fallback — treat unknown type as FD
            mat, interest = _calc_compound(amount, rate, tenure_months, n)
            return (
                f"Product: {deposit_type.upper()} (treated as compound-interest deposit)\n"
                f"Principal: {amount:,.2f} | Rate: {rate}% | Tenure: {tenure_months} months\n"
                f"Maturity Amount: {mat:,.2f}\nInterest Earned: {interest:,.2f}"
            )

        except Exception as e:
            return f"Calculation Error ({deposit_type}): {str(e)}"

    @staticmethod
    def _dual_rate_output(product_label, amount, tenure_months, compounding_freq,
                          rate, senior_rate, g_mat, g_int, s_mat, s_int, desc):
        return (
            f"Product: {product_label}\n"
            f"{desc}\nTenure: {tenure_months} months | Compounding: {compounding_freq.capitalize()}\n"
            f"--- General Customer ---\n"
            f"Rate: {rate}% | Maturity: {g_mat:,.2f} | Interest: {g_int:,.2f}\n"
            f"--- Senior Citizen ---\n"
            f"Rate: {senior_rate}% | Maturity: {s_mat:,.2f} | Interest: {s_int:,.2f}"
        )


# Module-level instance exported for agents
calculate_deposit = UniversalDepositCalculatorTool()