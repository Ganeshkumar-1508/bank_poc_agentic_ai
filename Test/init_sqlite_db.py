# init_sqlite_db.py
import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "bank_poc.db"
SCHEMA_PATH = BASE_DIR / "db_schema.sql"

def main() -> None:
    # Create a dummy schema file if it doesn't exist for the script to run
    if not SCHEMA_PATH.exists():
        with open(SCHEMA_PATH, "w") as f:
            f.write("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY AUTOINCREMENT,
                first_name TEXT NOT NULL,
                last_name TEXT NOT NULL,
                account_number TEXT UNIQUE,
                email TEXT,
                is_account_active INTEGER DEFAULT 1
            );
            CREATE TABLE IF NOT EXISTS address (
                address_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                user_address TEXT NOT NULL,
                pin_number TEXT NOT NULL,
                mobile_number TEXT NOT NULL,
                mobile_verified INTEGER DEFAULT 0,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            );
            CREATE TABLE IF NOT EXISTS kyc_verification (
                kyc_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                address_id INTEGER NOT NULL,
                account_number TEXT,
                pan_number TEXT,
                aadhaar_number TEXT,
                kyc_status TEXT DEFAULT 'NOT_VERIFIED',
                verified_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id),
                FOREIGN KEY (address_id) REFERENCES address(address_id)
            );
            CREATE TABLE IF NOT EXISTS accounts (
                account_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                account_number TEXT UNIQUE NOT NULL,
                account_type TEXT DEFAULT 'Savings',
                balance REAL DEFAULT 0.0,
                email TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            );
            CREATE TABLE IF NOT EXISTS fixed_deposit (
                fd_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                initial_amount REAL NOT NULL,
                bank_name TEXT NOT NULL,
                tenure_months INTEGER NOT NULL,
                interest_rate REAL NOT NULL,
                maturity_date TEXT NOT NULL,
                premature_penalty_percent REAL DEFAULT 1.0,
                fd_status TEXT DEFAULT 'ACTIVE',
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            );
            """)

    schema_sql = SCHEMA_PATH.read_text(encoding="utf-8")

    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.executescript(schema_sql)
        conn.commit()

    print(f"SQLite DB initialized: {DB_PATH}")

if __name__ == "__main__":
    main()