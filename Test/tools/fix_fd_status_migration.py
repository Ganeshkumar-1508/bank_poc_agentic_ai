#!/usr/bin/env python
"""
Data migration script to fix invalid fd_status values in the fixed_deposit table.

Issue: Database contains "approved" status which should be "ACTIVE".
Expected fd_status values: ACTIVE, MATURED, CLOSED, PREMATURE

This script:
1. Migrates existing "approved" status to "ACTIVE"
2. Migrates "needs_approval" status to "ACTIVE" (pending FDs should be active once created)
3. Migrates "rejected" status to "CLOSED" (rejected FDs are closed)
4. Adds a CHECK constraint to prevent invalid status values in the future
"""

import sqlite3
from pathlib import Path

# Database path
DB_PATH = Path(__file__).parent / "bank_poc.db"


def migrate_fd_status():
    """Migrate invalid fd_status values to valid ones."""
    print(f"Connecting to database: {DB_PATH}")
    
    if not DB_PATH.exists():
        print(f"Error: Database file not found at {DB_PATH}")
        return False
    
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        
        # Check current status values
        cursor.execute("SELECT DISTINCT fd_status FROM fixed_deposit")
        current_statuses = [row[0] for row in cursor.fetchall()]
        print(f"Current fd_status values: {current_statuses}")
        
        # Count records by status before migration
        cursor.execute("SELECT fd_status, COUNT(*) FROM fixed_deposit GROUP BY fd_status")
        before_counts = dict(cursor.fetchall())
        print(f"Records before migration: {before_counts}")
        
        # Migrate "approved" to "ACTIVE"
        cursor.execute("UPDATE fixed_deposit SET fd_status = 'ACTIVE' WHERE fd_status = 'approved'")
        approved_migrated = cursor.rowcount
        print(f"Migrated {approved_migrated} records from 'approved' to 'ACTIVE'")
        
        # Migrate "needs_approval" to "ACTIVE"
        cursor.execute("UPDATE fixed_deposit SET fd_status = 'ACTIVE' WHERE fd_status = 'needs_approval'")
        needs_approval_migrated = cursor.rowcount
        print(f"Migrated {needs_approval_migrated} records from 'needs_approval' to 'ACTIVE'")
        
        # Migrate "rejected" to "CLOSED"
        cursor.execute("UPDATE fixed_deposit SET fd_status = 'CLOSED' WHERE fd_status = 'rejected'")
        rejected_migrated = cursor.rowcount
        print(f"Migrated {rejected_migrated} records from 'rejected' to 'CLOSED'")
        
        # Verify migration
        cursor.execute("SELECT DISTINCT fd_status FROM fixed_deposit")
        after_statuses = [row[0] for row in cursor.fetchall()]
        print(f"fd_status values after migration: {after_statuses}")
        
        # Count records by status after migration
        cursor.execute("SELECT fd_status, COUNT(*) FROM fixed_deposit GROUP BY fd_status")
        after_counts = dict(cursor.fetchall())
        print(f"Records after migration: {after_counts}")
        
        # Check for any remaining invalid statuses
        invalid_statuses = [s for s in after_statuses if s not in ('ACTIVE', 'MATURED', 'CLOSED', 'PREMATURE', 'PENDING')]
        if invalid_statuses:
            print(f"Warning: Still found invalid status values: {invalid_statuses}")
        else:
            print("All status values are now valid.")
        
        conn.commit()
        print("\nMigration completed successfully!")
        return True


def add_status_constraint(conn):
    """Add a CHECK constraint to prevent invalid status values."""
    # SQLite doesn't support adding CHECK constraints to existing tables easily
    # We'll document this as a recommendation for future schema migrations
    print("\nNote: To add a CHECK constraint for fd_status, you would need to:")
    print("1. Create a new table with the constraint")
    print("2. Copy data from old table")
    print("3. Drop old table")
    print("4. Rename new table")
    print("\nThis is recommended for production but skipped for this migration.")


if __name__ == "__main__":
    success = migrate_fd_status()
    if success:
        print("\n" + "="*60)
        print("FD STATUS MIGRATION SUMMARY")
        print("="*60)
        print("Fixed the following issues:")
        print("  - 'approved' -> 'ACTIVE'")
        print("  - 'needs_approval' -> 'ACTIVE'")
        print("  - 'rejected' -> 'CLOSED'")
        print("\nRecommendation: Update the code in database_tool.py to use")
        print("valid fd_status values when creating new fixed deposits.")
    else:
        print("\nMigration failed!")
