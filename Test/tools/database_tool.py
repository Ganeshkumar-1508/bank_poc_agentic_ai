# tools/database_tool.py
import sqlite3
import random
from datetime import datetime, timedelta
from pathlib import Path
from typing import Type, Optional, List

from crewai.tools import BaseTool
from pydantic import BaseModel, Field, PrivateAttr

from tools.config import DB_PATH, langchain_db, fetch_country_data

# ---------------------------------------------------------------------------
# Supported product types (synced with PRODUCT_REGISTRY in calculator_tool.py)
# ---------------------------------------------------------------------------

DEPOSIT_PRODUCT_TYPES = (
    # ── Global ──────────────────────────────────────────────────────────────
    "FD",           # Fixed Deposit
    "TD",           # Term Deposit (US / AU / NZ / UK)
    "RD",           # Recurring Deposit
    "MF",           # Mutual Fund / SIP (lump sum or SIP)
    "BOND",         # Corporate / Government Bond
    "MMARKET",      # Money Market Account
    # ── India ───────────────────────────────────────────────────────────────
    "PPF",          # Public Provident Fund
    "NSC",          # National Savings Certificate
    "KVP",          # Kisan Vikas Patra
    "SSY",          # Sukanya Samriddhi Yojana
    "SCSS",         # Senior Citizens Savings Scheme
    "SGB",          # Sovereign Gold Bond
    "NPS",          # National Pension System
    # ── United States ───────────────────────────────────────────────────────
    "CD",           # Certificate of Deposit
    "T-BILL",       # Treasury Bill
    "T-NOTE",       # Treasury Note
    "T-BOND",       # Treasury Bond
    "I-BOND",       # I Bond (inflation-protected)
    # ── United Kingdom ──────────────────────────────────────────────────────
    "ISA",          # Individual Savings Account
    "PREMIUM_BOND", # Premium Bond (NS&I)
    # ── Canada ──────────────────────────────────────────────────────────────
    "GIC",          # Guaranteed Investment Certificate
    # ── Singapore ───────────────────────────────────────────────────────────
    "SSB",          # Singapore Savings Bond
    # ── Gulf / Islamic ──────────────────────────────────────────────────────
    "MURABAHA",     # Murabaha / Islamic Term Deposit
)

_PRODUCT_TYPES_DESC = (
    "Investment product type. One of: "
    + ", ".join(DEPOSIT_PRODUCT_TYPES)
    + ". Defaults to 'FD'."
)

# ---------------------------------------------------------------------------
# Input schemas
# ---------------------------------------------------------------------------

class SQLQueryInput(BaseModel):
    query: str = Field(..., description="SQL query string")


class UniversalDepositInput(BaseModel):
    first_name: str
    last_name: str
    email: str
    user_address: str
    pin_number: str
    mobile_number: str
    kyc_details_1: str = Field(..., description="Primary KYC Document: TYPE-VALUE (e.g. SSN-123456789)")
    kyc_details_2: str = Field(..., description="Secondary KYC Document: TYPE-VALUE (e.g. PASSPORT-GH12345)")
    account_number: Optional[str] = None
    product_type: str = Field(default="FD", description=_PRODUCT_TYPES_DESC)
    initial_amount: float = Field(
        ...,
        description=(
            "Principal amount for lump-sum products (FD, TD, NSC, KVP, SGB, CD, BOND, GIC, …), "
            "monthly installment for installment products (RD, MF-SIP, NPS), "
            "or annual deposit for PPF / SSY."
        ),
    )
    tenure_months: int = Field(
        ...,
        description=(
            "Tenure in months. Product defaults if not provided: "
            "PPF=180, NSC=60, KVP=115, SSY=252, SCSS=60, SGB=96."
        ),
    )
    bank_name: str
    interest_rate: float
    compounding_freq: str = Field(
        default="quarterly",
        description="monthly / quarterly / half_yearly / yearly. Quarterly is default for FD/TD/RD.",
    )
    country_code: str = Field(default="IN", description="ISO 3166-1 alpha-2 country code (e.g. IN, US, GB, CA, SG).")


# ---------------------------------------------------------------------------
# BankDatabaseTool — read-only SELECT
# ---------------------------------------------------------------------------

class BankDatabaseTool(BaseTool):
    """Read-only SQL queries against the bank SQLite database."""

    name: str = "Bank Database Query Tool"
    description: str = (
        "Runs a SQL SELECT query against the bank SQLite database. "
        "Input: a valid SQL query string. Returns the result as a formatted table string."
    )
    args_schema: Type[BaseModel] = SQLQueryInput

    def _run(self, query: str) -> str:
        try:
            result = langchain_db.run(query)
            if len(result) > 3000:
                result = result[:3000] + "\n... [truncated — add LIMIT to your query]"
            return result if result else "Query returned no rows."
        except Exception as e:
            return f"SQL error: {e}"


# ---------------------------------------------------------------------------
# RatesCacheSQLTool — SELECT / INSERT / UPDATE for the rates cache
# ---------------------------------------------------------------------------

class RatesCacheSQLTool(BaseTool):
    """SQL tool for reading and writing the interest_rates_catalog cache."""

    name: str = "Rates Cache SQL Tool"
    description: str = (
        "Run any SQL statement against bank_poc.db. "
        "Use SELECT to check the interest_rates_catalog cache, "
        "UPDATE to deactivate stale rows (set is_active=0), and INSERT to persist fresh rates. "
        "product_type column accepts any of: " + ", ".join(DEPOSIT_PRODUCT_TYPES) + ". "
        "Input: a single valid SQL statement."
    )
    args_schema: Type[BaseModel] = SQLQueryInput

    def _run(self, query: str) -> str:
        try:
            result = langchain_db.run(query)
            if len(result) > 3000:
                result = result[:3000] + "\n... [truncated]"
            return result if result else "Query executed successfully (no rows returned)."
        except Exception as e:
            return f"SQL error: {e}"


rates_sql_tool = RatesCacheSQLTool()


# ---------------------------------------------------------------------------
# UniversalDepositCreationTool — creates any product record in SQLite
# ---------------------------------------------------------------------------

_db_schema_migrated = False


class UniversalDepositCreationTool(BaseTool):
    name: str = "Deposit Creator"
    description: str = (
        "Creates any investment deposit record (FD, RD, PPF, NSC, KVP, SSY, SCSS, SGB, NPS, MF, BOND, "
        "CD, T-BILL, T-NOTE, T-BOND, I-BOND, ISA, GIC, MURABAHA, MMARKET, PREMIUM_BOND, SSB) in SQLite. "
        "Handles schema updates and country codes automatically."
    )
    args_schema: Type[BaseModel] = UniversalDepositInput

    def _run(self, first_name, last_name, email, user_address, pin_number, mobile_number,
             kyc_details_1, kyc_details_2, initial_amount, tenure_months, bank_name,
             interest_rate, account_number=None, product_type="FD",
             compounding_freq="quarterly", country_code="IN"):
        global _db_schema_migrated
        try:
            # Normalise product_type
            product_type = product_type.upper().strip()
            if product_type not in DEPOSIT_PRODUCT_TYPES:
                # Accept FD as safe fallback for unknown types; log as-is
                pass  # store as provided; DB is flexible text column

            with sqlite3.connect(DB_PATH) as conn:
                cursor = conn.cursor()
                conn.execute("PRAGMA foreign_keys = ON;")

                if not _db_schema_migrated:
                    cursor.execute("PRAGMA table_info(kyc_verification)")
                    columns = [col[1] for col in cursor.fetchall()]
                    if "pan_number" in columns and "kyc_details_1" not in columns:
                        try:
                            cursor.execute("ALTER TABLE kyc_verification ADD COLUMN kyc_details_1 TEXT")
                            cursor.execute("ALTER TABLE kyc_verification ADD COLUMN kyc_details_2 TEXT")
                            cursor.execute("UPDATE kyc_verification SET kyc_details_1 = 'PAN-' || pan_number WHERE pan_number IS NOT NULL")
                            cursor.execute("UPDATE kyc_verification SET kyc_details_2 = 'AADHAAR-' || aadhaar_number WHERE aadhaar_number IS NOT NULL")
                        except sqlite3.OperationalError:
                            pass
                    for stmt in [
                        "ALTER TABLE fixed_deposit ADD COLUMN product_type TEXT DEFAULT 'FD'",
                        "ALTER TABLE fixed_deposit ADD COLUMN monthly_installment REAL",
                        "ALTER TABLE fixed_deposit ADD COLUMN compounding_freq TEXT DEFAULT 'quarterly'",
                        "ALTER TABLE address ADD COLUMN country_code TEXT DEFAULT 'IN'",
                    ]:
                        try:
                            cursor.execute(stmt)
                        except sqlite3.OperationalError:
                            pass
                    _db_schema_migrated = True

                currency_code = fetch_country_data().get(country_code.upper(), {}).get("currency_code", "USD")
                user_id = account_id = None

                if account_number:
                    cursor.execute("SELECT user_id FROM users WHERE account_number = ?", (account_number,))
                    row = cursor.fetchone()
                    if row:
                        user_id = row[0]

                if not user_id:
                    if not account_number:
                        cursor.execute("SELECT account_number FROM users WHERE account_number IS NOT NULL")
                        existing = {r[0] for r in cursor.fetchall()}
                        cursor.execute("SELECT account_number FROM accounts WHERE account_number IS NOT NULL")
                        existing |= {r[0] for r in cursor.fetchall()}
                        for _ in range(10):
                            gen = str(random.randint(10**11, 10**12 - 1))
                            if gen not in existing:
                                account_number = gen
                                break

                    cursor.execute(
                        "INSERT INTO users (first_name, last_name, account_number, email, is_account_active) VALUES (?, ?, ?, ?, 1)",
                        (first_name, last_name, account_number, email),
                    )
                    user_id = cursor.lastrowid
                    cursor.execute(
                        "INSERT INTO address (user_id, user_address, pin_number, mobile_number, mobile_verified, country_code) VALUES (?, ?, ?, ?, 1, ?)",
                        (user_id, user_address, pin_number, mobile_number, country_code),
                    )
                    cursor.execute("""
                        INSERT INTO kyc_verification
                        (user_id, address_id, account_number, kyc_details_1, kyc_details_2,
                         kyc_status, verified_at, created_at, updated_at)
                        VALUES (?, (SELECT address_id FROM address WHERE user_id = ?),
                                ?, ?, ?, 'VERIFIED', datetime('now'), datetime('now'), datetime('now'))
                    """, (user_id, user_id, account_number, kyc_details_1, kyc_details_2))
                    cursor.execute(
                        "INSERT INTO accounts (user_id, account_number, account_type, balance, email, currency_code) VALUES (?, ?, 'SAVINGS', 0.00, ?, ?)",
                        (user_id, account_number, email, currency_code),
                    )
                    account_id = cursor.lastrowid

                if account_id is None:
                    cursor.execute("SELECT account_id FROM accounts WHERE user_id = ? LIMIT 1", (user_id,))
                    row = cursor.fetchone()
                    if row:
                        account_id = row[0]
                    else:
                        cursor.execute(
                            "INSERT INTO accounts (user_id, account_number, account_type, balance, email, currency_code) VALUES (?, ?, 'SAVINGS', 0.00, ?, ?)",
                            (user_id, account_number, email, currency_code),
                        )
                        account_id = cursor.lastrowid

                if tenure_months is None:
                    return "Error: tenure_months is required."

                maturity = (datetime.now() + timedelta(days=30 * tenure_months)).strftime("%Y-%m-%d")

                # For installment-based products, store amount as monthly_installment
                _installment_products = {"RD", "MF", "NPS", "PPF", "SSY"}
                monthly_installment = initial_amount if product_type in _installment_products else None

                cursor.execute("""
                    INSERT INTO fixed_deposit
                    (user_id, initial_amount, bank_name, tenure_months, interest_rate,
                     maturity_date, premature_penalty_percent, fd_status,
                     product_type, monthly_installment, compounding_freq)
                    VALUES (?, ?, ?, ?, ?, ?, 1.0, 'ACTIVE', ?, ?, ?)
                """, (user_id, initial_amount, bank_name, tenure_months, interest_rate,
                      maturity, product_type, monthly_installment, compounding_freq))
                fd_id = cursor.lastrowid

                ref_no = "TXN" + "".join(random.choices("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789", k=9))
                cursor.execute("""
                    INSERT INTO transactions
                    (fd_id, account_id, user_id, txn_type, txn_amount, currency_code,
                     txn_status, reference_no, remarks, txn_date)
                    VALUES (?, ?, ?, 'DEPOSIT', ?, ?, 'SUCCESS', ?, ?, datetime('now'))
                """, (fd_id, account_id, user_id, initial_amount, currency_code,
                      ref_no, f"Opening {product_type} — {bank_name}"))
                conn.commit()

                return (
                    f"Success! {product_type} Created.\n"
                    f"ID: {fd_id}\nAccount: {account_number}\nProduct: {product_type}\n"
                    f"Amount: {initial_amount}\nCurrency: {currency_code}\nCountry: {country_code}\n"
                    f"Rate: {interest_rate}%\nFrequency: {compounding_freq}\n"
                    f"Maturity: {maturity}\nTransaction Ref: {ref_no}"
                )
        except Exception as e:
            return f"Error: {e}"


# ---------------------------------------------------------------------------
# NL2SQL — natural-language SQL queries
# ---------------------------------------------------------------------------

try:
    from crewai_tools import NL2SQLTool as _CrewAINL2SQLTool
    _NL2SQL_AVAILABLE = True
except ImportError:
    _NL2SQL_AVAILABLE = False
    _CrewAINL2SQLTool = None


def _build_nl2sql_tool():
    if not _NL2SQL_AVAILABLE:
        return None
    try:
        return _CrewAINL2SQLTool(db_uri=f"sqlite:///{DB_PATH}")
    except Exception:
        return None


nl2sql_tool = _build_nl2sql_tool()


class NL2SQLInput(BaseModel):
    question: str = Field(
        ...,
        description="A natural-language question about the bank database, e.g. 'How many active FDs does John Doe have?'",
    )


class SafeNL2SQLTool(BaseTool):
    """Natural-language SQL tool — accepts plain-English, generates and executes SQL."""

    name: str = "Natural Language SQL Query"
    description: str = (
        "Answers natural-language questions about the bank database by auto-generating SQL SELECT queries. "
        "Use for: user lookups, deposit history, KYC status checks, account summaries. "
        "Supports all product types in the product_type column: " + ", ".join(DEPOSIT_PRODUCT_TYPES) + ". "
        "Input: a plain English question. Do NOT use for write operations."
    )
    args_schema: Type[BaseModel] = NL2SQLInput

    def _run(self, question: str) -> str:
        if not _NL2SQL_AVAILABLE:
            return "NL2SQL_ERROR: crewai-tools not installed. Run: pip install crewai-tools"
        if nl2sql_tool is None:
            return f"NL2SQL_ERROR: Could not initialise NL2SQLTool for {DB_PATH}."
        try:
            result = nl2sql_tool._run(question)
            if not result or str(result).strip() == "":
                return "Query returned no rows."
            result_str = str(result)
            if len(result_str) > 3000:
                result_str = result_str[:3000] + "\n... [truncated]"
            return result_str
        except Exception as e:
            return f"NL2SQL_ERROR: {e}"


# ---------------------------------------------------------------------------
# SQLDatabaseToolkit — 4 granular LangChain SQL tools wrapped for CrewAI
# ---------------------------------------------------------------------------

class LangChainToolWrapper(BaseTool):
    """Wraps a LangChain tool as a CrewAI BaseTool for Pydantic v2 compatibility."""
    name: str = ""
    description: str = ""
    _lc_tool: object = PrivateAttr(default=None)

    def _run(self, query: str = "") -> str:
        try:
            result = self._lc_tool.invoke(query or "")
            return str(result) if result is not None else ""
        except Exception as e:
            return f"Tool error: {e}"


_toolkit_tools_cache: Optional[List] = None


def get_sql_toolkit_tools(llm=None) -> List:
    """
    Returns the 4 LangChain SQLDatabaseToolkit tools wrapped for CrewAI:
    sql_db_list_tables, sql_db_schema, sql_db_query_checker, sql_db_query.
    """
    global _toolkit_tools_cache
    if _toolkit_tools_cache is not None:
        return _toolkit_tools_cache

    from langchain_community.agent_toolkits import SQLDatabaseToolkit

    if llm is None:
        from tools.config import get_llm_3
        llm = get_llm_3()

    toolkit = SQLDatabaseToolkit(db=langchain_db, llm=llm)
    wrapped = []
    for lc_tool in toolkit.get_tools():
        wrapper = LangChainToolWrapper(name=lc_tool.name, description=lc_tool.description)
        wrapper._lc_tool = lc_tool
        wrapped.append(wrapper)

    _toolkit_tools_cache = wrapped
    return wrapped


def get_all_sql_tools(llm=None) -> List:
    """Returns [SafeNL2SQLTool] + get_sql_toolkit_tools(llm) for a fully-equipped db_agent."""
    tools = [SafeNL2SQLTool()]
    try:
        tools += get_sql_toolkit_tools(llm=llm)
    except Exception:
        pass
    return tools