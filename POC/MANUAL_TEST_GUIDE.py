"""
MANUAL UI TESTING GUIDE — Loan Decision 3-Category Feature
=============================================================

This guide tells you exactly what borrower data to enter in the 
Streamlit UI (Module 3: Credit Risk tab) to trigger each of the 
three loan decision categories.


GRADE MAPPING (how the model works):
─────────────────────────────────────────────────────
  Grade A  →  prob 0.00% - 4.99%  →  LOAN_APPROVED
  Grade B  →  prob 5.00% - 9.99%  →  LOAN_APPROVED
  Grade C  →  prob 10.00% - 14.99% →  NEEDS_VERIFY
  Grade D  →  prob 15.00% - 19.99% →  NEEDS_VERIFY
  Grade E  →  prob 20.00% - 24.99% →  NEEDS_VERIFY
  Grade F  →  prob 25.00% - 29.99% →  REJECTED
  Grade G  →  prob 30.00%+         →  REJECTED


WHAT TO VERIFY FOR EACH CATEGORY:
─────────────────────────────────────────────────────
For EVERY category, check these 6 things:

  1. Banner appears with correct icon and color:
     - LOAN_APPROVED:  ✅ Green banner
     - NEEDS_VERIFY:   ⚠️ Yellow banner
     - REJECTED:       ❌ Red banner

  2. Decision label text is correct:
     - "LOAN APPROVED"
     - "NEEDS VERIFICATION & APPROVAL"
     - "LOAN REJECTED"

  3. Grade and probability displayed under the banner

  4. Decision rationale section appears with category-specific text

  5. Conditions list appears with category-specific items

  6. Next steps section appears with category-specific items

  7. "Notify Borrower" section has:
     - Email input field
     - "Send Decision Email" button
     - Info panel explaining email content

  8. After clicking "Send Decision Email":
     - Shows ✅ success or ❌ error message
     - (Requires SMTP env vars configured for actual sending)

  9. Loan Application History section at bottom shows the record
     with correct color-coded decision badge

  10. Export buttons (JSON/TXT) include loan_decision field


TEST SCENARIOS (enter these exact values in the form):
═════════════════════════════════════════════════════

SCENARIO 1: LOAN_APPROVED (Green)
─────────────────────────────────
  Loan Amount:        $5,000
  Term:               36 months
  Interest Rate:      6.50%
  Purpose:            debt_consolidation
  Annual Income:      $150,000
  Employment Length:  10+ years
  Home Ownership:     MORTGAGE
  Verification:       Verified
  FICO Score:         800
  DTI Ratio:          5.0%
  Delinquencies:      0
  Inquiries:          0
  Public Records:     0
  Revolving Util:     10.0%
  Revolving Balance:  $1,000
  Earliest Credit:    Jan-1990

  EXPECTED: Grade A or B → Green ✅ LOAN APPROVED banner
  If you get NEEDS_VERIFY instead: lower loan amount to $3000 
  or increase income to $200,000.


SCENARIO 2: NEEDS_VERIFY (Yellow)
──────────────────────────────────
  Loan Amount:        $15,000
  Term:               60 months
  Interest Rate:      14.00%
  Purpose:            credit_card
  Annual Income:      $45,000
  Employment Length:  3 years
  Home Ownership:     RENT
  Verification:       Not Verified
  FICO Score:         660
  DTI Ratio:          25.0%
  Delinquencies:      1
  Inquiries:          2
  Public Records:     0
  Revolving Util:     55.0%
  Revolving Balance:  $8,000
  Earliest Credit:    Jan-2008

  EXPECTED: Grade C, D, or E → Yellow ⚠️ NEEDS VERIFICATION banner
  If you get LOAN_APPROVED: increase DTI to 30% or lower FICO to 640.
  If you get REJECTED: decrease DTI to 18% or increase FICO to 690.


SCENARIO 3: REJECTED (Red)
──────────────────────────
  Loan Amount:        $35,000
  Term:               60 months
  Interest Rate:      25.00%
  Purpose:            small_business
  Annual Income:      $20,000
  Employment Length:  < 1 year
  Home Ownership:     RENT
  Verification:       Not Verified
  FICO Score:         520
  DTI Ratio:          45.0%
  Delinquencies:      3
  Inquiries:          5
  Public Records:     2
  Revolving Util:     90.0%
  Revolving Balance:  $15,000
  Earliest Credit:    Jan-2015

  EXPECTED: Grade F or G → Red ❌ LOAN REJECTED banner
  If you get NEEDS_VERIFY instead: increase DTI to 50%, lower FICO 
  to 480, or increase loan amount to $40,000.


EMAIL TESTING:
══════════════
To test email sending, configure these env vars in your .env file:
  SMTP_HOST=smtp.gmail.com
  SMTP_PORT=587
  SMTP_USER=your_email@gmail.com
  SMTP_PASSWORD=your_app_password

Then:
  1. Run any scenario above
  2. Enter a real email in "Borrower Email" field
  3. Click "📧 Send Decision Email"
  4. Check the recipient inbox
  5. Verify: correct color header, decision text, grade, rationale,
     conditions, next steps for that decision category


QUICK CALIBRATION TIPS:
════════════════════════
If the model doesn't give you the expected category, adjust these
key factors (in order of impact):

  For APPROVED:   High FICO (>750), Low DTI (<15%), Low loan/income ratio
  For NEEDS_VERIFY: FICO 640-700, DTI 20-30%, Moderate loan/income ratio
  For REJECTED:    Low FICO (<580), High DTI (>35%), High loan/income ratio

The default_probability shown on the results page is the definitive
indicator — use classify_loan_decision(grade, prob) logic to verify.
"""
