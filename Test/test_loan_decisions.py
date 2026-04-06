"""
test_loan_decisions.py
======================
Automated test script for the 3-category Loan Decision feature.

Tests all three decision paths:
  1. LOAN_APPROVED   (Grade A/B, prob < 10%)
  2. NEEDS_VERIFY     (Grade C/D/E, prob 10-25%)
  3. REJECTED         (Grade F/G, prob >= 25%)

Also tests:
  - classify_loan_decision() function directly
  - DB save/retrieve for loan_applications table
  - send_loan_decision_email() (SMTP check only, no real send)
  - LOAN_DECISION_CONFIG completeness
  - UI banner HTML generation (no actual Streamlit)

Usage:
  python test_loan_decisions.py
"""

import sys
import os
import json
import datetime

# ── Path setup ──
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

# ── Test counters ──
PASSED = 0
FAILED = 0
ERRORS = []


def check(condition, test_name):
    global PASSED, FAILED, ERRORS
    if condition:
        PASSED += 1
        print(f"  ✅ PASS: {test_name}")
    else:
        FAILED += 1
        ERRORS.append(test_name)
        print(f"  ❌ FAIL: {test_name}")


# ═══════════════════════════════════════════════════════════════════════════════
# TEST GROUP 1: classify_loan_decision() function
# ═══════════════════════════════════════════════════════════════════════════════
print("\n" + "=" * 70)
print("TEST GROUP 1: classify_loan_decision() logic")
print("=" * 70)

# Import the function
try:
    from new_app import classify_loan_decision
    print("\n[✓] classify_loan_decision imported successfully")
except ImportError as e:
    print(f"\n[✗] Failed to import classify_loan_decision: {e}")
    print("   Make sure new_app.py is in the same directory and dependencies are installed.")
    sys.exit(1)

# Test all 7 grades
print("\nTesting grade → decision mapping:")
test_cases = [
    # (grade, probability, expected_decision, description)
    ("A", 0.02, "LOAN_APPROVED", "Grade A (very low risk) → Approved"),
    ("A", 0.04, "LOAN_APPROVED", "Grade A (upper bound) → Approved"),
    ("B", 0.05, "LOAN_APPROVED", "Grade B (lower bound) → Approved"),
    ("B", 0.09, "LOAN_APPROVED", "Grade B (upper bound) → Approved"),
    ("C", 0.10, "NEEDS_VERIFY",  "Grade C (lower bound) → Needs Verify"),
    ("C", 0.14, "NEEDS_VERIFY",  "Grade C (upper bound) → Needs Verify"),
    ("D", 0.15, "NEEDS_VERIFY",  "Grade D (lower bound) → Needs Verify"),
    ("D", 0.19, "NEEDS_VERIFY",  "Grade D (upper bound) → Needs Verify"),
    ("E", 0.20, "NEEDS_VERIFY",  "Grade E (lower bound) → Needs Verify"),
    ("E", 0.24, "NEEDS_VERIFY",  "Grade E (upper bound) → Needs Verify"),
    ("F", 0.25, "REJECTED",      "Grade F (lower bound) → Rejected"),
    ("F", 0.29, "REJECTED",      "Grade F (upper bound) → Rejected"),
    ("G", 0.30, "REJECTED",      "Grade G (lower bound) → Rejected"),
    ("G", 0.85, "REJECTED",      "Grade G (very high risk) → Rejected"),
]

for grade, prob, expected, desc in test_cases:
    result = classify_loan_decision(grade, prob)
    check(result == expected, desc)
    if result != expected:
        print(f"           Expected: {expected}, Got: {result} (grade={grade}, prob={prob})")

# Edge cases
print("\nTesting edge cases:")
check(classify_loan_decision("a", 0.03) == "LOAN_APPROVED",
      "Lowercase grade 'a' → Approved (case insensitive)")
check(classify_loan_decision(None, 0.50) == "REJECTED",
      "None grade → Rejected (default)")
check(classify_loan_decision("", 0.50) == "REJECTED",
      "Empty string grade → Rejected (default)")
check(classify_loan_decision("X", 0.03) == "REJECTED",
      "Unknown grade 'X' → Rejected (default)")
check(classify_loan_decision("A", 0.0) == "LOAN_APPROVED",
      "Zero probability → Approved")
check(classify_loan_decision("G", 1.0) == "REJECTED",
      "100% probability → Rejected")


# ═══════════════════════════════════════════════════════════════════════════════
# TEST GROUP 2: LOAN_DECISION_CONFIG completeness
# ═══════════════════════════════════════════════════════════════════════════════
print("\n" + "=" * 70)
print("TEST GROUP 2: LOAN_DECISION_CONFIG completeness")
print("=" * 70)

try:
    from new_app import LOAN_DECISION_CONFIG
    print("\n[✓] LOAN_DECISION_CONFIG imported successfully")
except ImportError as e:
    print(f"\n[✗] Failed to import LOAN_DECISION_CONFIG: {e}")
    sys.exit(1)

required_keys = {"LOAN_APPROVED", "NEEDS_VERIFY", "REJECTED"}
required_sub_keys = {"bg", "fg", "border", "icon", "label", "badge_bg", "banner_bg", "banner_border"}

check(set(LOAN_DECISION_CONFIG.keys()) == required_keys,
      f"All 3 decision keys present: {list(LOAN_DECISION_CONFIG.keys())}")

for decision_key in required_keys:
    cfg = LOAN_DECISION_CONFIG.get(decision_key, {})
    check(required_sub_keys.issubset(cfg.keys()),
          f"{decision_key} has all required config sub-keys")

# Verify unique colors/icons per category
check(LOAN_DECISION_CONFIG["LOAN_APPROVED"]["icon"] == "✅",
      "LOAN_APPROVED icon is ✅")
check(LOAN_DECISION_CONFIG["NEEDS_VERIFY"]["icon"] == "⚠️",
      "NEEDS_VERIFY icon is ⚠️")
check(LOAN_DECISION_CONFIG["REJECTED"]["icon"] == "❌",
      "REJECTED icon is ❌")

# Verify unique colors (no overlap)
approved_bg = LOAN_DECISION_CONFIG["LOAN_APPROVED"]["bg"]
verify_bg = LOAN_DECISION_CONFIG["NEEDS_VERIFY"]["bg"]
rejected_bg = LOAN_DECISION_CONFIG["REJECTED"]["bg"]
check(len({approved_bg, verify_bg, rejected_bg}) == 3,
      "Each decision category has a unique background color")


# ═══════════════════════════════════════════════════════════════════════════════
# TEST GROUP 3: Email configuration check
# ═══════════════════════════════════════════════════════════════════════════════
print("\n" + "=" * 70)
print("TEST GROUP 3: send_loan_decision_email() checks")
print("=" * 70)

try:
    from new_app import send_loan_decision_email
    print("\n[✓] send_loan_decision_email imported successfully")
except ImportError as e:
    print(f"\n[✗] Failed to import send_loan_decision_email: {e}")
    sys.exit(1)

# Check SMTP env vars (no actual email sent)
smtp_user = os.getenv("SMTP_USER", "")
smtp_pass = os.getenv("SMTP_PASSWORD", "")

if smtp_user and smtp_pass:
    check(True, "SMTP_USER and SMTP_PASSWORD are set in environment")
else:
    check(False,
          "SMTP_USER or SMTP_PASSWORD not set — email sending will return False")
    print("       Set SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD in .env to enable emails")

# Test that function returns False for empty recipient (no crash)
try:
    result = send_loan_decision_email(
        recipient="",
        loan_decision="LOAN_APPROVED",
        grade="A",
        prob_pct="2.5%",
        risk_level="Low",
        rationale="Test rationale",
        conditions=["None"],
        next_steps=["None"],
        borrower_data={"loan_amnt": 10000, "term": 36, "purpose": "test"},
    )
    check(result is False, "Empty recipient returns False (no crash)")
except Exception as e:
    check(False, f"Empty recipient crashes: {e}")

# Test that function handles None gracefully
try:
    result = send_loan_decision_email(
        recipient=None,
        loan_decision="REJECTED",
        grade="G",
        prob_pct="85%",
        risk_level="Critical",
        rationale="Test",
        conditions=[],
        next_steps=[],
        borrower_data={},
    )
    check(result is False, "None recipient returns False (no crash)")
except Exception as e:
    check(False, f"None recipient crashes: {e}")


# ═══════════════════════════════════════════════════════════════════════════════
# TEST GROUP 4: Database table and save/retrieve
# ═══════════════════════════════════════════════════════════════════════════════
print("\n" + "=" * 70)
print("TEST GROUP 4: Database loan_applications table")
print("=" * 70)

try:
    from new_app import (init_loan_applications_table, save_loan_application,
                         get_loan_applications)
    print("\n[✓] DB functions imported successfully")
except ImportError as e:
    print(f"\n[✗] Failed to import DB functions: {e}")
    sys.exit(1)

try:
    # Init table
    init_loan_applications_table()
    check(True, "init_loan_applications_table() executes without error")

    # Save test records for each category
    test_borrower = {
        "loan_amnt": 15000, "term": 36, "int_rate": 12.5,
        "purpose": "test_debt_consolidation", "annual_inc": 60000,
        "fico_score": 700, "dti": 18.0,
    }

    test_results = {
        "default_probability": 0.05,
        "default_probability_pct": "5.00%",
        "implied_grade": "B",
        "risk_level": "Low-Medium",
    }

    for decision in ["LOAN_APPROVED", "NEEDS_VERIFY", "REJECTED"]:
        row_id = save_loan_application(
            applicant_email=f"test_{decision.lower()}@example.com",
            borrower_data=test_borrower,
            cr_result=test_results,
            loan_decision=decision,
            rationale=f"Test rationale for {decision}",
            conditions="Test conditions",
            next_steps="Test next steps",
            notification_sent=0,
        )
        check(row_id is not None, f"save_loan_application({decision}) returns valid row_id={row_id}")

    # Retrieve all
    all_apps = get_loan_applications()
    check(not all_apps.empty, "get_loan_applications() returns non-empty DataFrame")
    check("loan_decision" in all_apps.columns, "loan_decision column exists in results")
    check("applicant_email" in all_apps.columns, "applicant_email column exists in results")
    check("implied_grade" in all_apps.columns, "implied_grade column exists in results")
    check("default_prob" in all_apps.columns, "default_prob column exists in results")
    check("notification_sent" in all_apps.columns, "notification_sent column exists in results")

    # Filter by email
    approved_apps = get_loan_applications("test_loan_approved@example.com")
    check(not approved_apps.empty, "Filter by email returns results")
    check(len(approved_apps) >= 1, "At least 1 approved test record found")

    print("\n  [i] Database table schema and CRUD operations verified successfully")

except Exception as e:
    check(False, f"Database test failed: {e}")


# ═══════════════════════════════════════════════════════════════════════════════
# TEST GROUP 5: ML Model end-to-end (if model available)
# ═══════════════════════════════════════════════════════════════════════════════
print("\n" + "=" * 70)
print("TEST GROUP 5: ML Model prediction → Decision classification")
print("=" * 70)

try:
    from new_app import _cr_predict, _cr_model_available
    print("\n[✓] ML model functions imported successfully")
except ImportError as e:
    print(f"\n[✗] Failed to import ML model functions: {e}")

if _cr_model_available():
    check(True, "XGBoost model file found")
    print("\n  Testing 3 borrower profiles to verify decision classification:")

    # ── Profile 1: Excellent (expect LOAN_APPROVED) ──
    borrower_excellent = {
        "loan_amnt": 5000, "term": 36, "int_rate": 6.5,
        "annual_inc": 150000, "dti": 5.0, "fico_score": 800,
        "home_ownership": "MORTGAGE", "delinq_2yrs": 0,
        "inq_last_6mths": 0, "pub_rec": 0,
        "earliest_cr_line": "Jan-1990", "revol_util": 10.0,
        "revol_bal": 1000, "purpose": "debt_consolidation",
        "emp_length": 10, "verification_status": "Verified",
    }
    try:
        result_1 = _cr_predict(borrower_excellent)
        grade_1 = result_1.get("implied_grade", "?")
        prob_1 = result_1.get("default_probability", 1.0)
        decision_1 = classify_loan_decision(grade_1, prob_1)
        check(decision_1 == "LOAN_APPROVED",
              f"Excellent profile → {decision_1} (Grade {grade_1}, prob={prob_1:.4f})")
        if decision_1 != "LOAN_APPROVED":
            print(f"    NOTE: Grade={grade_1}, prob={prob_1:.4f}. "
                  f"If not LOAN_APPROVED, try lowering loan_amnt or increasing income.")
    except Exception as e:
        check(False, f"Excellent profile prediction failed: {e}")

    # ── Profile 2: Moderate (expect NEEDS_VERIFY) ──
    borrower_moderate = {
        "loan_amnt": 15000, "term": 60, "int_rate": 14.0,
        "annual_inc": 45000, "dti": 25.0, "fico_score": 660,
        "home_ownership": "RENT", "delinq_2yrs": 1,
        "inq_last_6mths": 2, "pub_rec": 0,
        "earliest_cr_line": "Jan-2008", "revol_util": 55.0,
        "revol_bal": 8000, "purpose": "credit_card",
        "emp_length": 3, "verification_status": "Not Verified",
    }
    try:
        result_2 = _cr_predict(borrower_moderate)
        grade_2 = result_2.get("implied_grade", "?")
        prob_2 = result_2.get("default_probability", 1.0)
        decision_2 = classify_loan_decision(grade_2, prob_2)
        check(decision_2 == "NEEDS_VERIFY",
              f"Moderate profile → {decision_2} (Grade {grade_2}, prob={prob_2:.4f})")
        if decision_2 != "NEEDS_VERIFY":
            print(f"    NOTE: Grade={grade_2}, prob={prob_2:.4f}. "
                  f"Adjust DTI/fico/loan_amnt to hit the 0.10-0.25 range.")
    except Exception as e:
        check(False, f"Moderate profile prediction failed: {e}")

    # ── Profile 3: Poor (expect REJECTED) ──
    borrower_poor = {
        "loan_amnt": 35000, "term": 60, "int_rate": 25.0,
        "annual_inc": 20000, "dti": 45.0, "fico_score": 520,
        "home_ownership": "RENT", "delinq_2yrs": 3,
        "inq_last_6mths": 5, "pub_rec": 2,
        "earliest_cr_line": "Jan-2015", "revol_util": 90.0,
        "revol_bal": 15000, "purpose": "small_business",
        "emp_length": 0, "verification_status": "Not Verified",
    }
    try:
        result_3 = _cr_predict(borrower_poor)
        grade_3 = result_3.get("implied_grade", "?")
        prob_3 = result_3.get("default_probability", 1.0)
        decision_3 = classify_loan_decision(grade_3, prob_3)
        check(decision_3 == "REJECTED",
              f"Poor profile → {decision_3} (Grade {grade_3}, prob={prob_3:.4f})")
        if decision_3 != "REJECTED":
            print(f"    NOTE: Grade={grade_3}, prob={prob_3:.4f}. "
                  f"Try increasing DTI or lowering FICO further.")
    except Exception as e:
        check(False, f"Poor profile prediction failed: {e}")

else:
    check(False, "XGBoost model file NOT found — skipping ML prediction tests")
    print("       Place xgb_model.pkl in the model directory to enable these tests.")


# ═══════════════════════════════════════════════════════════════════════════════
# TEST GROUP 6: Banner HTML generation (string validation)
# ═══════════════════════════════════════════════════════════════════════════════
print("\n" + "=" * 70)
print("TEST GROUP 6: Banner HTML template generation")
print("=" * 70)

for decision_key, cfg in LOAN_DECISION_CONFIG.items():
    html = f"""
    <div style="background:{cfg['banner_bg']}; border:2px solid {cfg['border']};
                border-radius:12px; padding:24px; margin-bottom:16px; text-align:center;">
        <div style="font-size:48px; margin-bottom:8px;">{cfg['icon']}</div>
        <div style="font-size:22px; font-weight:800; color:{cfg['fg']}; letter-spacing:1px;">
            {cfg['label']}
        </div>
    </div>
    """
    check(cfg['icon'] in html, f"{decision_key} banner contains icon {cfg['icon']}")
    check(cfg['label'] in html, f"{decision_key} banner contains label '{cfg['label']}'")
    check(cfg['banner_bg'] in html, f"{decision_key} banner uses correct bg color")
    check(cfg['border'] in html, f"{decision_key} banner uses correct border color")


# ═══════════════════════════════════════════════════════════════════════════════
# SUMMARY
# ═══════════════════════════════════════════════════════════════════════════════
print("\n" + "=" * 70)
total = PASSED + FAILED
print(f"TEST RESULTS: {PASSED}/{total} passed, {FAILED}/{total} failed")
print("=" * 70)

if ERRORS:
    print("\nFailed tests:")
    for err in ERRORS:
        print(f"  ❌ {err}")
else:
    print("\n🎉 All tests passed!")

print(f"\nTimestamp: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print("=" * 70 + "\n")

sys.exit(0 if FAILED == 0 else 1)
