"""
seed_data.py
------------
Ingests realistic test data into bank_poc.db.
Covers all tables: users, address, kyc_verification, accounts,
fixed_deposit, transactions, aml_cases, compliance_audit_log,
interest_rates_catalog.

Run AFTER create_db.py:
    python create_db.py
    python seed_data.py
"""

import sqlite3
import random
import string
from datetime import datetime, timedelta
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "bank_poc.db"

#
# Helpers
#


def rand_account() -> str:
    """Generate a random 12-digit account number."""
    return str(random.randint(10**11, 10**12 - 1))


def rand_ref() -> str:
    """Generate a random 12-char alphanumeric reference."""
    return "TXN" + "".join(random.choices(string.ascii_uppercase + string.digits, k=9))


def offset_date(days: int) -> str:
    return (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")


def future_date(months: int) -> str:
    return (datetime.now() + timedelta(days=30 * months)).strftime("%Y-%m-%d")


def past_date(days: int) -> str:
    return (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")


#
# Seed data definitions
#

USERS = [
    # (first_name, last_name, account_number, email, is_account_active)
    ("Arjun", "Sharma", rand_account(), "arjun.sharma@email.com", 1),
    ("Priya", "Nair", rand_account(), "priya.nair@email.com", 1),
    ("Mohammed", "Al-Rashid", rand_account(), "mohammed.alrashid@email.com", 1),
    ("Elena", "Petrov", rand_account(), "elena.petrov@email.com", 1),
    ("James", "Okafor", rand_account(), "james.okafor@email.com", 1),
    ("Sofia", "Martinez", rand_account(), "sofia.martinez@email.com", 1),
    ("Wei", "Zhang", rand_account(), "wei.zhang@email.com", 1),
    ("Amelia", "Brown", rand_account(), "amelia.brown@email.com", 0),  # inactive
    ("Rajan", "Pillai", rand_account(), "rajan.pillai@email.com", 1),
    ("Fatima", "Hassan", rand_account(), "fatima.hassan@email.com", 1),
]

# address data mirrors USERS order
ADDRESSES = [
    # (user_address, pin_number, mobile_number, mobile_verified, country_code)
    ("12 MG Road, Bangalore", "560001", "+91-9876543210", 1, "IN"),
    ("45 Anna Salai, Chennai", "600002", "+91-9123456780", 1, "IN"),
    ("7 King Fahd Road, Riyadh", "11564", "+966-501234567", 1, "SA"),
    ("23 Nevsky Prospekt, St Petersburg", "191025", "+7-9112345678", 1, "RU"),
    ("10 Victoria Island, Lagos", "101241", "+234-8012345678", 1, "NG"),
    ("Calle Mayor 5, Madrid", "28013", "+34-612345678", 1, "ES"),
    ("88 Nanjing Road, Shanghai", "200000", "+86-13812345678", 1, "CN"),
    ("22 Oxford Street, London", "W1D 1AN", "+44-7712345678", 0, "GB"),
    ("30 Marine Lines, Mumbai", "400002", "+91-9988776655", 1, "IN"),
    ("15 Downtown Dubai, Dubai", "00000", "+971-501234567", 1, "AE"),
]

# KYC data mirrors USERS order
KYC_DATA = [
    ("PAN-ABCDE1234F", "AADHAAR-123456789012"),
    ("PAN-PQRST5678G", "AADHAAR-987654321098"),
    ("PASSPORT-SA12345", "NATIONAL_ID-SA9876543"),
    ("PASSPORT-RU67890", "NATIONAL_ID-RU1234567"),
    ("NIN-NG11111111", "PASSPORT-NG-A1234567"),
    ("DNI-ES12345678", "PASSPORT-ES-BC987654"),
    ("RESIDENT_ID-CN001", "PASSPORT-CN-E1234567"),
    ("PASSPORT-GB-456789", "NIN-UK-QQ123456C"),
    ("PAN-ZZZZZ9999Z", "AADHAAR-111222333444"),
    ("PASSPORT-AE-00001", "EMIRATES_ID-784-1234-5678901-2"),
]

# Accounts: one savings account per user
ACCOUNT_TYPES = [
    "SAVINGS",
    "SAVINGS",
    "SAVINGS",
    "CURRENT",
    "SAVINGS",
    "SAVINGS",
    "CURRENT",
    "SAVINGS",
    "SALARY",
    "SAVINGS",
]
CURRENCIES = ["INR", "INR", "SAR", "RUB", "NGN", "EUR", "CNY", "GBP", "INR", "AED"]

# Fixed Deposits & RDs
DEPOSITS = [
    # (user_idx, product_type, initial_amount, monthly_installment, bank_name,
    #  tenure_months, interest_rate, compounding_freq, fd_status)
    (0, "FD", 500000.0, None, "HDFC Bank", 12, 7.00, "quarterly", "ACTIVE"),
    (1, "FD", 250000.0, None, "State Bank of India", 24, 6.80, "quarterly", "ACTIVE"),
    (2, "FD", 100000.0, None, "Al Rajhi Bank", 18, 5.50, "monthly", "ACTIVE"),
    (3, "FD", 750000.0, None, "Sberbank", 36, 8.00, "yearly", "MATURED"),
    (4, "RD", 10000.0, 10000.0, "Access Bank", 24, 9.50, "monthly", "ACTIVE"),
    (5, "FD", 200000.0, None, "Banco Santander", 12, 3.75, "quarterly", "ACTIVE"),
    (6, "FD", 1000000.0, None, "Bank of China", 60, 4.20, "half_yearly", "ACTIVE"),
    (7, "RD", 5000.0, 5000.0, "Barclays", 12, 4.00, "monthly", "PREMATURE"),
    (8, "FD", 300000.0, None, "Axis Bank", 6, 6.50, "quarterly", "ACTIVE"),
    (9, "FD", 150000.0, None, "Emirates NBD", 24, 5.00, "quarterly", "ACTIVE"),
    # Second deposit for user 0 (Arjun - loyal customer)
    (0, "RD", 15000.0, 15000.0, "ICICI Bank", 36, 7.25, "quarterly", "ACTIVE"),
    # Closed deposit for user 1
    (1, "FD", 100000.0, None, "Punjab National Bank", 6, 6.25, "quarterly", "CLOSED"),
]

# AML cases (only for some users to reflect realistic screening)
AML_CASES = [
    # (user_idx, risk_score, risk_band, decision, sanctions_hit, pep_flag, adverse_media)
    (0, 12, "LOW", "PASS", 0, 0, 0),
    (1, 18, "LOW", "PASS", 0, 0, 0),
    (2, 35, "MEDIUM", "PASS", 0, 1, 0),  # PEP flag
    (3, 55, "HIGH", "REVIEW", 0, 1, 1),  # PEP + adverse media
    (4, 8, "LOW", "PASS", 0, 0, 0),
    (5, 22, "MEDIUM", "PASS", 0, 0, 0),
    (6, 15, "LOW", "PASS", 0, 0, 0),
    (7, 72, "CRITICAL", "FAIL", 1, 0, 1),  # Sanctions hit
    (8, 10, "LOW", "PASS", 0, 0, 0),
    (9, 30, "MEDIUM", "PASS", 0, 1, 0),  # PEP flag (Dubai)
]

# Interest rates catalog
RATES_CATALOG = [
    # (bank_name, product_type, tenure_min, tenure_max, general_rate, senior_rate, country_code)
    ("HDFC Bank", "FD", 1, 3, 5.50, 6.00, "IN"),
    ("HDFC Bank", "FD", 4, 12, 6.60, 7.10, "IN"),
    ("HDFC Bank", "FD", 13, 24, 7.00, 7.50, "IN"),
    ("HDFC Bank", "FD", 25, 60, 7.20, 7.75, "IN"),
    ("HDFC Bank", "RD", 6, 120, 6.50, 7.00, "IN"),
    ("State Bank of India", "FD", 1, 3, 5.25, 5.75, "IN"),
    ("State Bank of India", "FD", 4, 12, 6.40, 6.90, "IN"),
    ("State Bank of India", "FD", 13, 60, 6.80, 7.30, "IN"),
    ("State Bank of India", "RD", 12, 120, 6.50, 7.00, "IN"),
    ("ICICI Bank", "FD", 1, 12, 6.70, 7.20, "IN"),
    ("ICICI Bank", "FD", 13, 60, 7.10, 7.60, "IN"),
    ("ICICI Bank", "RD", 6, 120, 6.60, 7.10, "IN"),
    ("Axis Bank", "FD", 1, 12, 6.50, 7.00, "IN"),
    ("Axis Bank", "FD", 13, 60, 7.00, 7.50, "IN"),
    ("Punjab National Bank", "FD", 1, 12, 6.30, 6.80, "IN"),
    ("Punjab National Bank", "FD", 13, 60, 6.75, 7.25, "IN"),
    ("Al Rajhi Bank", "FD", 1, 12, 5.00, 5.50, "SA"),
    ("Al Rajhi Bank", "FD", 13, 36, 5.50, 6.00, "SA"),
    ("Sberbank", "FD", 3, 12, 7.50, 8.00, "RU"),
    ("Sberbank", "FD", 13, 60, 8.00, 8.50, "RU"),
    ("Access Bank", "FD", 1, 12, 9.00, 9.50, "NG"),
    ("Access Bank", "RD", 12, 60, 9.50, 9.50, "NG"),
    ("Banco Santander", "FD", 1, 12, 3.50, 3.75, "ES"),
    ("Banco Santander", "FD", 13, 36, 3.75, 4.00, "ES"),
    ("Bank of China", "FD", 3, 12, 3.80, 4.20, "CN"),
    ("Bank of China", "FD", 13, 60, 4.20, 4.60, "CN"),
    ("Barclays", "FD", 1, 12, 4.00, 4.25, "GB"),
    ("Barclays", "RD", 12, 60, 3.75, 4.00, "GB"),
    ("Emirates NBD", "FD", 1, 12, 4.50, 5.00, "AE"),
    ("Emirates NBD", "FD", 13, 36, 5.00, 5.50, "AE"),
]


#
# Ingestion logic
#


def seed(conn: sqlite3.Connection):
    cur = conn.cursor()
    conn.execute("PRAGMA foreign_keys = ON;")

    #      1. Users
    print("  Seeding users...")
    user_ids = []
    for u in USERS:
        cur.execute(
            "INSERT INTO users (first_name, last_name, account_number, email, is_account_active, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (*u, past_date(random.randint(30, 730)), past_date(random.randint(1, 30))),
        )
        user_ids.append(cur.lastrowid)
    print(f"    → {len(user_ids)} users inserted.")

    #      2. Addresses
    print("  Seeding addresses...")
    address_ids = []
    for i, addr in enumerate(ADDRESSES):
        cur.execute(
            "INSERT INTO address (user_id, user_address, pin_number, mobile_number, mobile_verified, country_code) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (user_ids[i], *addr),
        )
        address_ids.append(cur.lastrowid)
    print(f"    → {len(address_ids)} addresses inserted.")

    #      3. KYC
    print("  Seeding KYC records...")
    for i, kyc in enumerate(KYC_DATA):
        uid = user_ids[i]
        aid = address_ids[i]
        acc = USERS[i][2]
        cur.execute(
            "INSERT INTO kyc_verification "
            "(user_id, address_id, account_number, kyc_details_1, kyc_details_2, kyc_status, verified_at, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, 'VERIFIED', ?, ?, ?)",
            (
                uid,
                aid,
                acc,
                kyc[0],
                kyc[1],
                past_date(random.randint(20, 180)),
                past_date(random.randint(30, 200)),
                past_date(random.randint(1, 10)),
            ),
        )
    print(f"    → {len(KYC_DATA)} KYC records inserted.")

    #      4. Accounts
    print("  Seeding accounts...")
    account_ids = []
    for i in range(len(USERS)):
        uid = user_ids[i]
        acc_no = USERS[i][2]
        balance = round(random.uniform(5000, 500000), 2)
        cur.execute(
            "INSERT INTO accounts (user_id, account_number, account_type, balance, email, currency_code) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (uid, acc_no, ACCOUNT_TYPES[i], balance, USERS[i][3], CURRENCIES[i]),
        )
        account_ids.append(cur.lastrowid)
    print(f"    → {len(account_ids)} accounts inserted.")

    #      5. Fixed / Recurring Deposits
    print("  Seeding deposits (FD / RD)...")
    fd_ids = []
    for dep in DEPOSITS:
        (
            u_idx,
            product_type,
            initial_amount,
            monthly_installment,
            bank_name,
            tenure_months,
            interest_rate,
            compounding_freq,
            fd_status,
        ) = dep
        uid = user_ids[u_idx]
        maturity = (
            future_date(tenure_months)
            if fd_status == "ACTIVE"
            else past_date(random.randint(10, 300))
        )
        cur.execute(
            "INSERT INTO fixed_deposit "
            "(user_id, product_type, initial_amount, monthly_installment, bank_name, "
            "tenure_months, interest_rate, compounding_freq, maturity_date, "
            "premature_penalty_percent, fd_status, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1.0, ?, ?, ?)",
            (
                uid,
                product_type,
                initial_amount,
                monthly_installment,
                bank_name,
                tenure_months,
                interest_rate,
                compounding_freq,
                maturity,
                fd_status,
                past_date(random.randint(30, 365)),
                past_date(random.randint(1, 30)),
            ),
        )
        fd_ids.append(cur.lastrowid)
    print(f"    → {len(fd_ids)} deposit records inserted.")

    #      6. Transactions
    print("  Seeding transactions...")
    txn_count = 0
    for dep_idx, (dep, fd_id) in enumerate(zip(DEPOSITS, fd_ids)):
        u_idx = dep[0]
        product_type = dep[1]
        amount = dep[2]
        uid = user_ids[u_idx]
        acc_id = account_ids[u_idx]
        fd_status = dep[8]

        # Opening DEPOSIT transaction
        cur.execute(
            "INSERT INTO transactions "
            "(fd_id, account_id, user_id, txn_type, txn_amount, currency_code, txn_status, reference_no, remarks, txn_date) "
            "VALUES (?, ?, ?, 'DEPOSIT', ?, ?, 'SUCCESS', ?, ?, ?)",
            (
                fd_id,
                acc_id,
                uid,
                amount,
                CURRENCIES[u_idx],
                rand_ref(),
                f"Initial {product_type} booking",
                past_date(random.randint(30, 365)),
            ),
        )
        txn_count += 1

        # INTEREST_CREDIT (simulate 1–3 credits for non-premature deposits)
        if fd_status not in ("PREMATURE",):
            for _ in range(random.randint(1, 3)):
                interest = round(amount * (dep[6] / 100) / 4, 2)  # rough quarterly
                cur.execute(
                    "INSERT INTO transactions "
                    "(fd_id, account_id, user_id, txn_type, txn_amount, currency_code, txn_status, reference_no, remarks, txn_date) "
                    "VALUES (?, ?, ?, 'INTEREST_CREDIT', ?, ?, 'SUCCESS', ?, ?, ?)",
                    (
                        fd_id,
                        acc_id,
                        uid,
                        interest,
                        CURRENCIES[u_idx],
                        rand_ref(),
                        "Quarterly interest credit",
                        past_date(random.randint(5, 25)),
                    ),
                )
                txn_count += 1

        # PENALTY for premature closure
        if fd_status == "PREMATURE":
            penalty = round(amount * 0.01, 2)
            cur.execute(
                "INSERT INTO transactions "
                "(fd_id, account_id, user_id, txn_type, txn_amount, currency_code, txn_status, reference_no, remarks, txn_date) "
                "VALUES (?, ?, ?, 'PENALTY', ?, ?, 'SUCCESS', ?, ?, ?)",
                (
                    fd_id,
                    acc_id,
                    uid,
                    penalty,
                    CURRENCIES[u_idx],
                    rand_ref(),
                    "Premature withdrawal penalty deducted",
                    past_date(5),
                ),
            )
            txn_count += 1

        # WITHDRAWAL on CLOSED/MATURED deposits
        if fd_status in ("CLOSED", "MATURED"):
            cur.execute(
                "INSERT INTO transactions "
                "(fd_id, account_id, user_id, txn_type, txn_amount, currency_code, txn_status, reference_no, remarks, txn_date) "
                "VALUES (?, ?, ?, 'WITHDRAWAL', ?, ?, 'SUCCESS', ?, ?, ?)",
                (
                    fd_id,
                    acc_id,
                    uid,
                    amount,
                    CURRENCIES[u_idx],
                    rand_ref(),
                    f"{fd_status} payout",
                    past_date(random.randint(1, 15)),
                ),
            )
            txn_count += 1

    print(f"    → {txn_count} transaction records inserted.")

    #      7. AML Cases
    print("  Seeding AML cases...")
    case_ids = []
    for ac in AML_CASES:
        (
            u_idx,
            risk_score,
            risk_band,
            decision,
            sanctions_hit,
            pep_flag,
            adverse_media,
        ) = ac
        uid = user_ids[u_idx]
        screened_at = past_date(random.randint(5, 60))
        report_name = (
            f"aml_report_{USERS[u_idx][0].lower()}_{USERS[u_idx][1].lower()}.pdf"
        )
        cur.execute(
            "INSERT INTO aml_cases "
            "(user_id, risk_score, risk_band, decision, screened_by, report_path, "
            "sanctions_hit, pep_flag, adverse_media, notes, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, 'Chief Risk Officer', ?, ?, ?, ?, ?, ?, ?)",
            (
                uid,
                risk_score,
                risk_band,
                decision,
                f"/reports/{report_name}",
                sanctions_hit,
                pep_flag,
                adverse_media,
                f"Auto-generated AML screening. Band: {risk_band}.",
                screened_at,
                screened_at,
            ),
        )
        case_ids.append(cur.lastrowid)
    print(f"    → {len(case_ids)} AML cases inserted.")

    #      8. Compliance Audit Log
    print("  Seeding compliance audit log...")
    audit_count = 0
    events = [
        ("KYC_SUBMIT", "KYC documents submitted for verification."),
        ("AML_CHECK", "AML screening initiated."),
        ("DEPOSIT_CREATED", "FD/RD product created post-compliance clearance."),
        ("EMAIL_SENT", "Welcome email with deposit confirmation dispatched."),
    ]
    for i, uid in enumerate(user_ids):
        case_id = case_ids[i] if i < len(case_ids) else None
        for event_type, detail in events:
            if event_type == "DEPOSIT_CREATED" and AML_CASES[i][3] != "PASS":
                detail = "DEPOSIT_REJECTED — AML decision was FAIL/REVIEW."
                event_type = "DEPOSIT_REJECTED"
            cur.execute(
                "INSERT INTO compliance_audit_log "
                "(user_id, case_id, event_type, event_detail, performed_by, logged_at) "
                "VALUES (?, ?, ?, ?, 'System', ?)",
                (uid, case_id, event_type, detail, past_date(random.randint(1, 30))),
            )
            audit_count += 1
    print(f"    → {audit_count} audit log entries inserted.")

    #      9. Interest Rates Catalog
    print("  Seeding interest rates catalog...")
    for rate in RATES_CATALOG:
        cur.execute(
            "INSERT INTO interest_rates_catalog "
            "(bank_name, product_type, tenure_min_months, tenure_max_months, "
            "general_rate, senior_rate, country_code, effective_date, is_active) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, date('now'), 1)",
            rate,
        )
    print(f"    → {len(RATES_CATALOG)} interest rate entries inserted.")

    conn.commit()


#
# Summary printer
#


def print_summary(conn: sqlite3.Connection):
    tables = [
        "users",
        "address",
        "kyc_verification",
        "accounts",
        "fixed_deposit",
        "transactions",
        "aml_cases",
        "compliance_audit_log",
        "interest_rates_catalog",
    ]
    print("\n" + "─" * 45)
    print(f"{'Table':<30} {'Rows':>10}")
    print("─" * 45)
    for t in tables:
        (count,) = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()
        print(f"  {t:<28} {count:>10}")
    print("─" * 45)


#
# Entry point
#

if __name__ == "__main__":
    if not DB_PATH.exists():
        print(f"[ERROR] Database not found at {DB_PATH}.")
        print("        Run 'python create_db.py' first.")
        raise SystemExit(1)

    print(f"[INFO] Connecting to: {DB_PATH}")

    with sqlite3.connect(DB_PATH) as conn:
        # Guard: skip if data already exists
        (existing,) = conn.execute("SELECT COUNT(*) FROM users").fetchone()
        if existing > 0:
            print(
                f"[WARN] Database already contains {existing} user(s). Skipping seed to avoid duplicates."
            )
            print(
                "       Delete 'bank_poc.db' and re-run create_db.py + seed_data.py to start fresh."
            )
            print_summary(conn)
            raise SystemExit(0)

        print("[INFO] Starting data ingestion...\n")
        seed(conn)

    print("\n[OK] Test data ingested successfully!")
    with sqlite3.connect(DB_PATH) as conn:
        print_summary(conn)
