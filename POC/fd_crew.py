import os
import sqlite3
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from pathlib import Path
from typing import Union, Type
from datetime import datetime, timedelta
import random
import tempfile
import io
from crewai import Agent, Task, Crew, Process, CrewOutput
from crewai.tools import BaseTool, tool 
from pydantic import BaseModel, Field
from langchain_community.tools import DuckDuckGoSearchResults
from langchain_community.utilities import DuckDuckGoSearchAPIWrapper
from langchain_nvidia import NVIDIA
from dotenv import load_dotenv
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet

load_dotenv()  

if 'NVIDIA_API_KEY' not in os.environ:
    raise ValueError("Please set the NVIDIA_API_KEY environment variable.")

def get_llm():
    return NVIDIA(model="qwen/qwen3-next-80b-a3b-instruct") 

def get_llm_2():
    return NVIDIA(model="qwen/qwen3-next-80b-a3b-instruct")

ddg_news_wrapper = DuckDuckGoSearchAPIWrapper(
    source="news",      # Fetches news articles
    max_results=5,      # Number of articles
    region="in-in",     # India region
    time="y"            # 1-2 year news for better relevance in financial data
)

langchain_ddg_tool = DuckDuckGoSearchResults(
    api_wrapper=ddg_news_wrapper,
    output_format="list" 
)

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
    n = 4  # 4 for Quarterly compounding, 12 for Monthly compounding, etc.
    t = tenure
    amount = principal * (1 + r/n)**(n*t)
    interest = amount - principal
    return f"Maturity Amount: {amount:.2f}, Interest Earned: {interest:.2f}"

class PDFInput(BaseModel):
    account_number: str = Field(..., description="Account Number of the customer")
    fd_id: int = Field(..., description="The newly created FD ID")
    amount: float = Field(..., description="FD Amount")
    bank_name: str = Field(..., description="Bank Name")
    rate: float = Field(..., description="Interest Rate")
    tenure: int = Field(..., description="Tenure in months")
    maturity_date: str = Field(..., description="Maturity Date YYYY-MM-DD")
    customer_name: str = Field(..., description="Customer Name")

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

class EmailInput(BaseModel):
    to_email: str = Field(..., description="Recipient email address")
    subject: str = Field(..., description="Email subject line")
    body: str = Field(..., description="Plain text body of the email")
    attachment_path: str = Field(default=None, description="Optional: Absolute path to PDF file to attach")

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
            
            # Cleanup temp file
            if attachment_path:
                try:
                    os.remove(attachment_path)
                except:
                    pass
                    
            return f"Email sent successfully to {to_email}."
        except Exception as e:
            return f"Failed to send email: {str(e)}"

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

class FixedDepositCreationTool(BaseTool):
    name: str = "Fixed Deposit Creation Manager"
    description: str = """
    Creates a Fixed Deposit by handling the entire backend workflow:
    1. Identifies if the user is new or existing (based on account_number).
    2. Creates User, Address, and KYC records if new.
    3. Checks 'accounts' table balance and deducts the FD amount.
    4. Creates the Fixed Deposit record.
    5. Returns a detailed success message including Account Number, FD ID, Maturity Date, and Email.
    """
    args_schema: Type[BaseModel] = FDCreationInput

    def _run(self, first_name: str, last_name: str, email: str, user_address: str, 
             pin_number: str, mobile_number: str, pan_number: str, aadhaar_number: str,
             account_number: str, initial_amount: float, tenure_months: int, 
             bank_name: str, interest_rate: float) -> str:
        
        base_dir = Path(__file__).resolve().parent
        db_path = base_dir / "bank_poc.db"
        
        try:
            with sqlite3.connect(db_path) as conn:
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
                    fin_account_id = fin_acc_row['account_id']
                    current_balance = fin_acc_row['balance']
                
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
                
                # EMAIL LOGIC REMOVED HERE - Handled by separate Agent now
                
                return base_msg
        except Exception as e:
            return f"Error processing FD creation: {str(e)}"

# -----------------------------------------

DB_SCHEMA_INFO = """
Database Schema for 'bank_poc.db':

1. Table 'users':
   - user_id (INTEGER, PK)
   - first_name (TEXT)
   - last_name (TEXT)
   - account_number (TEXT)
   - email (TEXT) -- NEW COLUMN
   - is_account_active (INTEGER, 0 or 1)

2. Table 'address':
   - address_id (INTEGER, PK)
   - user_id (INTEGER, FK)
   - user_address (TEXT)
   - pin_number (TEXT)
   - mobile_number (TEXT)
   - mobile_verified (INTEGER, 0 or 1)

3. Table 'kyc_verification':
   - kyc_id (INTEGER, PK)
   - user_id (INTEGER, FK)
   - address_id (INTEGER, FK)
   - account_number (TEXT)
   - pan_number (TEXT)
   - aadhaar_number (TEXT)
   - kyc_status (TEXT: 'VERIFIED', 'NOT_VERIFIED')
   - verified_at (DATETIME)
   - created_at (DATETIME)
   - updated_at (DATETIME)

4. Table 'accounts':
   - account_id (INTEGER, PK)
   - user_id (INTEGER, FK)
   - account_number (TEXT, Unique)
   - account_type (TEXT)
   - balance (REAL)
   - email (TEXT) -- NEW COLUMN ADDED
   - created_at (DATETIME)

5. Table 'fixed_deposit':
   - fd_id (INTEGER, PK)
   - user_id (INTEGER, FK)
   - initial_amount (REAL)
   - bank_name (TEXT)
   - tenure_months (INTEGER)
   - interest_rate (REAL)
   - maturity_date (TEXT)
   - premature_penalty_percent (REAL)
   - fd_status (TEXT: 'ACTIVE', etc.)
"""

class SQLQueryInput(BaseModel):
    query: str = Field(..., description="A read-only SQL SELECT query to execute on the bank database.")

class BankDatabaseTool(BaseTool):
    name: str = "Bank Database Query Tool"
    description: str = f"""
    Executes read-only SQL queries on the local SQLite database 'bank_poc.db'.
    Use this to retrieve information about users, addresses, KYC status, and fixed deposits.
    The database contains the following schema:
    {DB_SCHEMA_INFO}
    """
    args_schema: Type[BaseModel] = SQLQueryInput

    def _run(self, query: str) -> str:
        base_dir = Path(__file__).resolve().parent
        db_path = base_dir / "bank_poc.db"
        
        if not db_path.exists():
            return f"Error: Database file not found at {db_path}"

        try:
            with sqlite3.connect(db_path) as conn:
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

db_tool = BankDatabaseTool()

def create_agents():
    llm = get_llm()
    llm_2 = get_llm_2()
    
    query_parser_agent = Agent(
        role="Financial Query Analyzer",
        goal="Extract specific investment amount and tenure from natural language user queries.",
        backstory="You are an expert at understanding user intent and extracting structured financial data.",
        llm=llm_2,
        verbose=True
    )

    search_agent = Agent(
        role="Fixed Deposit Rate Researcher",
        goal="Find the top fixed deposit providers with the highest interest rates for specific tenures.",
        backstory="You are an expert at searching the web for financial products.",
        tools=[search_news], 
        llm=llm_2,
        verbose=True
    )

    research_agent = Agent(
        role="Financial Researcher",
        goal="Gather detailed information and recent news for each fixed deposit provider.",
        backstory="You are skilled at researching financial institutions and finding recent articles.",
        tools=[search_news], 
        llm=llm_2,
        verbose=True
    )

    safety_agent = Agent(
        role="Risk Analyst",
        goal="Categorize each fixed deposit provider by safety based on credit ratings and news.",
        backstory="You have expertise in assessing the safety of financial institutions.",
        tools=[search_news], 
        llm=llm,
        verbose=True
    )

    projection_agent = Agent(
        role="Financial Calculator",
        goal="Calculate projected maturity amounts for both General and Senior Citizen categories.",
        backstory="You are precise in financial calculations and can handle multiple scenarios.",
        tools=[fd_projection],
        llm=llm_2,
        verbose=True
    )

    summary_agent = Agent(
        role="Senior Investment Strategist",
        goal="Synthesize raw financial data, market news, safety ratings, and projections into a professional, exhaustive investment thesis.",
        backstory=(
            "You are a veteran Chief Investment Strategist at a leading wealth management firm. "
            "You specialize in Fixed Income portfolios. You excel at connecting the dots between "
            "quantitative data (interest rates, maturity amounts) and qualitative factors (market news, credit ratings). "
            "Your reports are known for being detailed, objective, and highly actionable."
        ),
        llm=llm,
        verbose=True
    )

    provider_search_agent = Agent(
        role="Market Scanner",
        goal="Identify the top 10 most popular and reliable Fixed Deposit providers in the current market.",
        backstory="You have a broad view of the financial market and know how to identify leading institutions.",
        tools=[search_news],
        llm=llm_2,
        verbose=True
    )

    deep_research_agent = Agent(
        role="Senior Financial Investigator",
        goal="Conduct exhaustive research on specific financial institutions to find credit ratings, recent news, and financial health.",
        backstory="You are an investigative journalist specializing in finance.",
        tools=[search_news],
        llm=llm,
        verbose=True
    )

    research_compilation_agent = Agent(
        role="Research Editor",
        goal="Compile detailed findings into a structured, exhaustive report.",
        backstory="You are an editor who ensures all critical details are presented clearly.",
        llm=llm,
        verbose=True
    )

    db_agent = Agent(
        role="Bank Database Administrator",
        goal="Answer questions about bank data by generating accurate SQL queries and analyzing the results.",
        backstory=f"""
        You are an expert SQL developer with full read-only access to the bank's internal SQLite database.
        You know the database schema by heart and can join tables (users, address, kyc_verification, fixed_deposit) effectively.
        {DB_SCHEMA_INFO}
        When asked a question, you construct a SQL SELECT query, execute it, and explain the results clearly.
        """,
        tools=[db_tool],
        llm=llm,
        verbose=True
    )
    
    # --- UPDATED ONBOARDING AGENT ---
    onboarding_agent = Agent(
        role="Customer Onboarding Specialist",
        goal="Gather details and use the tool to create the FD.",
        backstory=(
            "You are a helpful and efficient bank assistant. "
            
            "CRITICAL RULE 0: SEARCH RESTRICTIONS "
            "You HAVE access to the 'DuckDuckGo News Search' tool. "
            "You MUST ONLY use it to find INTEREST RATES. "
            "DO NOT use it to find customer details (like Name, Email, Phone, Address, PAN, Aadhaar). "
            "ALWAYS ASK THE USER FOR PERSONAL DETAILS. DO NOT SEARCH THE WEB FOR PERSONAL INFO."
            
            "CRITICAL RULE 1: CONVERSATIONAL FLOW (ONE BY ONE) "
            "Check the conversation history to see what is already known. "
            "Identify exactly ONE missing piece of information and ask for it. "
            "Do NOT list all missing questions. Do NOT summarize. Just ask the next question. "
            
            "CRITICAL RULE 2: EXISTING VS NEW CUSTOMER "
            "If the user provides an Account Number, assume they are an EXISTING customer. "
            "STOP asking for Name, Address, Mobile, PAN, Aadhaar, or Email. "
            "Focus only on: FD Amount, Tenure, Bank Name. "
            "If NO Account Number is provided, collect all details (Name, Address, etc.) one by one. "
            
            "CRITICAL RULE 3: AUTOMATIC INTEREST RATE SEARCH & FILL "
            "Once you have the 'Bank Name' AND 'Tenure (in months)': "
            "1. Use the 'DuckDuckGo News Search' tool. Query: '[Bank Name] fixed deposit interest rate for [Tenure] months'. "
            "2. Read the results to find the rate for that specific tenure. "
            "3. Tell the user: 'I found a rate of [X] for [Tenure] months. I will apply this rate to your FD.' "
            "4. DO NOT ask the user to confirm the rate. "
            
            "CRITICAL RULE 4: EXECUTE CREATION "
            "Once you have ALL details (Name, Email, Address, PIN, Mobile, PAN, Aadhaar, FD Amount, Tenure, Bank, Rate), "
            "STOP ASKING QUESTIONS. "
            "Use the 'Fixed Deposit Creation Manager' tool to create the FD. "
            "Do NOT output JSON. Use the tool."
            
            "CRITICAL RULE 5: FINAL OUTPUT FORMAT "
            "Upon success, output a message starting with 'Success!' and containing: "
            "Customer Name, Email, Account Number, FD ID, Bank Name, Amount, Rate, Tenure, Maturity Date."
        ),
        tools=[search_news, FixedDepositCreationTool()], 
        llm=llm_2,
        verbose=True
    )

    # --- UPDATED EMAIL AGENT ---
    email_specialist_agent = Agent(
        role="Email Dispatch Specialist",
        goal="Review FD creation success and send a PDF invoice to the user.",
        backstory=(
            "You are a backend transaction specialist. "
            "You receive the output from the Onboarding Agent. "
            
            "STRICT CONSTRAINTS: "
            "You do NOT have access to the internet. You do NOT have access to search tools. "
            "You must NOT browse the web or search for any information. "
            "You MUST ONLY use the 'FD Invoice PDF Generator' and 'Email Dispatcher with PDF' tools."
            
            "WORKFLOW: "
            "If the output indicates a successful FD creation (contains 'Success', 'FD ID', 'Maturity Date', etc.), "
            "1. Extract the following details from the text: Account Number, FD ID, Amount, Bank Name, Interest Rate, Tenure, Maturity Date, Customer Name, Email. "
            "2. Use the 'FD Invoice PDF Generator' tool with these details to generate a PDF file. "
            "3. Use the 'Email Dispatcher with PDF' tool to send the generated PDF to the customer's email address. "
            "4. Return a final message to the user confirming the FD creation and that the invoice has been emailed."
            
            "IMPORTANT FOR UI RESET: When returning the final success message, start the sentence with 'Success!' "
            "Example: 'Success! FD created... Invoice emailed to [email].'"
            
            "If the input is just a conversational question (e.g., 'What is your name?'), "
            "simply output that text exactly as is. Do nothing else."
        ),
        tools=[FDInvoicePDFTool(), EmailSenderTool()],
        llm=llm_2,
        verbose=True
    )

    manager_agent = Agent(
        role="Crew Manager",
        goal="Identify the user's intent and delegate the task to the appropriate team.",
        backstory="You are a senior manager at a financial firm.",
        llm=llm,
        verbose=True
    )

    return {
        "query_parser_agent": query_parser_agent,
        "search_agent": search_agent,
        "research_agent": research_agent,
        "safety_agent": safety_agent,
        "projection_agent": projection_agent,
        "summary_agent": summary_agent,
        "provider_search_agent": provider_search_agent,
        "deep_research_agent": deep_research_agent,
        "research_compilation_agent": research_compilation_agent,
        "db_agent": db_agent, 
        "onboarding_agent": onboarding_agent, 
        "email_specialist_agent": email_specialist_agent, 
        "manager_agent": manager_agent
    }

#Tasks

def create_analysis_tasks(agents, user_query: str):
    parse_task = Task(
        description=(
            f"Analyze the following user query: '{user_query}'. "
            f"Extract the investment amount and tenure. "
            f"Convert amounts like '100k' to full integers. "
            f"Convert tenure to years. "
            f"Output strictly in the format: 'Amount: [Integer], Tenure: [Integer]'. "
        ),
        expected_output="A string containing 'Amount: [Value], Tenure: [Value]'.",
        agent=agents["query_parser_agent"]
    )

    search_task = Task(
        description=(
            "Based on parsed parameters: {parse_task.output}, identify the tenure. "
            "Search for top fixed deposit interest rates for that specific tenure in India. "
            "CRITICAL: You must find BOTH 'General Interest Rate' and 'Senior Citizen Interest Rate'. "
            "If a provider does not have a specific senior rate, use the general rate for both."
            "CRITICAL COUNT: Return a list of the TOP 10 providers. Do not stop at 5. "
            "Return a list of the top 10 providers in the format: "
            "'Provider: [Name], General Rate: [X.X]%, Senior Rate: [Y.Y]%'"
        ),
        expected_output="A list of exactly 10 fixed deposit providers with both General and Senior interest rates.",
        agent=agents["search_agent"],
        context=[parse_task]
    )

    research_task = Task(
        description=(
            "For each provider in the list: {search_task.output}, "
            "use the search tool to find recent news. "
            "The tool returns a list of news items with 'title', 'link', and 'snippet'. "
            "You MUST include ALL news items returned by the tool (not just one). "
            "Output format (strictly follow this structure for every provider):\n\n"
            "Provider: [Provider Name]\n"
            "News: [Headline 1] | URL: [Link 1]\n"
            "News: [Headline 2] | URL: [Link 2]\n"
            "(Leave a blank line before starting the next provider)\n"
        ),
        expected_output="A structured list of providers with multiple news headlines and corresponding URLs.",
        agent=agents["research_agent"],
        context=[search_task]
    )

    safety_task = Task(
        description=(
            "Based on: {research_task.output}, "
            "categorize each provider's safety as 'Safe', 'Moderate', or 'Risky'. "
            "Format: 'Provider: [Name], Category: [Safe/Moderate/Risky], Reason: [Brief reason]'"
        ),
        expected_output="A list of safety categorizations with reasons.",
        agent=agents["safety_agent"],
        context=[research_task]
    )

    projection_task = Task(
        description=(
            "Calculate projections for each provider found in {search_task.output}. "
            "Use the amount from: {parse_task.output}. "
            "You must perform TWO calculations per provider: "
            "1. Using the General Rate to get General Maturity and General Interest. "
            "2. Using the Senior Rate to get Senior Maturity and Senior Interest. "
            "Use the fd_projection tool for these calculations. "
            "Output a table in strict CSV format with the following headers: "
            "'Provider,General Rate (%),Senior Rate (%),General Maturity,Senior Maturity,General Interest,Senior Interest'"
        ),
        expected_output="A CSV-formatted table with projections for both General and Senior categories.",
        agent=agents["projection_agent"],
        context=[parse_task, search_task]
    )

    summary_task = Task(
        description=(
            "Create a comprehensive, in-depth investment report using the data from:\n"
            "1. Research & News: {research_task.output}\n"
            "2. Safety Categorization: {safety_task.output}\n"
            "3. Financial Projections: {projection_task.output}\n\n"

            "CRITICAL INSTRUCTION FOR NEWS: "
            "The research output contains a list of news items for each provider. "
            "In the 'Market Overview & Provider Analysis' section, you MUST list ALL news items found. "
            "Format each as a bullet point with a clickable link: '- [Headline](URL)'.\n\n"

            "LENGTH & COMPLETENESS: "
            "You must cover ALL 10 providers listed in the research data. "
            "Do not cut off the list or the report early. "
            "If you are running out of space, shorten the 'Strategic Recommendations' slightly, but ensure the 'Market Overview' contains every single provider.\n\n"

            "Your report must be professionally formatted in Markdown and strictly follow this structure:\n\n"

            "# Comprehensive Fixed Deposit Analysis Report\n\n"

            "## 1. Summary\n"
            "- Provide a high-level overview of the best options found for both General and Senior citizens.\n"
            "- Highlight the highest yield for General and Senior citizens separately.\n\n"

            "## 2. Market Overview & Provider Analysis\n"
            "For EACH provider listed in the research data, provide a detailed subsection:\n"
            "- **Provider Name, General Rate & Senior Rate**\n"
            "- **Safety Profile**: (Safe/Moderate/Risky) and the specific reason why.\n"
            "- **Recent News & Sources**: List ALL news items provided in the research data as clickable links.\n\n"

            "## 3. Financial Projection Deep Dive\n"
            "- Analyze the raw numbers for both categories. Discuss General vs Senior Maturity and Interest Earned.\n\n"

            "## 4. Risk vs. Reward Assessment\n"
            "- Categorize findings into 'Maximum Safety', 'High Yield', and 'Balanced Choice' for General investors.\n"
            "- Do the same for Senior Citizens.\n\n"

            "## 5. Strategic Recommendations\n"
            "Based on the user's query and the analysis, provide tailored advice:\n"
            "- **Option A (Conservative)**: Best for capital preservation (Safe).\n"
            "- **Option B (Aggressive)**: Best for maximizing returns (High Rate).\n"
            "- **Option C (Balanced)**: Best mix of safety and return.\n"
            "- Note: If the user is a senior citizen, emphasize the higher rates available to them.\n\n"

            "## 6. Conclusion\n"
            "---\n"
            "*Disclaimer: This report is generated by AI for informational purposes only.*"
        ),
        expected_output="A highly detailed, structured Markdown report covering both General and Senior citizen categories, with clickable news and rating source links included.",
        agent=agents["summary_agent"],
        context=[research_task, safety_task, projection_task] 
    )

    return [parse_task, search_task, research_task, safety_task, projection_task, summary_task]

def create_research_tasks(agents, user_query: str):
    identify_providers_task = Task(
        description=(
            f"Analyze the query: '{user_query}'. "
            f"Identify and list the TOP 10 Fixed Deposit providers (Banks & NBFCs) in India. "
            f"Ensure you find exactly 10 distinct providers. "
            f"Output a simple list of 10 names."
        ),
        expected_output="A list of 10 top Fixed Deposit provider names.",
        agent=agents["provider_search_agent"]
    )

    deep_research_task = Task(
        description=(
            "For EVERY provider in the list: {identify_providers_task.output}, perform exhaustive research. "
            "You must find the following for EACH of the 10 providers:\n"
            "1. Credit Ratings (CARE, ICRA, CRISIL, etc.).\n"
            "2. Interest Rate ranges (General vs Senior Citizen) for common tenures (1yr, 2yr, 5yr).\n"
            "3. Recent News (last 6 months) including headlines and links.\n"
            "4. Financial Health indicators (NPA, Capital Adequacy, or general stability) if available.\n"
            "Ensure you research all 10 providers listed in the previous step. Do not skip any."
        ),
        expected_output="Detailed structured data for all 10 providers.",
        agent=agents["deep_research_agent"],
        context=[identify_providers_task]
    )

    compile_report_task = Task(
        description=(
            "Compile findings from: {deep_research_task.output} into a comprehensive final report. "
            "STRUCTURE: ## Analysis of Top FD Providers\n\n"
            
            "For EACH provider, create a detailed subsection:\n"
            "### [Provider Name]\n"
            "- **Credit Rating**: [Rating Agency - Grade]\n"
            "- **Interest Rates**: [Range for General and Senior citizens]\n"
            "- **Recent News**: [Summaries with clickable links]\n"
            "- **Financial Health**: [Summary of stability]\n\n"

            "CRITICAL INSTRUCTION: "
            "You must include ALL 10 providers identified in the research. "
            "Do not stop halfway. The response must be complete. "
            "If the response is getting too long, reduce the word count of the descriptions slightly, but ensure every single provider from the input list appears in the output."
        ),
        expected_output="A structured markdown report covering all 10 found providers with detailed ratings and news.",
        agent=agents["research_compilation_agent"],
        context=[deep_research_task]
    )

    return [identify_providers_task, deep_research_task, compile_report_task]


def get_analysis_crew(user_query: str):
    agents = create_agents()
    tasks = create_analysis_tasks(agents, user_query)
    return Crew(
        agents=[agents["query_parser_agent"], agents["search_agent"], agents["research_agent"], 
                agents["safety_agent"], agents["projection_agent"], agents["summary_agent"]],
        tasks=tasks,
        process=Process.sequential,
        verbose=True
    )

def get_research_crew(user_query: str):
    agents = create_agents()
    tasks = create_research_tasks(agents, user_query)
    return Crew(
        agents=[agents["provider_search_agent"], agents["deep_research_agent"], agents["research_compilation_agent"]],
        tasks=tasks,
        process=Process.sequential,
        verbose=True
    )

def get_database_crew(user_query: str):
    agents = create_agents()
    
    query_task = Task(
        description=f"""
        Analyze the user's request: '{user_query}'.
        Based on the request, write a SQL query to fetch the required information from the database.
        Execute the query using the Bank Database Query Tool.
        Synthesize the results into a clear, human-readable answer.
        """,
        expected_output="A detailed answer based on the database records. If listing records, present them in a table format.",
        agent=agents["db_agent"]
    )
    
    return Crew(
        agents=[agents["db_agent"]],
        tasks=[query_task],
        process=Process.sequential,
        verbose=True
    )

def get_onboarding_crew(conversation_history: str):
    agents = create_agents()
    
    onboarding_task = Task(
        description=(
            f"Conversation History:\n{conversation_history}\n\n"
            "Continue the onboarding process. Check what info is missing. "
            "If all info is present, use the 'Fixed Deposit Creation Manager' tool to create the FD."
        ),
        expected_output="Either a conversational question asking for missing details, or a result from the FD Creation Tool.",
        agent=agents["onboarding_agent"]
    )

    email_task = Task(
        description=(
            "Review the output from the previous Onboarding Task. "
            "If the output is a conversational question (e.g., asking for name, address, etc.), simply return the text EXACTLY as it is. Do not generate anything else."
            
            "If the output indicates a SUCCESSFUL FD creation (contains 'Success', 'FD ID', 'Maturity Date', etc.): "
            "1. Extract the following details from the text: Account Number, FD ID, Amount, Bank Name, Interest Rate, Tenure, Maturity Date, Customer Name, Email. "
            "2. Use the 'FD Invoice PDF Generator' tool with these details to generate a PDF file. "
            "3. Use the 'Email Dispatcher with PDF' tool to send the generated PDF to the customer's email address. "
            "4. Return a final message to the user confirming the FD creation and that the invoice has been emailed."
        ),
        expected_output="Either the original chat question, or a success message confirming the email was sent.",
        agent=agents["email_specialist_agent"],
        context=[onboarding_task]
    )
    
    return Crew(
        agents=[agents["onboarding_agent"], agents["email_specialist_agent"]], 
        tasks=[onboarding_task, email_task], 
        process=Process.sequential, 
        verbose=True
    )

def run_crew(user_query: str):
    agents = create_agents()
    manager = agents["manager_agent"]
    
    routing_task = Task(
        description=(
            f"Analyze the user query: '{user_query}'\n\n"
            f"Determine the intent:\n"
            f"- If the user asks about calculations, maturity amounts, or comparisons (external data), respond with 'ANALYSIS'.\n"
            f"- If the user asks for general info or detailed reports without calculations, respond with 'RESEARCH'.\n"
            f"- If the user asks about existing users, accounts, KYC status, or current FD records in the system (e.g. 'total tenure', 'list users'), respond with 'DATABASE'.\n"
            f"- If the user wants to open a new account, create a FD, or start onboarding (e.g. 'I want to open an account'), respond with 'ONBOARDING'.\n\n"
            f"Respond with ONLY one word: ANALYSIS, RESEARCH, DATABASE, or ONBOARDING."
        ),
        expected_output="Single word: ANALYSIS, RESEARCH, DATABASE, or ONBOARDING",
        agent=manager
    )
    
    router_crew = Crew(
        agents=[manager],
        tasks=[routing_task],
        verbose=True
    )
    
    route_result = router_crew.kickoff()
    decision = route_result.raw.strip().upper()
    
    if "ANALYSIS" in decision:
        crew = get_analysis_crew(user_query)
        return crew.kickoff()
    elif "DATABASE" in decision:
        crew = get_database_crew(user_query)
        return crew.kickoff()
    elif "ONBOARDING" in decision:
        return type('obj', (object,), {'raw': 'ONBOARDING'})()
    else:
        crew = get_research_crew(user_query)
        return crew.kickoff()