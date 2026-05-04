"""
Database Schema Examiner
========================
This script examines the actual schema of bank_poc.db and compares it
with the expected schema from create_db.py.

Run: python examine_db_schema.py
"""
import sqlite3
from pathlib import Path

DB_PATH = Path("Test/tools/bank_poc.db")
EXPECTED_SCHEMA = {
    "users": ["user_id", "first_name", "last_name", "account_number", "email", "is_account_active", "created_at", "updated_at"],
    "address": ["address_id", "user_id", "user_address", "pin_number", "mobile_number", "mobile_verified", "country_code", "created_at", "updated_at"],
    "kyc_verification": ["kyc_id", "user_id", "address_id", "account_number", "kyc_details_1", "kyc_details_2", "kyc_status", "verified_at", "created_at", "updated_at"],
    "accounts": ["account_id", "user_id", "account_number", "account_type", "balance", "email", "currency_code", "created_at", "updated_at"],
    "fixed_deposit": ["fd_id", "user_id", "product_type", "initial_amount", "monthly_installment", "bank_name", "tenure_months", "interest_rate", "compounding_freq", "maturity_date", "premature_penalty_percent", "fd_status", "account_number", "region", "user_session_id", "customer_name", "customer_email", "customer_phone", "start_date", "maturity_amount", "interest_earned", "senior_citizen", "loan_against_fd", "auto_renewal", "certificate_path", "certificate_generated", "email_sent", "email_sent_at", "confirmed_at", "risk_score", "created_at", "updated_at"],
    "transactions": ["txn_id", "fd_id", "account_id", "user_id", "txn_type", "txn_amount", "currency_code", "txn_status", "reference_no", "remarks", "txn_date"],
    "aml_cases": ["case_id", "user_id", "risk_score", "risk_band", "decision", "screened_by", "report_path", "sanctions_hit", "pep_flag", "adverse_media", "notes", "created_at", "updated_at"],
    "compliance_audit_log": ["log_id", "user_id", "case_id", "event_type", "event_detail", "performed_by", "ip_address", "logged_at"],
    "interest_rates_catalog": ["rate_id", "bank_name", "product_type", "tenure_min_months", "tenure_max_months", "general_rate", "senior_rate", "credit_rating", "news_headline", "news_url", "country_code", "effective_date", "is_active"],
    "loan_applications": ["application_id", "user_id", "applicant_email", "loan_amnt", "term", "int_rate", "purpose", "annual_inc", "fico_score", "dti", "home_ownership", "default_prob", "implied_grade", "risk_level", "loan_decision", "decision_rationale", "conditions", "next_steps", "notification_sent", "created_at", "updated_at"],
    "loan_disbursements": ["disbursement_id", "application_id", "user_id", "account_id", "sanctioned_amount", "disbursement_status", "disbursed_at", "created_at"],
}


def examine_database():
    if not DB_PATH.exists():
        print(f"❌ Database not found at {DB_PATH}")
        return False
    
    print(f"🔍 Examining database: {DB_PATH}")
    print("=" * 80)
    
    with sqlite3.connect(DB_PATH) as conn:
        # Get all tables
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;"
        )
        actual_tables = [row[0] for row in cursor.fetchall()]
        
        print(f"\n📊 Tables found ({len(actual_tables)}):")
        for table in actual_tables:
            marker = "✓" if table in EXPECTED_SCHEMA else "⚠️ UNEXPECTED"
            print(f"  {marker} {table}")
        
        # Check for missing tables
        missing_tables = set(EXPECTED_SCHEMA.keys()) - set(actual_tables)
        if missing_tables:
            print(f"\n⚠️ Missing tables: {missing_tables}")
        
        print("\n" + "=" * 80)
        print("📋 DETAILED SCHEMA COMPARISON:")
        print("=" * 80)
        
        all_match = True
        for table in actual_tables:
            print(f"\n{'─' * 60}")
            print(f"Table: {table}")
            print(f"{'─' * 60}")
            
            cursor = conn.execute(f"PRAGMA table_info({table});")
            actual_columns = [col[1] for col in cursor.fetchall()]
            
            expected_columns = EXPECTED_SCHEMA.get(table, [])
            
            print(f"  Expected columns ({len(expected_columns)}): {', '.join(expected_columns)}")
            print(f"  Actual columns   ({len(actual_columns)}): {', '.join(actual_columns)}")
            
            # Check for mismatches
            missing_cols = set(expected_columns) - set(actual_columns)
            extra_cols = set(actual_columns) - set(expected_columns)
            
            if missing_cols:
                print(f"  ⚠️ Missing columns: {missing_cols}")
                all_match = False
            if extra_cols:
                print(f"  ℹ️ Extra columns: {extra_cols}")
            
            # Show sample data
            cursor = conn.execute(f"SELECT * FROM {table} LIMIT 1;")
            row = cursor.fetchone()
            if row:
                sample = dict(zip(actual_columns, row))
                print(f"  📝 Sample row: {sample}")
            else:
                print(f"  📝 Sample row: (empty table)")
        
        print("\n" + "=" * 80)
        if all_match:
            print("✅ Schema matches expected structure!")
        else:
            print("⚠️ Schema has discrepancies - review above")
        print("=" * 80)
        
        return all_match


if __name__ == "__main__":
    examine_database()
