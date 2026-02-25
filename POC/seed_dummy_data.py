import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

from kyc_validation import evaluate_kyc_status


BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "bank_poc.db"


def reset_and_create_schema(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA foreign_keys = OFF;")
    
    # Updated schema definition including the new 'accounts' table and 'email' column
    schema_sql = """
    DROP TABLE IF EXISTS fixed_deposit;
    DROP TABLE IF EXISTS accounts;
    DROP TABLE IF EXISTS kyc_verification;
    DROP TABLE IF EXISTS address;
    DROP TABLE IF EXISTS users;

    CREATE TABLE users (
        user_id INTEGER PRIMARY KEY AUTOINCREMENT,
        first_name TEXT NOT NULL,
        last_name TEXT NOT NULL,
        account_number TEXT UNIQUE,
        email TEXT,
        is_account_active INTEGER DEFAULT 1
    );

    CREATE TABLE address (
        address_id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        user_address TEXT NOT NULL,
        pin_number TEXT NOT NULL,
        mobile_number TEXT NOT NULL,
        mobile_verified INTEGER DEFAULT 0,
        FOREIGN KEY (user_id) REFERENCES users(user_id)
    );

    CREATE TABLE kyc_verification (
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

    CREATE TABLE accounts (
        account_id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        account_number TEXT UNIQUE NOT NULL,
        account_type TEXT DEFAULT 'Savings',
        balance REAL DEFAULT 0.0,
        email TEXT, -- NEW COLUMN ADDED HERE
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(user_id)
    );

    CREATE TABLE fixed_deposit (
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
    """
    
    conn.executescript(schema_sql)
    conn.execute("PRAGMA foreign_keys = ON;")


def insert_dummy_users(conn: sqlite3.Connection) -> None:
    users = [
        ("Amit", "Sharma", "100000000001", "amit.sharma@example.com", 1),
        ("Neha", "Iyer", "100000000002", "neha.iyer@example.com", 1),
        ("Ravi", "Khan", "100000000003", "ravi.khan@example.com", 1),
        ("Pooja", "Das", "100000000004", "pooja.das@example.com", 0),
    ]
    conn.executemany(
        """
        INSERT INTO users (first_name, last_name, account_number, email, is_account_active)
        VALUES (?, ?, ?, ?, ?)
        """,
        users,
    )


def insert_dummy_addresses(conn: sqlite3.Connection) -> None:
    user_map = {
        row[1]: row[0]
        for row in conn.execute("SELECT user_id, account_number FROM users").fetchall()
    }
    addresses = [
        (user_map["100000000001"], "No 10, MG Road, Bengaluru", "560001", "9876543210", 1),
        (user_map["100000000002"], "No 5, Adyar, Chennai", "600020", "9123456789", 1),
        (user_map["100000000003"], "No 2, Bandra, Mumbai", "400050", "9988776655", 0),
        (user_map["100000000004"], "No 8, Salt Lake, Kolkata", "700091", "9090909090", 1),
    ]
    conn.executemany(
        """
        INSERT INTO address (user_id, user_address, pin_number, mobile_number, mobile_verified)
        VALUES (?, ?, ?, ?, ?)
        """,
        addresses,
    )


def insert_dummy_accounts(conn: sqlite3.Connection) -> None:
    """Inserts account details with varying balances to test FD logic."""
    users = conn.execute("SELECT user_id, account_number FROM users").fetchall()
    
    # Fetch emails to populate the accounts table
    user_emails = {row[0]: row[1] for row in conn.execute("SELECT user_id, email FROM users").fetchall()}
    
    accounts_data = [
        # Amit has plenty of money
        (users[0][0], users[0][1], "Savings", 500000.0, user_emails[users[0][0]]), 
        # Neha has moderate money
        (users[1][0], users[1][1], "Savings", 150000.0, user_emails[users[1][0]]), 
        # Ravi has low balance (likely insufficient for large FDs)
        (users[2][0], users[2][1], "Current", 10000.0, user_emails[users[2][0]]),   
        # Pooja is inactive user
        (users[3][0], users[3][1], "Savings", 200000.0, user_emails[users[3][0]]), 
    ]
    
    conn.executemany(
        """
        INSERT INTO accounts (user_id, account_number, account_type, balance, email)
        VALUES (?, ?, ?, ?, ?)
        """,
        accounts_data,
    )


def insert_dummy_kyc(conn: sqlite3.Connection) -> None:
    rows = conn.execute(
        """
        SELECT u.user_id, u.account_number, a.address_id, a.pin_number, a.mobile_number, a.mobile_verified
        FROM users u
        JOIN address a ON a.user_id = u.user_id
        ORDER BY u.user_id
        """
    ).fetchall()

    docs_by_user = {
        1: {"pan_number": "ABCDE1234F", "aadhaar_number": None},
        2: {"pan_number": None, "aadhaar_number": "123456789012"},
        3: {"pan_number": "BADPAN123", "aadhaar_number": None},
        4: {"pan_number": "PQRSX9876Z", "aadhaar_number": None},
    }

    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
    inserts = []
    for user_id, account_number, address_id, pin_number, mobile_number, mobile_verified in rows:
        doc_data = docs_by_user[user_id]
        payload = {
            "user_id": user_id,
            "account_number": account_number,
            "address_id": address_id,
            "pan_number": doc_data["pan_number"],
            "aadhaar_number": doc_data["aadhaar_number"],
            "pin_number": pin_number,
            "mobile_number": mobile_number,
            "mobile_verified": bool(mobile_verified),
        }
        status, _, parsed = evaluate_kyc_status(payload)
        verified_at = now if status == "VERIFIED" else None

        inserts.append(
            (
                user_id,
                address_id,
                account_number,
                parsed.pan_number if parsed else doc_data["pan_number"],
                parsed.aadhaar_number if parsed else doc_data["aadhaar_number"],
                status,
                verified_at,
                now,
                now,
            )
        )

    conn.executemany(
        """
        INSERT INTO kyc_verification (
            user_id, address_id, account_number, pan_number, aadhaar_number,
            kyc_status, verified_at, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        inserts,
    )


def insert_fd_for_verified_users(conn: sqlite3.Connection) -> None:
    eligible_users = conn.execute(
        """
        SELECT u.user_id
        FROM users u
        JOIN address a ON a.user_id = u.user_id
        JOIN kyc_verification k ON k.user_id = u.user_id
        WHERE u.is_account_active = 1
          AND a.mobile_verified = 1
          AND k.kyc_status = 'VERIFIED'
        ORDER BY u.user_id
        """
    ).fetchall()

    fd_rows = []
    dummy_banks = ["HDFC Bank", "ICICI Bank", "State Bank of India", "Axis Bank"]
    
    for index, (user_id,) in enumerate(eligible_users, start=1):
        maturity = (datetime.now(UTC) + timedelta(days=365 * index)).strftime("%Y-%m-%d")
        bank = dummy_banks[(index - 1) % len(dummy_banks)]
        amount = 100000.0 + (index * 25000.0) 
        
        fd_rows.append(
            (
                user_id,
                amount,           
                bank,             
                12 * index,        
                6.75 + (0.1 * index), 
                maturity,          
                1.00,              
                "ACTIVE",          
            )
        )

    if fd_rows:
        conn.executemany(
            """
            INSERT INTO fixed_deposit (
                user_id, initial_amount, bank_name, tenure_months, interest_rate, 
                maturity_date, premature_penalty_percent, fd_status
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            fd_rows,
        )


def main() -> None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("PRAGMA foreign_keys = ON;")
        reset_and_create_schema(conn)
        insert_dummy_users(conn)
        insert_dummy_addresses(conn)
        insert_dummy_accounts(conn) # New call
        insert_dummy_kyc(conn)
        insert_fd_for_verified_users(conn)
        conn.commit()

        users_count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        accounts_count = conn.execute("SELECT COUNT(*) FROM accounts").fetchone()[0] # New metric
        fd_count = conn.execute("SELECT COUNT(*) FROM fixed_deposit").fetchone()[0]

    print(f"Seeded DB: {DB_PATH}")
    print(f"users={users_count}, accounts={accounts_count}, fd={fd_count}")


if __name__ == "__main__":
    main()