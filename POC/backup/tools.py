# tools.py
import os
import sqlite3
import smtplib
import tempfile
import io
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from pathlib import Path
from typing import Type

import pandas as pd
from crewai.tools import BaseTool, tool
from pydantic import BaseModel, Field
from langchain_community.tools import DuckDuckGoSearchResults
from langchain_community.utilities import DuckDuckGoSearchAPIWrapper
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet

# --- Configuration & Globals ---
DB_PATH = Path(__file__).resolve().parent / "bank_poc.db"

ddg_news_wrapper = DuckDuckGoSearchAPIWrapper(
    source="news",
    max_results=5,
    region="in-in",
    time="y"
)

langchain_ddg_tool = DuckDuckGoSearchResults(
    api_wrapper=ddg_news_wrapper,
    output_format="list"
)

# --- Tool Schemas ---

class PDFInput(BaseModel):
    account_number: str = Field(..., description="Account Number of the customer")
    fd_id: int = Field(..., description="The newly created FD ID")
    amount: float = Field(..., description="FD Amount")
    bank_name: str = Field(..., description="Bank Name")
    rate: float = Field(..., description="Interest Rate")
    tenure: int = Field(..., description="Tenure in months")
    maturity_date: str = Field(..., description="Maturity Date YYYY-MM-DD")
    customer_name: str = Field(..., description="Customer Name")

class EmailInput(BaseModel):
    to_email: str = Field(..., description="Recipient email address")
    subject: str = Field(..., description="Email subject line")
    body: str = Field(..., description="Plain text body of the email")
    attachment_path: str = Field(default=None, description="Optional: Absolute path to PDF file to attach")

class FDCreationInput(BaseModel):
    first_name: str = Field(..., description="Customer's first name")
    last_name: str = Field(..., description="Customer's last name")
    email: str = Field(..., description="Customer's email address")
    user_address: str = Field(..., description="Customer's full address")
    pin_number: str = Field(..., description="6-digit PIN code")
    mobile_number: str = Field(..., description="10-digit mobile number")
    pan_number: str = Field(..., description="PAN number")
    aadhaar_number: str = Field(..., description="12-digit Aadhaar number")
    account_number: str = Field(default=None, description="Existing account number if customer exists")
    initial_amount: float = Field(..., description="FD Amount")
    tenure_months: int = Field(..., description="FD Tenure in months")
    bank_name: str = Field(..., description="Bank Name")
    interest_rate: float = Field(..., description="Interest Rate")

class SQLQueryInput(BaseModel):
    query: str = Field(..., description="A read-only SQL SELECT query to execute on the bank database.")

# --- Tool Definitions ---

@tool("DuckDuckGo News Search")
def search_news(query: str) -> str:
    """
    Search for recent news articles using DuckDuckGo.
    The input should be a search query string.
    Returns a string representation of the results including title, link, and snippet.
    """
    results = langchain_ddg_tool.invoke(query)
    return str(results)

@tool("Fixed Deposit Projection Calculator")
def fd_projection(principal: float, rate: float, tenure: int) -> str:
    """Calculate fixed deposit maturity amount and interest earned assuming quarterly compounding."""
    r = rate / 100
    n = 4  # Quarterly
    t = tenure
    amount = principal * (1 + r/n)**(n*t)
    interest = amount - principal
    return f"Maturity Amount: {amount:.2f}, Interest Earned: {interest:.2f}"

class FDInvoicePDFTool(BaseTool):
    name: str = "FD Invoice PDF Generator"
    description: str = "Generates a professional PDF invoice for a Fixed Deposit and returns the file path."
    args_schema: Type[BaseModel] = PDFInput

    def _run(self, account_number: str, fd_id: int, amount: float, bank_name: str, 
             rate: float, tenure: int, maturity_date: str, customer_name: str) -> str:
        
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
        filename = temp_file.name
        temp_file.close()

        doc = SimpleDocTemplate(filename, pagesize=letter)
        elements = []
        styles = getSampleStyleSheet()

        title = Paragraph("<b>Fixed Deposit Confirmation</b>", styles['Title'])
        elements.append(title)
        elements.append(Spacer(1, 12))

        data = [
            ["Customer Name", customer_name],
            ["Account Number", account_number],
            ["FD ID", str(fd_id)],
            ["Bank Name", bank_name],
            ["Deposit Amount", f"₹ {amount:,.2f}"],
            ["Interest Rate", f"{rate}%"],
            ["Tenure", f"{tenure} Months"],
            ["Maturity Date", maturity_date],
            ["Status", "ACTIVE"]
        ]

        table = Table(data, colWidths=[150, 300], hAlign='LEFT')
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 12),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]))
        elements.append(table)
        
        doc.build(elements)
        return filename

class EmailSenderTool(BaseTool):
    name: str = "Email Dispatcher with PDF"
    description: str = "Sends an email to the user with an optional PDF attachment."
    args_schema: Type[BaseModel] = EmailInput

    def _run(self, to_email: str, subject: str, body: str, attachment_path: str = None) -> str:
        try:
            smtp_server = os.getenv("SMTP_SERVER", "smtp.gmail.com")
            smtp_port = int(os.getenv("SMTP_PORT", 587))
            smtp_user = os.getenv("SMTP_USER")
            smtp_password = os.getenv("SMTP_PASSWORD")

            if not smtp_user or not smtp_password:
                return "Email skipped: SMTP credentials not configured."

            msg = MIMEMultipart()
            msg['From'] = smtp_user
            msg['To'] = to_email
            msg['Subject'] = subject
            msg.attach(MIMEText(body, 'plain'))

            if attachment_path and Path(attachment_path).exists():
                with open(attachment_path, "rb") as f:
                    part = MIMEApplication(f.read(), Name=Path(attachment_path).name)
                part['Content-Disposition'] = f'attachment; filename="{Path(attachment_path).name}"'
                msg.attach(part)

            server = smtplib.SMTP(smtp_server, smtp_port)
            server.starttls()
            server.login(smtp_user, smtp_password)
            server.sendmail(smtp_user, to_email, msg.as_string())
            server.quit()
            
            if attachment_path:
                try:
                    os.remove(attachment_path)
                except:
                    pass
                    
            return f"Email sent successfully to {to_email}."
        except Exception as e:
            return f"Failed to send email: {str(e)}"

class FixedDepositCreationTool(BaseTool):
    name: str = "Fixed Deposit Creation Manager"
    description: str = """
    Creates a Fixed Deposit by handling the entire backend workflow:
    1. Identifies if the user is new or existing.
    2. Creates User, Address, and KYC records if new.
    3. Checks 'accounts' table balance and deducts the FD amount.
    4. Creates the Fixed Deposit record.
    5. Returns a detailed success message.
    """
    args_schema: Type[BaseModel] = FDCreationInput

    def _run(self, first_name: str, last_name: str, email: str, user_address: str, 
             pin_number: str, mobile_number: str, pan_number: str, aadhaar_number: str,
             account_number: str, initial_amount: float, tenure_months: int, 
             bank_name: str, interest_rate: float) -> str:
        
        try:
            with sqlite3.connect(DB_PATH) as conn:
                cursor = conn.cursor()
                conn.execute("PRAGMA foreign_keys = ON;")

                user_id = None
                is_new_user = False

                if account_number:
                    cursor.execute("SELECT user_id FROM users WHERE account_number = ?", (account_number,))
                    row = cursor.fetchone()
                    if row:
                        user_id = row[0]
                
                if not user_id:
                    is_new_user = True
                    if not account_number:
                        cursor.execute("SELECT account_number FROM users WHERE account_number IS NOT NULL")
                        existing_users = {row[0] for row in cursor.fetchall()}
                        cursor.execute("SELECT account_number FROM accounts WHERE account_number IS NOT NULL")
                        existing_accounts = {row[0] for row in cursor.fetchall()}
                        all_existing = existing_users.union(existing_accounts)
                        for _ in range(10):
                            gen = str(random.randint(10**11, 10**12 - 1))
                            if gen not in all_existing:
                                account_number = gen
                                break
                    
                    cursor.execute(
                        "INSERT INTO users (first_name, last_name, account_number, email, is_account_active) VALUES (?, ?, ?, ?, 1)",
                        (first_name, last_name, account_number, email)
                    )
                    user_id = cursor.lastrowid
                    
                    cursor.execute(
                        "INSERT INTO address (user_id, user_address, pin_number, mobile_number, mobile_verified) VALUES (?, ?, ?, ?, 1)",
                        (user_id, user_address, pin_number, mobile_number)
                    )
                    
                    cursor.execute(
                        """INSERT INTO kyc_verification 
                           (user_id, address_id, account_number, pan_number, aadhaar_number, kyc_status, verified_at, created_at, updated_at) 
                           VALUES (?, (SELECT address_id FROM address WHERE user_id = ?), ?, ?, ?, 'VERIFIED', datetime('now'), datetime('now'), datetime('now'))""",
                        (user_id, user_id, account_number, pan_number, aadhaar_number)
                    )

                cursor.execute("SELECT account_id, balance FROM accounts WHERE user_id = ?", (user_id,))
                fin_acc_row = cursor.fetchone()
                fd_amount = float(initial_amount)
                
                if not fin_acc_row:
                    cursor.execute(
                        "INSERT INTO accounts (user_id, account_number, account_type, balance, email) VALUES (?, ?, 'Savings', ?, ?)",
                        (user_id, account_number, fd_amount, email)
                    )
                    fin_account_id = cursor.lastrowid
                    current_balance = fd_amount
                else:
                    fin_account_id = fin_acc_row[0]
                    current_balance = fin_acc_row[1]
                
                if current_balance < fd_amount:
                    return (f"Transaction Failed: Insufficient balance. "
                            f"Current: {current_balance:,.2f}, Requested: {fd_amount:,.2f}.")
                
                new_balance = current_balance - fd_amount
                cursor.execute("UPDATE accounts SET balance = ? WHERE account_id = ?", (new_balance, fin_account_id))
                
                maturity_date = (datetime.now() + timedelta(days=30*tenure_months)).strftime("%Y-%m-%d")
                cursor.execute(
                    """INSERT INTO fixed_deposit 
                       (user_id, initial_amount, bank_name, tenure_months, interest_rate, maturity_date, premature_penalty_percent, fd_status) 
                       VALUES (?, ?, ?, ?, ?, ?, 1.0, 'ACTIVE')""",
                    (user_id, fd_amount, bank_name, tenure_months, interest_rate, maturity_date)
                )
                fd_id = cursor.lastrowid
                conn.commit()
                
                base_msg = (f"Success! FD created for account {account_number}. "
                            f"Amount: {fd_amount:,.2f}. "
                            f"Rate: {interest_rate}%. "
                            f"Maturity Date: {maturity_date}. "
                            f"FD ID: {fd_id}. "
                            f"Remaining Balance: {new_balance:,.2f}. "
                            f"Customer Name: {first_name} {last_name}. "
                            f"Email: {email}.")
                
                return base_msg
        except Exception as e:
            return f"Error processing FD creation: {str(e)}"

class BankDatabaseTool(BaseTool):
    name: str = "Bank Database Query Tool"
    description: str = "Executes read-only SQL queries on the local SQLite database 'bank_poc.db'."
    args_schema: Type[BaseModel] = SQLQueryInput

    def _run(self, query: str) -> str:
        if not DB_PATH.exists():
            return f"Error: Database file not found at {DB_PATH}"

        try:
            with sqlite3.connect(DB_PATH) as conn:
                conn.row_factory = sqlite3.Row 
                cursor = conn.execute(query)
                rows = cursor.fetchall()
                
                if not rows:
                    return "No results found for the query."
                headers = rows[0].keys()
                output = [", ".join(headers)]
                for row in rows:
                    output.append(", ".join([str(val) for val in row]))
                
                return "\n".join(output)
        except Exception as e:
            return f"Error executing SQL query: {str(e)}"