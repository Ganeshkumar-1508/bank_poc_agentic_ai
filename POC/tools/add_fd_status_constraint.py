#!/usr/bin/env python
"""
Add CHECK constraint to fixed_deposit table to prevent invalid fd_status values.

This script:
1. Creates a new table with the CHECK constraint
2. Copies data from the old table
3. Drops the old table
4. Renames the new table

Valid fd_status values: ACTIVE, MATURED, CLOSED, PREMATURE
"""

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "bank_poc.db"


def add_fd_status_constraint():
    """Add CHECK constraint to fixed_deposit table."""
    print(f"Connecting to database: {DB_PATH}")
    
    if not DB_PATH.exists():
        print(f"Error: Database file not found at {DB_PATH}")
        return False
    
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        
        # Check if constraint already exists
        cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='fixed_deposit'")
        schema = cursor.fetchone()[0]
        if "CHECK" in schema and "fd_status" in schema:
            print("CHECK constraint already exists on fixed_deposit table.")
            return True
        
        print("Creating new table with CHECK constraint...")
        
        # Get all data from old table
        cursor.execute("SELECT * FROM fixed_deposit")
        columns = [desc[0] for desc in cursor.description]
        old_data = cursor.fetchall()
        
        # Create new table with CHECK constraint
        new_table_sql = """
        CREATE TABLE fixed_deposit_new (
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
            fd_status TEXT NOT NULL DEFAULT 'ACTIVE' CHECK(fd_status IN ('ACTIVE', 'MATURED', 'CLOSED', 'PREMATURE')),
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
        """
        cursor.execute(new_table_sql)
        print("New table created with CHECK constraint.")
        
        # Copy data to new table
        placeholders = ", ".join(["?" for _ in columns])
        insert_sql = f"INSERT INTO fixed_deposit_new ({', '.join(columns)}) VALUES ({placeholders})"
        cursor.executemany(insert_sql, old_data)
        print(f"Copied {len(old_data)} records to new table.")
        
        # Drop old table and rename new table
        cursor.execute("DROP TABLE fixed_deposit")
        cursor.execute("ALTER TABLE fixed_deposit_new RENAME TO fixed_deposit")
        print("Old table dropped, new table renamed to 'fixed_deposit'.")
        
        # Note: sqlite_sequence is automatically managed by SQLite for AUTOINCREMENT
        
        conn.commit()
        print("\nCHECK constraint added successfully!")
        
        # Verify the constraint
        cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='fixed_deposit'")
        new_schema = cursor.fetchone()[0]
        print("\nNew schema:")
        print(new_schema)
        
        return True


if __name__ == "__main__":
    success = add_fd_status_constraint()
    if success:
        print("\n" + "="*60)
        print("DATABASE CONSTRAINT ADDED")
        print("="*60)
        print("The fixed_deposit table now has a CHECK constraint that")
        print("prevents invalid fd_status values from being inserted.")
        print("\nValid values: ACTIVE, MATURED, CLOSED, PREMATURE")
    else:
        print("\nFailed to add constraint!")
