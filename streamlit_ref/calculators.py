# calculators.py — Financial Calculators for Fixed Deposit Advisor

# =============================================================================
# EMI AND LOAN CALCULATORS (Ported from CreditWise)
# =============================================================================


def calculate_emi(
    loan_amount: float,
    interest_rate: float,
    tenure_months: int,
    method: str = "Reducing Balance",
    processing_fee: float = 0,
) -> dict:
    """
    Calculate EMI using three different methods.

    Args:
        loan_amount: Principal loan amount in INR
        interest_rate: Annual interest rate (%)
        tenure_months: Loan tenure in months
        method: Calculation method - "Reducing Balance", "Flat Rate", or "Compound Interest"
        processing_fee: Processing fee in INR

    Returns:
        Dictionary with EMI, total interest, total cost, and amortization schedule
    """
    if loan_amount <= 0 or interest_rate <= 0 or tenure_months <= 0:
        return {"error": "Invalid input values. All values must be positive."}

    if method == "Reducing Balance":
        emi, total_interest = _calculate_reducing_balance_emi(
            loan_amount, interest_rate, tenure_months
        )
    elif method == "Flat Rate":
        emi, total_interest = _calculate_flat_rate_emi(
            loan_amount, interest_rate, tenure_months
        )
    elif method == "Compound Interest":
        emi, total_interest = _calculate_compound_interest_emi(
            loan_amount, interest_rate, tenure_months
        )
    else:
        return {"error": f"Unknown calculation method: {method}"}

    total_cost = loan_amount + total_interest + processing_fee

    # Generate amortization schedule
    amortization_schedule = generate_amortization_schedule(
        loan_amount, interest_rate, tenure_months, method, emi
    )

    return {
        "loan_amount": loan_amount,
        "interest_rate": interest_rate,
        "tenure_months": tenure_months,
        "method": method,
        "monthly_emi": round(emi, 2),
        "total_interest": round(total_interest, 2),
        "total_cost": round(total_cost, 2),
        "processing_fee": processing_fee,
        "amortization_schedule": amortization_schedule,
    }


def _calculate_reducing_balance_emi(
    principal: float, annual_rate: float, months: int
) -> tuple:
    """
    Calculate EMI using reducing balance method (most common in India).

    Formula: EMI = P * r * (1 + r)^n / ((1 + r)^n - 1)
    where r = monthly interest rate, n = tenure in months
    """
    monthly_rate = annual_rate / 12 / 100
    emi = (
        principal
        * monthly_rate
        * (1 + monthly_rate) ** months
        / ((1 + monthly_rate) ** months - 1)
    )
    total_payment = emi * months
    total_interest = total_payment - principal
    return emi, total_interest


def _calculate_flat_rate_emi(
    principal: float, annual_rate: float, months: int
) -> tuple:
    """
    Calculate EMI using flat rate method.

    Formula: Total Interest = P * r * t
    EMI = (Principal + Total Interest) / n
    """
    annual_rate_decimal = annual_rate / 100
    total_interest = principal * annual_rate_decimal * (months / 12)
    total_payment = principal + total_interest
    emi = total_payment / months
    return emi, total_interest


def _calculate_compound_interest_emi(
    principal: float, annual_rate: float, months: int
) -> tuple:
    """
    Calculate EMI using compound interest method.

    Formula: A = P * (1 + r/n)^(n*t)
    Where interest is compounded monthly
    """
    monthly_rate = annual_rate / 12 / 100
    amount = principal * (1 + monthly_rate) ** months
    total_interest = amount - principal
    emi = amount / months
    return emi, total_interest


def generate_amortization_schedule(
    loan_amount: float,
    interest_rate: float,
    tenure_months: int,
    method: str,
    monthly_emi: float,
) -> list:
    """
    Generate year-by-year amortization schedule.

    Returns:
        List of dictionaries with year, opening_balance, principal_paid, interest_paid, total_paid, closing_balance
    """
    schedule = []
    remaining_balance = loan_amount
    monthly_rate = interest_rate / 12 / 100

    year_data = {}
    current_year = 1

    for month in range(1, tenure_months + 1):
        if method == "Reducing Balance":
            interest_payment = remaining_balance * monthly_rate
            principal_payment = monthly_emi - interest_payment
        elif method == "Flat Rate":
            # For flat rate, interest is pre-calculated and evenly distributed
            interest_payment = monthly_emi * 0.3  # Approximate split
            principal_payment = monthly_emi - interest_payment
        else:
            interest_payment = remaining_balance * monthly_rate
            principal_payment = monthly_emi - interest_payment

        # Ensure principal payment doesn't exceed remaining balance
        if principal_payment > remaining_balance:
            principal_payment = remaining_balance
            monthly_emi = principal_payment + interest_payment

        remaining_balance -= principal_payment

        # Track yearly data
        if current_year not in year_data:
            year_data[current_year] = {
                "opening_balance": (
                    loan_amount
                    if month == 1
                    else year_data[current_year - 1]["closing_balance"]
                ),
                "principal_paid": 0,
                "interest_paid": 0,
                "total_paid": 0,
            }

        year_data[current_year]["principal_paid"] += principal_payment
        year_data[current_year]["interest_paid"] += interest_payment
        year_data[current_year]["total_paid"] += monthly_emi

        # Move to next year
        if month % 12 == 0:
            year_data[current_year]["closing_balance"] = max(0, remaining_balance)
            schedule.append(
                {
                    "Year": current_year,
                    "Opening Balance": round(
                        year_data[current_year]["opening_balance"], 2
                    ),
                    "Principal Paid": round(
                        year_data[current_year]["principal_paid"], 2
                    ),
                    "Interest Paid": round(year_data[current_year]["interest_paid"], 2),
                    "Total Paid": round(year_data[current_year]["total_paid"], 2),
                    "Closing Balance": round(
                        year_data[current_year]["closing_balance"], 2
                    ),
                }
            )
            current_year += 1

    # Add final year if tenure is not a multiple of 12
    if tenure_months % 12 != 0 and remaining_balance > 0:
        year_data[current_year] = {
            "opening_balance": (
                year_data[current_year - 1]["closing_balance"]
                if current_year > 1
                else loan_amount
            ),
            "principal_paid": 0,
            "interest_paid": 0,
            "total_paid": 0,
            "closing_balance": 0,
        }
        # Recalculate for remaining months
        for month in range((current_year - 1) * 12 + 1, tenure_months + 1):
            interest_payment = remaining_balance * monthly_rate
            principal_payment = monthly_emi - interest_payment
            if principal_payment > remaining_balance:
                principal_payment = remaining_balance
            remaining_balance -= principal_payment
            year_data[current_year]["principal_paid"] += principal_payment
            year_data[current_year]["interest_paid"] += interest_payment
            year_data[current_year]["total_paid"] += monthly_emi

        schedule.append(
            {
                "Year": current_year,
                "Opening Balance": round(year_data[current_year]["opening_balance"], 2),
                "Principal Paid": round(year_data[current_year]["principal_paid"], 2),
                "Interest Paid": round(year_data[current_year]["interest_paid"], 2),
                "Total Paid": round(year_data[current_year]["total_paid"], 2),
                "Closing Balance": round(year_data[current_year]["closing_balance"], 2),
            }
        )

    return schedule


# =============================================================================
# FINANCIAL CALCULATORS (Existing FD Calculators)
# =============================================================================
def calc_compound(
    principal: float,
    annual_rate: float,
    tenure_months: int,
    compounding: str = "quarterly",
) -> dict:
    n_map = {"monthly": 12, "quarterly": 4, "half_yearly": 2, "yearly": 1}
    n = n_map.get(compounding, 4)
    t = tenure_months / 12.0
    maturity = principal * (1 + annual_rate / 100 / n) ** (n * t)
    return {
        "maturity": round(maturity, 2),
        "interest": round(maturity - principal, 2),
    }


def calc_premature_withdrawal(
    principal: float,
    annual_rate: float,
    tenure_months: int,
    elapsed_months: int,
    penalty_pct: float,
    compounding: str = "quarterly",
) -> dict:
    elapsed_months = min(elapsed_months, tenure_months)
    n_map = {"monthly": 12, "quarterly": 4, "half_yearly": 2, "yearly": 1}
    n = n_map.get(compounding, 4)
    t = elapsed_months / 12.0
    maturity_val = principal * (1 + annual_rate / 100 / n) ** (n * t)
    interest_earned = maturity_val - principal
    penalty = interest_earned * penalty_pct / 100
    payout = maturity_val - penalty
    t_full = tenure_months / 12.0
    full_mat = principal * (1 + annual_rate / 100 / n) ** (n * t_full)
    return {
        "principal": principal,
        "interest_earned": round(interest_earned, 2),
        "penalty": round(penalty, 2),
        "payout": round(payout, 2),
        "full_maturity": round(full_mat, 2),
        "foregone": round(full_mat - payout, 2),
        "effective_annual_rate": (
            round((payout - principal) / principal * 100 / t, 2) if t > 0 else 0
        ),
    }


def calc_fd_ladder(total_amount: float, tranches: list) -> list:
    results = []
    for tr in tranches:
        amt = total_amount * tr["fraction"]
        res = calc_compound(
            amt, tr["rate"], tr["tenure_months"], tr.get("compounding", "quarterly")
        )
        results.append(
            {
                "bank": tr["bank"],
                "fraction_pct": round(tr["fraction"] * 100, 1),
                "amount": round(amt, 2),
                "tenure_months": tr["tenure_months"],
                "rate": tr["rate"],
                "maturity": res["maturity"],
                "interest": res["interest"],
            }
        )
    return results


def inflation_adjusted_return(
    nominal_balance: float, principal: float, inflation_rate: float, years: float
) -> dict:
    real_balance = nominal_balance / ((1 + inflation_rate / 100) ** years)
    real_return_pct = (real_balance - principal) / principal * 100
    return {
        "real_balance": round(real_balance, 2),
        "real_return_pct": round(real_return_pct, 2),
    }
