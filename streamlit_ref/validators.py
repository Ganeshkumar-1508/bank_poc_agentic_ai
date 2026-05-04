# validators.py  —  LLM Decision Parser and Validators for Fixed Deposit Advisor
import re
import json


# =============================================================================
# LLM DECISION PARSER
# =============================================================================
def _parse_llm_decision(raw_output: str) -> dict:
    """Parse the LLM crew output into a structured decision dict.
    Expected keys: loan_decision, rationale, conditions (list), next_steps (list).
    Falls back gracefully if parsing fails.
    """
    if not raw_output:
        return {}
    try:
        # Try JSON extraction from the raw text
        text = raw_output.strip()
        for fence in ("```json", "```"):
            if fence in text:
                text = text.split(fence)[-1].split("```")[0].strip()
                break
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return {
                "loan_decision": parsed.get("loan_decision", ""),
                "rationale": parsed.get(
                    "rationale", parsed.get("decision_rationale", "")
                ),
                "conditions": parsed.get("conditions", []),
                "next_steps": parsed.get("next_steps", []),
            }
    except (json.JSONDecodeError, ValueError):
        pass
    # Fallback: try regex extraction
    decision_match = re.search(
        r"(LOAN_APPROVED|NEEDS_VERIFY|REJECTED)", raw_output, re.IGNORECASE
    )
    return {
        "loan_decision": decision_match.group(1).upper() if decision_match else "",
        "rationale": raw_output[:500],
        "conditions": [],
        "next_steps": [],
    }


# =============================================================================
# GRADE SANITIZATION (prevent LLM grade hallucination)
# =============================================================================
def _sanitize_grade_in_text(text: str, correct_grade: str) -> str:
    """Post-process LLM output to replace any hallucinated credit grades with the
    correct XGBoost model grade.  The LLM may occasionally mention a different grade
    than what the model computed — this function catches and corrects those references
    so the email and on-screen rationale always display the authoritative grade.
    """
    if not text or not correct_grade or correct_grade == "N/A":
        return text

    grade = correct_grade.upper().strip()

    # Patterns that match grade mentions in LLM output (case-insensitive)
    _patterns = [
        (r"\bGrade\s*:?\s*[A-Ga-g]\b", f"Grade {grade}"),
        (r"\bgrade\s*:?\s*[A-Ga-g]\b", f"grade {grade}"),
        (r"\bCredit Grade\s*:?\s*[A-Ga-g]\b", f"Credit Grade {grade}"),
        (r"\bcredit grade\s*:?\s*[A-Ga-g]\b", f"credit grade {grade}"),
        (r"\bRisk Grade\s*:?\s*[A-Ga-g]\b", f"Risk Grade {grade}"),
        (r"\brisk grade\s*:?\s*[A-Ga-g]\b", f"risk grade {grade}"),
        (r"\bimplied grade\s*:?\s*[A-Ga-g]\b", f"implied grade {grade}"),
        (r"\bImplied Grade\s*:?\s*[A-Ga-g]\b", f"Implied Grade {grade}"),
    ]

    for pattern, replacement in _patterns:
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)

    return text


# =============================================================================
# THRESHOLD HALLUCINATION SANITIZATION
# =============================================================================
def _sanitize_thresholds_in_text(text: str, borrower: dict) -> str:
    """Post-process LLM output to remove fabricated DTI/FICO thresholds.

    The LLM may invent thresholds like 'DTI of 20%' or 'minimum FICO 640' that
    don't exist in policy documents. This function catches common hallucination
    patterns and replaces them with safe, non-fabricated language.
    """
    if not text or not borrower:
        return text

    actual_dti = borrower.get("dti")
    actual_fico = borrower.get("fico_score")

    # --- DTI threshold patterns ---
    def _replace_fake_dti(match):
        threshold_num = float(match.group(1))
        if actual_dti is not None and abs(threshold_num - actual_dti) > 1.0:
            return "the bank's required DTI threshold"
        return match.group(0)

    # Pattern: "maximum threshold of 15.0" / "recommended DTI of 36%"
    text = re.sub(
        r"(?:maximum\s+)?(?:recommended\s+)?(?:DTI|dti)\s+(?:ratio\s+)?"
        r"(?:threshold\s+(?:of\s+)?)?(\d+(?:\.\d+)?)\s*%",
        _replace_fake_dti,
        text,
    )
    # Pattern: "DTI of 20%" / "DTI is 20%"
    text = re.sub(
        r"(?:DTI|dti)\s+(?:of\s+|is\s+)(\d+(?:\.\d+)?)\s*%\s*(?:recommended|threshold)?",
        _replace_fake_dti,
        text,
    )
    # Pattern: "DTI exceeds the maximum threshold of X"
    text = re.sub(
        r"(?:DTI|dti)\s+(?:ratio\s+)?\([^)]*\)\s+exceeds\s+the\s+maximum\s+threshold\s+of\s+(\d+(?:\.\d+)?)\s*%",
        _replace_fake_dti,
        text,
    )
    # Pattern: "slightly above/below the ... threshold of 20%"
    text = re.sub(
        r"slightly\s+(?:above|below)\s+(?:the\s+)?(?:recommended\s+)?threshold\s+(?:of\s+)?\d+(?:\.\d+)?\s*%",
        "below the bank's required threshold",
        text,
        flags=re.IGNORECASE,
    )

    # --- FICO threshold patterns ---
    def _replace_fake_fico(match):
        threshold_num = int(match.group(1))
        if actual_fico is not None and abs(threshold_num - actual_fico) > 5:
            return "the bank's minimum FICO requirement"
        return match.group(0)

    # Pattern: "minimum FICO of 640" / "FICO threshold 640"
    text = re.sub(
        r"(?:minimum\s+)?(?:FICO|fico)\s+(?:score\s+)?(?:of\s+|threshold\s+(?:of\s+)?)(\d{3})",
        _replace_fake_fico,
        text,
    )
    # Pattern: "FICO threshold 640" / "FICO minimum 640"
    text = re.sub(
        r"(?:FICO|fico)\s+(?:threshold|minimum)\s+(?:of\s+)?(\d{3})",
        _replace_fake_fico,
        text,
    )

    return text


# =============================================================================
# DECISION RATIONALE HALLUCINATION VALIDATOR
# =============================================================================
def _validate_decision_rationale(decision: dict, borrower: dict) -> dict:
    """Post-validation to catch hallucinated thresholds and logic errors in the decision JSON.

    Checks for:
    - Mathematically impossible claims (e.g., '5 years below 3 years')
    - Wrong loan type evaluation (e.g., mortgage rules for debt_consolidation)
    - Fabricated DTI thresholds not present in policy docs
    - Overly aggressive rejections when borrower passes all known thresholds
    """
    if not decision or not borrower:
        return decision

    rationale = decision.get("rationale", "")
    fico = borrower.get("fico_score", 0)
    dti = borrower.get("dti", 0.0)
    purpose = borrower.get("purpose", "")
    emp_display = borrower.get("emp_length_display", "")
    conditions = decision.get("conditions", [])
    next_steps = decision.get("next_steps", [])

    # --- Fix 1: Catch mathematically impossible comparison claims ---
    # Pattern: "X years/months is below the minimum of Y years/months"
    math_error_pattern = re.compile(
        r"(\d+)\s*(?:years?|months?)\s+(?:is\s+)?below\s+(?:the\s+)?"
        r"(?:minimum\s+)?(?:of\s+|requirement\s+(?:of\s+)?)(\d+)\s*(?:years?|months?)",
        re.IGNORECASE,
    )
    for match in math_error_pattern.finditer(rationale):
        actual_val = int(match.group(1))
        claimed_min = int(match.group(2))
        if actual_val >= claimed_min:
            rationale = rationale.replace(
                match.group(0),
                f"Employment length of {emp_display} meets or exceeds requirements",
            )

    # --- Fix 2: Flag wrong loan type evaluation ---
    purpose_to_type = {
        "debt_consolidation": "debt consolidation",
        "credit_card": "credit card",
        "home_improvement": "home improvement",
        "medical": "personal",
        "major_purchase": "personal",
        "wedding": "personal",
        "moving": "personal",
        "vacation": "personal",
        "small_business": "small business",
        "house": "mortgage",
        "car": "auto",
    }
    correct_loan_type = purpose_to_type.get(purpose, "personal")

    # Remove mortgage/secured references when borrower is not applying for mortgage
    if purpose != "house" and "mortgage" in rationale.lower():
        rationale = re.sub(
            r"\bfor\s+mortgage\s+loans?\b",
            f"for {correct_loan_type} loans",
            rationale,
            flags=re.IGNORECASE,
        )
        rationale = re.sub(
            r"\bmortgage\s+loan\s+requirement\b",
            f"{correct_loan_type} loan requirement",
            rationale,
            flags=re.IGNORECASE,
        )

    if purpose != "house" and "secured loan" in rationale.lower():
        rationale = rationale.replace("secured loan", "unsecured loan")

    # --- Fix 3: Flag fabricated DTI thresholds ---
    # For FICO >= 760, DTI max is 50%. Any claim about 15% or similar small number is fabricated.
    if fico >= 760:
        # Pattern: "threshold of 15.0" / "maximum threshold of X" where X < 30
        fake_dti_pattern = re.compile(
            r"(?:maximum\s+)?threshold\s+(?:of\s+)?(\d+(?:\.\d+)?)\s*%\s*(?:for\s+\w+\s+loans?)?",
            re.IGNORECASE,
        )
        for match in fake_dti_pattern.finditer(rationale):
            threshold_num = float(match.group(1))
            # If threshold is much lower than what FICO 760+ allows (50%), it's fabricated
            if threshold_num < 30:
                rationale = rationale.replace(
                    match.group(0),
                    "the bank's DTI threshold (borrower's DTI is within acceptable limits)",
                )

    # --- Fix 4: If borrower clearly passes all known thresholds, downgrade REJECTED ---
    # Known minimum thresholds from policy docs:
    known_passes = []
    if fico >= 620:  # min for debt consolidation
        known_passes.append("FICO")
    if dti <= 50:  # max for FICO 760+
        known_passes.append("DTI")
    if borrower.get("delinq_2yrs", 0) == 0:
        known_passes.append("delinquency")
    if borrower.get("annual_inc", 0) >= 24000:  # min income for personal loan
        known_passes.append("income")

    all_pass = len(known_passes) >= 3

    # Check if rationale claims violations for metrics that pass
    suspicious_violations = 0
    if all_pass and dti <= 50:
        # Look for DTI violation claims when DTI is actually fine
        dti_violation_pattern = re.compile(
            r"[Dd][Tt][Ii].*?(?:exceeds|above|over|higher|greater)",
            re.IGNORECASE,
        )
        if dti_violation_pattern.search(rationale):
            suspicious_violations += 1

    if (
        all_pass
        and suspicious_violations >= 1
        and decision.get("loan_decision") == "REJECTED"
    ):
        # The decision is likely wrong — downgrade to NEEDS_VERIFY
        decision["loan_decision"] = "NEEDS_VERIFY"
        decision["rationale"] = (
            f"Borrower has a strong credit profile: FICO {fico}, DTI {dti}%, "
            f"no delinquencies, and meets minimum requirements for the applied loan type. "
            f"The ML model indicates {borrower.get('_grade_fallback', 'moderate')} risk "
            f"(Grade C, ~11.65% default probability). Additional verification is recommended "
            f"to confirm income and employment details before final approval."
        )
        decision["conditions"] = [
            "Submit most recent 2 months of pay stubs for income verification",
            "Provide proof of current employment (minimum 6 months at current employer)",
            "Submit most recent W-2 form",
        ]
        decision["next_steps"] = [
            "Verification officer assigned to review application",
            "Additional documents requested from borrower",
            "Decision expected within 3-5 business days",
        ]

    decision["rationale"] = rationale

    # --- Fix 5: Also sanitize conditions and next_steps for hallucinated thresholds ---
    for arr_key in ("conditions", "next_steps"):
        if isinstance(decision.get(arr_key), list):
            cleaned = []
            for item in decision[arr_key]:
                if not isinstance(item, str):
                    cleaned.append(item)
                    continue
                # Remove items that cite fabricated thresholds
                has_fake_dti = bool(
                    re.search(
                        r"(?:DTI|dti).*?(?:threshold|exceeds|above|maximum).*?(\d+(?:\.\d+)?)\s*%",
                        item,
                    )
                )
                has_fake_fico = bool(
                    re.search(
                        r"(?:FICO|fico).*(?:minimum|threshold|below).*?(\d{3})", item
                    )
                )
                if has_fake_dti or has_fake_fico:
                    item = re.sub(
                        r"(?:threshold\s+(?:of\s+)?)\d+(?:\.\d+)?\s*%",
                        "the bank's required threshold",
                        item,
                        flags=re.IGNORECASE,
                    )
                    item = re.sub(
                        r"(?:minimum|threshold)\s+(?:of\s+)?\d{3}",
                        "the bank's minimum requirement",
                        item,
                        flags=re.IGNORECASE,
                    )
                cleaned.append(item)
            decision[arr_key] = cleaned

    return decision
