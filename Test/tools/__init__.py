# tools/__init__.py
# Import crewai tools with graceful fallback for when crewai is not installed
CREWAI_AVAILABLE = False
try:
    from crewai.tools import tool, BaseTool
    CREWAI_AVAILABLE = True
except ImportError:
    # Provide dummy classes when crewai is not available
    class tool:
        def __init__(self, *args, **kwargs):
            pass
    BaseTool = object

# Import search tool with fallback
try:
    from tools.search_tool import (
        search_news,
        set_search_region,
        ProviderNewsAPISearchTool,
        provider_news_api_tool,
    )
except ImportError as e:
    if CREWAI_AVAILABLE:
        raise
    # Provide dummy exports when crewai is not available
    search_news = None
    set_search_region = None
    ProviderNewsAPISearchTool = None
    provider_news_api_tool = None
from tools.calculator_tool import calculate_deposit
from tools.database_tool import (
    BankDatabaseTool,
    RatesCacheSQLTool,
    UniversalDepositCreationTool,
    SafeNL2SQLTool,
    LangChainToolWrapper,
    rates_sql_tool,
    nl2sql_tool,
    get_sql_toolkit_tools,
    get_all_sql_tools,
)
from tools.document_tool import (
    MarkdownPDFTool,
    MarkdownLoaderTool,
    PDFLoaderTool,
    AMLReportLoaderTool,
    markdown_loader_tool,
    pdf_loader_tool,
    aml_report_loader_tool,
)
from tools.credit_risk_tool import USCreditRiskScorerTool, us_credit_risk_scorer_tool, IndianCreditRiskScorerTool, indian_credit_risk_scorer_tool
from tools.email_tool import EmailSenderTool, GmailSendTool, gmail_send_tool
from tools.neo4j_tool import (
    Neo4jQueryTool,
    Neo4jNameSearchTool,
    Neo4jSchemaInspectorTool,
    GraphCypherQATool,
    neo4j_schema_tool,
    graph_cypher_qa_tool,
    neo4j_name_search_tool,
    build_chain_with_llm,
)
from tools.compliance_tool import YenteEntitySearchTool, WikidataOSINTTool
from tools.news_tool import (
    GDELTEntitySearchTool,
    ICIJOffshoreLeaksTool,
    NewsApiEntitySearchTool,
    gdelt_news_search,
    news_api_tool,
    fetch_provider_news,
)
from tools.kyc_tool import KYCVisionTool, extract_kyc_from_image
from tools.echarts_tool import EChartsBuilderTool, echarts_builder_tool
from tools.config import (
    fetch_country_data,
    get_neo4j_schema_context,
    build_session_output_path,
    DB_PATH,
    langchain_db,
    SESSION_OUTPUT_DIR,
)
from tools.rag_policy_tool import (
    RAGPolicySearchTool,
    RAGPolicyStatsTool,
    RAGEnforcementTool,
    RAGPolicyCompleteTool,
    rag_policy_search_tool,
    rag_policy_stats_tool,
    rag_enforcement_tool,
    rag_policy_complete_tool,
)
from tools.US_mortgage_tool import US_Mortgage_Analytics_Tool

__all__ = [
    "search_news",
    "set_search_region",
    "ProviderNewsAPISearchTool",
    "provider_news_api_tool",
    "calculate_deposit",
    "BankDatabaseTool",
    "RatesCacheSQLTool",
    "UniversalDepositCreationTool",
    "SafeNL2SQLTool",
    "LangChainToolWrapper",
    "rates_sql_tool",
    "nl2sql_tool",
    "get_sql_toolkit_tools",
    "get_all_sql_tools",
    "MarkdownPDFTool",
    "MarkdownLoaderTool",
    "PDFLoaderTool",
    "AMLReportLoaderTool",
    "markdown_loader_tool",
    "pdf_loader_tool",
    "aml_report_loader_tool",
    # "CreditRiskScoringTool",  # Class does not exist
    "EmailSenderTool",
    "GmailSendTool",
    "gmail_send_tool",
    "Neo4jQueryTool",
    "Neo4jNameSearchTool",
    "Neo4jSchemaInspectorTool",
    "GraphCypherQATool",
    "neo4j_schema_tool",
    "graph_cypher_qa_tool",
    "neo4j_name_search_tool",
    "build_chain_with_llm",
    "YenteEntitySearchTool",
    "WikidataOSINTTool",
    "GDELTEntitySearchTool",
    "ICIJOffshoreLeaksTool",
    "NewsApiEntitySearchTool",
    "gdelt_news_search",
    "news_api_tool",
    "KYCVisionTool",
    "extract_kyc_from_image",
    "EChartsBuilderTool",
    "echarts_builder_tool",
    "fetch_country_data",
    "get_neo4j_schema_context",
    "build_session_output_path",
    "DB_PATH",
    "langchain_db",
    "SESSION_OUTPUT_DIR",
    "RAGPolicySearchTool",
    "RAGPolicyStatsTool",
    "RAGEnforcementTool",
    "RAGPolicyCompleteTool",
    "rag_policy_search_tool",
    "rag_policy_stats_tool",
    "rag_enforcement_tool",
    "rag_policy_complete_tool",
    "USCreditRiskScorerTool",
    "us_credit_risk_scorer_tool",
    "US_Mortgage_Analytics_Tool",
]
