# tools/config.py
# ---------------------------------------------------------------------------
# Shared configuration, directory paths, database connection, country data,
# and Neo4j lazy-loader helpers used across all tool modules.
# ---------------------------------------------------------------------------

import os
import re
import time
import random
import requests
import pycountry
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional
from langchain_community.utilities import SQLDatabase
from langchain_nvidia_ai_endpoints import NVIDIA
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Directory paths
# ---------------------------------------------------------------------------
DB_PATH = Path(__file__).resolve().parent.parent / "bank_poc.db"

GRAPH_OUTPUT_DIR = Path(__file__).resolve().parent.parent / "outputs" / "graphs"
GRAPH_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

PDF_OUTPUT_DIR = Path(__file__).resolve().parent.parent / "outputs" / "reports"
PDF_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

IMAGE_OUTPUT_DIR = Path(__file__).resolve().parent.parent / "outputs" / "images"
IMAGE_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

SESSION_OUTPUT_DIR = Path(__file__).resolve().parent.parent / "outputs" / "sessions"
SESSION_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def build_session_output_path(
    first_name: str,
    last_name: str,
    decision: str,
    ext: str = "pdf",
) -> Path:
    """
    Return a deterministic ``Path`` for any session-scoped output artefact.

    The filename follows the convention::

        outputs/sessions/{first_name}_{last_name}_{YYYY-MM-DD_HH-MM-SS}_{DECISION}.{ext}

    Examples
    --------
    >>> build_session_output_path("John", "Doe", "PASS")
    PosixPath('.../outputs/sessions/John_Doe_2025-07-01_14-35-22_PASS.pdf')
    >>> build_session_output_path("Jane", "Smith", "FAIL", ext="png")
    PosixPath('.../outputs/sessions/Jane_Smith_2025-07-01_09-10-05_FAIL.png')

    Parameters
    ----------
    first_name : str   Client's first name (spaces replaced with underscores).
    last_name  : str   Client's last name  (spaces replaced with underscores).
    decision   : str   AML decision label, e.g. ``'PASS'`` or ``'FAIL'``.
    ext        : str   File extension without leading dot (default ``'pdf'``).
    """
    datetime_str = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    safe_first   = first_name.strip().replace(" ", "_")
    safe_last    = last_name.strip().replace(" ", "_")
    safe_dec     = decision.strip().upper().replace(" ", "_")
    filename     = f"{safe_first}_{safe_last}_{datetime_str}_{safe_dec}.{ext}"
    return SESSION_OUTPUT_DIR / filename

# ---------------------------------------------------------------------------
# SQLite / LangChain DB connection (shared across tools)
# ---------------------------------------------------------------------------
langchain_db = SQLDatabase.from_uri(f"sqlite:///{DB_PATH}?check_same_thread=False")

# ---------------------------------------------------------------------------
# Neo4j settings
# ---------------------------------------------------------------------------
NEO4J_URI      = os.getenv("NEO4J_URI",      "bolt://localhost:7687")
NEO4J_USER     = os.getenv("NEO4J_USER",     "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password123")
YENTE_URL      = os.getenv("YENTE_URL",      "http://localhost:8000")

# Lazy-loaded Neo4j objects — populated by the helpers below
graph          = None   # LangChain Neo4jGraph (schema only)
_neo4j_driver  = None   # Native neo4j driver (query execution)
_neo4j_schema  = None   # Cached schema string


def _get_neo4j_graph():
    """
    Lazy-load LangChain Neo4jGraph and cache the schema on first use.
    Used ONLY for schema introspection — NOT for running queries.
    """
    global graph, _neo4j_schema
    if graph is None:
        try:
            from langchain_community.graphs import Neo4jGraph
            graph = Neo4jGraph(
                url=NEO4J_URI,
                username=NEO4J_USER,
                password=NEO4J_PASSWORD,
                timeout=5,
            )
            _neo4j_schema = graph.schema
        except Exception:
            pass
    return graph


def _get_native_neo4j_driver():
    """
    Lazy-load the native neo4j Python driver.
    Returns Record objects with real Node/Relationship types needed by the
    graph-image generator.
    """
    global _neo4j_driver
    if _neo4j_driver is None:
        try:
            from neo4j import GraphDatabase
            drv = GraphDatabase.driver(
                NEO4J_URI,
                auth=(NEO4J_USER, NEO4J_PASSWORD),
                connection_timeout=5,
                max_transaction_retry_time=5,
            )
            drv.verify_connectivity()
            _neo4j_driver = drv
        except Exception:
            _neo4j_driver = None
    return _neo4j_driver


def get_neo4j_schema_context() -> str:
    """
    Returns the cached Neo4j schema string, triggering a lazy load if not yet
    populated.  Always reads the live module-level ``_neo4j_schema`` so that
    callers who imported this function before the schema was loaded still get
    the correct value after ``_get_neo4j_graph()`` has been called.
    """
    import tools.config as _self   # re-import own module to read the live global
    if not _self._neo4j_schema:
        _get_neo4j_graph()         # populates _self._neo4j_schema as a side-effect
    return _self._neo4j_schema or "Schema not available. Use generic Cypher query patterns."


# ---------------------------------------------------------------------------
# Country / currency data (restcountries.com — cached in-process)
# ---------------------------------------------------------------------------
_COUNTRY_DATA_CACHE: Dict[str, Dict] = {}
_DEFAULT_DDG_REGION = "wt-wt"


def _make_ddg_region(country_code: str) -> str:
    return f"{country_code.lower()}-en"


def fetch_country_data() -> Dict[str, Dict]:
    """
    Fetches all countries from restcountries.com v3.
    Returns a dict keyed by ISO 3166-1 alpha-2 code with name, currency_symbol,
    currency_code, and ddg_region. Falls back to a minimal hardcoded set on failure.
    """
    global _COUNTRY_DATA_CACHE
    if _COUNTRY_DATA_CACHE:
        return _COUNTRY_DATA_CACHE

    try:
        resp = requests.get(
            "https://restcountries.com/v3.1/all?fields=cca2,name,languages,currencies",
            timeout=10,
        )
        resp.raise_for_status()
        raw = resp.json()
    except Exception:
        raw = []

    result: Dict[str, Dict] = {}
    for c in raw:
        cc = c.get("cca2", "").upper()
        if not cc:
            continue
        name        = c.get("name", {}).get("common", cc)
        currencies  = c.get("currencies", {})
        currency_code   = next(iter(currencies), "")
        currency_symbol = currencies[currency_code].get("symbol", currency_code) if currency_code else ""
        result[cc] = {
            "name":            name,
            "currency_symbol": currency_symbol,
            "currency_code":   currency_code,
            "ddg_region":      _make_ddg_region(cc),
        }

    result["WW"] = {
        "name":            "Worldwide",
        "currency_symbol": "",
        "currency_code":   "",
        "ddg_region":      _DEFAULT_DDG_REGION,
    }
    _COUNTRY_DATA_CACHE = result
    return result


# Small LLM helper (used for self-healing Cypher fixes)
def get_llm_3():
    return NVIDIA(model="meta/llama-3.1-8b-instruct")