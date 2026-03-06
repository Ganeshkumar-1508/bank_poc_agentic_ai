PRAGMA foreign_keys = OFF;

    DROP TABLE IF EXISTS fixed_deposit;
    DROP TABLE IF EXISTS accounts;
    DROP TABLE IF EXISTS kyc_verification;
    DROP TABLE IF EXISTS address;
    DROP TABLE IF EXISTS users;

PRAGMA foreign_keys = ON;

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