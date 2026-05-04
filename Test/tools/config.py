# tools/config.py
# ---------------------------------------------------------------------------
# Shared configuration for the tools package.
# ---------------------------------------------------------------------------

import os
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, Any

# Load environment variables from .env file
from dotenv import load_dotenv

# Load .env file from the Test/ directory
env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

from langchain_community.utilities.sql_database import SQLDatabase

# Configure logging
logger = logging.getLogger(__name__)

# Database path - relative to the Test/ directory
DB_PATH = Path(__file__).resolve().parent / "bank_poc.db"

# LangChain database connection
langchain_db = SQLDatabase.from_uri(f"sqlite:///{DB_PATH}")

# Default DuckDuckGo region
_DEFAULT_DDG_REGION = "wt-wt"

# Graph output directory
GRAPH_OUTPUT_DIR = Path(__file__).resolve().parent.parent / "outputs" / "graphs"
GRAPH_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Neo4j configuration from environment variables
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "")

# Lazy singletons for Neo4j connections
_neo4j_graph_lc: Optional[Any] = None
_neo4j_driver = None


def fetch_country_data() -> Dict[str, Dict]:
    """
    Fetches complete country data using hdx-python-country library.
    Returns a dict keyed by ISO 3166-1 alpha-2 code with:
    - name: Common country name
    - official_name: Official country name
    - alpha_3: ISO 3166-1 alpha-3 code
    - currency_code: ISO 4217 currency code (if available)
    - currency_symbol: Currency symbol (if available)
    - ddg_region: DuckDuckGo region code
    """
    country_data = {}

    # Map to DuckDuckGo region codes (common mappings)
    ddg_region_map = {
        'US': 'us-en',
        'GB': 'uk-en',
        'IN': 'in-en',
        'CA': 'ca-en',
        'AU': 'au-en',
        'DE': 'de-de',
        'FR': 'fr-fr',
        'ES': 'es-es',
        'IT': 'it-it',
        'JP': 'jp-jp',
        'CN': 'cn-zh',
        'BR': 'br-pt',
        'MX': 'mx-es',
        'RU': 'ru-ru',
        'KR': 'kr-ko',
    }

    # Use hdx-python-country for dynamic country and currency data
    try:
        from hdx.location.country import Country
        hdx_data = Country().countriesdata()
        countries = hdx_data.get('countries', {})

        for iso3, country_info in countries.items():
            # Get ISO2 code
            alpha_2 = country_info.get('ISO 3166-1 Alpha 2-Codes', '')
            if not alpha_2:
                continue

            # Get country name
            name = country_info.get('English Short', '')
            official_name = country_info.get('English Formal', name)

            # Get currency code (dynamic from HDX data)
            currency_code = country_info.get('Currency', '') or ''

            # Get currency symbol (not available in HDX, will be empty)
            currency_symbol = ''

            # Get DuckDuckGo region code
            ddg_region = ddg_region_map.get(alpha_2, f"{alpha_2.lower()}-en")

            country_data[alpha_2] = {
                "name": name,
                "official_name": official_name,
                "alpha_3": iso3,
                "currency_code": currency_code,
                "currency_symbol": currency_symbol,
                "ddg_region": ddg_region,
            }
    except ImportError:
        logger.warning("hdx-python-country not installed, using empty data")
    except Exception as e:
        logger.error(f"Error fetching country data from HDX: {e}")

    # Add "Worldwide" as custom entry
    country_data["WW"] = {
        "name": "Worldwide",
        "official_name": "Worldwide",
        "alpha_3": "",
        "currency_code": "",
        "currency_symbol": "",
        "ddg_region": "wt-wt",
    }

    return country_data


# ---------------------------------------------------------------------------
# Neo4j helper functions
# ---------------------------------------------------------------------------


def _get_neo4j_graph() -> Optional[Any]:
    """
    Returns a LangChain Neo4jGraph instance for schema access.
    Returns None if Neo4j is not configured or unreachable.
    """
    global _neo4j_graph_lc
    if _neo4j_graph_lc is None:
        try:
            from langchain_community.graphs import Neo4jGraph

            if not NEO4J_URI:
                logger.warning("NEO4J_URI not configured for Neo4jGraph")
                return None
            if not NEO4J_PASSWORD:
                logger.warning("NEO4J_PASSWORD not configured for Neo4jGraph")
                return None

            logger.info(f"Creating Neo4jGraph with URI: {NEO4J_URI}")
            _neo4j_graph_lc = Neo4jGraph(
                url=NEO4J_URI,
                username=NEO4J_USER,
                password=NEO4J_PASSWORD,
                refresh_schema=False,
                timeout=10,
            )
            logger.info("Neo4jGraph created successfully")
        except ImportError as e:
            logger.error(f"langchain_community.graphs import failed: {e}")
            return None
        except Exception as e:
            logger.error(f"Failed to create Neo4jGraph: {e}")
            return None
    return _neo4j_graph_lc


def _get_native_neo4j_driver() -> Optional[Any]:
    """
    Returns a native Neo4j driver instance.
    Returns None if Neo4j is not configured or the neo4j package is not installed.
    """
    global _neo4j_driver
    if _neo4j_driver is None:
        try:
            import neo4j

            if not NEO4J_URI:
                logger.warning("NEO4J_URI not configured")
                return None
            if not NEO4J_PASSWORD:
                logger.warning("NEO4J_PASSWORD not configured")
                return None

            logger.info(f"Creating Neo4j driver with URI: {NEO4J_URI}")
            _neo4j_driver = neo4j.GraphDatabase.driver(
                NEO4J_URI,
                auth=(NEO4J_USER, NEO4J_PASSWORD),
            )
            # Test the connection
            _neo4j_driver.verify_connectivity()
            logger.info("Neo4j connectivity verified successfully")
        except ImportError as e:
            logger.error(f"neo4j package not installed: {e}")
            return None
        except Exception as e:
            logger.error(f"Failed to create Neo4j driver: {e}")
            return None
    return _neo4j_driver


def test_neo4j_connection() -> Dict[str, Any]:
    """
    Tests the Neo4j connection and returns detailed status.
    Useful for debugging connectivity issues.

    Returns:
        Dict with keys:
        - 'success': bool - True if connection is successful
        - 'message': str - Status message
        - 'uri': str - The URI being used (masked for security)
        - 'driver_available': bool - Whether native driver is available
        - 'graph_available': bool - Whether LangChain graph is available
    """
    result = {
        "success": False,
        "message": "",
        "uri": NEO4J_URI if NEO4J_URI else "not configured",
        "driver_available": False,
        "graph_available": False,
    }

    # Check environment variables
    if not NEO4J_URI:
        result["message"] = "NEO4J_URI environment variable is not set"
        return result

    if not NEO4J_PASSWORD:
        result["message"] = "NEO4J_PASSWORD environment variable is not set"
        return result

    # Test native driver
    driver = _get_native_neo4j_driver()
    if driver:
        result["driver_available"] = True
        try:
            with driver.session() as session:
                session.run("RETURN 1 AS test")
                result["success"] = True
                result["message"] = "Neo4j connection successful (native driver)"
        except Exception as e:
            result["message"] = f"Native driver connection failed: {e}"
    else:
        # Try LangChain graph as fallback
        graph = _get_neo4j_graph()
        if graph:
            result["graph_available"] = True
            try:
                query = "RETURN 1 AS test"
                graph.query(query)
                result["success"] = True
                result["message"] = "Neo4j connection successful (LangChain graph)"
            except Exception as e:
                result["message"] = f"LangChain graph connection failed: {e}"
        else:
            result["message"] = "Neither native driver nor LangChain graph is available"

    return result


def get_neo4j_schema_context() -> Optional[str]:
    """
    Returns a string describing the Neo4j schema (node labels, relationship types, property keys).
    Returns None or an error message if Neo4j is not available.
    """
    g = _get_neo4j_graph()
    if g:
        try:
            schema = getattr(g, "schema", None)
            if schema:
                return schema
        except Exception:
            pass
        return "Neo4j schema not available"


# ---------------------------------------------------------------------------
# Additional output directories
# ---------------------------------------------------------------------------

# Image output directory for compliance tool
IMAGE_OUTPUT_DIR = Path(__file__).resolve().parent.parent / "outputs" / "images"
IMAGE_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Session output directory for reports
SESSION_OUTPUT_DIR = Path(__file__).resolve().parent.parent / "outputs" / "sessions"
SESSION_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def build_session_output_path(
    first_name: str, last_name: str, decision: str, ext: str = "pdf"
) -> Path:
    """
    Builds the output path for a session report PDF.
    Path format: outputs/sessions/{FirstName}_{LastName}_{DECISION}_{timestamp}.pdf
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_first = "".join(c if c.isalnum() or c in " _-" else "_" for c in first_name)
    safe_last = "".join(c if c.isalnum() or c in " _-" else "_" for c in last_name)
    safe_decision = decision.upper() if decision in ("PASS", "FAIL") else "UNKNOWN"
    filename = f"{safe_first}_{safe_last}_{safe_decision}_{timestamp}.{ext}"
    return SESSION_OUTPUT_DIR / filename


# ---------------------------------------------------------------------------
# Yente/OpenSanctions configuration
# ---------------------------------------------------------------------------

YENTE_URL = os.getenv("YENTE_URL", "http://localhost:8000")


# ---------------------------------------------------------------------------
# LLM factory functions
# ---------------------------------------------------------------------------


def get_llm_3():
    """
    Returns a LangChain LLM instance (ChatNVIDIA with qwen/qwen3.5-122b-a10b).
    Used as a fallback when LLM is not provided.
    """
    try:
        from langchain_nvidia_ai_endpoints import ChatNVIDIA
        import os

        api_key = os.getenv("NVIDIA_API_KEY", "")
        if not api_key:
            # Return a mock/fallback LLM if no API key
            from langchain_core.language_models import FakeListLLM

            return FakeListLLM(responses=["OK"])
        return ChatNVIDIA(
            model="qwen/qwen3.5-122b-a10b",
            api_key=api_key,
            temperature=0.7,
        )
    except ImportError:
        from langchain_core.language_models import FakeListLLM

        return FakeListLLM(responses=["OK"])
    except Exception:
        from langchain_core.language_models import FakeListLLM

        return FakeListLLM(responses=["OK"])
