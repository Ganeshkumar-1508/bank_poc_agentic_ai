"""
create_db.py
------------
Creates the SQLite database 'bank_poc.db' with the full schema
required by the Fixed Deposit / AML crew application.

Run:  python create_db.py
"""

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "bank_poc.db"


SCHEMA_SQL = """
PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;

--   ─
-- 1. USERS
--    Core identity table; one row per customer.
--   ─
CREATE TABLE IF NOT EXISTS users (
    user_id           INTEGER  PRIMARY KEY AUTOINCREMENT,
    first_name        TEXT     NOT NULL,
    last_name         TEXT     NOT NULL,
    account_number    TEXT     UNIQUE,               -- 12-digit generated account number
    email             TEXT,
    is_account_active INTEGER  NOT NULL DEFAULT 1,   -- 1 = active, 0 = inactive/frozen
    created_at        TEXT     NOT NULL DEFAULT (datetime('now')),
    updated_at        TEXT     NOT NULL DEFAULT (datetime('now'))
);

--   ─
-- 2. ADDRESS
--    Contact and location details for a user.
--   ─
CREATE TABLE IF NOT EXISTS address (
    address_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id          INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    user_address     TEXT,
    pin_number       TEXT,                           -- ZIP / Postal code
    mobile_number    TEXT,
    mobile_verified  INTEGER NOT NULL DEFAULT 0,     -- 1 = verified via OTP
    country_code     TEXT    NOT NULL DEFAULT 'IN',  -- ISO 3166-1 alpha-2
    created_at       TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at       TEXT    NOT NULL DEFAULT (datetime('now'))
);

--   ─
-- 3. KYC_VERIFICATION
--    Stores two dynamic KYC documents per customer.
--    Format: 'TYPE-VALUE'  (e.g. 'PASSPORT-AB123456', 'SSN-987654321')
--   ─
CREATE TABLE IF NOT EXISTS kyc_verification (
    kyc_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id       INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    address_id    INTEGER REFERENCES address(address_id),
    account_number TEXT,
    kyc_details_1 TEXT,                              -- Primary KYC doc  (TYPE-VALUE)
    kyc_details_2 TEXT,                              -- Secondary KYC doc (TYPE-VALUE)
    kyc_status    TEXT NOT NULL DEFAULT 'PENDING',   -- PENDING | VERIFIED | REJECTED
    verified_at   TEXT,
    created_at    TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

--   ─
-- 4. ACCOUNTS
--    Bank accounts linked to users (savings / current / NRI etc.).
--   ─
CREATE TABLE IF NOT EXISTS accounts (
    account_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id       INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    account_number TEXT   UNIQUE,
    account_type  TEXT    NOT NULL DEFAULT 'SAVINGS', -- SAVINGS | CURRENT | NRI | SALARY
    balance       REAL    NOT NULL DEFAULT 0.00,
    email         TEXT,
    currency_code TEXT    NOT NULL DEFAULT 'INR',
    created_at    TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at    TEXT    NOT NULL DEFAULT (datetime('now'))
);

--   ─
-- 5. FIXED_DEPOSIT
--    Stores both FD (Fixed Deposit) and RD (Recurring Deposit) products.
--   ─
CREATE TABLE IF NOT EXISTS fixed_deposit (
    fd_id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id                  INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    product_type             TEXT    NOT NULL DEFAULT 'FD',         -- 'FD' or 'RD'
    initial_amount           REAL    NOT NULL,                       -- Principal (FD) or first installment (RD)
    monthly_installment      REAL,                                   -- Only for RD
    bank_name                TEXT    NOT NULL,
    tenure_months            INTEGER NOT NULL,
    interest_rate            REAL    NOT NULL,                       -- Annual rate (e.g. 7.5)
    compounding_freq         TEXT    NOT NULL DEFAULT 'quarterly',   -- monthly | quarterly | half_yearly | yearly
    maturity_date            TEXT,                                   -- ISO date string
    premature_penalty_percent REAL   NOT NULL DEFAULT 1.0,
    fd_status                TEXT    NOT NULL DEFAULT 'ACTIVE',      -- ACTIVE | MATURED | CLOSED | PREMATURE
    created_at               TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at               TEXT    NOT NULL DEFAULT (datetime('now'))
);

--   ─
-- 6. TRANSACTIONS
--    Audit trail for all financial movements linked to a deposit.
--   ─
CREATE TABLE IF NOT EXISTS transactions (
    txn_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    fd_id           INTEGER REFERENCES fixed_deposit(fd_id),
    account_id      INTEGER REFERENCES accounts(account_id),
    user_id         INTEGER NOT NULL REFERENCES users(user_id),
    txn_type        TEXT    NOT NULL,           -- DEPOSIT | WITHDRAWAL | INTEREST_CREDIT | PENALTY
    txn_amount      REAL    NOT NULL,
    currency_code   TEXT    NOT NULL DEFAULT 'INR',
    txn_status      TEXT    NOT NULL DEFAULT 'SUCCESS',  -- SUCCESS | FAILED | PENDING | REVERSED
    reference_no    TEXT    UNIQUE,
    remarks         TEXT,
    txn_date        TEXT    NOT NULL DEFAULT (datetime('now'))
);

--   ─
-- 7. AML_CASES
--    Records AML screening outcomes for customers.
--   ─
CREATE TABLE IF NOT EXISTS aml_cases (
    case_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id        INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    risk_score     INTEGER NOT NULL DEFAULT 0,   -- 1–100 numeric score
    risk_band      TEXT    NOT NULL DEFAULT 'LOW',  -- LOW | MEDIUM | HIGH | CRITICAL
    decision       TEXT    NOT NULL DEFAULT 'PASS', -- PASS | FAIL | REVIEW
    screened_by    TEXT,                            -- Agent role that produced the report
    report_path    TEXT,                            -- Path to generated PDF report
    sanctions_hit  INTEGER NOT NULL DEFAULT 0,      -- 1 if OpenSanctions match found
    pep_flag       INTEGER NOT NULL DEFAULT 0,      -- 1 if Politically Exposed Person
    adverse_media  INTEGER NOT NULL DEFAULT 0,      -- 1 if negative news found
    notes          TEXT,
    created_at     TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at     TEXT NOT NULL DEFAULT (datetime('now'))
);

--   ─
-- 8. COMPLIANCE_AUDIT_LOG
--    Immutable log of every compliance event.
--   ─
CREATE TABLE IF NOT EXISTS compliance_audit_log (
    log_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id      INTEGER REFERENCES users(user_id),
    case_id      INTEGER REFERENCES aml_cases(case_id),
    event_type   TEXT NOT NULL,    -- KYC_SUBMIT | AML_CHECK | DEPOSIT_CREATED | DEPOSIT_REJECTED | EMAIL_SENT
    event_detail TEXT,
    performed_by TEXT,             -- Agent role or system
    ip_address   TEXT,
    logged_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

--   ─
-- 9. INTEREST_RATES_CATALOG
--    Cache of FD/RD rates fetched by the research agent.
--    Rows are reused for 6 hours (is_active=1) before a fresh search
--    is triggered.  credit_rating, news_headline, and news_url are
--    persisted alongside the rates so every lookup is self-contained.
--   ─
CREATE TABLE IF NOT EXISTS interest_rates_catalog (
    rate_id           INTEGER PRIMARY KEY AUTOINCREMENT,
    bank_name         TEXT    NOT NULL,
    product_type      TEXT    NOT NULL DEFAULT 'FD',        -- FD | RD
    tenure_min_months INTEGER NOT NULL,
    tenure_max_months INTEGER NOT NULL,
    general_rate      REAL    NOT NULL,
    senior_rate       REAL,
    credit_rating     TEXT,                                  -- e.g. 'CRISIL AAA', 'Not Found'
    news_headline     TEXT,                                  -- Most recent headline at fetch time
    news_url          TEXT,                                  -- Direct URL to the news article
    country_code      TEXT    NOT NULL DEFAULT 'IN',
    effective_date    TEXT    NOT NULL DEFAULT (datetime('now')),
    is_active         INTEGER NOT NULL DEFAULT 1             -- 0 = stale/superseded, 1 = current
);

--   ─
-- INDEXES for common query patterns
--   ─
CREATE INDEX IF NOT EXISTS idx_users_account    ON users(account_number);
CREATE INDEX IF NOT EXISTS idx_users_email      ON users(email);
CREATE INDEX IF NOT EXISTS idx_address_user     ON address(user_id);
CREATE INDEX IF NOT EXISTS idx_kyc_user         ON kyc_verification(user_id);
CREATE INDEX IF NOT EXISTS idx_accounts_user    ON accounts(user_id);
CREATE INDEX IF NOT EXISTS idx_fd_user          ON fixed_deposit(user_id);
CREATE INDEX IF NOT EXISTS idx_fd_status        ON fixed_deposit(fd_status);
CREATE INDEX IF NOT EXISTS idx_txn_user         ON transactions(user_id);
CREATE INDEX IF NOT EXISTS idx_txn_fd           ON transactions(fd_id);
CREATE INDEX IF NOT EXISTS idx_aml_user         ON aml_cases(user_id);
CREATE INDEX IF NOT EXISTS idx_aml_decision     ON aml_cases(decision);
CREATE INDEX IF NOT EXISTS idx_audit_user       ON compliance_audit_log(user_id);
CREATE INDEX IF NOT EXISTS idx_rates_bank       ON interest_rates_catalog(bank_name, product_type, country_code);
"""


def create_database():
    if DB_PATH.exists():
        print(f"[INFO] Database already exists at: {DB_PATH}")
        print("[INFO] Re-applying schema (CREATE IF NOT EXISTS — safe to re-run).")
    else:
        print(f"[INFO] Creating new database at: {DB_PATH}")

    with sqlite3.connect(DB_PATH) as conn:
        conn.executescript(SCHEMA_SQL)
        conn.commit()

    print("[OK] Schema applied successfully.")

    #      Live-database migration       
    # Safely adds columns introduced after initial deployment.
    # OperationalError is silently swallowed when the column already exists.
    _MIGRATIONS = [
        ("interest_rates_catalog", "credit_rating", "TEXT"),
        ("interest_rates_catalog", "news_headline", "TEXT"),
        ("interest_rates_catalog", "news_url",      "TEXT"),
    ]
    with sqlite3.connect(DB_PATH) as conn:
        migrated = []
        for table, column, col_type in _MIGRATIONS:
            try:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")
                conn.commit()
                migrated.append(f"{table}.{column}")
            except sqlite3.OperationalError:
                pass  # Column already exists
        if migrated:
            print(f"[MIGRATED] New columns added: {chr(44)+chr(32).join(migrated)}")
        else:
            print("[INFO] No migrations needed — all columns already present.")

    print("\nTables created:")
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;")
        for row in cur.fetchall():
            print(f"  • {row[0]}")


if __name__ == "__main__":
    create_database()