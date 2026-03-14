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
import math
import markdown
import matplotlib
import matplotlib.pyplot as plt
import networkx as nx
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from pathlib import Path
from typing import Type, Dict, Any, Optional, List, ClassVar, Callable
from langchain_community.graphs import Neo4jGraph
from langchain_nvidia_ai_endpoints import ChatNVIDIA, NVIDIA
from langchain_community.tools import DuckDuckGoSearchResults
from langchain_community.utilities import DuckDuckGoSearchAPIWrapper, SQLDatabase
from crewai.tools import BaseTool, tool
from pydantic import BaseModel, Field
import shutil
import subprocess
from markdown_pdf import MarkdownPdf, Section
from langchain_community.agent_toolkits import SQLDatabaseToolkit
from dotenv import load_dotenv

matplotlib.use('Agg') 

load_dotenv()

DB_PATH = Path(__file__).resolve().parent / "bank_poc.db"

langchain_db = SQLDatabase.from_uri(f"sqlite:///{DB_PATH}?check_same_thread=False")

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password123")
YENTE_URL = os.getenv("YENTE_URL", "http://localhost:8000")

try:
    graph = Neo4jGraph(
        url=NEO4J_URI,
        username=NEO4J_USER,
        password=NEO4J_PASSWORD
    )
    graph.refresh_schema()
except Exception:
    graph = None  


ISO3_TO_ISO1: Dict[str, str] = {
    "ara": "ar", "fra": "fr", "deu": "de", "spa": "es", "por": "pt",
    "jpn": "ja", "zho": "zh", "rus": "ru", "kor": "ko", "ita": "it",
    "nld": "nl", "pol": "pl", "tur": "tr", "swe": "sv", "nor": "no",
    "dan": "da", "fin": "fi", "ces": "cs", "ron": "ro", "hun": "hu",
    "tha": "th", "vie": "vi", "ind": "id", "msa": "ms", "bos": "bs",
    "hrv": "hr", "srp": "sr", "slk": "sk", "slv": "sl", "bul": "bg",
    "ukr": "uk", "heb": "he", "ell": "el", "cat": "ca", "hin": "en",
    "ben": "en", "urd": "en", "tam": "en", "tel": "en", "mar": "en",
}

DEFAULT_DDG_REGION = "wt-wt" 

# In-memory cache so we only hit the network once per process
COUNTRY_DATA_CACHE: Dict[str, Dict] = {}


def fetch_country_data() -> Dict[str, Dict]:
    """
    Fetches all countries from the restcountries.com v3 API.
    Returns a dict keyed by ISO 3166-1 alpha-2 code:
      {
        "IN": {
          "name": "India",
          "currency_symbol": "₹",
          "currency_code": "INR",
          "ddg_region": "in-en",
        },
        ...
      }
    Falls back to a minimal hardcoded set on network failure.
    """
    global COUNTRY_DATA_CACHE
    if COUNTRY_DATA_CACHE:
        return COUNTRY_DATA_CACHE

    try:
        resp = requests.get(
            "https://restcountries.com/v3.1/all"
            "?fields=cca2,name,languages,currencies",
            timeout=10,
        )
        resp.raise_for_status()
        raw = resp.json()
    except Exception:
        # Minimal fallback so the app still works offline
        raw = []

    result: Dict[str, Dict] = {}
    for c in raw:
        cc = c.get("cca2", "").upper()
        if not cc:
            continue

        name = c.get("name", {}).get("common", cc)

        # --- Currency ---
        currencies = c.get("currencies", {})
        currency_code   = next(iter(currencies), "")
        currency_symbol = currencies[currency_code].get("symbol", currency_code) if currency_code else ""

        lang_code = "en"  # default
        for iso3 in c.get("languages", {}).keys():
            mapped = ISO3_TO_ISO1.get(iso3.lower())
            if mapped and mapped != "en":
                lang_code = mapped
                break  

        ddg_region = f"{cc.lower()}-{lang_code}"

        result[cc] = {
            "name": name,
            "currency_symbol": currency_symbol,
            "currency_code": currency_code,
            "ddg_region": ddg_region,
        }

    # Ensure a worldwide fallback entry exists
    result["WW"] = {
        "name": "Worldwide",
        "currency_symbol": "",
        "currency_code": "",
        "ddg_region": DEFAULT_DDG_REGION,
    }

    COUNTRY_DATA_CACHE = result
    return result


ddg_news_wrapper = DuckDuckGoSearchAPIWrapper(
    max_results=5, time="y", region=DEFAULT_DDG_REGION
)
langchain_ddg_tool = DuckDuckGoSearchResults(api_wrapper=ddg_news_wrapper, output_format="list")


def set_search_region(country_code: str) -> str:
    """
    Hot-swap the global DuckDuckGo wrapper to the user's detected region.
    Returns the DDG region code applied.
    """
    global ddg_news_wrapper, langchain_ddg_tool

    countries = fetch_country_data()
    info = countries.get(country_code.upper(), {})
    region_code = info.get("ddg_region", DEFAULT_DDG_REGION)

    ddg_news_wrapper = DuckDuckGoSearchAPIWrapper(
        max_results=5, time="y", region=region_code
    )
    langchain_ddg_tool = DuckDuckGoSearchResults(
        api_wrapper=ddg_news_wrapper, output_format="list"
    )
    return region_code

def get_llm_3():
    # Only used for self-healing Cypher fixes — a small model is perfectly sufficient.
    return NVIDIA(model="meta/llama-3.1-8b-instruct")

def extract_json_balanced(text: str):
    """
    Extracts the first complete JSON value (object OR array) from a string.
    Returns a dict or list. Handles responses wrapped in markdown fences.
    """
    # Strip markdown fences first
    clean = re.sub(r"```(?:json)?\s*", "", text).strip()

    try:
        return json.loads(clean)
    except json.JSONDecodeError:
        pass

    # Find whichever comes first: '{' (object) or '[' (array)
    obj_idx = clean.find('{')
    arr_idx = clean.find('[')

    if obj_idx == -1 and arr_idx == -1:
        raise ValueError("No JSON object or array found in response.")

    # Pick the earlier opener; -1 means absent so treat as infinity
    if arr_idx == -1 or (obj_idx != -1 and obj_idx < arr_idx):
        start_idx = obj_idx
        open_ch, close_ch = '{', '}'
    else:
        start_idx = arr_idx
        open_ch, close_ch = '[', ']'

    depth = 0
    in_string = False
    escape_next = False

    for i in range(start_idx, len(clean)):
        char = clean[i]
        if escape_next:
            escape_next = False
            continue
        if char == '\\':
            escape_next = True
            continue
        if char == '"':
            in_string = not in_string
        if not in_string:
            if char == open_ch:
                depth += 1
            elif char == close_ch:
                depth -= 1
                if depth == 0:
                    json_str = clean[start_idx: i + 1]
                    try:
                        return json.loads(json_str)
                    except json.JSONDecodeError as e:
                        raise ValueError(f"Extracted JSON is invalid: {e}")

    raise ValueError("Could not find a complete JSON value.")

class DepositCalculatorInput(BaseModel):
    deposit_type: str = Field(..., description="'FD' for Fixed/Term Deposit or 'RD' for Recurring Deposit")
    amount: float = Field(..., description="Principal for FD. Monthly Installment for RD.")
    rate: float = Field(..., description="Annual Interest Rate (e.g., 7.5)")
    tenure_months: int = Field(..., description="Tenure in months")
    compounding_freq: str = Field(default="quarterly", description="Compounding frequency: 'monthly', 'quarterly', 'half_yearly', 'yearly'")
    category: str = Field(default="general", description="'general' or 'senior'")

class GraphDataInput(BaseModel):
    nodes: List[Dict[str, str]] = Field(..., description="List of nodes, e.g., [{'id': 'Entity1', 'label': 'Person'}, ...]")
    edges: List[Dict[str, str]] = Field(..., description="List of edges, e.g., [{'source': 'Entity1', 'target': 'Entity2', 'label': 'OWNS'}, ...]")

class MarkdownPDFInput(BaseModel):
    title: str = Field(..., description="Report Title")
    markdown_content: str = Field(..., description="Markdown text to convert to PDF")
    filename: str = Field(..., description="Output filename")
    graph_image_path: Optional[str] = Field(default=None, description="Optional path to Neo4j network graph image")
    subject_image_path: Optional[str] = Field(default=None, description="Optional path to subject portrait image fetched from Wikidata")

class UniversalDepositInput(BaseModel):
    first_name: str
    last_name: str
    email: str
    user_address: str
    pin_number: str
    mobile_number: str
    # NEW: Dynamic KYC fields
    kyc_details_1: str = Field(..., description="Primary KYC Document in format: TYPE-VALUE (e.g. SSN-123456789)")
    kyc_details_2: str = Field(..., description="Secondary KYC Document in format: TYPE-VALUE (e.g. PASSPORT-GH12345)")
    account_number: Optional[str] = None
    product_type: str = Field(default="FD", description="'FD' or 'RD'")
    initial_amount: float = Field(..., description="Principal (FD) or Monthly Installment (RD)")
    tenure_months: int
    bank_name: str
    interest_rate: float
    compounding_freq: str = Field(default="quarterly", description="Compounding frequency")
    country_code: str = Field(default="IN", description="ISO Country Code")

class SQLQueryInput(BaseModel):
    query: str = Field(..., description="SQL query")

class YenteInput(BaseModel):
    query: str = Field(..., description="Search query for local Yente/OpenSanctions")

class CypherQueryInput(BaseModel):
    query: str = Field(..., description="A valid Cypher query string.")

class WikidataOSINTInput(BaseModel):
    yente_output: str = Field(..., description="Full text output from YenteEntitySearchTool. Must contain ENTITY_NAME: and ENTITY_ID: lines.")

class EmailInput(BaseModel):
    to_email: str = Field(..., description="Recipient email")
    subject: str = Field(..., description="Subject")
    body: str = Field(..., description="Body")
    attachment_paths: Optional[List[str]] = Field(default=None, description="List of file paths to attach")

@tool("DuckDuckGo News Search")
def search_news(query: str) -> str:
    """Search for recent news articles using DuckDuckGo. Returns compressed title, snippet, and URL."""
    try:
        results = langchain_ddg_tool.invoke(query)
        if isinstance(results, list):
            compressed = []
            for r in results[:5]:
                title   = r.get("title", "").strip()
                snippet = r.get("snippet", r.get("body", "")).strip()[:350]
                url     = r.get("link", r.get("url", "")).strip()
                if title or snippet:
                    compressed.append(f"Title: {title}\nSnippet: {snippet}\nURL: {url}")
            return "\n---\n".join(compressed) if compressed else "No results found."
        return str(results)[:2000]
    except Exception as e:
        return f"Search failed: {str(e)}"

class EmailSenderTool(BaseTool):
    name: str = "Email Sender"
    description: str = "Sends email with multiple attachments."
    args_schema: Type[BaseModel] = EmailInput

    def _run(self, to_email: str, subject: str, body: str, attachment_paths: List[str] = None) -> str:
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

            if attachment_paths:
                for path in attachment_paths:
                    if path and Path(path).exists():
                        with open(path, "rb") as f:
                            part = MIMEApplication(f.read(), Name=Path(path).name)
                        part['Content-Disposition'] = f'attachment; filename="{Path(path).name}"'
                        msg.attach(part)

            server = smtplib.SMTP(smtp_server, smtp_port)
            server.starttls()
            server.login(smtp_user, smtp_password)
            server.sendmail(smtp_user, to_email, msg.as_string())
            server.quit()
            
            if attachment_paths:
                for path in attachment_paths:
                    try: 
                        if Path(path).exists(): os.remove(path)
                    except: pass
            return f"Email sent to {to_email} with {len(attachment_paths or [])} attachments."
        except Exception as e:
            return f"Email failed: {str(e)}"

@tool("Universal Deposit Calculator")
def calculate_deposit(deposit_type: str, amount: float, rate: float, tenure_months: int, compounding_freq: str = "quarterly", category: str = "general") -> str:
    """Calculates maturity for FD or RD with dynamic compounding frequencies."""
    r = rate / 100
    freq_map = {
        "monthly": 12,
        "quarterly": 4,
        "half_yearly": 2,
        "yearly": 1
    }
    n = freq_map.get(compounding_freq.lower(), 4)
    
    try:
        if deposit_type.upper() == "FD":
            t_years = tenure_months / 12
            maturity_amount = amount * pow((1 + r/n), n * t_years)
            interest = maturity_amount - amount
            input_desc = f"Principal: {amount:,.2f}"

        elif deposit_type.upper() == "RD":
            maturity_val = 0.0
            rate_per_period = r / n
            months_in_period = 12 / n
            for month in range(1, tenure_months + 1):
                months_remaining = tenure_months - month
                periods = months_remaining / months_in_period
                maturity_val += amount * pow((1 + rate_per_period), periods)
            maturity_amount = maturity_val
            total_invested = amount * tenure_months
            interest = maturity_amount - total_invested
            input_desc = f"Monthly Installment: {amount:,.2f} for {tenure_months} months"

        else:
            return f"Error: Unknown type '{deposit_type}'"

        return (
            f"Type: {deposit_type} | Category: {category}\n"
            f"{input_desc}\n"
            f"Rate: {rate}% | Compounding: {compounding_freq.capitalize()}\n"
            f"Maturity Amount: {maturity_amount:,.2f}\n"
            f"Interest Earned: {interest:,.2f}"
        )
    except Exception as e:
        return f"Calculation Error: {str(e)}"

class MarkdownPDFTool(BaseTool):
    name: str = "Markdown Report Generator"
    description: str = "Converts Markdown text into a styled PDF document using markdown-pdf."
    args_schema: Type[BaseModel] = MarkdownPDFInput

    def _run(self, title: str, markdown_content: str, filename: str,
             graph_image_path: str = None, subject_image_path: str = None) -> str:
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
        filepath = temp_file.name
        temp_file.close()

        # markdown-pdf resolves relative image paths against a single root directory.
        # When both images exist they may live in different temp dirs, so we copy
        # any subject image into the same directory as the graph image (or vice-versa)
        # so we only need to set one root.
        try:
            # Normalise paths — strip the "WIKIDATA_IMAGE_PATH: " prefix the tool emits
            if subject_image_path and subject_image_path.startswith("WIKIDATA_IMAGE_PATH:"):
                subject_image_path = subject_image_path.split(":", 1)[1].strip().splitlines()[0].strip()

            graph_exists   = bool(graph_image_path   and Path(graph_image_path).exists())
            subject_exists = bool(subject_image_path and Path(subject_image_path).exists())

            # Choose a single working directory for images
            if graph_exists:
                img_root = str(Path(graph_image_path).parent)
                if subject_exists and Path(subject_image_path).parent != Path(graph_image_path).parent:
                    dest = Path(img_root) / Path(subject_image_path).name
                    shutil.copy2(subject_image_path, dest)
                    subject_image_path = str(dest)
            elif subject_exists:
                img_root = str(Path(subject_image_path).parent)
            else:
                img_root = None

            final_markdown = f"# {title}\n\n"
            final_markdown += f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"

            # Subject portrait — placed immediately after the header
            if subject_exists:
                subject_img_name = Path(subject_image_path).name
                final_markdown += (
                    f'<div align="center">\n\n'
                    f"![Subject Portrait]({subject_img_name})\n\n"
                    f"</div>\n\n"
                )

            final_markdown += "---\n\n"
            final_markdown += markdown_content

            # Entity relationship graph — appended at the end
            if graph_exists:
                graph_img_name = Path(graph_image_path).name
                final_markdown += (
                    "\n\n## Entity Relationship Network\n\n"
                    f"![Network Graph]({graph_img_name})\n"
                )

            section_kwargs = {}
            if img_root:
                section_kwargs["root"] = img_root

            pdf = MarkdownPdf(toc_level=2, optimize=True)
            pdf.meta["title"] = title
            pdf.add_section(Section(final_markdown, **section_kwargs))
            pdf.save(filepath)

            return filepath

        except Exception as e:
            return f"Error generating PDF: {str(e)}"

db_schema_migrated = False


class UniversalDepositCreationTool(BaseTool):
    name: str = "Deposit Creator"
    description: str = "Creates FD or RD in SQLite DB. Handles schema updates and country codes."
    args_schema: Type[BaseModel] = UniversalDepositInput

    def _run(self, **kwargs):
        global db_schema_migrated
        try:
            with sqlite3.connect(DB_PATH) as conn:
                cursor = conn.cursor()
                conn.execute("PRAGMA foreign_keys = ON;")

                # --- Schema Migration (runs once per process, not on every call) ---
                if not db_schema_migrated:
                    cursor.execute("PRAGMA table_info(kyc_verification)")
                    columns = [col[1] for col in cursor.fetchall()]

                    if 'pan_number' in columns and 'kyc_details_1' not in columns:
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

                    db_schema_migrated = True
                
                # --- Insert Logic ---
                product_type = kwargs.get('product_type', 'FD')
                initial_amount = kwargs.get('initial_amount')
                tenure_months = kwargs.get('tenure_months')
                bank_name = kwargs.get('bank_name')
                interest_rate = kwargs.get('interest_rate')
                compounding_freq = kwargs.get('compounding_freq', 'quarterly')
                first_name = kwargs.get('first_name')
                last_name = kwargs.get('last_name')
                email = kwargs.get('email')
                account_number = kwargs.get('account_number')
                kyc_1 = kwargs.get('kyc_details_1')
                kyc_2 = kwargs.get('kyc_details_2')
                country_code = kwargs.get('country_code', 'IN')

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
                    cursor.execute("INSERT INTO address (user_id, user_address, pin_number, mobile_number, mobile_verified, country_code) VALUES (?, ?, ?, ?, 1, ?)", (user_id, kwargs.get('user_address'), kwargs.get('pin_number'), kwargs.get('mobile_number'), country_code))
                    
                    cursor.execute("""
                        INSERT INTO kyc_verification 
                        (user_id, address_id, account_number, kyc_details_1, kyc_details_2, kyc_status, verified_at, created_at, updated_at) 
                        VALUES (?, (SELECT address_id FROM address WHERE user_id = ?), ?, ?, ?, 'VERIFIED', datetime('now'), datetime('now'), datetime('now'))
                    """, (user_id, user_id, account_number, kyc_1, kyc_2))
                
                tenure_months = kwargs.get('tenure_months')
                if tenure_months is None:
                    return "Error: Tenure months is required."

                maturity = (datetime.now() + timedelta(days=30*tenure_months)).strftime("%Y-%m-%d")
                monthly_installment = initial_amount if product_type == 'RD' else None
                
                cursor.execute("""
                    INSERT INTO fixed_deposit 
                    (user_id, initial_amount, bank_name, tenure_months, interest_rate, maturity_date, premature_penalty_percent, fd_status, product_type, monthly_installment, compounding_freq) 
                    VALUES (?, ?, ?, ?, ?, ?, 1.0, 'ACTIVE', ?, ?, ?)
                """, (user_id, initial_amount, bank_name, tenure_months, interest_rate, maturity, product_type, monthly_installment, compounding_freq))
                
                fd_id = cursor.lastrowid
                conn.commit()
                
                return (
                    f"Success! {product_type} Created.\n"
                    f"ID: {fd_id}\n"
                    f"Account: {account_number}\n"
                    f"Product: {product_type}\n"
                    f"Amount: {initial_amount}\n"
                    f"Country: {country_code}\n"
                    f"Rate: {interest_rate}%\n"
                    f"Frequency: {compounding_freq}\n"
                    f"Maturity: {maturity}"
                )
        except Exception as e:
            return f"Error: {str(e)}"

def generate_network_graph_from_results(records: list) -> Optional[str]:
    """
    Parses neo4j raw driver Record objects into nodes/edges and saves a PNG network graph.
    """
    try:
        nodes: Dict[str, str] = {}   
        edges: Dict[tuple, str] = {} 

        def process_value(value: Any) -> None:
            try:
                from neo4j.graph import Node, Relationship, Path
            except ImportError:
                return

            if isinstance(value, Node):
                nid = str(value.element_id)
                if nid not in nodes:
                    label = (
                        value.get("name")
                        or value.get("caption")
                        or value.get("title")
                        or (list(value.labels)[0] if value.labels else nid[:8])
                    )
                    nodes[nid] = str(label)[:40]

            elif isinstance(value, Relationship):
                src = str(value.start_node.element_id)
                tgt = str(value.end_node.element_id)
                for n in (value.start_node, value.end_node):
                    nid = str(n.element_id)
                    if nid not in nodes:
                        nodes[nid] = str(n.get("name") or n.get("caption") or nid[:8])[:40]
                edge_key = (src, tgt)
                if edge_key not in edges:
                    edges[edge_key] = str(value.type)

            elif isinstance(value, Path):
                for n in value.nodes:
                    nid = str(n.element_id)
                    if nid not in nodes:
                        nodes[nid] = str(n.get("name") or n.get("caption") or nid[:8])[:40]
                for r in value.relationships:
                    src = str(r.start_node.element_id)
                    tgt = str(r.end_node.element_id)
                    edge_key = (src, tgt)
                    if edge_key not in edges:
                        edges[edge_key] = str(r.type)

            elif isinstance(value, (list, tuple)):
                for item in value:
                    process_value(item)

        for record in records:
            if hasattr(record, "values"):
                for v in record.values():
                    process_value(v)
            elif isinstance(record, dict):
                for v in record.values():
                    process_value(v)

        if not nodes:
            return None

        MAX_NODES = 80
        MAX_EDGES = 150

        if len(nodes) > MAX_NODES:
            kept_ids = set(list(nodes.keys())[:MAX_NODES])
            nodes = {k: v for k, v in nodes.items() if k in kept_ids}
            edges = {k: v for k, v in edges.items() if k[0] in kept_ids and k[1] in kept_ids}

        if len(edges) > MAX_EDGES:
            edges = dict(list(edges.items())[:MAX_EDGES])

        G = nx.DiGraph()
        for nid, label in nodes.items():
            G.add_node(nid, label=label)
        for (src, tgt), rel in edges.items():
            if G.has_node(src) and G.has_node(tgt):
                G.add_edge(src, tgt, label=rel)

        n_nodes = G.number_of_nodes()

        # Cap figure size: max 20 inches to prevent multi-thousand-pixel PNGs
        fig_size = min(20, max(12, n_nodes // 4))
        plt.figure(figsize=(fig_size, fig_size))
        try:
            if n_nodes <= 20:
                pos = nx.spring_layout(G, k=2.5, seed=42, iterations=80)
            elif n_nodes <= 50:
                pos = nx.kamada_kawai_layout(G)
            else:
                shells = []
                deg_sorted = sorted(G.degree(), key=lambda x: x[1], reverse=True)
                center = [deg_sorted[0][0]] if deg_sorted else []
                inner  = [n for n, _ in deg_sorted[1:min(8, n_nodes)]]
                outer  = [n for n, _ in deg_sorted[8:]]
                for shell in [center, inner, outer]:
                    if shell:
                        shells.append(shell)
                pos = nx.shell_layout(G, nlist=shells if len(shells) > 1 else None)
        except Exception:
            pos = nx.spring_layout(G, seed=42)

        degrees = dict(G.degree())
        node_sizes = [max(800, 300 + degrees.get(n, 0) * 200) for n in G.nodes()]
        node_font  = max(6, min(10, 100 // max(n_nodes, 1)))

        nx.draw_networkx_nodes(G, pos, node_color="#1E3A8A", node_size=node_sizes, alpha=0.88)
        display_labels = {n: d.get("label", n) for n, d in G.nodes(data=True)}
        nx.draw_networkx_labels(G, pos, labels=display_labels,
                                font_color="white", font_size=node_font, font_weight="bold")

        if edges:
            nx.draw_networkx_edges(G, pos, edgelist=list(G.edges()),
                                   edge_color="#555555", arrows=True,
                                   arrowsize=15, arrowstyle="-|>",
                                   connectionstyle="arc3,rad=0.05",
                                   min_source_margin=15, min_target_margin=15)
            if n_nodes <= 40:
                edge_labels = {(u, v): d["label"] for u, v, d in G.edges(data=True) if d.get("label")}
                nx.draw_networkx_edge_labels(G, pos, edge_labels=edge_labels,
                                             font_color="#CC0000", font_size=7,
                                             bbox={"alpha": 0})

        title_suffix = f" ({n_nodes} nodes, {G.number_of_edges()} edges)"
        plt.title("Entity Relationship Network" + title_suffix, fontsize=14, pad=12)
        plt.axis("off")
        plt.tight_layout()

        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".png")
        tmp.close()
        plt.savefig(tmp.name, format="png", dpi=100, bbox_inches="tight")
        plt.close()
        return tmp.name

    except Exception:
        plt.close("all")
        return None


class Neo4jQueryTool(BaseTool):
    """
    Executes a Cypher query against Neo4j with automatic self-healing.
    Retries up to 3 times on both syntax errors AND empty results,
    asking a small LLM to rewrite the query each time.
    Returns a compact node/edge summary + GRAPH_IMAGE_PATH on success.
    """
    name: str = "Neo4j Graph Query"
    description: str = (
        "Runs a Cypher query against the Neo4j graph database. "
        "Auto-rewrites and retries the query up to 3 times if it errors or returns no data. "
        "Returns a compact summary of nodes and relationships plus GRAPH_IMAGE_PATH."
    )
    args_schema: Type[BaseModel] = CypherQueryInput
    max_retries: int = 5

    @staticmethod
    def slim_serialize(obj: Any) -> Any:
        try:
            from neo4j.graph import Node, Relationship, Path
            if isinstance(obj, Node):
                name = (
                    obj.get("name") or obj.get("caption") or obj.get("title")
                    or (list(obj.labels)[0] if obj.labels else "?")
                )
                return {
                    "type": "Node",
                    "labels": list(obj.labels),
                    "name": str(name)[:60],
                }
            if isinstance(obj, Relationship):
                def node_name(n: Any) -> str:
                    return str(n.get("name") or n.get("caption") or list(n.labels)[0] if n.labels else "?")[:60]
                return {
                    "type": "Relationship",
                    "rel": obj.type,
                    "from": node_name(obj.start_node),
                    "to": node_name(obj.end_node),
                }
            if isinstance(obj, Path):
                return {
                    "type": "Path",
                    "nodes": [Neo4jQueryTool.slim_serialize(n) for n in obj.nodes],
                    "rels": [Neo4jQueryTool.slim_serialize(r) for r in obj.relationships],
                }
        except ImportError:
            pass
        if isinstance(obj, dict):
            return {k: Neo4jQueryTool.slim_serialize(v) for k, v in obj.items()}
        if isinstance(obj, (list, tuple)):
            return [Neo4jQueryTool.slim_serialize(i) for i in obj]
        return obj

    def rewrite_query(self, current_query: str, reason: str) -> Optional[str]:
        """Ask the small LLM to fix or broaden the query. Returns new query or None."""
        llm = get_llm_3()
        prompt = (
            f"You are a Cypher expert. Rewrite the query below to fix the issue.\n\n"
            f"QUERY:\n{current_query}\n\n"
            f"ISSUE: {reason}\n\n"
            "Rules:\n"
            "- If the issue is an error: fix the syntax/schema problem.\n"
            "- If the issue is zero results: broaden the match "
            "(e.g. remove extra WHERE clauses, use CONTAINS instead of =, "
            "increase LIMIT, or try a parent label).\n"
            "Return ONLY the corrected Cypher query. No explanation, no markdown fences."
        )
        try:
            resp = llm.invoke(prompt)
            fixed = resp.content.strip()
            # Strip any accidental markdown fences
            if "```" in fixed:
                fixed = re.sub(r"```(?:cypher)?", "", fixed, flags=re.IGNORECASE).replace("```", "").strip()
            return fixed if fixed else None
        except Exception:
            return None

    def _run(self, query: str) -> str:
        import time
        from neo4j import GraphDatabase

        current_query = query.strip()
        last_issue = ""
        driver = None

        try:
            # Single driver for the entire run — not recreated on every retry.
            # connection_timeout: seconds to wait for the initial TCP handshake.
            # max_connection_lifetime: recycle connections older than 5 min to
            #   avoid "stale connection" errors from Neo4j's server-side idle timeout.
            driver = GraphDatabase.driver(
                NEO4J_URI,
                auth=(NEO4J_USER, NEO4J_PASSWORD),
                connection_timeout=10,
                max_connection_lifetime=300,
            )
            # Verify connectivity once up front rather than discovering it mid-query.
            driver.verify_connectivity()

            for attempt in range(self.max_retries):
                try:
                    with driver.session() as session:
                        result = session.run(current_query)
                        records = list(result)

                    # --- Empty results: retry with broadened query ---
                    if not records:
                        last_issue = "Query returned 0 results."
                        if attempt < self.max_retries - 1:
                            rewritten = self.rewrite_query(current_query, last_issue)
                            if rewritten:
                                current_query = rewritten
                                time.sleep(0.5)
                                continue
                        return (
                            f"No results after {attempt + 1} attempt(s). "
                            f"Last query tried:\n{current_query}"
                        )

                    # --- Success: build compact output ---
                    graph_path = generate_network_graph_from_results(records)

                    try:
                        slim = [self.slim_serialize(dict(r)) for r in records]
                        result_text = json.dumps(slim, default=str)
                    except Exception:
                        result_text = json.dumps([str(r) for r in records], default=str)

                    if len(result_text) > 4000:
                        result_text = result_text[:4000] + "\n... [truncated for brevity]"

                    if graph_path:
                        result_text += f"\n\nGRAPH_IMAGE_PATH: {graph_path}"

                    return result_text

                except Exception as e:
                    last_issue = str(e)
                    if attempt < self.max_retries - 1:
                        rewritten = self.rewrite_query(current_query, last_issue)
                        if rewritten:
                            current_query = rewritten
                        else:
                            return f"LLM failed to rewrite query. Last error: {last_issue}"
                        # Exponential backoff: 1s, 2s, 4s … so transient errors have
                        # time to resolve before the next attempt.
                        time.sleep(2 ** attempt)
                    else:
                        return f"Failed after {self.max_retries} attempts. Last error: {last_issue}"

        except Exception as e:
            # Connectivity check failed — Neo4j is unreachable
            return f"Neo4j connection failed: {e}"
        finally:
            if driver:
                try:
                    driver.close()
                except Exception:
                    pass

        return f"Exhausted retries. Last issue: {last_issue}"

class YenteEntitySearchTool(BaseTool):
    name: str = "Deep Entity Enrichment (Yente/OpenSanctions)"
    description: str = (
        "Screens an entity against OpenSanctions using the /match API. "
        "Input: a name string OR a JSON string with keys like name, birthDate, nationality. "
        "Returns scored matches, sanctions/PEP flags, properties, and related entities."
    )
    args_schema: Type[BaseModel] = YenteInput

    def build_query_entity(self, query: str) -> Dict[str, Any]:
        structured: Dict[str, Any] = {}
        try:
            structured = json.loads(query)
        except (json.JSONDecodeError, ValueError):
            pass

        if not structured:
            return {
                "schema": "LegalEntity",
                "properties": {"name": [query.strip()]},
            }

        props: Dict[str, List[str]] = {}
        schema = structured.get("schema", "LegalEntity")

        for src_key, ftm_key in [
            ("name",        "name"),
            ("first_name",  "firstName"),
            ("last_name",   "lastName"),
            ("birth_date",  "birthDate"),
            ("birthDate",   "birthDate"),
            ("nationality", "nationality"),
            ("country",     "country"),
            ("id_number",   "idNumber"),
            ("pan",         "idNumber"),
            ("passport",    "passportNumber"),
            ("email",       "email"),
            ("phone",       "phone"),
        ]:
            val = structured.get(src_key)
            if val:
                props.setdefault(ftm_key, []).append(str(val))

        if not props:
            full_name = structured.get("full_name") or structured.get("first_name", "") + " " + structured.get("last_name", "")
            props["name"] = [full_name.strip() or query.strip()]

        return {"schema": schema, "properties": props}

    def _run(self, query: str) -> str:
        try:
            entity_query = self.build_query_entity(query)
            name_val: str = (
                entity_query.get("properties", {}).get("name", [query])[0]
                if entity_query.get("properties", {}).get("name")
                else query.strip()
            )

            # --- /match against deduplicated schemas ---
            match_candidates: List[Dict[str, Any]] = []
            base_schema = entity_query["schema"]
            schemas_to_try = list(dict.fromkeys([base_schema, "Person"]))

            for schema in schemas_to_try:
                variant = dict(entity_query, schema=schema)
                try:
                    resp = requests.post(
                        f"{YENTE_URL}/match/default",
                        json={"queries": {"q1": variant}},
                        params={"algorithm": "best", "limit": 5},
                        timeout=20,
                    )
                    if resp.status_code == 200:
                        for r in resp.json().get("responses", {}).get("q1", {}).get("results", []):
                            match_candidates.append(r)
                except Exception:
                    pass

            # --- /search fallback ---
            search_candidates: List[Dict[str, Any]] = []
            try:
                search_resp = requests.get(
                    f"{YENTE_URL}/search/default",
                    params={"q": name_val, "limit": 5, "fuzzy": "true"},
                    timeout=15,
                )
                if search_resp.status_code == 200:
                    search_candidates = search_resp.json().get("results", [])
            except Exception:
                pass

            # --- Merge and rank ---
            seen: Dict[str, Dict[str, Any]] = {}
            for candidate in match_candidates:
                eid = candidate.get("id")
                if eid and (eid not in seen or candidate.get("score", 0) > seen[eid].get("score", 0)):
                    candidate["_source"] = "match"
                    seen[eid] = candidate
            for candidate in search_candidates:
                eid = candidate.get("id")
                if eid and eid not in seen:
                    candidate["_source"] = "search"
                    candidate.setdefault("score", None)
                    seen[eid] = candidate

            if not seen:
                return (
                    f"YENTE_RESULT: No match for '{name_val}'.\n"
                    "Entity is likely not in the local OpenSanctions database.\n"
                    f"ENTITY_NAME: {name_val}"
                )

            ranked = sorted(
                seen.values(),
                key=lambda x: (x.get("_source") == "match", x.get("score") or 0),
                reverse=True,
            )
            best = ranked[0]
            entity_id = best.get("id")
            if not entity_id:
                return "YENTE_RESULT: Candidates found but all are missing entity IDs."

            # --- Fetch full profile for the best candidate only ---
            full_profile: Dict[str, Any] = {}
            for candidate in ranked[:3]:
                eid = candidate.get("id")
                if not eid:
                    continue
                try:
                    ep = requests.get(
                        f"{YENTE_URL}/entities/{eid}",
                        params={"nested": "true"},
                        timeout=20,
                    )
                    if ep.status_code == 200:
                        full_profile = ep.json()
                        entity_id = eid
                        best = candidate
                        break
                except Exception:
                    continue

            if not full_profile:
                return f"YENTE_RESULT: Found entity ID {entity_id} but could not fetch its full profile."

            # ----------------------------------------------------------------
            # Extract fields — structured by AML relevance
            # ----------------------------------------------------------------
            props  = full_profile.get("properties", {})
            topics = props.get("topics", [])

            # --- Risk classification ---
            risk_flags = []
            if "sanction"  in topics: risk_flags.append("SANCTIONED")
            if "pep"       in topics: risk_flags.append("PEP")
            if "crime"     in topics: risk_flags.append("CRIMINAL")
            if "wanted"    in topics: risk_flags.append("WANTED")
            if "debarred"  in topics: risk_flags.append("DEBARRED")
            if "terrorism" in topics: risk_flags.append("TERRORISM")
            if "freeze"    in topics: risk_flags.append("ASSET_FREEZE")

            # --- PEP level inference ---
            pep_level = "N/A"
            if "pep" in topics:
                pep_level_raw = props.get("pepLevel", [None])[0]
                if pep_level_raw:
                    pep_level = str(pep_level_raw)
                else:
                    # Infer from position text
                    positions_raw = [str(p).lower() for p in props.get("position", [])]
                    if any(w in " ".join(positions_raw) for w in
                           ["president", "prime minister", "head of state", "minister of", "secretary of state"]):
                        pep_level = "1 (Head of State / Senior Minister)"
                    elif any(w in " ".join(positions_raw) for w in
                             ["deputy", "director", "governor", "ambassador", "general", "judge"]):
                        pep_level = "2 (Senior Official)"
                    else:
                        pep_level = "3 (Associate / Family Member)"

            # --- Sanction program details (name + listing date + authority) ---
            sanction_details: List[str] = []
            for ds in full_profile.get("datasets", [])[:8]:
                # Try to get listing date from sanctionDate or startDate
                s_date = (props.get("sanctionDate") or props.get("startDate") or [None])[0]
                s_auth = (props.get("authority") or props.get("listingAuthority") or [None])[0]
                detail = str(ds)
                if s_date: detail += f" (listed: {s_date})"
                if s_auth: detail += f" by {s_auth}"
                sanction_details.append(detail)

            # --- Reason for listing / description ---
            listing_reason = (
                props.get("reason") or props.get("notes") or props.get("summary") or []
            )
            listing_reason_str = " | ".join(str(r)[:120] for r in listing_reason[:2]) or "not stated"

            # --- Aliases (critical for AML — people use many names) ---
            all_names = props.get("name", []) + props.get("alias", []) + props.get("weakAlias", [])
            aliases = list(dict.fromkeys(str(n) for n in all_names))  # dedupe, preserve order
            primary_name = aliases[0] if aliases else full_profile.get("caption", name_val)
            alias_str = "; ".join(aliases[1:8]) if len(aliases) > 1 else "none"

            # --- Identity fields ---
            gender      = (props.get("gender") or [None])[0] or "not listed"
            birth_dates = props.get("birthDate", [])
            birth_place = (props.get("birthPlace") or props.get("birthCity") or [None])[0] or "not listed"
            death_date  = (props.get("deathDate") or [None])[0]
            nationalities = props.get("nationality", []) + props.get("citizenship", [])
            nationalities = list(dict.fromkeys(nationalities))

            # --- Document / ID fields ---
            id_numbers    = props.get("idNumber", [])[:4]
            passport_nums = props.get("passportNumber", [])[:3]
            national_ids  = props.get("nationalId", [])[:3]
            tax_ids       = props.get("taxNumber", [])[:2]

            # --- Address / jurisdiction ---
            addresses: List[str] = []
            for addr in (props.get("address") or [])[:3]:
                addresses.append(str(addr)[:100])
            countries_mentioned = list(dict.fromkeys(
                props.get("country", []) + props.get("jurisdiction", [])
            ))[:5]

            # --- Positions (for PEP assessment) ---
            positions = [str(p)[:80] for p in props.get("position", [])[:5]]

            # --- Related entities with typed roles ---
            related_lines: List[str] = []
            for ent in full_profile.get("referenced_entities", []):
                if ent.get("id") == entity_id:
                    continue
                ep2      = ent.get("properties", {})
                rel_name = ((ep2.get("name") or [None])[0]) or ent.get("caption", "Unknown")
                rel_ctry = ((ep2.get("country") or ep2.get("nationality") or [None])[0]) or "?"
                # Try to infer relationship type from schema
                rel_schema = ent.get("schema", "")
                if rel_schema in ("Company", "Organization", "LegalEntity"):
                    role = "organization"
                elif rel_schema == "Ownership":
                    role = "owner/shareholder"
                elif rel_schema == "Family":
                    role = "family member"
                elif rel_schema == "Associate":
                    role = "known associate"
                else:
                    role = rel_schema.lower() or "associated"
                # Include their risk topics if present
                rel_topics = ep2.get("topics", [])
                risk_note = f" ⚠ {','.join(rel_topics)}" if rel_topics else ""
                related_lines.append(f"{rel_name} ({rel_ctry}) [{role}]{risk_note}")
                if len(related_lines) >= 8:
                    break

            # --- Other candidates (ambiguous matches the AML officer must review) ---
            other_candidates: List[str] = []
            for c in ranked[1:4]:
                c_caption = c.get("caption") or c.get("id", "?")
                c_score   = c.get("score")
                c_src     = c.get("_source", "?")
                other_candidates.append(
                    f"{c_caption} (score={c_score}, source={c_src})"
                )

            # --- Data freshness ---
            last_seen   = full_profile.get("last_seen") or full_profile.get("last_change") or "unknown"
            first_seen  = full_profile.get("first_seen") or "unknown"

            # --- Source URLs ---
            sources = props.get("sourceUrl", [])[:4]

            # --- Websites / contact (bonus identity signal) ---
            websites = props.get("website", [])[:2]
            emails   = props.get("email", [])[:2]

            # ----------------------------------------------------------------
            # Format as structured plain text — ~400–600 tokens for a rich PEP
            # ----------------------------------------------------------------
            sep = "-" * 50
            sections: List[str] = [
                "=== YENTE / OPENSANCTIONS RESULT ===",
                "",
                "[ IDENTITY ]",
                f"  Primary Name  : {primary_name}",
                f"  Aliases       : {alias_str}",
                f"  Schema        : {full_profile.get('schema', '?')}",
                f"  Gender        : {gender}",
                f"  Date of Birth : {', '.join(birth_dates) or 'not listed'}",
                f"  Place of Birth: {birth_place}",
                f"  Nationalities : {', '.join(nationalities) or 'not listed'}",
            ]
            if death_date:
                sections.append(f"  Date of Death : {death_date}")

            sections += [
                "",
                "[ RISK ASSESSMENT ]",
                f"  Match Score   : {best.get('score', 'N/A')} "
                f"({'HIGH' if (best.get('score') or 0) > 0.8 else 'MEDIUM' if (best.get('score') or 0) > 0.5 else 'LOW — treat with caution'})",
                f"  Risk Flags    : {', '.join(risk_flags) if risk_flags else 'NONE'}",
                f"  Topics        : {', '.join(topics) if topics else 'none'}",
                f"  PEP Level     : {pep_level}",
                f"  Listing Reason: {listing_reason_str}",
                "",
                "[ SANCTIONS & PROGRAMS ]",
            ]
            if sanction_details:
                for sd in sanction_details:
                    sections.append(f"  • {sd}")
            else:
                sections.append("  none")

            sections += [
                "",
                "[ POSITIONS HELD ]",
            ]
            if positions:
                for pos in positions:
                    sections.append(f"  • {pos}")
            else:
                sections.append("  none on record")

            sections += [
                "",
                "[ DOCUMENTS & IDENTIFIERS ]",
                f"  ID Numbers    : {', '.join(id_numbers) or 'none'}",
                f"  Passports     : {', '.join(passport_nums) or 'none'}",
                f"  National IDs  : {', '.join(national_ids) or 'none'}",
                f"  Tax IDs       : {', '.join(tax_ids) or 'none'}",
                "",
                "[ ADDRESSES & JURISDICTION ]",
                f"  Countries     : {', '.join(countries_mentioned) or 'not listed'}",
            ]
            if addresses:
                for addr in addresses:
                    sections.append(f"  Address       : {addr}")

            sections += [
                "",
                f"[ RELATED ENTITIES ({len(related_lines)}) ]",
            ]
            if related_lines:
                for rl in related_lines:
                    sections.append(f"  • {rl}")
            else:
                sections.append("  none on record")

            if other_candidates:
                sections += [
                    "",
                    "[ OTHER POSSIBLE MATCHES — REVIEW REQUIRED ]",
                ]
                for oc in other_candidates:
                    sections.append(f"  ? {oc}")

            sections += [
                "",
                "[ DATA PROVENANCE ]",
                f"  First Seen    : {first_seen}",
                f"  Last Updated  : {last_seen}",
                f"  Sources       : {' | '.join(sources) or 'none'}",
            ]
            if websites:
                sections.append(f"  Websites      : {' | '.join(websites)}")
            if emails:
                sections.append(f"  Emails        : {' | '.join(emails)}")

            # ENTITY_NAME and ENTITY_ID lines — consumed by WikidataImageFetchTool downstream
            sections += ["", f"ENTITY_NAME: {primary_name}", f"ENTITY_ID: {entity_id}"]

            return "\n".join(sections)

        except Exception as e:
            return f"Yente query failed: {str(e)}"

class WikidataOSINTTool(BaseTool):
    name: str = "Wikidata Subject Image Fetcher"
    description: str = (
        "Fetches the official portrait/photo of a person from Wikidata using their name. "
        "Input: the full text output from YenteEntitySearchTool (contains ENTITY_NAME: and ENTITY_ID: lines). "
        "Searches Wikidata for the person by name, retrieves the P18 image claim, "
        "downloads the image from Wikimedia Commons, saves it to a temp file, "
        "and returns the local file path. Pass this path as subject_image_path to "
        "the Markdown Report Generator so the subject photo appears in the PDF."
    )
    args_schema: Type[BaseModel] = WikidataOSINTInput

    # Wikimedia Foundation User-Agent Policy requires:
    #   <client-name>/<version> (<contact-url-or-email>) <library/platform>
    # Ref: https://meta.wikimedia.org/wiki/User-Agent_policy
    WM_HEADERS: ClassVar[dict] = {
        "User-Agent": (
            "FDAdvisorAMLTool/1.0 "
            "(https://github.com/your-org/fd-advisor; compliance@your-org.example) "
            "python-requests/2.x"
        ),
        "Accept": "application/json",
    }

    def _run(self, yente_output: str) -> str:
        # Step 1: extract ENTITY_NAME from Yente output
        name = None
        for line in yente_output.splitlines():
            if line.startswith("ENTITY_NAME:"):
                name = line.split(":", 1)[1].strip()
                break

        if not name:
            return "WIKIDATA_IMAGE: Could not extract ENTITY_NAME from Yente output."

        try:
            # Step 2: search Wikidata for matching QID
            search_resp = requests.get(
                "https://www.wikidata.org/w/api.php",
                params={
                    "action": "wbsearchentities",
                    "search": name,
                    "language": "en",
                    "type": "item",
                    "format": "json",
                    "limit": 5,
                },
                headers=self.WM_HEADERS,
                timeout=10,
            )
            search_resp.raise_for_status()
            results = search_resp.json().get("search", [])
            if not results:
                return f"WIKIDATA_IMAGE: No Wikidata entity found for '{name}'."

            # Step 3: pick first candidate that has a P18 (image) claim
            image_filename = None
            qid_used = None
            for candidate in results:
                qid = candidate.get("id")
                if not qid:
                    continue
                entity_resp = requests.get(
                    "https://www.wikidata.org/w/api.php",
                    params={
                        "action": "wbgetentities",
                        "ids": qid,
                        "props": "claims",
                        "format": "json",
                    },
                    headers=self.WM_HEADERS,
                    timeout=10,
                )
                entity_resp.raise_for_status()
                claims = (
                    entity_resp.json()
                    .get("entities", {})
                    .get(qid, {})
                    .get("claims", {})
                )
                p18 = claims.get("P18", [])
                if p18:
                    image_filename = (
                        p18[0]
                        .get("mainsnak", {})
                        .get("datavalue", {})
                        .get("value", "")
                    )
                    qid_used = qid
                    break

            if not image_filename:
                return (
                    f"WIKIDATA_IMAGE: Entity '{name}' found on Wikidata "
                    f"but has no P18 portrait image."
                )

            # Step 4: download from Wikimedia Commons at capped width
            # Use the Wikimedia REST thumb API — more reliable than Special:FilePath
            safe_name = image_filename.replace(" ", "_")
            # Commons thumb URL format:
            #   https://commons.wikimedia.org/wiki/Special:FilePath/<file>?width=400
            # We pass our User-Agent so Wikimedia can contact us if there are issues.
            image_url = (
                "https://commons.wikimedia.org/wiki/Special:FilePath/"
                + requests.utils.quote(safe_name, safe="")
                + "?width=400"
            )
            img_resp = requests.get(
                image_url,
                headers={
                    "User-Agent": self.WM_HEADERS["User-Agent"],
                },
                timeout=20,
                stream=True,
            )
            img_resp.raise_for_status()

            content_type = img_resp.headers.get("content-type", "")
            ext = ".png" if "png" in content_type else ".svg" if "svg" in content_type else ".jpg"

            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=ext)
            for chunk in img_resp.iter_content(chunk_size=8192):
                if chunk:
                    tmp.write(chunk)
            tmp.close()

            return (
                f"WIKIDATA_IMAGE_PATH: {tmp.name}\n"
                f"Source: Wikidata {qid_used} — P18 image for '{name}'"
            )

        except Exception as e:
            return f"WIKIDATA_IMAGE: Failed to fetch image for '{name}': {str(e)}'"


class BankDatabaseTool(BaseTool):
    name: str = "Bank Database Query Tool"
    description: str = "Input: SQL query string. Output: Result as JSON string. Use for reading bank data."
    args_schema: Type[BaseModel] = SQLQueryInput

    def _run(self, query: str) -> str:
        try:
            with sqlite3.connect(DB_PATH) as conn:
                cursor = conn.cursor()
                cursor.execute(query)
                records = cursor.fetchall()
                columns = [description[0] for description in cursor.description]
                
                result = []
                for record in records:
                    result.append(dict(zip(columns, record)))
                
                return json.dumps(result, default=str, indent=2)
        except Exception as e:
            return f"Database error: {str(e)}"