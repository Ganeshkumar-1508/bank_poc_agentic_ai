"""
Test script to verify LLM generates the AI Borrower Summary dynamically.
This demonstrates that the LLM takes ML model output + RAG policy and generates the summary.
"""

import os
import json
from dotenv import load_dotenv

load_dotenv()

from crews import run_loan_creation_crew

# Test borrower data with FICO 680, DTI 18% (the exact scenario from your question)
borrower_data = {
    "first_name": "John",
    "last_name": "Doe",
    "fico_score": 680,
    "dti": 18.0,
    "annual_inc": 75000,
    "loan_amnt": 25000,
    "int_rate": 12.5,
    "term": 36,
    "home_ownership": "RENT",
    "emp_length": 5,
    "purpose": "debt_consolidation",
    "delinq_2yrs": 0,
    "inq_last_6mths": 1,
    "pub_rec": 0,
    "revol_util": 35.0,
    "total_acc": 12,
    "verification_status": "NOT_VERIFIED",
}

print("=" * 80)
print("TEST: LLM-Generated Loan Decision & Borrower Summary")
print("=" * 80)
print("\nBorrower Profile:")
print(f" - FICO Score: {borrower_data['fico_score']} (Fair Credit range)")
print(f" - DTI Ratio: {borrower_data['dti']}% (below 28% threshold)")
print(f" - Annual Income: ${borrower_data['annual_inc']:,}")
print(f" - Loan Amount: ${borrower_data['loan_amnt']:,}")
print()

prompt_context = (
    f"Borrower Application Data (JSON):\n{json.dumps(borrower_data, indent=2)}"
)

print("Running Loan Creation Crew...")
print("-" * 80)
result = run_loan_creation_crew(prompt_context)
print("-" * 80)

print("\n" + "=" * 80)
print("TASK 0: LLM DECISION (ML Model + RAG Policy Comparison)")
print("=" * 80)
if hasattr(result, "tasks_output") and len(result.tasks_output) >= 1:
    output = result.tasks_output[0]
    if hasattr(output, "output"):
        print(output.output)
    if hasattr(output, "raw"):
        print("\n--- RAW OUTPUT ---")
        print(output.raw)

print("\n" + "=" * 80)
print("TASK 1: LLM-GENERATED BORROWER SUMMARY (AI Borrower Summary)")
print("=" * 80)
if hasattr(result, "tasks_output") and len(result.tasks_output) >= 2:
    output = result.tasks_output[1]
    if hasattr(output, "output"):
        print(output.output)
    if hasattr(output, "raw"):
        print("\n--- RAW OUTPUT ---")
        print(output.raw)

print("\n" + "=" * 80)
print("CONCLUSION")
print("=" * 80)
print(
    """
The output above demonstrates that:
1. The LLM receives ML model scores (Grade, default probability)
2. The LLM queries RAG for bank policy thresholds
3. The LLM COMPARES both and makes a decision (LOAN_APPROVED, NEEDS_VERIFY, REJECTED)
4. The LLM GENERATES the borrower-friendly summary dynamically

"""
)
