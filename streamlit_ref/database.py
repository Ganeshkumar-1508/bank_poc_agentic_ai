# database.py  —  Database Helper Functions for Fixed Deposit Advisor
import sqlite3
import json
import pandas as pd
import streamlit as st
from datetime import datetime, timedelta
from pathlib import Path

from .config import DB_PATH


# =============================================================================
# DB HELPERS
# =============================================================================
def get_db_connection():
    if not DB_PATH.exists():
        return None
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def db_query(sql: str, params=()) -> pd.DataFrame:
    conn = get_db_connection()
    if conn is None:
        return pd.DataFrame()
    try:
        df = pd.read_sql_query(sql, conn, params=params)
        return df
    except Exception:
        return pd.DataFrame()
    finally:
        conn.close()


def db_execute(sql: str, params=()):
    conn = get_db_connection()
    if conn is None:
        return None
    try:
        with conn:
            cur = conn.execute(sql, params)
            return cur.lastrowid
    except Exception as e:
        st.error(f"DB error: {e}")
        return None
    finally:
        conn.close()


# =============================================================================
# LOAN APPLICATION FUNCTIONS
# =============================================================================
def _ensure_loan_tables_exist():
    """Auto-create loan_applications & loan_disbursements tables if missing.
    This is a safety net in case create_db.py was not re-run after schema update.
    """
    conn = get_db_connection()
    if conn is None:
        return False
    try:
        # Check if loan_applications table exists
        table_check = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='loan_applications'"
        ).fetchone()
        if not table_check:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS loan_applications (
                    application_id    INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id           INTEGER,
                    applicant_email   TEXT    NOT NULL,
                    loan_amnt         REAL    NOT NULL,
                    term              INTEGER NOT NULL,
                    int_rate          REAL,
                    purpose           TEXT,
                    annual_inc        REAL,
                    fico_score        INTEGER,
                    dti               REAL,
                    home_ownership    TEXT,
                    default_prob      REAL,
                    implied_grade     TEXT,
                    risk_level        TEXT,
                    loan_decision     TEXT    NOT NULL DEFAULT 'NEEDS_VERIFY',
                    decision_rationale TEXT,
                    conditions        TEXT,
                    next_steps        TEXT,
                    notification_sent INTEGER NOT NULL DEFAULT 0,
                    created_at        TEXT    NOT NULL DEFAULT (datetime('now')),
                    updated_at        TEXT    NOT NULL DEFAULT (datetime('now'))
                );
                CREATE TABLE IF NOT EXISTS loan_disbursements (
                    disbursement_id   INTEGER PRIMARY KEY AUTOINCREMENT,
                    application_id    INTEGER NOT NULL,
                    user_id           INTEGER,
                    account_id        INTEGER,
                    sanctioned_amount REAL    NOT NULL,
                    disbursement_status TEXT   NOT NULL DEFAULT 'PENDING',
                    disbursed_at      TEXT,
                    remarks           TEXT,
                    created_at        TEXT    NOT NULL DEFAULT (datetime('now'))
                );
            """
            )
            conn.commit()
        return True
    except Exception as e:
        st.error(f"DB table creation failed: {e}")
        return False
    finally:
        conn.close()


def save_loan_application(
    applicant_email: str,
    borrower: dict,
    result: dict,
    loan_decision: str,
    rationale: str,
    conditions: list,
    next_steps: list,
    user_id: int = None,
) -> int:
    """Save loan application with 3-condition logic:
    Condition 1 (LOAN_APPROVED): Insert into loan_applications + loan_disbursements.
    Condition 2 (NEEDS_VERIFY):  Insert into loan_applications only (review needed).
    Condition 3 (REJECTED):      Insert into loan_applications only (rejected).
    """
    # Safety net: ensure tables exist before inserting
    if not _ensure_loan_tables_exist():
        return None

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Use direct connection for better error visibility
    conn = get_db_connection()
    if conn is None:
        st.error("❌ Database not found. Run `python create_db.py` first.")
        return None

    try:
        cur = conn.execute(
            """INSERT INTO loan_applications
               (user_id, applicant_email, loan_amnt, term, int_rate, purpose,
                annual_inc, fico_score, dti, home_ownership,
                default_prob, implied_grade, risk_level,
                loan_decision, decision_rationale, conditions, next_steps,
                notification_sent, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)""",
            (
                user_id,
                applicant_email,
                borrower.get("loan_amnt", 0),
                borrower.get("term", 0),
                borrower.get("int_rate", 0),
                borrower.get("purpose", ""),
                borrower.get("annual_inc", 0),
                borrower.get("fico_score", 0),
                borrower.get("dti", 0),
                borrower.get("home_ownership", ""),
                result.get("default_probability", 0),
                result.get("implied_grade", ""),
                result.get("risk_level", ""),
                loan_decision,
                rationale,
                (
                    json.dumps(conditions)
                    if isinstance(conditions, list)
                    else str(conditions)
                ),
                (
                    json.dumps(next_steps)
                    if isinstance(next_steps, list)
                    else str(next_steps)
                ),
                now,
                now,
            ),
        )
        conn.commit()
        app_id = cur.lastrowid

        # Create disbursement record for ALL decisions with status based on risk model
        if app_id:
            _disb_status = {
                "LOAN_APPROVED": "APPROVE_DISBURSEMENT",
                "NEEDS_VERIFY": "PENDING_VERIFICATION",
                "REJECTED": "CANCELLED",
            }.get(loan_decision, "PENDING")
            _disb_remarks = {
                "LOAN_APPROVED": "Auto-approved by credit risk model — awaiting disbursement",
                "NEEDS_VERIFY": "Flagged by credit risk model — additional verification required",
                "REJECTED": "Auto-rejected by credit risk model",
            }.get(loan_decision, "")
            conn.execute(
                """INSERT INTO loan_disbursements
                   (application_id, user_id, sanctioned_amount, disbursement_status, remarks, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    app_id,
                    user_id,
                    borrower.get("loan_amnt", 0),
                    _disb_status,
                    _disb_remarks,
                    now,
                ),
            )
            conn.commit()

        return app_id
    except Exception as e:
        st.error(f"❌ Failed to save loan application: {e}")
        return None
    finally:
        conn.close()


def get_loan_applications(
    user_id: int = None, loan_decision: str = None
) -> pd.DataFrame:
    """Fetch loan applications with optional filters. Returns newest-first."""
    conn = get_db_connection()
    if conn is None:
        return pd.DataFrame()
    try:
        conditions = []
        params = []
        if user_id:
            conditions.append("la.user_id = ?")
            params.append(user_id)
        if loan_decision:
            conditions.append("la.loan_decision = ?")
            params.append(loan_decision)
        where = " WHERE " + " AND ".join(conditions) if conditions else ""
        df = pd.read_sql_query(
            f"""SELECT la.*, u.first_name, u.last_name, u.email AS user_email
                FROM loan_applications la
                LEFT JOIN users u ON la.user_id = u.user_id
                {where}
                ORDER BY la.created_at DESC""",
            conn,
            params=tuple(params) if params else (),
        )
        return df
    except Exception as e:
        st.error(f"DB query error: {e}")
        return pd.DataFrame()
    finally:
        conn.close()


def update_loan_status(
    application_id: int,
    new_decision: str,
    rationale: str = None,
    reviewer_notes: str = None,
) -> bool:
    """Update loan_decision to LOAN_APPROVED, NEEDS_VERIFY, or REJECTED.

    Updates BOTH loan_applications and loan_disbursements tables:
      - LOAN_APPROVED:  set disbursement_status = 'APPROVE_DISBURSEMENT'
      - NEEDS_VERIFY:   set disbursement_status = 'PENDING_VERIFICATION'
      - REJECTED:       set disbursement_status = 'CANCELLED'
    Creates a disbursement record if one does not exist yet.
    """
    if new_decision not in ("LOAN_APPROVED", "NEEDS_VERIFY", "REJECTED"):
        st.error(f"Invalid decision: {new_decision}")
        return False
    conn = get_db_connection()
    if conn is None:
        st.error("Database not found.")
        return False
    try:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Build reviewer rationale
        _rationale = rationale
        if reviewer_notes and not _rationale:
            _rationale = reviewer_notes
        elif reviewer_notes and _rationale:
            _rationale = f"{_rationale}\n\n[Reviewer] {reviewer_notes}"

        # 1. Update the loan_decision in loan_applications
        conn.execute(
            """UPDATE loan_applications
               SET loan_decision = ?,
                   decision_rationale = COALESCE(?, decision_rationale),
                   updated_at = ?
               WHERE application_id = ?""",
            (new_decision, _rationale, now, application_id),
        )
        conn.commit()

        # 2. Map decision to disbursement status and remarks
        _disb_map = {
            "LOAN_APPROVED": {
                "status": "APPROVE_DISBURSEMENT",
                "remarks": "Loan approved — awaiting disbursement",
            },
            "NEEDS_VERIFY": {
                "status": "PENDING_VERIFICATION",
                "remarks": "Loan flagged — additional verification required",
            },
            "REJECTED": {
                "status": "CANCELLED",
                "remarks": "Loan rejected",
            },
        }
        _disb_info = _disb_map[new_decision]

        # 3. Check if a disbursement record already exists
        existing = conn.execute(
            "SELECT disbursement_id, disbursement_status FROM loan_disbursements WHERE application_id = ?",
            (application_id,),
        ).fetchone()

        if existing:
            # Update existing disbursement status for all 3 categories
            # Skip updating if already DISBURSED (irreversible terminal state)
            if existing[1] != "DISBURSED":
                conn.execute(
                    """UPDATE loan_disbursements
                       SET disbursement_status = ?,
                           remarks = COALESCE(?, remarks),
                           disbursed_at = CASE WHEN ? = 'CANCELLED' OR ? = 'PENDING_VERIFICATION' THEN NULL ELSE disbursed_at END
                       WHERE application_id = ?""",
                    (
                        _disb_info["status"],
                        _disb_info["remarks"],
                        new_decision,
                        new_decision,
                        application_id,
                    ),
                )
                conn.commit()
        else:
            # Create a new disbursement record
            app = conn.execute(
                "SELECT user_id, loan_amnt FROM loan_applications WHERE application_id = ?",
                (application_id,),
            ).fetchone()
            if app:
                conn.execute(
                    """INSERT INTO loan_disbursements
                       (application_id, user_id, sanctioned_amount, disbursement_status, remarks, created_at)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (
                        application_id,
                        app[0],
                        app[1],
                        _disb_info["status"],
                        _disb_info["remarks"],
                        now,
                    ),
                )
                conn.commit()

        return True
    except Exception as e:
        st.error(f"❌ Failed to update loan status: {e}")
        return False
    finally:
        conn.close()


# =============================================================================
# USER SESSION FUNCTIONS
# =============================================================================
def upsert_user_session(display_name: str, email: str, country_code: str) -> dict:
    conn = get_db_connection()
    if conn is None:
        return {}
    try:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn.execute(
            """INSERT INTO user_sessions (display_name, email, country_code, created_at, last_seen)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(email) DO UPDATE SET
                 display_name=excluded.display_name,
                 country_code=excluded.country_code,
                 last_seen=excluded.last_seen""",
            (display_name, email, country_code, now, now),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM user_sessions WHERE email=?", (email,)
        ).fetchone()
        return dict(row) if row else {}
    finally:
        conn.close()


def get_linked_user(email: str) -> dict:
    """Return users row matching email, or {}."""
    conn = get_db_connection()
    if conn is None:
        return {}
    try:
        row = conn.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
        return dict(row) if row else {}
    finally:
        conn.close()


# =============================================================================
# PORTFOLIO FUNCTIONS
# =============================================================================
def get_all_deposits(user_id: int = None) -> pd.DataFrame:
    if user_id:
        return db_query(
            """SELECT fd.*, u.first_name||' '||u.last_name AS customer_name, u.email
               FROM fixed_deposit fd JOIN users u ON fd.user_id=u.user_id
               WHERE fd.user_id=? ORDER BY fd.created_at DESC""",
            (user_id,),
        )
    return db_query(
        """SELECT fd.*, u.first_name||' '||u.last_name AS customer_name, u.email
           FROM fixed_deposit fd JOIN users u ON fd.user_id=u.user_id
           ORDER BY fd.created_at DESC"""
    )


def get_portfolio_summary(user_id: int = None) -> dict:
    df = get_all_deposits(user_id)
    if df.empty:
        return {}
    active = df[df["fd_status"] == "ACTIVE"]
    total_invested = active["initial_amount"].sum()
    total_deposits = len(df)
    active_count = len(active)
    # next maturity
    next_mat = None
    if not active.empty and "maturity_date" in active.columns:
        valid_mat = active["maturity_date"].dropna()
        if not valid_mat.empty:
            next_mat = valid_mat.sort_values().iloc[0]
    return {
        "total_invested": total_invested,
        "total_deposits": total_deposits,
        "active_count": active_count,
        "next_maturity": next_mat,
    }


# =============================================================================
# AML FUNCTIONS
# =============================================================================
def get_all_aml_cases() -> pd.DataFrame:
    return db_query(
        """SELECT ac.*, u.first_name||' '||u.last_name AS customer_name, u.email
           FROM aml_cases ac JOIN users u ON ac.user_id=u.user_id
           ORDER BY ac.created_at DESC"""
    )


def get_aml_case(user_id: int) -> dict:
    conn = get_db_connection()
    if conn is None:
        return {}
    try:
        row = conn.execute(
            "SELECT * FROM aml_cases WHERE user_id=? ORDER BY created_at DESC LIMIT 1",
            (user_id,),
        ).fetchone()
        return dict(row) if row else {}
    finally:
        conn.close()


def save_aml_case(
    user_id: int,
    risk_score: int,
    risk_band: str,
    decision: str,
    report_markdown: str = "",
    sanctions_hit: int = 0,
    pep_flag: int = 0,
    adverse_media: int = 0,
    notes: str = "",
    ubo_findings: str = "",
) -> int:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return db_execute(
        """INSERT INTO aml_cases
           (user_id, risk_score, risk_band, decision, screened_by,
            report_markdown, sanctions_hit, pep_flag, adverse_media,
            ubo_findings, notes, created_at, updated_at)
           VALUES (?, ?, ?, ?, 'Chief Risk Officer (AI)', ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            user_id,
            risk_score,
            risk_band,
            decision,
            report_markdown,
            sanctions_hit,
            pep_flag,
            adverse_media,
            ubo_findings,
            notes,
            now,
            now,
        ),
    )


def log_audit(
    user_id: int, case_id, event_type: str, detail: str, performed_by: str = "System"
):
    db_execute(
        """INSERT INTO compliance_audit_log
           (user_id, case_id, event_type, event_detail, performed_by, logged_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (
            user_id,
            case_id,
            event_type,
            detail,
            performed_by,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        ),
    )


# =============================================================================
# TRANSACTIONS
# =============================================================================
def get_transactions(
    user_id: int = None, txn_type: str = None, days_back: int = 365
) -> pd.DataFrame:
    since = (datetime.now() - timedelta(days=days_back)).strftime("%Y-%m-%d")
    conditions = ["t.txn_date >= ?"]
    params: list = [since]
    if user_id:
        conditions.append("t.user_id = ?")
        params.append(user_id)
    if txn_type and txn_type != "ALL":
        conditions.append("t.txn_type = ?")
        params.append(txn_type)
    where = " AND ".join(conditions)
    return db_query(
        f"""SELECT t.*, u.first_name||' '||u.last_name AS customer_name
            FROM transactions t JOIN users u ON t.user_id=u.user_id
            WHERE {where} ORDER BY t.txn_date DESC""",
        tuple(params),
    )


# =============================================================================
# RATE ALERTS
# =============================================================================
def save_rate_alert(
    user_id, bank: str, product_type: str, min_rate: float, email: str
) -> int:
    return db_execute(
        """INSERT INTO rate_alerts
           (user_id, bank_name, product_type, min_rate, email, is_active, created_at)
           VALUES (?, ?, ?, ?, ?, 1, ?)""",
        (
            user_id,
            bank,
            product_type,
            min_rate,
            email,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        ),
    )


def get_rate_alerts(user_id=None) -> pd.DataFrame:
    if user_id:
        return db_query(
            "SELECT * FROM rate_alerts WHERE user_id=? ORDER BY created_at DESC",
            (user_id,),
        )
    return db_query("SELECT * FROM rate_alerts ORDER BY created_at DESC")


def toggle_alert(alert_id: int, active: int):
    db_execute(
        "UPDATE rate_alerts SET is_active=? WHERE alert_id=?", (active, alert_id)
    )


# =============================================================================
# INTEREST RATES CATALOG
# =============================================================================
def get_catalog_rates(country_code: str = None) -> pd.DataFrame:
    if country_code:
        return db_query(
            """SELECT * FROM interest_rates_catalog
               WHERE country_code=? AND is_active=1
               ORDER BY bank_name, product_type, tenure_min_months""",
            (country_code,),
        )
    return db_query(
        "SELECT * FROM interest_rates_catalog WHERE is_active=1 ORDER BY bank_name"
    )


# =============================================================================
# SESSION ARTIFACTS (PDF blobs)
# =============================================================================
def get_session_artifacts() -> pd.DataFrame:
    """
    Returns all rows from session_artifacts ordered newest-first.
    Columns: artifact_id, filename, file_blob, created_at.
    Returns an empty DataFrame if the table does not yet exist.
    """
    conn = get_db_connection()
    if conn is None:
        return pd.DataFrame()
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS session_artifacts (
                artifact_id  INTEGER PRIMARY KEY AUTOINCREMENT,
                filename     TEXT    NOT NULL,
                file_blob    BLOB    NOT NULL,
                created_at   TEXT    DEFAULT (datetime('now'))
            )
        """
        )
        conn.commit()
        df = pd.read_sql_query(
            "SELECT artifact_id, filename, file_blob, created_at "
            "FROM session_artifacts ORDER BY artifact_id DESC",
            conn,
        )
        return df
    except Exception:
        return pd.DataFrame()
    finally:
        conn.close()


def save_laddering_plan(
    user_id,
    total_amount: float,
    plan: list,
    total_maturity: float,
    total_interest: float,
) -> int:
    return db_execute(
        """INSERT INTO fd_laddering_plans
           (user_id, total_amount, plan_json, total_maturity, total_interest, created_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (
            user_id,
            total_amount,
            json.dumps(plan),
            total_maturity,
            total_interest,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        ),
    )


def get_laddering_plans(user_id) -> pd.DataFrame:
    return db_query(
        "SELECT * FROM fd_laddering_plans WHERE user_id=? ORDER BY created_at DESC",
        (user_id,),
    )


# =============================================================================
# FD TABLE LOADER
# =============================================================================
def load_fd_table() -> pd.DataFrame:
    if not DB_PATH.exists():
        return pd.DataFrame()
    try:
        with sqlite3.connect(DB_PATH) as conn:
            return pd.read_sql_query(
                "SELECT * FROM fixed_deposit ORDER BY fd_id DESC LIMIT 20", conn
            )
    except Exception:
        return pd.DataFrame()
