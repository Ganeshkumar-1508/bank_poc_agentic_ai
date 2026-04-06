# new_app.py  —  Fixed Deposit Advisor (Full-featured)
import os
import re
import sqlite3
import json
import plotly.graph_objects as go
import numpy as np
import math
from tools.credit_risk_tool import (
    _load_model, _engineer_features, _probability_to_grade,
    _compute_installment, MODEL_DIR,
)
import random
import smtplib
import requests
import pandas as pd
import matplotlib
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import io
import streamlit as st
from pathlib import Path
from dotenv import load_dotenv
from streamlit_echarts import st_echarts, JsCode
from datetime import datetime, timedelta, date
from crews import run_crew, FixedDepositCrews
from tools import set_search_region, fetch_country_data
from langchain_nvidia_ai_endpoints import ChatNVIDIA
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

matplotlib.use("Agg")

def extract_json_balanced(text: str):

    import json as _json
    import re as _re

    # Strip markdown fences
    text = _re.sub(r"```[a-z]*", "", text).strip()

    for start_char, end_char in [("[", "]"), ("{", "}")]:
        start = text.find(start_char)
        if start == -1:
            continue
        depth = 0
        in_string = False
        escape_next = False
        for i, ch in enumerate(text[start:], start):
            if escape_next:
                escape_next = False
                continue
            if ch == "\\" and in_string:
                escape_next = True
                continue
            if ch == '"' and not escape_next:
                in_string = not in_string
                continue
            if in_string:
                continue
            if ch == start_char:
                depth += 1
            elif ch == end_char:
                depth -= 1
                if depth == 0:
                    return _json.loads(text[start : i + 1])
    raise ValueError("No valid JSON object or array found in text.")

# =============================================================================
# LANGFUSE INTEGRATION
# =============================================================================
try:
    from langfuse_instrumentation import instrument_crewai, get_langfuse_client
    from langfuse import propagate_attributes
    from langfuse_evaluator import evaluate_crew_output_async
except ImportError as _import_err:
    st.error(
        f"Missing dependency: {_import_err}. "
        "Ensure langfuse_instrumentation.py, langfuse_evaluator.py, and the "
        "'langfuse' / 'langchain' packages are installed."
    )
    st.stop()

load_dotenv()
instrument_crewai()
langfuse = get_langfuse_client()

# =============================================================================
# DATABASE & CONFIG
# =============================================================================
DB_PATH = Path(__file__).resolve().parent / "bank_poc.db"

RISK_COLORS = {
    "LOW":      ("#D1FAE5", "#065F46"),
    "MEDIUM":   ("#FEF3C7", "#92400E"),
    "HIGH":     ("#FEE2E2", "#991B1B"),
    "CRITICAL": ("#7F1D1D", "#FECACA"),
}
DECISION_COLORS = {
    "PASS":   ("#D1FAE5", "#065F46"),
    "FAIL":   ("#FEE2E2", "#991B1B"),
    "REVIEW": ("#FEF3C7", "#92400E"),
    "APPROVE":("#D1FAE5", "#065F46"),
    "REJECT": ("#FEE2E2", "#991B1B"),
}

LOAN_DECISION_CONFIG = {
    "LOAN_APPROVED": {
        "bg": "#DCFCE7", "fg": "#166534", "border": "#22C55E",
        "icon": "✅", "label": "LOAN APPROVED", "badge_bg": "#16A34A",
        "banner_bg": "#F0FDF4", "banner_border": "#86EFAC",
    },
    "NEEDS_VERIFY": {
        "bg": "#FEF9C3", "fg": "#854D0E", "border": "#EAB308",
        "icon": "⚠️", "label": "NEEDS VERIFICATION & APPROVAL", "badge_bg": "#CA8A04",
        "banner_bg": "#FFFBEB", "banner_border": "#FDE68A",
    },
    "REJECTED": {
        "bg": "#FEE2E2", "fg": "#991B1B", "border": "#EF4444",
        "icon": "❌", "label": "LOAN REJECTED", "badge_bg": "#DC2626",
        "banner_bg": "#FEF2F2", "banner_border": "#FECACA",
    },
}

def classify_loan_decision(implied_grade: str, default_probability: float) -> str:
    """Classify loan into 3 categories based on ML model output."""
    grade = implied_grade.upper() if implied_grade else "E"
    if grade in ("A", "B"):
        return "LOAN_APPROVED"
    elif grade in ("C", "D", "E"):
        return "NEEDS_VERIFY"
    else:  # F, G or unknown
        return "REJECTED"


def _parse_llm_decision(llm_text: str) -> dict:
    """Parse LLM-generated loan decision text into structured dict."""
    if not llm_text:
        return {}
    parsed = {}
    keys = ["DECISION", "GRADE", "DEFAULT_PROBABILITY", "RISK_LEVEL", "RATIONALE", "CONDITIONS", "NEXT_STEPS"]
    lines = llm_text.strip().split("\n")
    current_key = None
    current_value = []
    for line in lines:
        found_key = None
        for key in keys:
            if line.upper().startswith(f"{key}:"):
                if current_key:
                    parsed[current_key] = "\n".join(current_value).strip()
                found_key = key
                current_key = key
                current_value = [line.split(":", 1)[1].strip()]
                break
        if found_key is None and current_key:
            current_value.append(line.strip())
    if current_key:
        parsed[current_key] = "\n".join(current_value).strip()
    return parsed

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


# ---------- user sessions ----------
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
        row = conn.execute(
            "SELECT * FROM users WHERE email=?", (email,)
        ).fetchone()
        return dict(row) if row else {}
    finally:
        conn.close()


# ---------- portfolio ----------
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


# ---------- AML ----------
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


def save_aml_case(user_id: int, risk_score: int, risk_band: str, decision: str,
                  report_markdown: str = "", sanctions_hit: int = 0,
                  pep_flag: int = 0, adverse_media: int = 0, notes: str = "",
                  ubo_findings: str = "") -> int:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return db_execute(
        """INSERT INTO aml_cases
           (user_id, risk_score, risk_band, decision, screened_by,
            report_markdown, sanctions_hit, pep_flag, adverse_media,
            ubo_findings, notes, created_at, updated_at)
           VALUES (?, ?, ?, ?, 'Chief Risk Officer (AI)', ?, ?, ?, ?, ?, ?, ?, ?)""",
        (user_id, risk_score, risk_band, decision, report_markdown,
         sanctions_hit, pep_flag, adverse_media, ubo_findings, notes, now, now),
    )


def log_audit(user_id: int, case_id, event_type: str, detail: str, performed_by: str = "System"):
    db_execute(
        """INSERT INTO compliance_audit_log
           (user_id, case_id, event_type, event_detail, performed_by, logged_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (user_id, case_id, event_type, detail, performed_by,
         datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
    )


# ---------- loan applications ----------
def init_loan_applications_table():
    """Create loan_applications and loan_disbursements tables if they don't exist."""
    db_execute("""
        CREATE TABLE IF NOT EXISTS loan_applications (
            application_id   INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id          INTEGER,
            applicant_email  TEXT    NOT NULL,
            loan_amnt        REAL    NOT NULL,
            term             INTEGER NOT NULL,
            int_rate         REAL,
            purpose          TEXT,
            annual_inc       REAL,
            fico_score       INTEGER,
            dti              REAL,
            home_ownership   TEXT,
            default_prob     REAL,
            implied_grade    TEXT,
            risk_level       TEXT,
            loan_decision    TEXT    NOT NULL DEFAULT 'NEEDS_VERIFY',
            decision_rationale TEXT,
            conditions       TEXT,
            next_steps       TEXT,
            notification_sent  INTEGER DEFAULT 0,
            created_at       TEXT DEFAULT (datetime('now')),
            updated_at       TEXT DEFAULT (datetime('now'))
        )
    """)
    db_execute("""
        CREATE TABLE IF NOT EXISTS loan_disbursements (
            disbursement_id     INTEGER PRIMARY KEY AUTOINCREMENT,
            application_id      INTEGER NOT NULL REFERENCES loan_applications(application_id),
            user_id             INTEGER,
            account_id          INTEGER,
            sanctioned_amount   REAL    NOT NULL,
            disbursement_status TEXT    NOT NULL DEFAULT 'PENDING',
            disbursed_at        TEXT,
            remarks             TEXT,
            created_at          TEXT DEFAULT (datetime('now'))
        )
    """)


def save_loan_application(applicant_email: str, borrower_data: dict, cr_result: dict,
                          loan_decision: str, rationale: str, conditions: str,
                          next_steps: str, notification_sent: int = 0) -> int:
    """
    Save loan application to DB with 3-condition logic:

    Condition 1 (LOAN_APPROVED):  Insert application + create disbursement record
                                  with sanctioned_amount = loan_amnt (PENDING status).
    Condition 2 (NEEDS_VERIFY):    Insert application as review/verification required.
    Condition 3 (REJECTED):         Insert application as rejected.
    """
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    linked_user = get_linked_user(applicant_email)
    user_id = linked_user.get("user_id") if linked_user else None

    app_id = db_execute(
        """INSERT INTO loan_applications
           (user_id, applicant_email, loan_amnt, term, int_rate, purpose,
            annual_inc, fico_score, dti, home_ownership,
            default_prob, implied_grade, risk_level,
            loan_decision, decision_rationale, conditions, next_steps,
            notification_sent, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (user_id, applicant_email,
         borrower_data.get("loan_amnt", 0), borrower_data.get("term", 0),
         borrower_data.get("int_rate"), borrower_data.get("purpose"),
         borrower_data.get("annual_inc"), borrower_data.get("fico_score"),
         borrower_data.get("dti"), borrower_data.get("home_ownership"),
         cr_result.get("default_probability", 0),
         cr_result.get("implied_grade", "N/A"),
         cr_result.get("risk_level", "UNKNOWN"),
         loan_decision, rationale, conditions, next_steps,
         notification_sent, now, now),
    )

    # Condition 1: LOAN_APPROVED → create disbursement record
    if loan_decision == "LOAN_APPROVED" and app_id:
        db_execute(
            """INSERT INTO loan_disbursements
               (application_id, user_id, sanctioned_amount, disbursement_status, remarks, created_at)
               VALUES (?, ?, ?, 'PENDING', ?, ?)""",
            (app_id, user_id, borrower_data.get("loan_amnt", 0),
             f"Auto-approved via ML risk model. Grade: {cr_result.get('implied_grade', 'N/A')}", now),
        )

    return app_id


def get_loan_applications(email: str = None) -> pd.DataFrame:
    if email:
        return db_query(
            "SELECT * FROM loan_applications WHERE applicant_email=? ORDER BY created_at DESC",
            (email,),
        )
    return db_query("SELECT * FROM loan_applications ORDER BY created_at DESC")


def get_loan_disbursements(application_id: int = None) -> pd.DataFrame:
    if application_id:
        return db_query(
            "SELECT * FROM loan_disbursements WHERE application_id=? ORDER BY created_at DESC",
            (application_id,),
        )
    return db_query("SELECT * FROM loan_disbursements ORDER BY created_at DESC")


# ---------- transactions ----------
def get_transactions(user_id: int = None, txn_type: str = None,
                     days_back: int = 365) -> pd.DataFrame:
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
        f"""SELECT t.*, u.first_name||' '||u.last_name AS customer_name,
                   fd.bank_name, fd.product_type
            FROM transactions t
            JOIN users u ON t.user_id=u.user_id
            LEFT JOIN fixed_deposit fd ON t.fd_id=fd.fd_id
            WHERE {where}
            ORDER BY t.txn_date DESC""",
        tuple(params),
    )


# ---------- rate alerts ----------
def save_rate_alert(user_id, bank: str, product_type: str,
                    min_rate: float, email: str) -> int:
    return db_execute(
        """INSERT INTO rate_alerts
           (user_id, bank_name, product_type, min_rate, email, is_active, created_at)
           VALUES (?, ?, ?, ?, ?, 1, ?)""",
        (user_id, bank, product_type, min_rate, email,
         datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
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


# ---------- interest rates catalog ----------
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


# ---------- session artifacts (PDF blobs) ----------
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
        conn.execute("""
            CREATE TABLE IF NOT EXISTS session_artifacts (
                artifact_id  INTEGER PRIMARY KEY AUTOINCREMENT,
                filename     TEXT    NOT NULL,
                file_blob    BLOB    NOT NULL,
                created_at   TEXT    DEFAULT (datetime('now'))
            )
        """)
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



def save_laddering_plan(user_id, total_amount: float, plan: list,
                         total_maturity: float, total_interest: float) -> int:
    return db_execute(
        """INSERT INTO fd_laddering_plans
           (user_id, total_amount, plan_json, total_maturity, total_interest, created_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (user_id, total_amount, json.dumps(plan), total_maturity, total_interest,
         datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
    )


def get_laddering_plans(user_id) -> pd.DataFrame:
    return db_query(
        "SELECT * FROM fd_laddering_plans WHERE user_id=? ORDER BY created_at DESC",
        (user_id,),
    )


# =============================================================================
# FINANCIAL CALCULATORS
# =============================================================================
def calc_compound(principal: float, annual_rate: float, tenure_months: int,
                  compounding: str = "quarterly") -> dict:
    n_map = {"monthly": 12, "quarterly": 4, "half_yearly": 2, "yearly": 1}
    n = n_map.get(compounding, 4)
    t = tenure_months / 12.0
    maturity = principal * (1 + annual_rate / 100 / n) ** (n * t)
    return {
        "maturity": round(maturity, 2),
        "interest": round(maturity - principal, 2),
    }


def calc_premature_withdrawal(principal: float, annual_rate: float,
                               tenure_months: int, elapsed_months: int,
                               penalty_pct: float, compounding: str = "quarterly") -> dict:
    elapsed_months = min(elapsed_months, tenure_months)
    n_map = {"monthly": 12, "quarterly": 4, "half_yearly": 2, "yearly": 1}
    n = n_map.get(compounding, 4)
    t = elapsed_months / 12.0
    maturity_val = principal * (1 + annual_rate / 100 / n) ** (n * t)
    interest_earned = maturity_val - principal
    penalty = interest_earned * penalty_pct / 100
    payout = maturity_val - penalty
    t_full = tenure_months / 12.0
    full_mat = principal * (1 + annual_rate / 100 / n) ** (n * t_full)
    return {
        "principal": principal,
        "interest_earned": round(interest_earned, 2),
        "penalty": round(penalty, 2),
        "payout": round(payout, 2),
        "full_maturity": round(full_mat, 2),
        "foregone": round(full_mat - payout, 2),
        "effective_annual_rate": round((payout - principal) / principal * 100 / t, 2) if t > 0 else 0,
    }


def calc_fd_ladder(total_amount: float, tranches: list) -> list:
    results = []
    for tr in tranches:
        amt = total_amount * tr["fraction"]
        res = calc_compound(amt, tr["rate"], tr["tenure_months"], tr.get("compounding", "quarterly"))
        results.append({
            "bank": tr["bank"],
            "fraction_pct": round(tr["fraction"] * 100, 1),
            "amount": round(amt, 2),
            "tenure_months": tr["tenure_months"],
            "rate": tr["rate"],
            "maturity": res["maturity"],
            "interest": res["interest"],
        })
    return results


def inflation_adjusted_return(nominal_balance: float, principal: float,
                               inflation_rate: float, years: float) -> dict:
    real_balance = nominal_balance / ((1 + inflation_rate / 100) ** years)
    real_return_pct = (real_balance - principal) / principal * 100
    return {"real_balance": round(real_balance, 2), "real_return_pct": round(real_return_pct, 2)}


# =============================================================================
# EMAIL DIGEST
# =============================================================================
def send_digest_email(recipient: str, maturing_df: pd.DataFrame) -> bool:
    smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER", "")
    smtp_pass = os.getenv("SMTP_PASSWORD", "")
    if not smtp_user or not smtp_pass:
        return False
    rows = ""
    for _, r in maturing_df.iterrows():
        rows += (
            f"<tr><td>{r.get('bank_name','')}</td>"
            f"<td>{r.get('product_type','')}</td>"
            f"<td>{r.get('initial_amount', 0):,.0f}</td>"
            f"<td>{r.get('maturity_date','')}</td></tr>"
        )
    html = f"""<html><body>
    <h2>📅 FD Maturity Digest — Next 30 Days</h2>
    <table border='1' cellpadding='6' style='border-collapse:collapse'>
    <tr><th>Bank</th><th>Type</th><th>Amount</th><th>Maturity Date</th></tr>
    {rows}
    </table>
    <p>Sent by Fixed Deposit Advisor</p></body></html>"""
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = "Your FD Maturity Digest — Next 30 Days"
        msg["From"] = smtp_user
        msg["To"] = recipient
        msg.attach(MIMEText(html, "html"))
        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.sendmail(smtp_user, recipient, msg.as_string())
        return True
    except Exception:
        return False


def send_loan_decision_email(recipient: str, loan_decision: str, grade: str,
                              prob_pct: str, risk_level: str, rationale: str,
                              conditions: list, next_steps: list,
                              borrower_data: dict) -> bool:
    """Send loan decision notification email to the borrower."""
    smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER", "")
    smtp_pass = os.getenv("SMTP_PASSWORD", "")
    if not smtp_user or not smtp_pass or not recipient:
        return False

    # Color and icon per decision
    decision_config = {
        "LOAN_APPROVED": {"icon": "✅", "title": "APPROVED", "color": "#166534", "bg": "#DCFCE7"},
        "NEEDS_VERIFY":  {"icon": "⚠️", "title": "VERIFICATION REQUIRED", "color": "#854D0E", "bg": "#FEF9C3"},
        "REJECTED":      {"icon": "❌", "title": "NOT APPROVED", "color": "#991B1B", "bg": "#FEE2E2"},
    }
    cfg = decision_config.get(loan_decision, decision_config["NEEDS_VERIFY"])

    conditions_html = "".join(f"<li>{c}</li>" for c in conditions) if conditions else "<li>None</li>"
    next_steps_html = "".join(f"<li>{s}</li>" for s in next_steps) if next_steps else "<li>None</li>"

    loan_amount = borrower_data.get("loan_amnt", 0)
    loan_term = borrower_data.get("term", 0)
    loan_purpose = borrower_data.get("purpose", "N/A").replace("_", " ").title()

    html = f"""<html><body style="font-family: Arial, sans-serif; color: #333;">
    <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
        <div style="background: #1E3A8A; color: white; padding: 20px; border-radius: 8px 8px 0 0;">
            <h1 style="margin: 0;">Loan Application Decision</h1>
        </div>
        <div style="background: {cfg['bg']}; padding: 20px; border-left: 4px solid {cfg['color']};">
            <h2 style="color: {cfg['color']}; margin: 0;">{cfg['icon']} Your Loan Application Has Been {cfg['title']}</h2>
        </div>
        <div style="background: #F8FAFC; padding: 20px; border: 1px solid #E2E8F0;">
            <h3 style="color: #1E3A8A;">Application Details</h3>
            <table style="width: 100%; border-collapse: collapse;">
                <tr><td style="padding: 8px; border-bottom: 1px solid #E2E8F0;"><strong>Loan Amount:</strong></td>
                    <td style="padding: 8px; border-bottom: 1px solid #E2E8F0;">${loan_amount:,.0f}</td></tr>
                <tr><td style="padding: 8px; border-bottom: 1px solid #E2E8F0;"><strong>Term:</strong></td>
                    <td style="padding: 8px; border-bottom: 1px solid #E2E8F0;">{loan_term} months</td></tr>
                <tr><td style="padding: 8px; border-bottom: 1px solid #E2E8F0;"><strong>Purpose:</strong></td>
                    <td style="padding: 8px; border-bottom: 1px solid #E2E8F0;">{loan_purpose}</td></tr>
                <tr><td style="padding: 8px; border-bottom: 1px solid #E2E8F0;"><strong>Risk Grade:</strong></td>
                    <td style="padding: 8px; border-bottom: 1px solid #E2E8F0;">{grade} ({risk_level})</td></tr>
                <tr><td style="padding: 8px;"><strong>Default Probability:</strong></td>
                    <td style="padding: 8px;">{prob_pct}</td></tr>
            </table>
        </div>
        <div style="padding: 20px; border: 1px solid #E2E8F0; border-top: none;">
            <h3 style="color: #1E3A8A;">Decision Rationale</h3>
            <p>{rationale}</p>
            <h3 style="color: #1E3A8A;">Conditions</h3>
            <ul>{conditions_html}</ul>
            <h3 style="color: #1E3A8A;">Next Steps</h3>
            <ul>{next_steps_html}</ul>
        </div>
        <div style="background: #F1F5F9; padding: 15px; border-radius: 0 0 8px 8px; font-size: 12px; color: #64748B; text-align: center;">
            <p>This decision was generated by our AI-powered credit risk assessment system using an XGBoost model trained on US Lending Club data (2007-2018).</p>
            <p>For questions, please contact your loan officer or reply to this email.</p>
        </div>
    </div>
    </body></html>"""

    subject_map = {
        "LOAN_APPROVED": f"✅ Your Loan Application Has Been APPROVED — ${loan_amount:,.0f}",
        "NEEDS_VERIFY":  f"⚠️ Action Required — Additional Verification Needed for Your Loan Application",
        "REJECTED":      f"Update on Your Loan Application — Reference #{datetime.now().strftime('%Y%m%d%H%M')}",
    }

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject_map.get(loan_decision, "Loan Application Decision")
        msg["From"] = smtp_user
        msg["To"] = recipient
        msg.attach(MIMEText(html, "html"))
        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.sendmail(smtp_user, recipient, msg.as_string())
        return True
    except Exception:
        return False


# =============================================================================
# GEOLOCATION & REGION
# =============================================================================
def detect_user_region() -> dict:
    countries = fetch_country_data()
    try:
        resp = requests.get("https://ipinfo.io/json", timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            cc = data.get("country", "WW").upper()
            info = countries.get(cc, {})
            ddg = set_search_region(cc)
            return {
                "country_code": cc,
                "country_name": info.get("name", cc),
                "ddg_region": ddg,
                "currency_symbol": info.get("currency_symbol", ""),
                "currency_code": info.get("currency_code", ""),
            }
    except Exception:
        pass
    return {
        "country_code": "WW", "country_name": "Worldwide",
        "ddg_region": "wt-wt", "currency_symbol": "", "currency_code": "",
    }


if "user_region" not in st.session_state:
    st.session_state.user_region = detect_user_region()
else:
    set_search_region(st.session_state.user_region["country_code"])

if "langfuse_session_id" not in st.session_state:
    st.session_state.langfuse_session_id = (
        f"fd-session-{st.session_state.user_region.get('country_code','WW')}-{os.urandom(4).hex()}"
    )
if "langfuse_user_id" not in st.session_state:
    st.session_state.langfuse_user_id = st.session_state.langfuse_session_id

# logged_in_user: {session_id, display_name, email, country_code} or None
if "logged_in_user" not in st.session_state:
    st.session_state.logged_in_user = None

# Initialize loan applications table on startup
init_loan_applications_table()

# =============================================================================
# PAGE CONFIG
# =============================================================================
st.set_page_config(
    page_title="Fixed Deposit Advisor",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
.main-header{font-size:2.2rem!important;color:#1E3A8A;margin-bottom:.5rem}
.sub-header{font-size:1.3rem;color:#3B82F6;margin-top:1rem;margin-bottom:.4rem}
.badge{display:inline-block;border-radius:4px;padding:3px 10px;font-size:.82rem;font-weight:600;margin:2px}
.metric-card{background:#F8FAFC;border:1px solid #E2E8F0;border-radius:8px;padding:1rem;text-align:center}
</style>
""", unsafe_allow_html=True)

st.markdown('<h1 class="main-header">Fixed Deposit Advisor</h1>', unsafe_allow_html=True)

# =============================================================================
# SESSION STATE INIT
# =============================================================================
for key, val in [
    ("messages", []),
    ("last_analysis_data", None),
    ("last_tenure_months", 12),
]:
    if key not in st.session_state:
        st.session_state[key] = val


def get_currency_symbol() -> str:
    return st.session_state.get("user_region", {}).get("currency_symbol", "")


def reset_session():
    for k in ["messages", "last_analysis_data", "last_tenure_months",
              "ONBOARDING_FLOW", "PENDING_AML_JSON",
              "langfuse_session_id", "langfuse_user_id"]:
        if k in st.session_state:
            del st.session_state[k]
    st.rerun()


# =============================================================================
# LANGFUSE WRAPPER
# =============================================================================
def run_crew_with_langfuse(crew_callable, crew_name, user_input="",
                            region="Worldwide", extra_metadata=None):
    session_id = st.session_state.get("langfuse_session_id")
    user_id = st.session_state.get("langfuse_user_id")
    metadata = {"region": region, "crew_name": crew_name, "streamlit_session": "active"}
    if extra_metadata:
        metadata.update(extra_metadata)
    output_text = None
    trace_id = None
    with langfuse.start_as_current_observation(
        as_type="trace", name=crew_name,
        input={"user_input": user_input}, metadata=metadata,
    ) as trace:
        trace.update(session_id=session_id, user_id=user_id)
        trace_id = getattr(trace, "trace_id", None) or getattr(trace, "id", None)
        with propagate_attributes(session_id=session_id, user_id=user_id):
            result = crew_callable()
            if hasattr(result, "raw"):
                output_text = result.raw
            elif isinstance(result, str):
                output_text = result
            if output_text:
                trace.update(output={"output": output_text[:2000]})
    langfuse.flush()
    evaluate_crew_output_async(
        langfuse_client=langfuse,
        trace_id=trace_id,
        crew_name=crew_name,
        user_input=user_input,
        output_text=output_text or "",
    )
    return result


# =============================================================================
# CACHED HELPERS
# =============================================================================
@st.cache_data(ttl=3600)
def get_dynamic_kyc_docs(country_name: str) -> tuple:
    if not os.getenv("NVIDIA_API_KEY"):
        return ("Government-issued Photo ID", "Proof of Address")
    llm = ChatNVIDIA(model="meta/llama-3.1-8b-instruct")

    def _parse_docs(text):
        text = text.strip()
        for fence in ("```json", "```"):
            if fence in text:
                text = text.split(fence)[1].split("```")[0].strip()
                break
        import re as _re
        match = _re.search(r'\[.*?\]', text, _re.DOTALL)
        if match:
            text = match.group(0)
        try:
            docs = json.loads(text)
            if isinstance(docs, list) and len(docs) >= 2:
                d1, d2 = str(docs[0]).strip(), str(docs[1]).strip()
                generic = {"national id card", "proof of address",
                           "government-issued photo id", "passport"}
                if d1.lower() not in generic or d2.lower() not in generic:
                    return (d1, d2)
        except (json.JSONDecodeError, ValueError):
            pass
        return None

    try:
        prompt = (
            f"What are the TWO primary mandatory government-issued identity documents that banks "
            f"in '{country_name}' require for KYC?\n"
            f"Return ONLY a raw JSON array with exactly two strings. Example: [\"Aadhaar Card\", \"PAN Card\"]"
        )
        response = llm.invoke(prompt)
        result = _parse_docs(response.content)
        if result:
            return result
    except Exception:
        pass
    return ("Government-issued Photo ID", "Proof of Address")


@st.cache_resource
def get_crews():
    return FixedDepositCrews()


def clean_response(raw: str) -> str:
    text = raw.strip()
    for prefix in ("QUESTION:", "DATA_READY:"):
        if text.startswith(prefix):
            text = text[len(prefix):].strip()
            break
    return text


def append_assistant(text: str, chart_options=None):
    msg = {"role": "assistant", "content": text}
    if chart_options:
        msg["chart_options"] = chart_options
    st.session_state.messages.append(msg)


# =============================================================================
# PARSE & RENDER HELPERS
# =============================================================================
def parse_projection_table(text: str) -> pd.DataFrame:
    try:
        clean = text.replace("```csv", " ").replace("```", " ").strip()
        lines = clean.splitlines()
        header_idx = next(
            (i for i, l in enumerate(lines) if "Provider" in l and "Rate" in l), 0
        )
        clean = "\n".join(lines[header_idx:])
        df = pd.read_csv(io.StringIO(clean))
        df.columns = [c.strip() for c in df.columns]
        required = {"Provider", "General Rate (%)", "Senior Rate (%)",
                    "General Maturity", "Senior Maturity", "General Interest", "Senior Interest"}
        if not required.issubset(df.columns):
            return pd.DataFrame()
        numeric_cols = list(required - {"Provider"})
        for col in numeric_cols:
            df[col] = pd.to_numeric(
                df[col].astype(str).str.replace(",", "").str.replace("N/A", "").str.strip(),
                errors="coerce",
            )
        df = df.dropna(subset=numeric_cols, how="all").reset_index(drop=True)
        return df
    except Exception:
        return pd.DataFrame()


def render_bar_charts(df: pd.DataFrame):
    numeric_cols = ["General Maturity", "Senior Maturity", "General Interest", "Senior Interest"]
    df = df.dropna(subset=numeric_cols).head(10).copy()
    if df.empty:
        st.warning("No projection data available to chart.")
        return
    sym = get_currency_symbol()
    providers_list = df["Provider"].tolist()
    axis_fmt = JsCode(f"function(v){{return '{sym}'+(v/1000).toFixed(0)+'K';}}")
    tooltip_fn = JsCode(
        f"function(params){{var s=params[0].axisValue+'<br/>';"
        f"params.forEach(function(p){{s+=p.marker+p.seriesName+': {sym}'"
        f"+p.value.toLocaleString(undefined,{{maximumFractionDigits:0}})+'<br/>';}});"
        f"return s;}}"
    )
    st.markdown("### Maturity & Interest Breakdown")
    col1, col2 = st.columns(2)
    for col, label, mat_col, int_col, mat_color, int_color, key in [
        (col1, "General", "General Maturity", "General Interest", "#3B82F6", "#93C5FD", "ec_general"),
        (col2, "Senior Citizen", "Senior Maturity", "Senior Interest", "#EF4444", "#FCA5A5", "ec_senior"),
    ]:
        with col:
            st.markdown(f"#### {label}")
            st_echarts(options={
                "tooltip": {"trigger": "axis", "axisPointer": {"type": "shadow"}, "formatter": tooltip_fn},
                "legend": {"data": ["Maturity Amount", "Interest Earned"], "bottom": 0},
                "grid": {"left": "3%", "right": "4%", "bottom": "15%", "containLabel": True},
                "xAxis": {"type": "category", "data": providers_list,
                          "axisLabel": {"rotate": 35, "interval": 0, "fontSize": 10}},
                "yAxis": {"type": "value", "name": f"Amount ({sym})" if sym else "Amount",
                          "axisLabel": {"formatter": axis_fmt}},
                "series": [
                    {"name": "Maturity Amount", "type": "bar", "data": df[mat_col].round(0).tolist(),
                     "itemStyle": {"color": mat_color}},
                    {"name": "Interest Earned", "type": "bar", "data": df[int_col].round(0).tolist(),
                     "itemStyle": {"color": int_color}},
                ],
            }, height="380px", key=key)


def export_analysis_data():
    if st.session_state.get("last_analysis_data") is not None:
        return st.session_state.last_analysis_data.to_csv(index=False).encode("utf-8")
    return b""


def export_report_content():
    if st.session_state.messages:
        for msg in reversed(st.session_state.messages):
            if msg["role"] == "assistant" and len(msg["content"]) > 50:
                return msg["content"].encode("utf-8")
    return b"No report available."


def risk_badge(band: str) -> str:
    bg, fg = RISK_COLORS.get(band.upper(), ("#E5E7EB", "#374151"))
    return f'<span class="badge" style="background:{bg};color:{fg}">{band}</span>'


def decision_badge(decision: str) -> str:
    bg, fg = DECISION_COLORS.get(decision.upper(), ("#E5E7EB", "#374151"))
    return f'<span class="badge" style="background:{bg};color:{fg}">{decision}</span>'


def _cr_model_available():
    return (MODEL_DIR / "xgb_model.pkl").exists()


def _cr_predict(data):
    try:
        model, fi_df, mf = _load_model()
        feats = _engineer_features(data)
        if mf:
            for f in mf:
                if f not in feats:
                    feats[f] = np.nan
            ordered = [feats[f] for f in mf]
        else:
            ordered = list(feats.values())
        X = np.array(ordered).reshape(1, -1)
        try:
            prob = float(model.predict_proba(X)[0][1])
        except Exception:
            prob = float(model.predict(X)[0])
        grade, risk = _probability_to_grade(prob)
        top = []
        try:
            imp = model.get_booster().get_score(importance_type="gain")
            if not imp:
                imp = model.get_booster().get_score(importance_type="weight")

            tot = sum(imp.values()) or 1.0

            # Build f0→real-name map.
            # Priority 1: mf (booster.feature_names when available)
            # Priority 2: sklearn feature_names_in_
            # Priority 3: ordered keys from _engineer_features() — same order passed to model
            resolved_names = (
                mf
                or (list(model.feature_names_in_) if hasattr(model, "feature_names_in_") else None)
                or list(feats.keys())
            )
            feature_name_map = {f"f{idx}": fname for idx, fname in enumerate(resolved_names)}

            for fn, g in sorted(imp.items(), key=lambda x: x[1], reverse=True)[:8]:
                actual_name = feature_name_map.get(fn, fn)
                rat = ""
                if fi_df is not None and not fi_df.empty:
                    m = fi_df[fi_df.iloc[:, 0].astype(str).str.lower() == actual_name.lower()]
                    if not m.empty and m.shape[1] > 1:
                        rat = str(m.iloc[0, -1])
                value = data.get(actual_name, data.get(fn, feats.get(actual_name, feats.get(fn, "N/A"))))
                top.append({
                    "feature": actual_name,
                    "importance_pct": round(g / tot * 100, 1),
                    "rationale": rat,
                    "value": value
                })
        except Exception as e:
            import traceback
            traceback.print_exc()
            
        return {
            "default_probability": round(prob, 6),
            "default_probability_pct": f"{prob*100:.2f}%",
            "implied_grade": grade,
            "risk_level": risk,
            "top_features": top
        }
    except Exception as e:
        return {"error": str(e)}
# =============================================================================
# TABS DEFINITION
# =============================================================================
tab1, tab2, tab3, tab4 = st.tabs([
    "FD Advisor",
    "New Account",
    "Credit Risk",
    "Financial News",
])


# =============================================================================
# TAB 1: FD ADVISOR CHAT
# =============================================================================
with tab1:
    for idx, message in enumerate(st.session_state.messages):
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
            if "chart_options" in message and message["chart_options"]:
                for i, opt in enumerate(message["chart_options"]):
                    st_echarts(options=opt, height="400px", key=f"hist_viz_{idx}_{i}")

    user_input = st.chat_input("Ask about FDs, check your data, or say 'Open an account'")

    if user_input:
        st.session_state.messages.append({"role": "user", "content": user_input})

        if not bool(os.getenv("NVIDIA_API_KEY")):
            append_assistant("⚠️ NVIDIA_API_KEY not found. Please configure it.")
            st.rerun()

        crews = get_crews()

        try:
            viz_keywords = ["plot", "chart", "graph", "visualize", "show me",
                            "donut", "pie", "line", "bar", "break down"]
            if any(kw in user_input.lower() for kw in viz_keywords):
                with st.spinner("Generating chart..."):
                    data_json = (
                        st.session_state.last_analysis_data.to_json(orient="records")
                        if st.session_state.last_analysis_data is not None else "None"
                    )
                    viz_result = run_crew_with_langfuse(
                        crew_callable=lambda: crews.get_visualization_crew(user_input, data_json).kickoff(),
                        crew_name="fd-visualization-crew",
                        user_input=user_input,
                        region=st.session_state.get("user_region", {}).get("country_name", "Worldwide"),
                        extra_metadata={"has_data_context": data_json != "None"},
                    )
                try:
                    chart_options_raw = extract_json_balanced(viz_result.raw)
                    chart_options = chart_options_raw if isinstance(chart_options_raw, list) else [chart_options_raw]
                    append_assistant(f"Here are the visualizations for: {user_input}", chart_options)
                except Exception as e:
                    append_assistant(f"Sorry, couldn't generate that chart. ({e})")
                st.rerun()

            else:
                with st.spinner("Processing..."):
                    result = run_crew_with_langfuse(
                        crew_callable=lambda: run_crew(
                            user_input,
                            region=st.session_state.get("user_region", {}).get("country_name", "Worldwide"),
                        ),
                        crew_name="fd-analysis-crew",
                        user_input=user_input,
                        region=st.session_state.get("user_region", {}).get("country_name", "Worldwide"),
                    )

                if hasattr(result, "raw") and result.raw.strip() == "ONBOARDING":
                    append_assistant("To open a new account, switch to the **New Account** tab.")
                    st.rerun()

                elif hasattr(result, "tasks_output") and len(result.tasks_output) >= 5:
                    st.markdown(result.raw)
                    projection_output = result.tasks_output[2].raw
                    try:
                        parse_raw = result.tasks_output[0].raw
                        tenure_match = re.search(r"Tenure:\s*(\d+)", parse_raw, re.IGNORECASE)
                        if tenure_match:
                            st.session_state.last_tenure_months = int(tenure_match.group(1))
                    except Exception:
                        pass
                    df = parse_projection_table(projection_output)
                    if not df.empty:
                        st.session_state.last_analysis_data = df
                        st.success("Analysis complete!")

                        def fmt(x):
                            return f"{x:,.2f}" if isinstance(x, (int, float)) else str(x)

                        styled_df = df.copy()
                        for col in ["General Rate (%)", "Senior Rate (%)",
                                    "General Maturity", "Senior Maturity",
                                    "General Interest", "Senior Interest"]:
                            if col in styled_df.columns:
                                styled_df[col] = styled_df[col].apply(fmt)
                        st.dataframe(styled_df, use_container_width=True, key="analysis_df")
                        render_bar_charts(df)

                        st.markdown("---")
                        ec1, ec2 = st.columns(2)
                        with ec1:
                            st.download_button(
                                "Download Analysis (CSV)", export_analysis_data(),
                                "fd_analysis.csv", "text/csv",
                            )
                        with ec2:
                            st.download_button(
                                "Download Report (MD)", export_report_content(),
                                "fd_report.md", "text/markdown",
                            )

                    append_assistant(result.raw)
                    st.rerun()
                else:
                    append_assistant(result.raw)
                    st.rerun()

        except Exception as e:
            append_assistant(f"An error occurred: {e}")
            st.rerun()


# =============================================================================
# TAB 2: NEW ACCOUNT (ONBOARDING)
# =============================================================================
with tab2:
    st.markdown("##  Open a New Account")
    country_info = st.session_state.user_region
    selected_country_name = country_info["country_name"]
    selected_country_code = country_info["country_code"]
    all_countries = fetch_country_data()
    country_lookup = {v["name"]: cc for cc, v in all_countries.items() if v["name"]}
    country_names_sorted = sorted(country_lookup.keys())
    detected_idx = country_names_sorted.index(selected_country_name) if selected_country_name in country_names_sorted else 0

    col_country, _ = st.columns([1, 2])
    with col_country:
        selected_country_name = st.selectbox(
            "Country", options=country_names_sorted, index=detected_idx, key="onboard_country"
        )
    selected_country_code = country_lookup.get(selected_country_name, "WW")

    with st.spinner("Loading KYC requirements..."):
        doc1, doc2 = get_dynamic_kyc_docs(selected_country_name)
    if "kyc_document_names" not in st.session_state or st.session_state.get("_last_kyc_country") != selected_country_name:
        st.session_state.kyc_document_names = [doc1, doc2]
        st.session_state["_last_kyc_country"] = selected_country_name

    badge_bg, badge_color = "#DBEAFE", "#1E40AF"
    st.markdown(
        f"""<div style="background:#F0FDF4;border:1px solid #BBF7D0;border-radius:8px;padding:12px 16px;margin-bottom:1rem">
          <b style="color:#166534">📋 KYC Requirements for {selected_country_name}</b><br>
          <span class="badge" style="background:{badge_bg};color:{badge_color}">1. {doc1}</span>
          <span class="badge" style="background:{badge_bg};color:{badge_color}">2. {doc2}</span>
        </div>""",
        unsafe_allow_html=True,
    )

    with st.form("onboarding_form"):
        st.markdown("#### Applicant Information")
        col1, col2 = st.columns(2)
        with col1:
            first_name = st.text_input("First Name")
            last_name = st.text_input("Last Name")
            email = st.text_input("Email Address")
            mobile = st.text_input("Mobile Number")
        with col2:
            address = st.text_area("Residential Address")
            pin_code = st.text_input("PIN / Postal Code")
            st.text_input("Country", value=selected_country_name, disabled=True)

        st.markdown("#### Deposit Details")
        col3, col4 = st.columns(2)
        with col3:
            product_type = st.radio("Product Type", ["FD", "RD"])
            amount = st.number_input(
                f"Amount ({'Principal' if product_type == 'FD' else 'Monthly Installment'})",
                min_value=1000,
            )
            tenure = st.slider("Tenure (Months)", 6, 120, 12)
        with col4:
            bank_name = st.text_input("Preferred Bank Name", value="SBI")
            compounding = st.selectbox("Compounding Frequency", ["quarterly", "monthly", "yearly"])

        st.markdown("#### KYC Documentation")
        col5, col6 = st.columns(2)
        with col5:
            kyc_val_1 = st.text_input(f"{doc1} Number")
        with col6:
            kyc_val_2 = st.text_input(f"{doc2} Number")

        submitted = st.form_submit_button("Submit Application")

        if submitted:
            if not all([first_name, last_name, email, mobile, address, pin_code, kyc_val_1, kyc_val_2]):
                st.error("Please fill all mandatory fields.")
            else:
                client_data = {
                    "first_name": first_name, "last_name": last_name,
                    "email": email, "user_address": address,
                    "pin_number": pin_code, "mobile_number": mobile,
                    "bank_name": bank_name, "product_type": product_type,
                    "initial_amount": float(amount), "tenure_months": int(tenure),
                    "compounding_freq": compounding,
                    "kyc_details_1": f"{doc1}-{kyc_val_1}",
                    "kyc_details_2": f"{doc2}-{kyc_val_2}",
                    "country_code": selected_country_code,
                }
                json_str = json.dumps(client_data)
                crews_inst = get_crews()
                st.session_state.langfuse_user_id = email
                st.info("Application submitted. Running compliance and risk checks...")
                try:
                    aml_response = run_crew_with_langfuse(
                        crew_callable=lambda: crews_inst.get_aml_execution_crew(json_str).kickoff(),
                        crew_name="aml-execution-crew",
                        user_input=f"New account application for {first_name} {last_name}",
                        region=selected_country_name,
                        extra_metadata={"product_type": product_type, "bank_name": bank_name,
                                        "applicant_email": email},
                    )
                    report_text = aml_response.raw if hasattr(aml_response, "raw") else str(aml_response)

                    # Persist AML result to DB
                    linked_user = get_linked_user(email)
                    if linked_user:
                        score_match = re.search(r"SCORE:\s*(\d+)", report_text)
                        risk_score = int(score_match.group(1)) if score_match else 50
                        dec_match = re.search(r"DECISION:\s*(PASS|FAIL|APPROVE|REJECT)", report_text, re.IGNORECASE)
                        decision = dec_match.group(1).upper() if dec_match else "REVIEW"
                        band = ("LOW" if risk_score <= 20 else "MEDIUM" if risk_score <= 40
                                else "HIGH" if risk_score <= 60 else "CRITICAL")
                        sanctions = 1 if "sanctions" in report_text.lower() and "hit" in report_text.lower() else 0
                        pep = 1 if "politically exposed" in report_text.lower() or "pep" in report_text.lower() else 0
                        adverse = 1 if "adverse" in report_text.lower() else 0
                        case_id = save_aml_case(
                            linked_user["user_id"], risk_score, band, decision,
                            report_markdown=report_text,
                            sanctions_hit=sanctions, pep_flag=pep, adverse_media=adverse,
                        )
                        log_audit(linked_user["user_id"], case_id, "DEPOSIT_APPLICATION",
                                  f"Application submitted for {product_type} at {bank_name}",
                                  "Onboarding Form")

                    st.markdown("### Compliance Report")
                    st.markdown(report_text)
                except Exception as e:
                    st.error(f"An error occurred during processing: {e}")

# =============================================================================

# =============================================================================
# TAB 3: CREDIT RISK
# =============================================================================
with tab3:
    st.markdown('<h2 class="sub-header">Credit Risk Assessment</h2>', unsafe_allow_html=True)
    
    # Region gating - Credit Risk is US-only
    user_region = st.session_state.get("user_region", {})
    user_country_code = user_region.get("country_code", "WW")
    user_country_name = user_region.get("country_name", "Worldwide")
    
    is_us_region = user_country_code.upper() in ("US", "UNITED STATES", "USA")
    
    if not is_us_region:
        detected_flag = f": {user_country_name}" if user_country_name != "Worldwide" else ""
        st.markdown(f"""
        <div style="text-align:center; padding:50px 20px; background:#FEF2F2; border-radius:12px; border:1px solid #FECACA; margin:20px 0;">
            <div style="width:48px; height:48px; background:#FEE2E2; border-radius:50%; display:flex; align-items:center; justify-content:center; margin:0 auto 16px auto; border:2px solid #FECACA;">
                <span style="color:#DC2626; font-size:24px; font-weight:bold;">!</span>
            </div>
            <h3 style="color:#991B1B; margin:0 0 8px 0;">Region Not Supported</h3>
            <p style="color:#7F1D1D; max-width:500px; margin:0 auto 16px auto; line-height:1.6;">
                Credit Risk Assessment is currently available only for <strong>United States</strong> region users.
            </p>
            <div style="background:#FEE2E2; display:inline-block; padding:8px 16px; border-radius:6px; font-size:14px; color:#991B1B;">
                Detected Region{detected_flag}
            </div>
        </div>
        """, unsafe_allow_html=True)
        
        st.markdown("---")
        st.markdown("#### Why is this restricted?")
        st.markdown("""
        The credit risk model is trained on **US Lending Club data (2007-2018)** and uses US-specific 
        credit scoring conventions (FICO scores, US-style DTI calculations, US lending terminology). 
        Applying this model to borrowers from other regions would produce unreliable results.
        """)
        
        st.markdown("#### Available alternatives in your region")
        st.markdown(f"""
        - Use the **FD Advisor** tab to compare deposit rates in {user_country_name or "your region"}
        - Use the **FD Advisor** tab to compare deposit rates across banks
        - Open a new account via the **New Account** tab
        """)
        
        with st.expander("Region Detection Details", expanded=False):
            st.markdown(f"""
            | Field | Value |
            |-------|-------|
            | Country Code | `{user_country_code}` |
            | Country Name | {user_country_name} |
            | Currency | {user_region.get('currency_code', 'N/A')} |
            | Currency Symbol | {user_region.get('currency_symbol', 'N/A')} |
            | Search Region | `{user_region.get('ddg_region', 'wt-wt')}` |
            """)
    else:
        # US users get full access
        st.markdown(f"""
        <div style="display:flex; align-items:center; gap:8px; margin-bottom:16px; padding:8px 12px; background:#F0FDF4; border-radius:6px; border:1px solid #BBF7D0;">
            <span style="color:#16A34A; font-weight:600;">US Region</span>
            <span style="color:#166534; font-size:13px;">Detected -- Credit Risk model is applicable for your region</span>
        </div>
        """, unsafe_allow_html=True)
        
        if not _cr_model_available():
            st.warning("Credit risk model not available. Please ensure the model files are in the expected directory.")
            st.stop()
        
        # Initialize session state for credit risk
        if "cr_form_data" not in st.session_state:
            st.session_state.cr_form_data = {}
        if "cr_results" not in st.session_state:
            st.session_state.cr_results = None
        
        cr_form_col, cr_results_col = st.columns([1, 2])
        
        with cr_form_col:
            st.markdown("### Borrower Information")
            st.caption("Enter borrower attributes for the US credit risk model")
            
            with st.form("credit_risk_form"):
                st.markdown("#### Loan Details")
                col_a, col_b = st.columns(2)
                with col_a:
                    loan_amnt = st.number_input("Loan Amount ($)", min_value=1000, max_value=500000, value=15000, step=1000)
                    term = st.selectbox("Term", options=[36, 60], format_func=lambda x: f"{x} months", index=0)
                with col_b:
                    int_rate = st.number_input("Interest Rate (%)", min_value=1.0, max_value=30.0, value=12.5, step=0.25)
                    purpose = st.selectbox("Purpose", options=[
                        "debt_consolidation", "credit_card", "home_improvement", "major_purchase",
                        "medical", "small_business", "car", "moving", "vacation", "house",
                        "renewable_energy", "wedding", "educational", "other"
                    ], index=0)
                
                st.markdown("#### Income & Employment")
                col_c, col_d = st.columns(2)
                with col_c:
                    annual_inc = st.number_input("Annual Income ($)", min_value=5000, max_value=5000000, value=60000, step=5000)
                    emp_length = st.selectbox("Employment Length", options=[
                        "< 1 year", "1 year", "2 years", "3 years", "4 years",
                        "5 years", "6 years", "7 years", "8 years", "9 years", "10+ years"
                    ], index=5)
                with col_d:
                    home_ownership = st.selectbox("Home Ownership", options=["RENT", "OWN", "MORTGAGE", "OTHER"], index=0)
                    verification_status = st.selectbox("Verification Status", options=["Not Verified", "Source Verified", "Verified"], index=0)
                
                st.markdown("#### Credit Profile")
                col_e, col_f = st.columns(2)
                with col_e:
                    fico_score = st.number_input("FICO Score", min_value=300, max_value=850, value=680, step=5)
                    dti = st.number_input("DTI Ratio (%)", min_value=0.0, max_value=100.0, value=18.0, step=0.5)
                with col_f:
                    delinq_2yrs = st.number_input("Delinquencies (2yr)", min_value=0, max_value=20, value=0, step=1)
                    inq_last_6mths = st.number_input("Inquiries (6mo)", min_value=0, max_value=20, value=1, step=1)
                
                col_g, col_h = st.columns(2)
                with col_g:
                    pub_rec = st.number_input("Public Records", min_value=0, max_value=20, value=0, step=1)
                    revol_util = st.number_input("Revolving Util (%)", min_value=0.0, max_value=150.0, value=45.0, step=1.0)
                with col_h:
                    revol_bal = st.number_input("Revolving Balance ($)", min_value=0, max_value=500000, value=5000, step=500)
                    earliest_cr_line = st.text_input("Earliest Credit Line", value="Jan-2010", help="Format: Mon-YYYY")
                
                st.markdown("#### Optional Fields")
                with st.expander("Advanced Options", expanded=False):
                    col_i, col_j = st.columns(2)
                    with col_i:
                        total_acc = st.number_input("Total Accounts", min_value=1, max_value=100, value=15, step=1)
                        open_acc = st.number_input("Open Accounts", min_value=0, max_value=50, value=8, step=1)
                    with col_j:
                        mths_since_last_delinq = st.number_input("Months Since Last Delinq", min_value=0, max_value=180, value=36, step=1)
                        total_rev_hi_lim = st.number_input("Total Rev High Limit ($)", min_value=0, max_value=1000000, value=20000, step=1000)
                
                submitted = st.form_submit_button("Run Credit Risk Assessment", type="primary", use_container_width=True)
            
            if submitted:
                emp_map = {
                    "< 1 year": 0, "1 year": 1, "2 years": 2, "3 years": 3, "4 years": 4,
                    "5 years": 5, "6 years": 6, "7 years": 7, "8 years": 8, "9 years": 9, "10+ years": 10
                }
                ver_map = {"Not Verified": "Not Verified", "Source Verified": "Source Verified", "Verified": "Verified"}
                
                borrower_data = {
                    "loan_amnt": loan_amnt,
                    "term": term,
                    "int_rate": int_rate,
                    "annual_inc": annual_inc,
                    "dti": dti,
                    "fico_score": fico_score,
                    "home_ownership": home_ownership,
                    "delinq_2yrs": delinq_2yrs,
                    "inq_last_6mths": inq_last_6mths,
                    "pub_rec": pub_rec,
                    "earliest_cr_line": earliest_cr_line,
                    "revol_util": revol_util,
                    "revol_bal": revol_bal,
                    "purpose": purpose,
                    "emp_length": emp_map.get(emp_length, 5),
                    "verification_status": ver_map.get(verification_status, "Not Verified"),
                    "total_acc": total_acc if total_acc > 1 else None,
                    "open_acc": open_acc if open_acc > 0 else None,
                    "mths_since_last_delinq": mths_since_last_delinq if mths_since_last_delinq > 0 else None,
                    "total_rev_hi_lim": total_rev_hi_lim if total_rev_hi_lim > 0 else None,
                }
                
                with st.spinner("Running credit risk model..."):
                    result = _cr_predict(borrower_data)
                    result["_borrower_data"] = borrower_data

                # Use LLM (loan_creation_agent via CrewAI) to generate decision response
                _nvidia_key = os.getenv("NVIDIA_NIM_API_KEY", "") or os.getenv("NVIDIA_API_KEY", "")
                if not _nvidia_key:
                    result["_llm_decision"] = None
                    result["_llm_error"] = "NVIDIA_NIM_API_KEY not set. Add it to your .env file."
                else:
                    with st.spinner("Loan Creation Agent generating decision via LLM..."):
                        try:
                            _crews_instance = FixedDepositCrews()
                            _risk_summary = (
                                f"Grade: {result.get('implied_grade', 'N/A')}\n"
                                f"Default Probability: {result.get('default_probability_pct', 'N/A')}\n"
                                f"Risk Level: {result.get('risk_level', 'N/A')}\n"
                                f"Top Features: {json.dumps(result.get('top_features', []))}\n"
                            )
                            _borrower_email = st.session_state.logged_in_user.get("email", "") if st.session_state.logged_in_user else ""
                            _loan_crew = _crews_instance.get_loan_creation_crew(
                                risk_assessment_result=_risk_summary,
                                borrower_data=borrower_data,
                                borrower_email=_borrower_email,
                            )
                            _crew_result = _loan_crew.kickoff()
                            result["_llm_decision"] = _crew_result.raw
                        except Exception as _crew_err:
                            result["_llm_decision"] = None
                            result["_llm_error"] = str(_crew_err)

                st.session_state.cr_results = result
        
        with cr_results_col:
            if st.session_state.cr_results is None:
                st.markdown("""
                <div style="text-align:center; padding:60px 20px; background:#F8FAFC; border-radius:12px; border:1px solid #E2E8F0;">
                    <div style="width:64px; height:64px; background:#E2E8F0; border-radius:50%; display:flex; align-items:center; justify-content:center; margin:0 auto 16px auto;">
                        <span style="color:#64748B; font-size:28px; font-weight:bold;">?</span>
                    </div>
                    <h3 style="color:#64748B; margin:0 0 8px 0;">No Assessment Yet</h3>
                    <p style="color:#94A3B8; max-width:400px; margin:0 auto;">
                        Complete the borrower information form and click "Run Credit Risk Assessment" 
                        to generate a comprehensive credit risk report.
                    </p>
                </div>
                """, unsafe_allow_html=True)
                
                st.markdown("---")
                st.markdown("""
                <div style="background:#F1F5F9; border-radius:8px; padding:16px; border-left:4px solid #3B82F6;">
                    <h4 style="margin:0 0 8px 0; color:#1E3A8A;">Model Information</h4>
                    <table style="width:100%; font-size:13px; color:#475569;">
                        <tr><td style="padding:4px 0;"><strong>Algorithm:</strong></td><td>XGBoost Classifier</td></tr>
                        <tr><td style="padding:4px 0;"><strong>Training Data:</strong></td><td>US Lending Club (2007-2018)</td></tr>
                        <tr><td style="padding:4px 0;"><strong>Output:</strong></td><td>Default Probability, Risk Grade, Feature Importance</td></tr>
                        <tr><td style="padding:4px 0;"><strong>Grade Scale:</strong></td><td>AAA (safest) to D (highest risk)</td></tr>
                    </table>
                </div>
                """, unsafe_allow_html=True)
            else:
                result = st.session_state.cr_results
                borrower = result.get("_borrower_data", {})
                borrower_data = borrower  # Ensure borrower_data is available for downstream usage (email, save, export)
                
                if "error" in result:
                    st.error(f"Model Error: {result['error']}")
                else:
                    prob = result.get("default_probability", 0)
                    prob_pct = result.get("default_probability_pct", "0%")
                    grade = result.get("implied_grade", "N/A")
                    risk_level = result.get("risk_level", "UNKNOWN")
                    top_features = result.get("top_features", [])
                    
                    risk_config = {
                        "LOW": {"bg": "#DCFCE7", "fg": "#166534", "border": "#22C55E"},
                        "MEDIUM": {"bg": "#FEF9C3", "fg": "#854D0E", "border": "#EAB308"},
                        "HIGH": {"bg": "#FEE2E2", "fg": "#991B1B", "border": "#EF4444"},
                        "CRITICAL": {"bg": "#7F1D1D", "fg": "#FEE2E2", "border": "#DC2626"},
                    }
                    rc = risk_config.get(risk_level.upper(), risk_config["MEDIUM"])
                    
                    st.markdown(f"""
                    <div style="background:{rc['bg']}; border:2px solid {rc['border']}; border-radius:12px; padding:20px; margin-bottom:20px;">
                        <div style="display:flex; justify-content:space-between; align-items:center;">
                            <div>
                                <div style="font-size:12px; text-transform:uppercase; letter-spacing:1px; color:{rc['fg']}; opacity:0.8;">
                                    Risk Assessment Result
                                </div>
                                <div style="font-size:28px; font-weight:700; color:{rc['fg']}; margin:4px 0;">
                                    {risk_level.upper()} RISK
                                </div>
                            </div>
                            <div style="text-align:right;">
                                <div style="font-size:48px; font-weight:800; color:{rc['fg']};">{grade}</div>
                                <div style="font-size:13px; color:{rc['fg']}; opacity:0.8;">Implied Grade</div>
                            </div>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
                    
                    m1, m2, m3, m4 = st.columns(4)
                    
                    with m1:
                        st.markdown(f"""
                        <div class="metric-card">
                            <div style="font-size:11px; text-transform:uppercase; letter-spacing:0.5px; color:#64748B;">
                                Default Probability
                            </div>
                            <div style="font-size:24px; font-weight:700; color:{rc['fg']}; margin:4px 0;">
                                {prob_pct}
                            </div>
                            <div style="font-size:11px; color:#94A3B8;">Likelihood of default</div>
                        </div>
                        """, unsafe_allow_html=True)
                    
                    with m2:
                        loan_to_income = borrower.get("loan_amnt", 0) / max(borrower.get("annual_inc", 1), 1) * 100
                        lti_color = "#16A34A" if loan_to_income < 30 else "#EAB308" if loan_to_income < 50 else "#DC2626"
                        st.markdown(f"""
                        <div class="metric-card">
                            <div style="font-size:11px; text-transform:uppercase; letter-spacing:0.5px; color:#64748B;">
                                Loan-to-Income
                            </div>
                            <div style="font-size:24px; font-weight:700; color:{lti_color}; margin:4px 0;">
                                {loan_to_income:.1f}%
                            </div>
                            <div style="font-size:11px; color:#94A3B8;">Loan / Annual Income</div>
                        </div>
                        """, unsafe_allow_html=True)
                    
                    with m3:
                        fico = borrower.get("fico_score", 680)
                        fico_color = "#16A34A" if fico >= 740 else "#EAB308" if fico >= 670 else "#DC2626"
                        st.markdown(f"""
                        <div class="metric-card">
                            <div style="font-size:11px; text-transform:uppercase; letter-spacing:0.5px; color:#64748B;">
                                FICO Score
                            </div>
                            <div style="font-size:24px; font-weight:700; color:{fico_color}; margin:4px 0;">
                                {fico}
                            </div>
                            <div style="font-size:11px; color:#94A3B8;">Credit score range</div>
                        </div>
                        """, unsafe_allow_html=True)
                    
                    with m4:
                        dti_val = borrower.get("dti", 0)
                        dti_color = "#16A34A" if dti_val < 20 else "#EAB308" if dti_val < 36 else "#DC2626"
                        st.markdown(f"""
                        <div class="metric-card">
                            <div style="font-size:11px; text-transform:uppercase; letter-spacing:0.5px; color:#64748B;">
                                DTI Ratio
                            </div>
                            <div style="font-size:24px; font-weight:700; color:{dti_color}; margin:4px 0;">
                                {dti_val:.1f}%
                            </div>
                            <div style="font-size:11px; color:#94A3B8;">Debt-to-income</div>
                        </div>
                        """, unsafe_allow_html=True)
                    
                    # Collect valid features (still needed for export)
                    valid_features = []
                    if top_features:
                        for feat in top_features:
                            fname = feat.get("feature", "")
                            imp_val = feat.get("importance_pct", 0)
                            if fname and imp_val and imp_val > 0 and not re.match(r'^f\d+$', fname):
                                valid_features.append(feat)

                    bench_col, _ = st.columns([1, 1])
                    with bench_col:
                        st.markdown("#### Risk Benchmarks")
                        fico_val  = borrower.get("fico_score", 680)
                        dti_val2  = borrower.get("dti", 0)
                        lti_val   = borrower.get("loan_amnt", 0) / max(borrower.get("annual_inc", 1), 1) * 100
                        ru_val    = borrower.get("revol_util", 0)

                        def _bench_row(label, value, good_max, warn_max, fmt="{:.1f}"):
                            color = "#16A34A" if value <= good_max else "#EAB308" if value <= warn_max else "#DC2626"
                            status = "✅ Good" if value <= good_max else "⚠️ Watch" if value <= warn_max else "🔴 High"
                            formatted = fmt.format(value)
                            st.markdown(
                                f"<div style='display:flex;justify-content:space-between;align-items:center;"
                                f"padding:8px 0;border-bottom:1px solid #F1F5F9;'>"
                                f"<span style='color:#64748B;font-size:13px;'>{label}</span>"
                                f"<span style='color:{color};font-size:13px;font-weight:600;'>{formatted} — {status}</span>"
                                f"</div>",
                                unsafe_allow_html=True,
                            )

                        # FICO: higher is better — invert thresholds
                        fico_color = "#16A34A" if fico_val >= 740 else "#EAB308" if fico_val >= 670 else "#DC2626"
                        fico_status = "✅ Good" if fico_val >= 740 else "⚠️ Watch" if fico_val >= 670 else "🔴 Weak"
                        st.markdown(
                            f"<div style='display:flex;justify-content:space-between;align-items:center;"
                            f"padding:8px 0;border-bottom:1px solid #F1F5F9;'>"
                            f"<span style='color:#64748B;font-size:13px;'>FICO Score</span>"
                            f"<span style='color:{fico_color};font-size:13px;font-weight:600;'>{fico_val} — {fico_status}</span>"
                            f"</div>",
                            unsafe_allow_html=True,
                        )
                        _bench_row("DTI Ratio",        dti_val2, 20,  36,  fmt="{:.1f}%")
                        _bench_row("Loan-to-Income",   lti_val,  30,  50,  fmt="{:.1f}%")
                        _bench_row("Revolving Util",   ru_val,   30,  60,  fmt="{:.1f}%")

                        st.markdown(
                            "<p style='font-size:11px;color:#94A3B8;margin-top:10px;'>"
                            "Thresholds: DTI &lt;20% good / &lt;36% watch · "
                            "LTI &lt;30% / &lt;50% · Util &lt;30% / &lt;60% · FICO ≥740 / ≥670</p>",
                            unsafe_allow_html=True,
                        )
                    
                    st.markdown("---")
                    st.markdown("#### Borrower Profile")
                    
                    profile_col1, profile_col2 = st.columns(2)
                    with profile_col1:
                        loan_info = [
                            ("Loan Amount", f"${borrower.get('loan_amnt', 0):,}"),
                            ("Term", f"{borrower.get('term', 0)} months"),
                            ("Interest Rate", f"{borrower.get('int_rate', 0):.2f}%"),
                            ("Purpose", borrower.get('purpose', '').replace('_', ' ').title()),
                        ]
                        for label, value in loan_info:
                            st.markdown(f"**{label}:** {value}")
                    with profile_col2:
                        credit_info = [
                            ("FICO Score", f"{borrower.get('fico_score', 0)}"),
                            ("DTI Ratio", f"{borrower.get('dti', 0):.1f}%"),
                            ("Revolving Util", f"{borrower.get('revol_util', 0):.1f}%"),
                            ("Home Ownership", borrower.get('home_ownership', 'N/A')),
                        ]
                        for label, value in credit_info:
                            st.markdown(f"**{label}:** {value}")

                    st.markdown("---")
                    st.markdown("#### Credit Committee Recommendation")
                    
                    if risk_level.upper() == "LOW":
                        rec_decision = "APPROVE"
                        rec_color = "#166534"
                        rec_bg = "#DCFCE7"
                        rec_text = "Borrower presents low default risk. Recommend standard approval with standard terms."
                        conditions = ["No additional conditions required", "Standard monitoring protocols apply"]
                    elif risk_level.upper() == "MEDIUM":
                        rec_decision = "CONDITIONAL APPROVAL"
                        rec_color = "#854D0E"
                        rec_bg = "#FEF9C3"
                        rec_text = "Borrower presents moderate default risk. Recommend approval with enhanced conditions."
                        conditions = [
                            "Enhanced documentation verification required",
                            "Quarterly monitoring of DTI ratio",
                            "Consider reduced loan amount or shorter term",
                            "Obtain additional income verification"
                        ]
                    elif risk_level.upper() == "HIGH":
                        rec_decision = "REVIEW REQUIRED"
                        rec_color = "#991B1B"
                        rec_bg = "#FEE2E2"
                        rec_text = "Borrower presents elevated default risk. Requires senior committee review."
                        conditions = [
                            "Escalate to senior credit committee",
                            "Require collateral or guarantor",
                            "Mandatory income verification",
                            "Consider significant rate premium if approved"
                        ]
                    else:
                        rec_decision = "DECLINE"
                        rec_color = "#991B1B"
                        rec_bg = "#FEE2E2"
                        rec_text = "Borrower presents unacceptably high default risk. Recommend decline."
                        conditions = [
                            "Application does not meet credit policy",
                            "Reapplication considered after 12 months with improved profile",
                            "Provide adverse action notice per regulation"
                        ]
                    
                    st.markdown(f"""
                    <div style="background:{rec_bg}; border-left:4px solid {rec_color}; border-radius:0 8px 8px 0; padding:16px; margin-bottom:16px;">
                        <div style="font-size:18px; font-weight:700; color:{rec_color}; margin-bottom:8px;">
                            {rec_decision}
                        </div>
                        <p style="color:{rec_color}; margin:0; font-size:14px;">{rec_text}</p>
                    </div>
                    """, unsafe_allow_html=True)
                    
                    if conditions:
                        st.markdown("**Conditions:**")
                        for cond in conditions:
                            st.markdown(f"- {cond}")
                    
                    # ── 3-Category Loan Decision ──
                    st.markdown("---")
                    st.markdown("#### Loan Creation — Decision Classification")

                    # Step 1: Initial classification from XGBoost model output
                    loan_decision = classify_loan_decision(grade, prob)

                    # Step 2: Parse LLM-generated decision if available
                    llm_decision_raw = result.get("_llm_decision", "")
                    llm_parsed = _parse_llm_decision(llm_decision_raw) if llm_decision_raw else {}
                    llm_error = result.get("_llm_error", "")

                    # Step 3: If LLM returned a valid decision category, use it
                    if llm_parsed.get("DECISION"):
                        _llm_cat = llm_parsed["DECISION"].upper().strip()
                        if _llm_cat in ("LOAN_APPROVED", "NEEDS_VERIFY", "REJECTED"):
                            loan_decision = _llm_cat

                    ldc = LOAN_DECISION_CONFIG.get(loan_decision, LOAN_DECISION_CONFIG["NEEDS_VERIFY"])

                    # Show LLM status indicator
                    if llm_decision_raw:
                        st.info("🤖 **LLM-Generated Decision** — The Loan Creation Agent (LLM) has analyzed the XGBoost model output and generated this decision.")
                    elif llm_error:
                        st.warning(f"⚠️ LLM decision unavailable ({llm_error}). Using rule-based fallback.")

                    # Prominent decision banner
                    st.markdown(f"""
                    <div style="background:{ldc['banner_bg']}; border:2px solid {ldc['border']}; 
                                border-radius:12px; padding:24px; margin-bottom:16px; text-align:center;">
                        <div style="font-size:48px; margin-bottom:8px;">{ldc['icon']}</div>
                        <div style="font-size:22px; font-weight:800; color:{ldc['fg']}; letter-spacing:1px;">
                            {ldc['label']}
                        </div>
                        <div style="font-size:14px; color:{ldc['fg']}; opacity:0.8; margin-top:4px;">
                            Grade: {grade} | Default Probability: {prob_pct} | Risk: {risk_level}
                        </div>
                    </div>
                    """, unsafe_allow_html=True)

                    # Decision-specific details (hardcoded fallback)
                    if loan_decision == "LOAN_APPROVED":
                        decision_rationale = (
                            f"Borrower's credit profile (Grade {grade}, {prob_pct} default probability) "
                            f"meets the bank's low-risk threshold. The XGBoost model indicates strong "
                            f"repayment capacity based on FICO score ({borrower.get('fico_score', 0)}), "
                            f"DTI ratio ({borrower.get('dti', 0):.1f}%), and income profile. "
                            f"Standard loan terms are approved."
                        )
                        decision_conditions = "No additional conditions required; standard monitoring protocols apply"
                        decision_next_steps = (
                            "Loan agreement will be generated; "
                            "expect disbursement within 3-5 business days; "
                            "monitor your email for loan documents"
                        )
                        st.success("🎉 Congratulations! The loan has been auto-approved based on the ML risk assessment.")

                    elif loan_decision == "NEEDS_VERIFY":
                        decision_rationale = (
                            f"Borrower's credit profile (Grade {grade}, {prob_pct} default probability) "
                            f"falls in the moderate-risk zone. While the profile shows some positive indicators, "
                            f"additional verification is required before a final decision can be made. "
                            f"Key risk factors should be reviewed by the credit committee."
                        )
                        decision_conditions = (
                            "Enhanced documentation verification required; "
                            "Quarterly monitoring of DTI ratio; "
                            "Consider reduced loan amount or shorter term; "
                            "Obtain additional income verification"
                        )
                        decision_next_steps = (
                            "Submit requested documents within 10 business days; "
                            "A credit committee member will review your application; "
                            "Expect a decision within 5-7 business days after document submission"
                        )
                        st.warning("⚠️ Additional verification is required before the loan can be approved.")

                    else:  # REJECTED
                        decision_rationale = (
                            f"Borrower's credit profile (Grade {grade}, {prob_pct} default probability) "
                            f"exceeds the bank's acceptable risk threshold. The ML model identifies "
                            f"significant default risk factors including elevated DTI ({borrower.get('dti', 0):.1f}%), "
                            f"FICO score below threshold ({borrower.get('fico_score', 0)}), and other risk indicators. "
                            f"Application does not meet current credit policy requirements."
                        )
                        decision_conditions = "Application does not meet credit policy"
                        decision_next_steps = (
                            "Adverse action notice has been recorded per regulation; "
                            "Reapplication may be considered after 12 months with improved credit profile; "
                            "Contact a financial advisor for credit improvement guidance"
                        )
                        st.error("❌ The loan application has been rejected based on the ML risk assessment.")

                    # Step 4: Override with LLM-generated rationale/conditions/next_steps if available
                    if llm_parsed.get("RATIONALE"):
                        decision_rationale = llm_parsed["RATIONALE"]
                    if llm_parsed.get("CONDITIONS"):
                        decision_conditions = llm_parsed["CONDITIONS"]
                    if llm_parsed.get("NEXT_STEPS"):
                        decision_next_steps = llm_parsed["NEXT_STEPS"]

                    # Show rationale
                    st.markdown("**Decision Rationale:**")
                    st.markdown(decision_rationale)

                    # Show conditions
                    st.markdown("**Conditions:**")
                    for cond in decision_conditions.split("; "):
                        st.markdown(f"- {cond}")

                    # Show next steps
                    st.markdown("**Next Steps:**")
                    for step in decision_next_steps.split("; "):
                        st.markdown(f"- {step}")

                    # ── Save to DB (3-condition logic) ──
                    try:
                        app_id = save_loan_application(
                            applicant_email=st.session_state.logged_in_user.get("email", "") if st.session_state.logged_in_user else "",
                            borrower_data=borrower_data,
                            cr_result=result,
                            loan_decision=loan_decision,
                            rationale=decision_rationale,
                            conditions=decision_conditions,
                            next_steps=decision_next_steps,
                        )
                        if app_id:
                            st.caption(f"Application #{app_id} saved to database.")
                            if loan_decision == "LOAN_APPROVED":
                                st.success(f"💰 Loan amount ${borrower_data.get('loan_amnt', 0):,.0f} recorded for disbursement (PENDING).")
                            elif loan_decision == "NEEDS_VERIFY":
                                st.info("📋 Application flagged for review — verification required before processing.")
                            else:
                                st.info("🚫 Application recorded as REJECTED — no disbursement created.")
                    except Exception as e:
                        st.caption(f"Note: Could not save to database: {e}")

                    # ── Email Notification ──
                    st.markdown("---")
                    st.markdown("#### Notify Borrower")
                    notify_col1, notify_col2 = st.columns([1, 2])
                    with notify_col1:
                        borrower_email_input = st.text_input(
                            "Borrower Email",
                            value=st.session_state.logged_in_user.get("email", "") if st.session_state.logged_in_user else "",
                            key="loan_notify_email",
                            help="Email address to send the loan decision notification"
                        )
                        if st.button("📧 Send Decision Email", type="primary", use_container_width=True, key="send_loan_email_btn"):
                            if borrower_email_input:
                                with st.spinner("Sending email notification..."):
                                    email_sent = send_loan_decision_email(
                                        recipient=borrower_email_input,
                                        loan_decision=loan_decision,
                                        grade=grade,
                                        prob_pct=prob_pct,
                                        risk_level=risk_level,
                                        rationale=decision_rationale,
                                        conditions=decision_conditions.split("; "),
                                        next_steps=decision_next_steps.split("; "),
                                        borrower_data=borrower_data,
                                    )
                                if email_sent:
                                    st.success(f"✅ Decision notification sent to {borrower_email_input}")
                                    # Update notification_sent in DB
                                    try:
                                        db_execute(
                                            "UPDATE loan_applications SET notification_sent=1, updated_at=? WHERE applicant_email=? ORDER BY created_at DESC LIMIT 1",
                                            (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), borrower_email_input),
                                        )
                                    except Exception:
                                        pass
                                else:
                                    st.error("Failed to send email. Check SMTP configuration (SMTP_HOST, SMTP_USER, SMTP_PASSWORD).")
                            else:
                                st.warning("Please enter a valid email address.")
                    with notify_col2:
                        st.markdown("""
                        <div style="background:#F1F5F9; border-radius:8px; padding:16px; border-left:4px solid #3B82F6;">
                            <h4 style="margin:0 0 8px 0; color:#1E3A8A;">Email Notification</h4>
                            <p style="color:#475569; margin:0; font-size:13px;">
                                The borrower will receive a professionally formatted email with the loan decision,
                                risk metrics, rationale, conditions, and next steps. The email is styled according
                                to the decision category (green for approved, yellow for verification, red for rejected).
                            </p>
                        </div>
                        """, unsafe_allow_html=True)

                    st.markdown("---")
                    btn_col1, btn_col2, btn_col3 = st.columns([1, 1, 1])
                    
                    with btn_col1:
                        if st.button("Reset Assessment", use_container_width=True):
                            st.session_state.cr_results = None
                            st.rerun()
                    
                    with btn_col2:
                        export_data = {
                            "assessment_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            "borrower_data": {k: v for k, v in borrower.items() if v is not None},
                            "results": {
                                "default_probability": result.get("default_probability"),
                                "default_probability_pct": result.get("default_probability_pct"),
                                "implied_grade": result.get("implied_grade"),
                                "risk_level": result.get("risk_level"),
                                "recommendation": rec_decision,
                                "loan_decision": loan_decision,
                                "top_features": valid_features[:5]
                            }
                        }
                        st.download_button(
                            "Export Report (JSON)",
                            data=json.dumps(export_data, indent=2, default=str).encode("utf-8"),
                            file_name=f"credit_risk_assessment_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                            mime="application/json",
                            use_container_width=True
                        )
                    
                    with btn_col3:
                        report_text = f"""
CREDIT RISK ASSESSMENT REPORT
Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

LOAN DECISION: {loan_decision}
GRADE: {grade}
DEFAULT PROBABILITY: {prob_pct}
RISK LEVEL: {risk_level}

BORROWER PROFILE:
- Loan Amount: ${borrower.get('loan_amnt', 0):,}
- Term: {borrower.get('term', 0)} months
- Interest Rate: {borrower.get('int_rate', 0):.2f}%
- Annual Income: ${borrower.get('annual_inc', 0):,}
- FICO Score: {borrower.get('fico_score', 0)}
- DTI: {borrower.get('dti', 0):.1f}%
- Purpose: {borrower.get('purpose', '')}

TOP RISK DRIVERS:
"""
                        for i, feat in enumerate(valid_features[:5], 1):
                            report_text += f"{i}. {feat['feature'].replace('_', ' ').title()}: {feat.get('importance_pct', 0)}% importance\n"
                        
                        report_text += f"\nRECOMMENDATION:\n{rec_text}\n\nLOAN DECISION: {loan_decision}\n\nCONDITIONS:\n"
                        for cond in conditions:
                            report_text += f"- {cond}\n"
                        
                        report_text += "\n---\nModel: XGBoost Classifier (US Lending Club 2007-2018)\nThis report is AI-generated for informational purposes only."
                        
                        st.download_button(
                            "Export Report (TXT)",
                            data=report_text.encode("utf-8"),
                            file_name=f"credit_risk_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
                            mime="text/plain",
                            use_container_width=True
                        )


# =============================================================================

# =============================================================================
# TAB 4: FINANCIAL NEWS
# =============================================================================
with tab4:
    st.markdown("## Financial News")
    st.markdown("Latest financial and business news for your region, powered by NewsData.io.")

    import requests as _nd_requests

    _NEWSDATA_API_KEY = os.getenv("NEWSDATA_API_KEY", "")

    def _country_to_newsdata_code(country_code: str) -> str:
        """Map country code to newsdata.io 2-letter ISO code."""
        if not country_code or country_code.upper() in ("WW", "WORLDWIDE"):
            return "us"
        return country_code.lower()[:2]

    def fetch_financial_news(country_code: str) -> dict:
        nd_country = _country_to_newsdata_code(country_code)
        # /market endpoint returns only financial, stock market, and business news natively
        url = "https://newsdata.io/api/1/market"
        params = {
            "apikey": _NEWSDATA_API_KEY,
            "country": nd_country,
            "language": "en",
            "removeduplicate": 1,
        }
        try:
            resp = _nd_requests.get(url, params=params, timeout=15)
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            return {"status": "error", "message": str(exc)}

    _region_info = st.session_state.user_region
    _country_code = _region_info.get("country_code", "WW")
    _country_name = _region_info.get("country_name", "Worldwide")

    col_news_hdr, col_news_refresh = st.columns([4, 1])
    with col_news_hdr:
        st.caption(f"Showing news for: {_country_name}  |  country code: {_country_code.lower()[:2]}")
    with col_news_refresh:
        _refresh_news = st.button("Refresh", key="news_refresh_btn")

    if not _NEWSDATA_API_KEY:
        st.warning(
            "NEWSDATA_API_KEY is not set in your .env file. "
            "Add NEWSDATA_API_KEY=your_key_here to .env and restart the app."
        )
    else:
        _news_cache_key = f"news_data_{_country_code}"
        if _news_cache_key not in st.session_state or _refresh_news:
            with st.spinner("Fetching latest news..."):
                st.session_state[_news_cache_key] = fetch_financial_news(_country_code)

        _news_data = st.session_state.get(_news_cache_key, {})

        if _news_data.get("status") == "error":
            st.error(f"Failed to fetch news: {_news_data.get('message', 'Unknown error')}")
        elif _news_data.get("status") == "success":
            _articles = _news_data.get("results", [])
            if not _articles:
                st.info("No articles found for your region right now. Try refreshing.")
            else:
                st.markdown(f"**{len(_articles)} articles found**")
                st.markdown("---")
                for _article in _articles:
                    _title    = _article.get("title") or "Untitled"
                    _desc     = _article.get("description") or ""
                    _source   = _article.get("source_name") or _article.get("source_id") or "Unknown"
                    _pub_date = _article.get("pubDate") or ""
                    _link     = _article.get("link") or ""
                    _image    = _article.get("image_url") or ""
                    _category = ", ".join(_article.get("category") or []).title() or "General"

                    with st.container():
                        if _image:
                            img_col, txt_col = st.columns([1, 3])
                            with img_col:
                                try:
                                    st.image(_image, use_container_width=True)
                                except Exception:
                                    pass
                            with txt_col:
                                st.markdown(f"### {_title}")
                                if _desc:
                                    st.markdown(_desc[:300] + ("..." if len(_desc) > 300 else ""))
                                m1, m2, m3 = st.columns(3)
                                m1.caption(f"Source: {_source}")
                                m2.caption(f"Date: {_pub_date[:10] if _pub_date else 'N/A'}")
                                m3.caption(f"Category: {_category}")
                                if _link:
                                    st.markdown(f"[Read full article]({_link})")
                        else:
                            st.markdown(f"### {_title}")
                            if _desc:
                                st.markdown(_desc[:300] + ("..." if len(_desc) > 300 else ""))
                            m1, m2, m3 = st.columns(3)
                            m1.caption(f"Source: {_source}")
                            m2.caption(f"Date: {_pub_date[:10] if _pub_date else 'N/A'}")
                            m3.caption(f"Category: {_category}")
                            if _link:
                                st.markdown(f"[Read full article]({_link})")
                        st.markdown("---")
        else:
            st.info("Press Refresh to load the latest financial news.")

# SIDEBAR
# =============================================================================
#      User Login           
st.sidebar.markdown("##  Your Profile")
logged_user = st.session_state.logged_in_user

if logged_user:
    st.sidebar.success(f"Logged in as **{logged_user['display_name']}**")
    st.sidebar.caption(f"Email: {logged_user['email']}")
    if st.sidebar.button("Log Out"):
        st.session_state.logged_in_user = None
        st.rerun()
else:
    with st.sidebar.form("login_form", clear_on_submit=False):
        login_name = st.text_input("Your Name")
        login_email = st.text_input("Email")
        login_submit = st.form_submit_button("Login / Register")
    if login_submit and login_name and login_email:
        session_row = upsert_user_session(
            login_name, login_email, st.session_state.user_region["country_code"]
        )
        st.session_state.logged_in_user = session_row
        st.session_state.langfuse_user_id = login_email
        st.sidebar.success(f"Welcome, {login_name}!")
        st.rerun()

st.sidebar.markdown("---")

#      Search Region        ─
st.sidebar.markdown("###  Search Region")
region_info = st.session_state.user_region
detected_name = region_info["country_name"]
all_countries = fetch_country_data()
country_lookup_sb = {v["name"]: cc for cc, v in all_countries.items() if v["name"]}
country_names_sb = sorted(country_lookup_sb.keys())
detected_idx_sb = country_names_sb.index(detected_name) if detected_name in country_names_sb else 0
st.sidebar.caption(f"Auto-detected: {detected_name}")
selected_country_name_sb = st.sidebar.selectbox(
    "Override region", options=country_names_sb, index=detected_idx_sb, key="region_selectbox"
)
selected_cc = country_lookup_sb.get(selected_country_name_sb, "WW")
if selected_cc != st.session_state.user_region["country_code"]:
    info = all_countries.get(selected_cc, {})
    ddg = set_search_region(selected_cc)
    st.session_state.user_region = {
        "country_code": selected_cc, "country_name": selected_country_name_sb,
        "ddg_region": ddg, "currency_symbol": info.get("currency_symbol", ""),
        "currency_code": info.get("currency_code", ""),
    }
    st.rerun()

active_region = st.session_state.user_region["country_name"]
active_sym = st.session_state.user_region.get("currency_symbol", "")
st.sidebar.success(
    f"Active: {active_region}" + (f" ({active_sym})" if active_sym else "")
)

st.sidebar.markdown("---")

#      Maturity Digest Email      
st.sidebar.markdown("###  Maturity Digest")
if st.sidebar.button("Send 30-Day Digest Email"):
    digest_email = st.session_state.logged_in_user["email"] if st.session_state.logged_in_user else ""
    if not digest_email:
        st.sidebar.warning("Log in to receive the digest.")
    else:
        all_dep = get_all_deposits()
        if not all_dep.empty and "maturity_date" in all_dep.columns:
            cutoff = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")
            today = datetime.now().strftime("%Y-%m-%d")
            maturing = all_dep[
                (all_dep["fd_status"] == "ACTIVE") &
                (all_dep["maturity_date"].fillna("9999-12-31").str[:10] <= cutoff) &
                (all_dep["maturity_date"].fillna("0000-00-00").str[:10] >= today)
            ]
            if maturing.empty:
                st.sidebar.info("No deposits maturing in the next 30 days.")
            elif send_digest_email(digest_email, maturing):
                st.sidebar.success(f"Digest sent to {digest_email}!")
            else:
                st.sidebar.warning("Email not configured (set SMTP_HOST, SMTP_USER, SMTP_PASSWORD).")

st.sidebar.markdown("---")

#      System Status        ─
st.sidebar.markdown("###  System Status")
langfuse_active = os.getenv("LANGFUSE_PUBLIC_KEY") and os.getenv("LANGFUSE_SECRET_KEY")
nvidia_active = bool(os.getenv("NVIDIA_API_KEY"))
db_active = DB_PATH.exists()

st.sidebar.markdown(
    f"{'' if nvidia_active else ''} NVIDIA API  \n"
    f"{'' if langfuse_active else ''} Langfuse Observability  \n"
    f"{'' if db_active else ''} Database"
)

#      Quick DB Stats        ─
st.sidebar.markdown("---")
st.sidebar.markdown("###  Database Records")

def load_fd_table() -> pd.DataFrame:
    if not DB_PATH.exists():
        return pd.DataFrame()
    try:
        with sqlite3.connect(DB_PATH) as conn:
            return pd.read_sql_query("SELECT * FROM fixed_deposit ORDER BY fd_id DESC LIMIT 20", conn)
    except Exception:
        return pd.DataFrame()

fd_df = load_fd_table()
if not fd_df.empty:
    st.sidebar.dataframe(fd_df[["fd_id", "bank_name", "product_type", "initial_amount", "fd_status"]],
                          use_container_width=True, key="sidebar_df")
else:
    st.sidebar.info("No FD records found.")

if st.sidebar.button("Refresh Data"):
    st.rerun()

st.sidebar.markdown("---")
if st.sidebar.button("Reset Session / Clear Chat"):
    reset_session()

st.sidebar.markdown("---")
st.sidebar.markdown("###  Debug Info")
st.sidebar.json({
    "Country": st.session_state.user_region["country_code"],
    "DDG Region": st.session_state.user_region["ddg_region"],
    "Currency": st.session_state.user_region["currency_symbol"],
    "Langfuse Session": st.session_state.get("langfuse_session_id", "N/A"),
    "Logged In": st.session_state.logged_in_user["email"] if st.session_state.logged_in_user else "None",
})