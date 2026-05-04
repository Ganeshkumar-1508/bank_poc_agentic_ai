"""
Database utility functions for direct SQLite access to legacy bank_poc.db.
This module bypasses Django ORM and provides direct SQL access to the legacy database.
"""
import sqlite3
import logging
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

logger = logging.getLogger(__name__)

# Path to the legacy database
LEGACY_DB_PATH = Path(__file__).parent.parent / "tools" / "bank_poc.db"

# Mapping of legacy table names to their primary key columns
TABLE_PRIMARY_KEYS = {
    'loan_applications': 'application_id',
    'loan_disbursements': 'disbursement_id',
    'users': 'user_id',
    'address': 'address_id',
    'kyc_verification': 'kyc_id',
    'accounts': 'account_id',
    'fixed_deposit': 'fd_id',
    'transactions': 'txn_id',
    'aml_cases': 'case_id',
    'compliance_audit_log': 'log_id',
    'interest_rates_catalog': 'rate_id',
}


@contextmanager
def get_legacy_connection():
    """
    Context manager for getting a connection to the legacy SQLite database.
    
    Usage:
        with get_legacy_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM loan_applications")
            rows = cursor.fetchall()
    """
    conn = None
    try:
        conn = sqlite3.connect(str(LEGACY_DB_PATH))
        conn.row_factory = sqlite3.Row  # Enable column access by name
        logger.debug(f"Connected to legacy database: {LEGACY_DB_PATH}")
        yield conn
    except sqlite3.Error as e:
        logger.error(f"Database connection error: {e}")
        raise
    finally:
        if conn:
            conn.close()
            logger.debug("Database connection closed")


def dictfetchall(cursor: sqlite3.Cursor) -> List[Dict[str, Any]]:
    """
    Fetch all rows from a cursor as a list of dictionaries.
    
    Args:
        cursor: SQLite cursor object
        
    Returns:
        List of dictionaries where keys are column names
    """
    columns = [col[0] for col in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def dictfetchone(cursor: sqlite3.Cursor) -> Optional[Dict[str, Any]]:
    """
    Fetch one row from a cursor as a dictionary.
    
    Args:
        cursor: SQLite cursor object
        
    Returns:
        Dictionary with column names as keys, or None if no row
    """
    row = cursor.fetchone()
    if row:
        columns = [col[0] for col in cursor.description]
        return dict(zip(columns, row))
    return None


# =============================================================================
# COUNT OPERATIONS
# =============================================================================

def count_records(table_name: str, where_clause: str = "", params: Tuple = ()) -> int:
    """
    Count records in a table.
    
    Args:
        table_name: Name of the table
        where_clause: Optional WHERE clause (without 'WHERE' keyword)
        params: Parameters for the query
        
    Returns:
        Count of records
    """
    query = f"SELECT COUNT(*) as count FROM {table_name}"
    if where_clause and where_clause.strip():
        query += f" WHERE {where_clause}"
    
    with get_legacy_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(query, params)
        result = cursor.fetchone()
        return result[0] if result else 0


# =============================================================================
# READ OPERATIONS
# =============================================================================

def get_all_records(
    table_name: str,
    where_clause: str = "",
    params: Tuple = (),
    columns: str = "*",
    order_by: str = "",
    limit: int = 0,
    offset: int = 0
) -> List[Dict[str, Any]]:
    """
    Get all records from a table.
    
    Args:
        table_name: Name of the table
        where_clause: Optional WHERE clause (without 'WHERE' keyword)
        params: Parameters for the query
        columns: Columns to select (default: *)
        order_by: Optional ORDER BY clause
        limit: Optional limit (0 = no limit)
        offset: Optional offset for pagination
        
    Returns:
        List of dictionaries representing rows
    """
    query = f"SELECT {columns} FROM {table_name}"
    if where_clause and where_clause.strip():
        query += f" WHERE {where_clause}"
    if order_by:
        query += f" ORDER BY {order_by}"
    if limit > 0:
        query += f" LIMIT {limit}"
        if offset > 0:
            query += f" OFFSET {offset}"
    
    with get_legacy_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(query, params)
        return dictfetchall(cursor)


def get_record_by_id(table_name: str, record_id: Union[int, str]) -> Optional[Dict[str, Any]]:
    """
    Get a single record by its primary key.
    
    Args:
        table_name: Name of the table
        record_id: Primary key value
        
    Returns:
        Dictionary representing the row, or None if not found
    """
    if record_id is None:
        return None
    
    pk_column = TABLE_PRIMARY_KEYS.get(table_name, 'id')
    query = f"SELECT * FROM {table_name} WHERE {pk_column} = ?"
    
    with get_legacy_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(query, (int(record_id),))
        return dictfetchone(cursor)


def get_records_by_ids(
    table_name: str,
    ids: List[Union[int, str]],
    columns: str = "*"
) -> List[Dict[str, Any]]:
    """
    Get multiple records by their primary keys.
    
    Args:
        table_name: Name of the table
        ids: List of primary key values
        columns: Columns to select
        
    Returns:
        List of dictionaries representing rows
    """
    if not ids:
        return []
    
    pk_column = TABLE_PRIMARY_KEYS.get(table_name, 'id')
    placeholders = ','.join(['?' for _ in ids])
    query = f"SELECT {columns} FROM {table_name} WHERE {pk_column} IN ({placeholders})"
    
    with get_legacy_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(query, ids)
        return dictfetchall(cursor)


# =============================================================================
# CREATE OPERATIONS
# =============================================================================

def create_record(
    table_name: str,
    data: Dict[str, Any],
    return_columns: str = "*"
) -> Optional[Dict[str, Any]]:
    """
    Create a new record in a table.
    
    Args:
        table_name: Name of the table
        data: Dictionary of column names and values
        return_columns: Columns to return after insert
        
    Returns:
        Dictionary representing the created row, or None on failure
    """
    columns = ', '.join(data.keys())
    placeholders = ', '.join(['?' for _ in data])
    query = f"INSERT INTO {table_name} ({columns}) VALUES ({placeholders})"
    
    with get_legacy_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(query, list(data.values()))
        conn.commit()
        
        # Get the inserted record
        pk_column = TABLE_PRIMARY_KEYS.get(table_name, 'id')
        last_id = cursor.lastrowid
        if last_id:
            return get_record_by_id(table_name, last_id)
        return None


# =============================================================================
# UPDATE OPERATIONS
# =============================================================================

def update_record(
    table_name: str,
    record_id: Union[int, str],
    data: Dict[str, Any]
) -> bool:
    """
    Update a record by its primary key.
    
    Args:
        table_name: Name of the table
        record_id: Primary key value
        data: Dictionary of column names and values to update
        
    Returns:
        True if update was successful, False otherwise
    """
    pk_column = TABLE_PRIMARY_KEYS.get(table_name, 'id')
    set_clause = ', '.join([f"{col} = ?" for col in data.keys()])
    query = f"UPDATE {table_name} SET {set_clause} WHERE {pk_column} = ?"
    
    with get_legacy_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(query, list(data.values()) + [record_id])
        conn.commit()
        return cursor.rowcount > 0


def update_records_where(
    table_name: str,
    data: Dict[str, Any],
    where_clause: str,
    params: Tuple = ()
) -> int:
    """
    Update multiple records matching a condition.
    
    Args:
        table_name: Name of the table
        data: Dictionary of column names and values to update
        where_clause: WHERE clause (without 'WHERE' keyword)
        params: Parameters for the WHERE clause
        
    Returns:
        Number of rows updated
    """
    set_clause = ', '.join([f"{col} = ?" for col in data.keys()])
    query = f"UPDATE {table_name} SET {set_clause}"
    if where_clause:
        query += f" WHERE {where_clause}"
    
    with get_legacy_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(query, list(data.values()) + list(params))
        conn.commit()
        return cursor.rowcount


# =============================================================================
# DELETE OPERATIONS
# =============================================================================

def delete_record(table_name: str, record_id: Union[int, str]) -> bool:
    """
    Delete a record by its primary key.
    
    Args:
        table_name: Name of the table
        record_id: Primary key value
        
    Returns:
        True if deletion was successful, False otherwise
    """
    pk_column = TABLE_PRIMARY_KEYS.get(table_name, 'id')
    query = f"DELETE FROM {table_name} WHERE {pk_column} = ?"
    
    with get_legacy_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(query, (record_id,))
        conn.commit()
        return cursor.rowcount > 0


def delete_records_where(
    table_name: str,
    where_clause: str,
    params: Tuple = ()
) -> int:
    """
    Delete multiple records matching a condition.
    
    Args:
        table_name: Name of the table
        where_clause: WHERE clause (without 'WHERE' keyword)
        params: Parameters for the query
        
    Returns:
        Number of rows deleted
    """
    query = f"DELETE FROM {table_name}"
    if where_clause:
        query += f" WHERE {where_clause}"
    
    with get_legacy_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(query, params)
        conn.commit()
        return cursor.rowcount


# =============================================================================
# EXECUTE RAW SQL
# =============================================================================

def execute_raw_sql(
    query: str,
    params: Tuple = (),
    fetch: str = "all"
) -> Union[List[Dict[str, Any]], Dict[str, Any], int]:
    """
    Execute a raw SQL query.
    
    Args:
        query: SQL query string
        params: Parameters for the query
        fetch: "all", "one", "count", or "none"
        
    Returns:
        Query results based on fetch parameter
    """
    with get_legacy_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(query, params)
        
        if fetch == "none":
            conn.commit()
            return cursor.rowcount
        elif fetch == "one":
            return dictfetchone(cursor)
        elif fetch == "count":
            result = cursor.fetchone()
            return result[0] if result else 0
        else:  # "all"
            return dictfetchall(cursor)


# =============================================================================
# HELPER FUNCTIONS FOR SPECIFIC TABLES
# =============================================================================

def get_loan_applications(
    status: str = "",
    limit: int = 0,
    offset: int = 0
) -> List[Dict[str, Any]]:
    """Get loan applications with optional status filter."""
    where = ""
    params = ()
    if status:
        where = "loan_decision = ?"
        params = (status,)
    return get_all_records(
        'loan_applications',
        where_clause=where,
        params=params,
        order_by='created_at DESC',
        limit=limit,
        offset=offset
    )


def get_fixed_deposits(
    user_id: int = 0,
    status: str = "",
    limit: int = 0
) -> List[Dict[str, Any]]:
    """Get fixed deposits with optional filters."""
    where = ""
    params = ()
    if user_id:
        where = "user_id = ?"
        params = (user_id,)
    elif status:
        where = "fd_status = ?"
        params = (status,)
    return get_all_records(
        'fixed_deposit',
        where_clause=where,
        params=params,
        order_by='created_at DESC',
        limit=limit
    )


def get_users(
    search: str = "",
    country_code: str = "",
    limit: int = 0
) -> List[Dict[str, Any]]:
    """Get users with optional search and filter."""
    where = ""
    params = ()
    
    conditions = []
    if search:
        conditions.append("(first_name LIKE ? OR last_name LIKE ? OR email LIKE ?)")
        search_param = f"%{search}%"
        params = params + (search_param, search_param, search_param)
    
    if country_code:
        conditions.append("country_code = ?")
        params = params + (country_code,)
    
    if conditions:
        where = " AND ".join(conditions)
    
    return get_all_records(
        'users',
        where_clause=where,
        params=params,
        order_by='created_at DESC',
        limit=limit
    )


def get_transactions(
    user_id: int = 0,
    account_id: int = 0,
    txn_type: str = "",
    limit: int = 0
) -> List[Dict[str, Any]]:
    """Get transactions with optional filters."""
    where = ""
    params = ()
    
    conditions = []
    if user_id:
        conditions.append("user_id = ?")
        params = params + (user_id,)
    if account_id:
        conditions.append("account_id = ?")
        params = params + (account_id,)
    if txn_type:
        conditions.append("txn_type = ?")
        params = params + (txn_type,)
    
    if conditions:
        where = " AND ".join(conditions)
    
    return get_all_records(
        'transactions',
        where_clause=where,
        params=params,
        order_by='txn_date DESC',
        limit=limit
    )


def get_table_counts() -> Dict[str, int]:
    """
    Get counts for all legacy tables.
    
    Returns:
        Dictionary mapping table names to their record counts
    """
    tables = list(TABLE_PRIMARY_KEYS.keys())
    counts = {}
    for table in tables:
        counts[table] = count_records(table)
    return counts
