# tools.py
import os
import sqlite3
import smtplib
import tempfile
import io
import requests
import json
import random
import re
import markdown
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from pathlib import Path
from typing import Type, Dict, Any, Optional, List
from typing import ClassVar

# LangChain & LLM Imports
from langchain_community.tools.wikidata.tool import WikidataQueryRun
from langchain_community.utilities.wikidata import WikidataAPIWrapper
from langchain_community.graphs import Neo4jGraph
from langchain_nvidia_ai_endpoints import ChatNVIDIA, NVIDIA
from langchain_core.prompts import PromptTemplate
from langchain_community.tools import DuckDuckGoSearchResults
from langchain_community.utilities import DuckDuckGoSearchAPIWrapper
from crewai.tools import BaseTool, tool
from pydantic import BaseModel, Field

# PDF Generation Imports
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, KeepTogether
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch

# --- Configuration ---
DB_PATH = Path(__file__).resolve().parent / "bank_poc.db"

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password123")
YENTE_URL = os.getenv("YENTE_URL", "http://localhost:8000")

# Initialize Neo4j Graph
graph = Neo4jGraph(
    url=NEO4J_URI,
    username=NEO4J_USER,
    password=NEO4J_PASSWORD
)
try:
    graph.refresh_schema()
    print("Neo4j Schema Refreshed Successfully.")
except Exception as e:
    print(f"Warning: Could not refresh Neo4j schema: {e}")

# Search Tools Setup
ddg_news_wrapper = DuckDuckGoSearchAPIWrapper(max_results=5, time="y")
langchain_ddg_tool = DuckDuckGoSearchResults(api_wrapper=ddg_news_wrapper, output_format="list")

# --- Helper Functions ---

def get_llm_3():
    return NVIDIA(model="qwen/qwen3-next-80b-a3b-instruct") 

def extract_json_balanced(text: str) -> dict:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    start_idx = text.find('{')
    if start_idx == -1: raise ValueError("No JSON object found in response.")
    brace_level = 0
    in_string = False
    escape_next = False
    for i in range(start_idx, len(text)):
        char = text[i]
        if escape_next:
            escape_next = False
            continue
        if char == '\\':
            escape_next = True
            continue
        if char == '"':
            in_string = not in_string
        if not in_string:
            if char == '{': brace_level += 1
            elif char == '}':
                brace_level -= 1
                if brace_level == 0:
                    json_str = text[start_idx : i+1]
                    try: return json.loads(json_str)
                    except json.JSONDecodeError as e: raise ValueError(f"Extracted JSON is invalid: {e}")
    raise ValueError("Could not find a complete JSON object.")

# --- Tool Schemas ---

class WikidataOSINTInput(BaseModel):
    yente_output: str = Field(..., description="JSON string from YenteEntitySearchTool")

class CypherQueryInput(BaseModel):
    query: str = Field(..., description="A valid Cypher query string.")

class YenteInput(BaseModel):
    query: str = Field(..., description="Search query for local Yente/OpenSanctions")

class AMLReportInput(BaseModel):
    title: str = Field(..., description="Report Title")
    content: str = Field(..., description="Full report text (Markdown compatible)")
    filename: str = Field(..., description="Filename, e.g., 'AML_Report_John_Doe.pdf'")

class PDFInput(BaseModel):
    account_number: str = Field(..., description="Account Number")
    fd_id: int = Field(..., description="FD ID")
    amount: float = Field(..., description="FD Amount")
    bank_name: str = Field(..., description="Bank Name")
    rate: float = Field(..., description="Interest Rate")
    tenure: int = Field(..., description="Tenure")
    maturity_date: str = Field(..., description="Maturity Date")
    customer_name: str = Field(..., description="Customer Name")

class EmailInput(BaseModel):
    to_email: str = Field(..., description="Recipient email")
    subject: str = Field(..., description="Subject")
    body: str = Field(..., description="Body")
    attachment_path: str = Field(default=None)

class FDCreationInput(BaseModel):
    first_name: str = Field(..., description="First Name")
    last_name: str = Field(..., description="Last Name")
    email: str = Field(..., description="Email")
    user_address: str = Field(..., description="Address")
    pin_number: str = Field(..., description="PIN")
    mobile_number: str = Field(..., description="Mobile")
    pan_number: str = Field(..., description="PAN")
    aadhaar_number: str = Field(..., description="Aadhaar")
    account_number: Optional[str] = Field(default=None, description="Account Number") 
    initial_amount: float = Field(..., description="Amount")
    tenure_months: int = Field(..., description="Tenure")
    bank_name: str = Field(..., description="Bank")
    interest_rate: Optional[float] = Field(default=None, description="Rate") 

class SQLQueryInput(BaseModel):
    query: str = Field(..., description="SQL query")

# --- Tool Definitions ---

@tool("DuckDuckGo News Search")
def search_news(query: str) -> str:
    """Search for recent news articles using DuckDuckGo."""
    try:
        results = langchain_ddg_tool.invoke(query)
        return str(results)
    except Exception as e:
        return f"Search failed: {str(e)}"

@tool("Fixed Deposit Projection Calculator")
def fd_projection(principal: float, rate: float, tenure: int) -> str:
    """Calculate fixed deposit maturity amount and interest earned assuming quarterly compounding."""
    r = rate / 100
    n = 4
    t = tenure
    amount = principal * (1 + r/n)**(n*t)
    interest = amount - principal
    return f"Maturity Amount: {amount:.2f}, Interest Earned: {interest:.2f}"

# --- AML Tools ---

class SelfHealingNeo4jTool(BaseTool):
    name: str = "Self-Healing Neo4j Executor"
    description: str = (
        "Executes a Cypher query. If it fails, it automatically analyzes the error, "
        "fixes the query, and retries up to 3 times."
    )
    args_schema: Type[BaseModel] = CypherQueryInput
    max_retries: int = 3

    def _run(self, query: str) -> str:
        llm = get_llm_3() # Get the high-end LLM instance for fixing
        current_query = query.strip()

        for attempt in range(self.max_retries):
            try:
                # Step 1: Dry Run using EXPLAIN
                # This catches syntax errors and schema mismatches without changing data
                explain_result = graph.query(f"EXPLAIN {current_query}")

                # Step 2: Actual Execution
                # If EXPLAIN worked, we assume it's safe enough to run
                context = graph.query(current_query)

                if not context:
                    return "Query executed successfully, but returned 0 results."
                
                output_lines = [f"Query returned {len(context)} results:"]
                for record in context:
                    output_lines.append(str(dict(record)))
                return "\n".join(output_lines)

            except Exception as e:
                error_msg = str(e)
                print(f"Attempt {attempt + 1} failed: {error_msg}")

                # If this was the last attempt, give up
                if attempt == self.max_retries - 1:
                    return f"Failed after {self.max_retries} attempts. Last Error: {error_msg}"

                # Step 3: The "Self-Healing" Loop
                # Ask the LLM to fix the query based on the specific error message
                fix_prompt = (
                    f"You are a Cypher expert. The following query failed:\n"
                    f"QUERY: {current_query}\n\n"
                    f"ERROR: {error_msg}\n\n"
                    f"Analyze the error and rewrite the query to fix it. "
                    f"Ensure you fix syntax, labels, and property names. "
                    f"Return ONLY the corrected Cypher query string, nothing else."
                )
                
                try:
                    # Invoke the LLM to get the fixed query
                    response = llm.invoke(fix_prompt)
                    # Clean up the response (remove markdown ticks if present)
                    fixed_query = response.content.strip()
                    if "```" in fixed_query:
                        fixed_query = fixed_query.split("```")[1].replace("cypher", "").replace("Cypher", "").strip()
                    
                    print(f"Generated fix: {fixed_query}")
                    current_query = fixed_query # Update query for next loop iteration
                    
                except Exception as llm_error:
                    return f"LLM failed to generate a fix: {llm_error}"

        return "Unexpected error in loop."


class YenteEntitySearchTool(BaseTool):
    name: str = "Deep Entity Enrichment (Yente/OpenSanctions)"
    description: str = (
        "Searches for an entity and retrieves the TOP 1 matching full profile. "
        "Input: A name (e.g., 'Vladimir Putin' or 'Sberbank'). "
        "Returns a JSON object with detailed properties, topics, and datasets."
    )
    args_schema: Type[BaseModel] = YenteInput

    def _run(self, query: str) -> str:
        try:
            search_endpoint = f"{YENTE_URL}/search/default"
            
            # Search for Top 1 Candidate
            search_resp = requests.get(
                search_endpoint, 
                params={"q": query, "limit": 1, "dataset": "default"}, 
                timeout=15
            )
            
            if search_resp.status_code != 200:
                return f"Search Error: {search_resp.status_code} - {search_resp.text}"
            
            search_data = search_resp.json()
            results = search_data.get("results", [])
            
            if not results:
                return f"No entity found for: '{query}'"
            
            best_match = results[0]
            entity_id = best_match.get("id")
            
            if not entity_id:
                return "Match found, but ID missing."

            # Fetch Full Profile
            entity_endpoint = f"{YENTE_URL}/entities/{entity_id}"
            entity_resp = requests.get(entity_endpoint, timeout=15)
            
            if entity_resp.status_code != 200:
                return f"Error fetching entity {entity_id}: {entity_resp.status_code}"
            
            full_data = entity_resp.json()
            
            # Return structured JSON with necessary fields
            return json.dumps({
                "match_id": entity_id,
                "match_score": best_match.get("score"),
                "full_profile": full_data
            }, indent=2)

        except Exception as e:
            import traceback
            return f"Yente Entity Tool Error: {str(e)}\n{traceback.format_exc()}"

class WikidataOSINTTool(BaseTool):
    name: str = "Wikidata OSINT (Social Media)"
    description: str = (
        "Takes Yente/OpenSanctions output (with full_profile), extracts the Wikidata Q-ID if present, "
        "queries Wikidata via LangChain, and extracts social media links (Facebook, Instagram, LinkedIn, X/Twitter, YouTube). "
        "Input: the JSON string returned by YenteEntitySearchTool."
    )
    args_schema: Type[BaseModel] = WikidataOSINTInput

    # Social media property IDs and URL templates
    SOCIAL_MEDIA_PROPS: ClassVar[dict[str, tuple[str, callable]]] = {
        "P2013": ("facebook_username", lambda v: f"https://www.facebook.com/{v}"),
        "P2003": ("instagram_username", lambda v: f"https://www.instagram.com/{v}"),
        "P6634": ("linkedin_personal_id", lambda v: f"https://www.linkedin.com/in/{v}"),
        "P2002": ("twitter_username", lambda v: f"https://x.com/{v}"),
        "P2397": ("youtube_channel_id", lambda v: f"https://www.youtube.com/channel/{v}"),
    }

    def _run(self, yente_output: str) -> str:
        try:
            data = json.loads(yente_output)
        except Exception:
            return "Invalid Yente output: not valid JSON."

        full_profile = data.get("full_profile", {})
        if not isinstance(full_profile, dict):
            return "No full_profile found in Yente output."

        # 1) Try to find a Wikidata Q-ID in common places
        qid = (
            full_profile.get("wikidataId")
            or full_profile.get("wikidata_id")
            or full_profile.get("wikidata")
        )
        if not qid:
            # Some datasets put identifiers under an 'identifiers' list
            identifiers = full_profile.get("identifiers", [])
            if isinstance(identifiers, list):
                for ident in identifiers:
                    if isinstance(ident, dict) and ident.get("scheme") == "wikidata":
                        qid = ident.get("id")
                        break

        if not qid:
            return "No Wikidata ID found in Yente/OpenSanctions profile."

        # Normalize QID (Q42, q42, http://www.wikidata.org/entity/Q42)
        qid_str = str(qid).strip()
        if qid_str.startswith("http"):
            qid_str = qid_str.rstrip("/").split("/")[-1]
        if not qid_str.upper().startswith("Q"):
            qid_str = f"Q{qid_str.lstrip('Qq')}"

        # 2) Query Wikidata via LangChain
        try:
            wikidata = WikidataQueryRun(api_wrapper=WikidataAPIWrapper())
            raw = wikidata.run(qid_str)
        except Exception as e:
            return f"Wikidata query failed for {qid_str}: {e}"

        # 3) Parse properties of the form "property name (PXXXX): value"
        social_media = {}
        for line in raw.splitlines():
            line = line.strip()
            if "(P" not in line:
                continue
            # Find the first (PXXXX) occurrence
            start = line.find("(P")
            if start == -1:
                continue
            end = line.find(")", start)
            if end == -1:
                continue
            prop_id = line[start + 1:end]  # e.g., "P2013"
            if prop_id not in self.SOCIAL_MEDIA_PROPS:
                continue
            # Use everything after the ') ' as the value (simplified)
            if end + 2 <= len(line):
                value = line[end + 2 :].strip()
                key, url_fn = self.SOCIAL_MEDIA_PROPS[prop_id]
                social_media[key] = url_fn(value)

        if not social_media:
            return f"Wikidata ID {qid_str} found, but no known social media properties extracted."

        # 4) Return JSON with links
        return json.dumps(
            {
                "wikidata_id": qid_str,
                "social_media": social_media,
            },
            indent=2,
        )

wikidata_osint_tool = WikidataOSINTTool()

class AMLReportPDFTool(BaseTool):
    name: str = "AML Report Generator"
    description: str = "Generates a clean, professional AML report using ReportLab."
    args_schema: Type[BaseModel] = AMLReportInput

    def _run(self, title: str, content: str, filename: str) -> str:
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
        filepath = temp_file.name
        temp_file.close()

        doc = SimpleDocTemplate(filepath, pagesize=letter, topMargin=0.5*inch, bottomMargin=0.5*inch, leftMargin=0.75*inch, rightMargin=0.75*inch)
        elements = []
        styles = getSampleStyleSheet()

        styles.add(ParagraphStyle(name='CustomTitle', fontSize=22, spaceAfter=12, textColor=colors.white, fontName='Helvetica-Bold', alignment=1))
        styles.add(ParagraphStyle(name='CustomSubTitle', fontSize=12, spaceAfter=30, textColor=colors.lightgrey, fontName='Helvetica', alignment=1))
        styles.add(ParagraphStyle(name='CustomBody', fontSize=10, leading=14, alignment=4, spaceAfter=12))
        styles.add(ParagraphStyle(name='H1', fontSize=16, spaceAfter=12, textColor=colors.navy, fontName='Helvetica-Bold'))
        styles.add(ParagraphStyle(name='H2', fontSize=13, spaceAfter=6, textColor=colors.black, fontName='Helvetica-Bold', leftIndent=10))
        styles.add(ParagraphStyle(name='DecisionText', fontSize=11, leading=14, textColor=colors.white, fontName='Helvetica-Bold'))

        header_data = [
            [Paragraph("User AML/UBO/OSINT/RISK REPORT", styles['CustomTitle'])],
            [Paragraph("CONFIDENTIAL - Generated by AML Agent", styles['CustomSubTitle'])],
            [Paragraph(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}", styles['CustomSubTitle'])]
        ]
        header_table = Table(header_data, colWidths=[7*inch])
        header_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.navy),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 12),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
        ]))
        elements.append(header_table)
        elements.append(Spacer(1, 0.2*inch))

        lines = content.split('\n')
        decision_buffer = []
        in_decision_block = False

        for line in lines:
            clean_line = line.strip()
            if not clean_line:
                elements.append(Spacer(1, 0.1*inch))
                continue

            if "DECISION:" in clean_line.upper():
                in_decision_block = True
                decision_buffer.append(clean_line)
                continue
            
            if in_decision_block:
                decision_buffer.append(clean_line)
                continue

            if clean_line.startswith("## "):
                text = clean_line.replace("## ", "").replace("**", "")
                elements.append(Paragraph(text, styles['H1']))
            elif clean_line.startswith("### "):
                text = clean_line.replace("### ", "").replace("**", "")
                elements.append(Paragraph(text, styles['H2']))
            elif clean_line.startswith("- "):
                text = clean_line.replace("- ", "").replace("**", "")
                elements.append(Paragraph(f"• {text}", styles['CustomBody']))
            else:
                text = clean_line.replace("**", "")
                elements.append(Paragraph(text, styles['CustomBody']))

        if decision_buffer:
            decision_text = " ".join(decision_buffer)
            bg_color = colors.green if "PASS" in decision_text.upper() else colors.red
            
            t = Table([[Paragraph(decision_text, styles['DecisionText'])]], colWidths=[6.5*inch])
            t.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, -1), bg_color),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('LEFTPADDING', (0, 0), (-1, -1), 10),
                ('RIGHTPADDING', (0, 0), (-1, -1), 10),
                ('TOPPADDING', (0, 0), (-1, -1), 10),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
                ('TEXTCOLOR', (0, 0), (-1, -1), colors.white)
            ]))
            elements.append(t)

        elements.append(Spacer(1, 0.5*inch))
        elements.append(Paragraph("Generated automatically. All findings based on available data sources.", styles['CustomSubTitle']))

        try:
            doc.build(elements)
            return filepath
        except Exception as e:
            return f"PDF Generation Failed: {str(e)}"

class FDInvoicePDFTool(BaseTool):
    name: str = "FD Invoice PDF"
    description: str = "Generates FD Invoice PDF"
    args_schema: Type[BaseModel] = PDFInput

    def _run(self, account_number: str, fd_id: int, amount: float, bank_name: str, rate: float, tenure: int, maturity_date: str, customer_name: str) -> str:
        temp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
        path = temp.name
        temp.close()
        doc = SimpleDocTemplate(path, pagesize=letter)
        styles = getSampleStyleSheet()
        elements = [Paragraph("<b>Fixed Deposit Confirmation</b>", styles['Title']), Spacer(1,12)]
        
        data = [
            ["Customer", customer_name], ["Account", account_number], ["FD ID", str(fd_id)],
            ["Bank", bank_name], ["Amount", f"₹ {amount:,.2f}"], ["Rate", f"{rate}%"],
            ["Tenure", f"{tenure} Months"], ["Maturity", maturity_date]
        ]
        table = Table(data, colWidths=[150, 300], hAlign='LEFT')
        table.setStyle(TableStyle([('BACKGROUND',(0,0),(1,0),colors.grey),('TEXTCOLOR',(0,0),(1,0),colors.whitesmoke),('ALIGN',(0,0),(-1,-1),'LEFT'),('GRID',(0,0),(-1,-1),1,colors.black)]))
        elements.append(table)
        doc.build(elements)
        return path

class EmailSenderTool(BaseTool):
    name: str = "Email Sender"
    description: str = "Sends email with attachment"
    args_schema: Type[BaseModel] = EmailInput

    def _run(self, to_email: str, subject: str, body: str, attachment_path: str = None) -> str:
        try:
            smtp_server = os.getenv("SMTP_SERVER", "smtp.gmail.com")
            smtp_port = int(os.getenv("SMTP_PORT", 587))
            smtp_user = os.getenv("SMTP_USER")
            smtp_password = os.getenv("SMTP_PASSWORD")

            if not smtp_user: return "Email skipped: No config."

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
                try: os.remove(attachment_path)
                except: pass
                
            return f"Email sent to {to_email}"
        except Exception as e:
            return f"Email failed: {str(e)}"

class FixedDepositCreationTool(BaseTool):
    name: str = "FD Creator"
    description: str = "Creates FD in SQLite DB."
    args_schema: Type[BaseModel] = FDCreationInput

    def _run(self, first_name: str, last_name: str, email: str, user_address: str, pin_number: str, mobile_number: str, pan_number: str, aadhaar_number: str, account_number: Optional[str], initial_amount: float, tenure_months: int, bank_name: str, interest_rate: Optional[float]) -> str:
        try:
            with sqlite3.connect(DB_PATH) as conn:
                cursor = conn.cursor()
                conn.execute("PRAGMA foreign_keys = ON;")
                
                user_id = None
                if account_number:
                    cursor.execute("SELECT user_id FROM users WHERE account_number = ?", (account_number,))
                    row = cursor.fetchone()
                    if row: user_id = row[0]
                
                if not user_id:
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
                    
                    cursor.execute("INSERT INTO users (first_name, last_name, account_number, email, is_account_active) VALUES (?, ?, ?, ?, 1)", (first_name, last_name, account_number, email))
                    user_id = cursor.lastrowid
                    cursor.execute("INSERT INTO address (user_id, user_address, pin_number, mobile_number, mobile_verified) VALUES (?, ?, ?, ?, 1)", (user_id, user_address, pin_number, mobile_number))
                    cursor.execute("INSERT INTO kyc_verification (user_id, address_id, account_number, pan_number, aadhaar_number, kyc_status, verified_at, created_at, updated_at) VALUES (?, (SELECT address_id FROM address WHERE user_id = ?), ?, ?, ?, 'VERIFIED', datetime('now'), datetime('now'), datetime('now'))", (user_id, user_id, account_number, pan_number, aadhaar_number))

                cursor.execute("SELECT account_id, balance FROM accounts WHERE user_id = ?", (user_id,))
                acc = cursor.fetchone()
                if not acc:
                    cursor.execute("INSERT INTO accounts (user_id, account_number, account_type, balance, email) VALUES (?, ?, 'Savings', ?, ?)", (user_id, account_number, initial_amount, email))
                    current_balance = initial_amount
                    acc_id = cursor.lastrowid
                else:
                    acc_id, current_balance = acc
                
                if current_balance < initial_amount:
                    return f"Failed: Insufficient Balance. Current: {current_balance}"

                new_balance = current_balance - initial_amount
                cursor.execute("UPDATE accounts SET balance = ? WHERE account_id = ?", (new_balance, acc_id))
                
                final_rate = interest_rate if interest_rate else 7.0
                maturity = (datetime.now() + timedelta(days=30*tenure_months)).strftime("%Y-%m-%d")
                cursor.execute("INSERT INTO fixed_deposit (user_id, initial_amount, bank_name, tenure_months, interest_rate, maturity_date, premature_penalty_percent, fd_status) VALUES (?, ?, ?, ?, ?, ?, 1.0, 'ACTIVE')", (user_id, initial_amount, bank_name, tenure_months, final_rate, maturity))
                fd_id = cursor.lastrowid
                conn.commit()
                return f"Success! FD ID: {fd_id}, Amount: {initial_amount}, Rate: {final_rate}%, Maturity: {maturity}, Account: {account_number}, Name: {first_name} {last_name}, Email: {email}"
        except Exception as e:
            return f"Error: {str(e)}"

class BankDatabaseTool(BaseTool):
    name: str = "Bank Database Query Tool"
    description: str = "Executes SQL on local DB."
    args_schema: Type[BaseModel] = SQLQueryInput

    def _run(self, query: str) -> str:
        if not DB_PATH.exists(): return "DB not found."
        try:
            with sqlite3.connect(DB_PATH) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute(query)
                rows = cursor.fetchall()
                if not rows: return "No results."
                headers = rows[0].keys()
                output = [", ".join(headers)]
                for row in rows: output.append(", ".join([str(val) for val in row]))
                return "\n".join(output)
        except Exception as e:
            return f"SQL Error: {str(e)}"