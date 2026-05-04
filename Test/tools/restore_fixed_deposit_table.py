#!/usr/bin/env python
"""
Restore the fixed_deposit table with the correct schema.
This script recreates the table that was accidentally deleted.
"""

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "bank_poc.db"


def restore_fixed_deposit_table():
    """Restore the fixed_deposit table with correct schema."""
    print(f"Connecting to database: {DB_PATH}")
    
    if not DB_PATH.exists():
        print(f"Error: Database file not found at {DB_PATH}")
        return False
    
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        
        # Check if table already exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='fixed_deposit'")
        if cursor.fetchone():
            print("Table fixed_deposit already exists. Nothing to restore.")
            return True
        
        # Create the fixed_deposit table with correct schema
        cursor.execute("""
        CREATE TABLE fixed_deposit (
            fd_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER REFERENCES users(user_id) ON DELETE CASCADE,
            product_type TEXT NOT NULL DEFAULT 'FD',
            initial_amount REAL NOT NULL,
            monthly_installment REAL,
            bank_name TEXT NOT NULL,
            tenure_months INTEGER NOT NULL,
            interest_rate REAL NOT NULL,
            compounding_freq TEXT NOT NULL DEFAULT 'quarterly',
            maturity_date TEXT,
            premature_penalty_percent REAL NOT NULL DEFAULT 1.0,
            fd_status TEXT NOT NULL DEFAULT 'ACTIVE',
            account_number TEXT,
            region TEXT NOT NULL DEFAULT 'IN',
            user_session_id TEXT,
            customer_name TEXT,
            customer_email TEXT,
            customer_phone TEXT,
            start_date TEXT,
            maturity_amount REAL DEFAULT 0,
            interest_earned REAL DEFAULT 0,
            senior_citizen INTEGER NOT NULL DEFAULT 0,
            loan_against_fd INTEGER NOT NULL DEFAULT 0,
            auto_renewal INTEGER NOT NULL DEFAULT 0,
            certificate_path TEXT,
            certificate_generated INTEGER NOT NULL DEFAULT 0,
            email_sent INTEGER NOT NULL DEFAULT 0,
            email_sent_at TEXT,
            confirmed_at TEXT,
            risk_score INTEGER,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """)
        
        print("Table fixed_deposit created successfully.")
        
        # Verify the table was created
        cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='fixed_deposit'")
        schema = cursor.fetchone()[0]
        print("\nCreated schema:")
        print(schema)
        
        conn.commit()
        return True


if __name__ == "__main__":
    success = restore_fixed_deposit_table()
    if success:
        print("\n" + "="*60)
        print("TABLE RESTORED SUCCESSFULLY")
        print("="*60)
    else:
        print("\nFailed to restore table!")
