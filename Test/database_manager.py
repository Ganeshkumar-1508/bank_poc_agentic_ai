import sqlite3
import os

DB_NAME = "fd_advisor_users.db"

def init_db():
    """Initialize the SQLite database with the user schema."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_profiles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT,
            name TEXT,
            dob TEXT,
            address TEXT,
            pan TEXT,
            phone TEXT,
            email TEXT,
            account_number TEXT,
            aml_status TEXT,
            aml_details TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

def save_user_data(session_id: str, user_data: dict, aml_result: dict = None):
    """Save or update user data and AML results."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # Check if session exists
    cursor.execute("SELECT id FROM user_profiles WHERE session_id = ?", (session_id,))
    exists = cursor.fetchone()

    aml_status = aml_result.get('status', 'Pending') if aml_result else 'Pending'
    aml_details = str(aml_result) if aml_result else None

    data_tuple = (
        user_data.get('name'),
        user_data.get('dob'),
        user_data.get('address'),
        user_data.get('pan'),
        user_data.get('phone'),
        user_data.get('email'),
        user_data.get('account_number'),
        aml_status,
        aml_details,
        session_id
    )

    if exists:
        cursor.execute('''
            UPDATE user_profiles 
            SET name=?, dob=?, address=?, pan=?, phone=?, email=?, account_number=?, 
                aml_status=?, aml_details=?
            WHERE session_id=?
        ''', data_tuple)
    else:
        cursor.execute('''
            INSERT INTO user_profiles 
            (name, dob, address, pan, phone, email, account_number, aml_status, aml_details, session_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', data_tuple)
    
    conn.commit()
    conn.close()
    print(f"[DB] Data saved for session: {session_id}")

# Initialize DB on import
init_db()