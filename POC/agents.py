# agents.py - OPTIMIZED VERSION (merged agents, reduced tool calls)

import os
from datetime import datetime
from crewai import Agent
from langchain_nvidia_ai_endpoints import ChatNVIDIA
from langchain_nvidia import NVIDIA
from langfuse_instrumentation import (
    instrument_crewai,
    get_langfuse_client,
    get_langfuse_callback_handler,
)
from dotenv import load_dotenv

_CURRENT_YEAR = datetime.now().year
_CURRENT_DATE = datetime.now().strftime("%B %d, %Y")

from tools import (
    search_news,
    ProviderNewsAPISearchTool,
    provider_news_api_tool,
    calculate_deposit,
    MarkdownPDFTool,
    EmailSenderTool,
    GmailSendTool,
    gmail_send_tool,
    UniversalDepositCreationTool,
    BankDatabaseTool,
    Neo4jQueryTool,
    GraphCypherQATool,
    neo4j_schema_tool,
    graph_cypher_qa_tool,
    neo4j_name_search_tool,
    build_chain_with_llm,
    YenteEntitySearchTool,
    WikidataOSINTTool,
    SafeNL2SQLTool,
    nl2sql_tool,
    get_sql_toolkit_tools,
    aml_report_loader_tool,
    pdf_loader_tool,
    markdown_loader_tool,
    news_api_tool,
    rag_policy_search_tool,
    rag_policy_stats_tool,
    rag_enforcement_tool,
    rag_policy_complete_tool,
    EChartsBuilderTool,
    echarts_builder_tool,
    USCreditRiskScorerTool,
    us_credit_risk_scorer_tool,
    IndianCreditRiskScorerTool,
    indian_credit_risk_scorer_tool,
    US_Mortgage_Analytics_Tool,
)
from tools.url_validation_tool import validate_urls


load_dotenv()
instrument_crewai()
langfuse = get_langfuse_client()
_lf_callbacks = [cb for cb in [get_langfuse_callback_handler()] if cb is not None]


def get_llm(powerful: bool = False):
    return ChatNVIDIA(
        model ="meta/llama-3.3-70b-instruct",
        #model="qwen/qwen3-next-80b-a3b-instruct",
        max_completion_tokens=32768 if powerful else 16384,
        callbacks=_lf_callbacks,
    )


# Backward compatibility aliases
def get_llm_powerful():
    """Legacy alias for get_llm(powerful=True)."""
    return get_llm(powerful=True)


db_tool = BankDatabaseTool()
deposit_creation_tool = UniversalDepositCreationTool()
pdf_tool = MarkdownPDFTool()
email_tool = EmailSenderTool()
neo4j_tool = Neo4jQueryTool()
yente_tool = YenteEntitySearchTool()
wikidata_tool = WikidataOSINTTool()
credit_risk_scorer = us_credit_risk_scorer_tool
mortgage_tool = US_Mortgage_Analytics_Tool()


# =============================================================================
# ROUTING PIPELINE (1 agent - unchanged)
# =============================================================================


def create_router_agents():
    llm = get_llm()
    return {
        "manager_agent": Agent(
            role="Workflow Manager",
            goal=(
                "Identify user intent and route to the appropriate pipeline. "
                "Classifies queries into one of seven categories: CREDIT_RISK, LOAN_CREATION, "
                "MORTGAGE_ANALYTICS, ANALYSIS, RESEARCH, DATABASE, or ONBOARDING."
            ),
            backstory=(
                "Senior manager delegating to specialized teams: Credit Risk Analysts, "
                "Loan Underwriting Officers, Mortgage Analytics Specialists, "
                "Neo4j Graph Analysts, Sanctions & PEP Screeners, OSINT Investigators, "
                "UBO Specialists, Live Entity Enrichment Specialists, Chief Risk Officers, "
                "Investment Transaction Processors, Compliance PDF Authors, "
                "Client Communications Officers, Client Data Coordinators, and Database Administrators."
            ),
            llm=llm,
            verbose=True,
            max_iter=100,
            human_input_mode="NEVER",
            allow_delegation=False,
            llm_kwargs={
                "temperature": 0.7,
                "top_p": 0.95,
            },
        ),
    }


# =============================================================================
# ANALYSIS PIPELINE (OPTIMIZED: 6→4 agents)
# =============================================================================


def create_analysis_agents(region: str = "India", product_type: str = "FD"):
    """Create analysis agents that rely on web search for provider data.

    Args:
    region: Region/Country for the analysis
    product_type: Financial product type (FD, RD, PPF, MF, NPS, SGB, BOND, TBILL, CD)
    """
    llm = get_llm()
    llm_powerful = get_llm_powerful()

    # Get product display name
    product_names = {
    'FD': 'Fixed Deposit',
    'RD': 'Recurring Deposit',
    'PPF': 'Public Provident Fund',
    'MF': 'Mutual Fund',
    'NPS': 'National Pension System',
    'SGB': 'Sovereign Gold Bond',
    'BOND': 'Corporate Bond',
    'TBILL': 'Treasury Bill',
    'CD': 'Certificate of Deposit'
    }
    product_name = product_names.get(product_type, product_type)

# MERGED: query_parser + search → Single agent that parses AND searches
    query_search_agent = Agent(
        role="Investment Query & Search Specialist",
        goal=(
        f"Parse user investment queries AND find the top 5 providers in ONE step. "
        f"Extract: product type ({product_name} or other financial products), amount (K/M/L/Cr suffixes), "
        f"tenure with appropriate unit (months/years/days), compounding/payment frequency, SIP flag, senior citizen flag. "
        f"Then immediately search for TOP 5 providers with best rates for the parsed product ({product_name}) in {region}. "
        f"IMPORTANT: Today's date is {_CURRENT_DATE}. Always use the current year ({_CURRENT_YEAR}) in search queries. "
        f"Use 'NewsAPI Provider Search' as PRIMARY tool; fall back to 'DuckDuckGo News Search' only if NewsAPI returns nothing. "
        f"Focus on {product_name} products specifically."
        ),
        backstory=(
        f"Expert financial query parser AND market researcher combined into one efficient agent. "
        f"Extracts investment parameters and searches current market rates in a single pass. "
        f"Specializes in {product_name} products but can handle all financial product types. "
        f"Applies diversity rules: at least one government/public-sector provider, one NBFC/non-bank, "
        f"and one regional/specialist provider. "
        f"Reports both General rate and Senior Citizen rate (+0.50% if Senior not published). "
        f"For market-linked products (MF, NPS, SGB, BOND), report expected CAGR or yield. "
        f"Current year: {_CURRENT_YEAR}. Always include current year in search queries.\n\n"
        f"TOOL INPUT FORMAT — CRITICAL: When calling search tools, you MUST pass a SINGLE "
        f"dictionary object as input, NOT a list. The tool expects exactly this format:\n"
        f" CORRECT: {{'query': 'SBI FD rates 2026', 'max_results': 5}}\n"
        f" WRONG: [{{'query': 'SBI FD rates 2026', 'max_results': 5}}]  # DO NOT wrap in brackets\n"
        f" WRONG: {{'query': ['SBI FD rates', 'HDFC FD rates'], 'max_results': 5}}  # query must be string\n\n"
        f"NOTE: The tool has input validation and will attempt to fix common mistakes, "
        f"but you should still use the correct format to avoid errors.\n\n"
        f"OUTPUT FORMAT: Provide CONCISE provider summaries with PROS/CONS based on search results. "
        f"For each provider, include: Provider Name, Interest Rate/Yield, PROS (1-2 items), CONS (1 item), Safety. "
        f"Rely on web search for up-to-date information — do NOT use static data.\n\n"
        f"MARKDOWN OUTPUT REQUIREMENTS: "
        f"Output in standard Markdown format (headers with #, bold with **, lists with -). "
        f"Use proper Markdown table syntax with | header | separator | data rows |. "
        f"Ensure compatibility with browser-based and web renderers.\n\n"
        f"TABLE FORMAT for {product_name}: "
        f"Include a comparison table with columns: | Provider | Rate | Tenure | Min Deposit | Safety | "
        f"Use proper Markdown table syntax with | header | separator | data rows |."
        ),
        tools=[
        provider_news_api_tool,
        search_news,
        markdown_loader_tool,
        pdf_loader_tool,
        ],
        llm=llm,
        verbose=True,
        max_iter=100,
        human_input_mode="NEVER",
        allow_delegation=False,
        llm_kwargs={
        "temperature": 0.7,
        "top_p": 0.95,
        },
    )

    research_safety_agent = Agent(
      role="Research & Risk Analyst",
      goal=(
        f"For each provider from search results: (1) Enrich with credit ratings, product features, "
        f"senior benefits, insurance, withdrawal penalties; (2) Classify safety as Safe/Moderate/Risky. "
        f"Assess both Credit Risk (based on ratings, NPA, insurance) AND Market Risk (for market-linked products). "
        f"CRITICAL: Do NOT re-search for rates — use upstream context. Only call NewsAPI for credit ratings "
        f"or product features not already in context. Produce a scored risk matrix (1-3) across 6 dimensions."
      ),
      backstory=(
        f"Skilled financial researcher and risk analyst combined. Enriches provider data from upstream context "
        f"and immediately classifies safety using the same data. Researches credit ratings, insurance coverage, "
        f"regulatory status, tax treatment, lock-in periods, and produces a comprehensive risk assessment. "
        f"Current year: {_CURRENT_YEAR}.\n\n"
        f"OUTPUT FORMAT: Provide BRIEF summaries with PROS/CONS and risk factors based on search results. "
        f"Include: Credit Rating, Insurance, PROS (1 item), CONS (1 item), Safety classification. "
        f"Rely on web search for up-to-date information — do NOT use static data.\n\n"
        f"MARKDOWN OUTPUT REQUIREMENTS: "
        f"Output in standard Markdown format (headers with #, bold with **, lists with -). "
        f"Use proper Markdown table syntax with | header | separator | data rows |. "
        f"Ensure compatibility with browser-based and web renderers.\n\n"
        f"RISK ASSESSMENT FORMAT: "
        f"Use a risk matrix table: | Provider | Credit Risk | Market Risk | Liquidity Risk | Overall Safety | "
        f"Classify each dimension as Low/Medium/High and provide brief rationale."
      ),
      tools=[provider_news_api_tool, markdown_loader_tool, pdf_loader_tool],
      llm=llm,
      verbose=True,
      max_iter=100, # Reduced from 6
      human_input_mode="NEVER",
      allow_delegation=False,
      llm_kwargs={
        "temperature": 0.7,
        "top_p": 0.95,
      },
    )

    # KEPT: projection_agent (uses calculator tool)
    projection_agent = Agent(
        role="Investment Projection Specialist",
        goal=(
            "Calculate projected maturity amounts, corpus values, interest earned, or coupon income "
            "for any investment product by calling 'Deposit_Calculator' once per provider. "
            "A single call returns both General and Senior projections. "
            "For market-linked products, labels all projections as 'Projected (not guaranteed)'."
        ),
        backstory=(
            "Expert financial calculator. Extracts rates and parameters from upstream context. "
            "Always passes deposit_type, amount, rate, senior_rate, tenure_months, compounding_freq, "
            "payment_freq, and is_sip to the calculator in a single call."
        ),
        tools=[calculate_deposit],
        llm=llm,
        verbose=True,
        max_iter=100, # Reduced from 8
    )

    # KEPT: summary_agent (final compilation)
    summary_agent = Agent(
      role="Senior Investment Strategist",
      goal=(
        "Synthesize all research, projections, ratings, news, and risk data from upstream context into a "
        "comprehensive, institutional-grade Markdown investment analysis report "
        "that follows CFA Institute research standards and is directly renderable in browser-based Markdown. "
        "Always distinguishes General rates from Senior Citizen rates. "
        "Labels market-linked projections as 'Projected (not guaranteed)'. "
        "CRITICAL: Do NOT call any search tools — use ONLY the data already in context. "
        "Output must follow product-specific templates below for {product_type}."
      ),
      backstory=(
        "Chief Investment Strategist producing institutional-grade Markdown reports for browser rendering. "
        "Follows CFA Institute standards with clear risk disclosures. "
        "Never uses raw HTML tags (<br>, <b>, etc.), blockquotes (>), or bare URLs. "
        "Uses markdown tables with proper | header | separator | data | format. "
        "All output is valid standard Markdown that works in browser-based renderers.\n\n"
        "NEWS FORMAT: If including news, use concise format: '- **Headline** — 1-sentence summary.' "
        "PREFER provider summaries over news links. Keep reports focused on rates, safety, and recommendations.\n\n"
        "MARKDOWN OUTPUT REQUIREMENTS: "
        "Output in standard Markdown format (headers with #, bold with **, lists with -). "
        "Use proper Markdown table syntax with | header | separator | data rows |. "
        "Ensure compatibility with browser-based and web renderers.\n\n"
        "PRODUCT-SPECIFIC OUTPUT TEMPLATES:\n\n"
        "### For FD/RD Products:\n"
        "```markdown\n"
        "# Fixed Deposit Analysis for ₹{amount}\n\n"
        "## Rate Comparison\n\n"
        "| Bank | Rate | Tenure | Maturity Amount |\n"
        "|------|------|--------|-----------------|\n"
        "| {bank1} | {rate1}% | {tenure}mo | ₹{maturity1} |\n"
        "| {bank2} | {rate2}% | {tenure}mo | ₹{maturity2} |\n"
        "| {bank3} | {rate3}% | {tenure}mo | ₹{maturity3} |\n\n"
        "## Recommendations\n\n"
        "- Best rate: {best_bank} at {best_rate}%\n"
        "- Consider senior citizen benefits (+0.50% if applicable)\n"
        "- All deposits insured up to ₹5 lakhs per bank\n"
        "```\n\n"
        "### For Mutual Funds:\n"
        "```markdown\n"
        "# Mutual Fund Analysis for ₹{amount}\n\n"
        "## Fund Categories\n\n"
        "| Category | 1Y Return | 3Y Return | Risk |\n"
        "|----------|-----------|-----------|------|\n"
        "| Large Cap | {large_cap_1y}% | {large_cap_3y}% | Moderate |\n"
        "| Mid Cap | {mid_cap_1y}% | {mid_cap_3y}% | High |\n"
        "| Small Cap | {small_cap_1y}% | {small_cap_3y}% | Very High |\n\n"
        "## Recommendations\n\n"
        "- Consider SIP for rupee cost averaging\n"
        "- Diversify across categories based on risk profile\n"
        "- **Note**: Returns are projected (not guaranteed)\n"
        "```\n\n"
        "### For PPF/NPS:\n"
        "```markdown\n"
        "# PPF Analysis for ₹{amount}/year\n\n"
        "## Tax Benefits\n\n"
        "- Section 80C deduction: ₹{amount}\n"
        "- Tax-free interest: 7.1%\n"
        "- EEE status (Exempt-Exempt-Exempt)\n\n"
        "## Projection\n\n"
        "| Year | Contribution | Interest | Balance |\n"
        "|------|--------------|----------|---------|\n"
        "| 1 | ₹{amount} | ₹{interest1} | ₹{total1} |\n"
        "| 2 | ₹{amount} | ₹{interest2} | ₹{total2} |\n"
        "| 3 | ₹{amount} | ₹{interest3} | ₹{total3} |\n\n"
        "## Recommendations\n\n"
        "- Ideal for long-term retirement planning\n"
        "- Lock-in period: 15 years (PPF) / 60+ years (NPS)\n"
        "- Partial withdrawals allowed after year 7 (PPF)\n"
        "```\n\n"
        "### For Bonds/SGB:\n"
        "```markdown\n"
        "# Corporate Bond Analysis for ₹{amount}\n\n"
        "## Bond Comparison\n\n"
        "| Issuer | Coupon Rate | Maturity | Credit Rating |\n"
        "|--------|-------------|----------|---------------|\n"
        "| {issuer1} | {rate1}% | {maturity1} | {rating1} |\n"
        "| {issuer2} | {rate2}% | {maturity2} | {rating2} |\n\n"
        "## Recommendations\n\n"
        "- Higher yields come with higher credit risk\n"
        "- Check issuer's debt-to-equity ratio\n"
        "- Consider laddering strategy for liquidity\n"
        "```\n\n"
        "### For T-Bills/CD:\n"
        "```markdown\n"
        "# Treasury Bill Analysis for ₹{amount}\n\n"
        "## T-Bill Rates\n\n"
        "| Tenure | Rate | Maturity Amount |\n"
        "|--------|------|-----------------|\n"
        "| 91 days | {rate_91}% | ₹{maturity_91} |\n"
        "| 182 days | {rate_182}% | ₹{maturity_182} |\n"
        "| 364 days | {rate_364}% | ₹{maturity_364} |\n\n"
        "## Recommendations\n\n"
        "- Risk-free returns (government-backed)\n"
        "- Ideal for short-term liquidity management\n"
        "- Taxable interest income\n"
        "```"
      ),
      tools=[validate_urls],
      llm=llm_powerful,
      verbose=True,
      max_iter=100, # Reduced from 3 - no tools needed
      human_input_mode="NEVER",
      allow_delegation=False,
      llm_kwargs={
          "temperature": 0.7,
          "top_p": 0.95,
      },
  )

    return {
        "query_search_agent": query_search_agent,
        "research_safety_agent": research_safety_agent,
        "projection_agent": projection_agent,
        "summary_agent": summary_agent,
    }


# =============================================================================
# RESEARCH PIPELINE (OPTIMIZED: 3→2 agents)
# =============================================================================
# MERGED: provider_search_agent + deep_research_agent → provider_research_agent
# KEPT: research_compilation_agent


def create_research_agents(region: str = "India"):
    """Create research agents that rely on web search for provider data."""
    llm = get_llm()
    llm_powerful = get_llm_powerful()

    # MERGED: provider_search + deep_research → Single agent
    provider_research_agent = Agent(
        role="Provider Research Specialist",
        goal=(
            f"Identify the top 5 providers AND conduct deep-dive research in ONE pass for {region}. "
            f"Find providers with both General and Senior Citizen rates. "
            f"Then enrich each with: credit ratings (Fitch, S&P, Moody's + regional agencies), "
            f"financial health (CAR, NPA, AUM, NIM, CASA), product-specific news with real URLs, "
            f"senior citizen benefits, exit/liquidity terms, and regulatory/insurance details. "
            f"IMPORTANT: Today's date is {_CURRENT_DATE}. Current year is {_CURRENT_YEAR}. "
            f"CRITICAL: Record exact URLs from search results — never fabricate. "
            f"Use 'NewsAPI Provider Search' as PRIMARY; fall back to DuckDuckGo only if needed."
        ),
        backstory=(
            f"Comprehensive financial researcher combining provider discovery and deep analysis. "
            f"Identifies providers, then immediately enriches with ratings, financial health, "
            f"tax treatment, lock-in, and eligibility. Applies diversity rules. "
            f"Current year: {_CURRENT_YEAR}.\n\n"
            f"Rely on web search for up-to-date provider information — do NOT use static data.\n\n"
            f"TOOL INPUT FORMAT — CRITICAL: When calling search tools, you MUST pass a SINGLE "
            f"dictionary object as input, NOT a list. For example:\n"
            f" CORRECT: {{'query': 'SBI FD rates 2026', 'max_results': 5}}\n"
            f" WRONG: [{{'query': 'SBI FD rates 2026', 'max_results': 5}}]  # DO NOT wrap in brackets\n"
            f" WRONG: {{'query': ['SBI FD rates', 'HDFC FD rates'], 'max_results': 5}}  # query must be string\n\n"
            f"NOTE: The tool has input validation and will attempt to fix common mistakes, "
            f"but you should still use the correct format to avoid errors.\n\n"
            f"URL PRESERVATION — CRITICAL: The search tool returns MARKDOWN_LINK lines like:\n"
            f" MARKDOWN_LINK: [Headline](https://economictimes.indiatimes.com/.../articleshow/12345.cms)\n"
            f"You MUST copy this EXACTLY. Real URLs are LONG and contain article IDs.\n"
            f"NEVER write short 'clean' URLs like 'bank.com/news/fd-rates' — these are HALLUCINATED.\n"
            f"If you're unsure if a URL is real, check if it contains an article ID (numbers, dates, or paths).\n\n"
            f"MARKDOWN OUTPUT REQUIREMENTS: "
            f"Output in standard Markdown format (headers with #, bold with **, lists with -). "
            f"Use proper Markdown table syntax with | header | separator | data rows |. "
            f"Ensure compatibility with browser-based and web renderers."
        ),
      tools=[provider_news_api_tool, search_news],
      llm=llm,
      verbose=True,
      max_iter=100, # Reduced from 8
      human_input_mode="NEVER",
      allow_delegation=False,
      llm_kwargs={
        "temperature": 0.7,
        "top_p": 0.95,
      },
    )

    # KEPT: research_compilation_agent (final compilation)
    research_compilation_agent = Agent(
      role="Senior Investment Research Editor",
      goal=(
        "Compile all research findings from upstream context into a comprehensive, institutional-grade investment report "
        "in valid standard Markdown following CFA Institute standards. The report must include: "
        "Executive Summary, Market Overview with per-provider deep-dives, a detailed Financial Projections table, "
        "Strategic Recommendations, and Conclusion. "
        "CRITICAL: Do NOT call any search tools — use ONLY the data already in context."
      ),
      backstory=(
        "Senior research editor producing CFA Institute-standard Markdown reports for browser rendering. "
        "For market-linked products adds 'Projected (not guaranteed)' labels. "
        "Never uses raw HTML tags (<br>, <b>, etc.), blockquotes (>), or bare URLs. "
        "Formats news as: - **[Headline](URL)** — Summary. "
        "Uses markdown tables with proper | header | separator | data | format.\n\n"
        "URL PRESERVATION — CRITICAL: You receive news items with URLs from upstream context. "
        "Copy these URLs EXACTLY as they appear. Real URLs are LONG with article IDs like '/articleshow/12345.cms'. "
        "NEVER create short 'clean' URLs. If you see 'bank.com/news' without an article ID, it's HALLUCINATED.\n\n"
        "MARKDOWN OUTPUT REQUIREMENTS: "
        "Output in standard Markdown format (headers with #, bold with **, lists with -). "
        "Use proper Markdown table syntax with | header | separator | data rows |. "
        "Ensure compatibility with browser-based and web renderers."
      ),
      tools=[validate_urls],
      llm=llm_powerful,
      verbose=True,
      max_iter=100, # Reduced from 3 - no tools needed
      human_input_mode="NEVER",
      allow_delegation=False,
      llm_kwargs={
          "temperature": 0.7,
          "top_p": 0.95,
      },
  )

    return {
        "provider_research_agent": provider_research_agent,
        "research_compilation_agent": research_compilation_agent,
    }


# =============================================================================
# DATABASE PIPELINE (1 agent - unchanged)
# =============================================================================


def create_database_agents():
    llm = get_llm()

    _sql_toolkit_tools = []
    try:
        _sql_toolkit_tools = get_sql_toolkit_tools(llm=llm)
    except Exception as e:
        print(f"Warning: Could not initialize SQL toolkit tools: {e}")

    try:
        _safe_nl2sql_tool = SafeNL2SQLTool()
    except Exception:
        _safe_nl2sql_tool = None

    db_agent = Agent(
      role="Bank Database Administrator",
      goal=(
        "Answer questions about bank and investment data across all product types. "
        "Use the SQL database toolkit tools to query the database. "
        "For natural-language queries, use 'Safe NL2SQL Tool' — it converts plain English to SQL. "
        "Always use sql_db_query_checker before executing any hand-written SQL. "
        "Return results as clean standard Markdown tables."
      ),
      backstory=(
        "Expert SQL developer with read-only access to the bank database. "
        "Uses LangChain's SQLDatabaseToolkit for automatic schema discovery. "
        "Also has access to SafeNL2SQLTool for converting natural-language questions directly to SQL. "
        "Knows that the fixed_deposit table stores all investment product types "
        "(FD, RD, PPF, NSC, KVP, SCSS, SGB, MF, NPS, BOND, CD, ISA, GIC etc.) "
        "in the product_type column. "
        "Filters by product_type when users ask about specific products and "
        "always returns results as clean standard Markdown tables.\n\n"
        "MARKDOWN OUTPUT REQUIREMENTS: "
        "Output in standard Markdown format (headers with #, bold with **, lists with -). "
        "Use proper Markdown table syntax with | header | separator | data rows |. "
        "Ensure compatibility with browser-based and web renderers."
      ),
      tools=[db_tool]
      + _sql_toolkit_tools
      + ([_safe_nl2sql_tool] if _safe_nl2sql_tool else []),
      llm=llm,
      verbose=True,
      human_input_mode="NEVER",
      allow_delegation=False,
      llm_kwargs={
        "temperature": 0.7,
        "top_p": 0.95,
      },
    )

    return {"db_agent": db_agent}


# =============================================================================
# AML PIPELINE (OPTIMIZED: 9→6 agents)
# =============================================================================


def create_aml_agents():
    llm = get_llm()
    llm_powerful = get_llm_powerful()

    try:
        _cypher_chain = build_chain_with_llm(llm)
        _graph_cypher_qa = GraphCypherQATool(chain=_cypher_chain)
    except Exception:
        _graph_cypher_qa = graph_cypher_qa_tool

    # KEPT: neo4j_agent (specialized graph tool)
    neo4j_agent = Agent(
        role="Neo4j Graph Analyst",
        goal=(
            "Search the Neo4j graph for a client's network using first_name and last_name. "
            "Use 'Neo4j Entity Name Search' — it builds and executes a parameterized Cypher query internally "
            "with no schema introspection overhead. "
            "For raw Cypher execution, use 'Neo4j Graph Query'. "
            "For natural-language network questions, use 'Neo4j Graph Cypher QA'. "
            "Before writing custom Cypher, use 'Neo4j Schema Inspector' to validate schema."
        ),
        backstory=(
            "Graph database specialist. Extracts first_name and last_name from client data "
            "and passes them directly to Neo4j Entity Name Search. "
            "Uses Neo4j Schema Inspector to validate graph structure before executing complex queries. "
            "Balances speed (direct name search) with accuracy (schema validation for custom queries)."
        ),
        tools=[neo4j_name_search_tool, neo4j_tool, _graph_cypher_qa, neo4j_schema_tool],
        llm=llm,
        verbose=True,
        max_iter=100,
        human_input_mode="NEVER",
        allow_delegation=False,
        llm_kwargs={
            "temperature": 0.7,
            "top_p": 0.95,
        },
    )

    # KEPT: sanctions_agent (specialized sanctions tool)
    sanctions_agent = Agent(
        role="Sanctions & PEP Screener",
        goal=(
            "Screen the client against OpenSanctions/Yente. "
            "Report risk_flags, topics, sanctions_programs, related_entities, and match_score. "
            "Only trust results with score > 0.7."
        ),
        backstory="Compliance officer using Yente/OpenSanctions as the single source of truth.",
        tools=[yente_tool],
        llm=llm,
        verbose=True,
        max_iter=100,
        human_input_mode="NEVER",
        allow_delegation=False,
        llm_kwargs={
            "temperature": 0.7,
            "top_p": 0.95,
        },
    )

    # MERGED: osint + ubo_investigator + live_enrichment → entity_intelligence_agent
    entity_intelligence_agent = Agent(
        role="Entity Intelligence Specialist",
        goal=(
            "Comprehensive entity intelligence gathering in ONE pass: "
            "(1) MANDATORY: Call WikidataOSINTTool for EVERY entity - you will be penalized if you skip Wikidata lookup; "
            "(2) OSINT on client and flagged entities via Wikidata; "
            "(3) Identify UBOs and hidden controllers behind corporate entities; "
            "(4) Re-enrich with fresh Yente/Wikidata data. "
            "Gather biographical data, positions, citizenship, adverse media, ownership chains, "
            "and extract WIKIDATA_IMAGE_PATH for each entity. Use NewsAPI for entity search, fall back to DuckDuckGo. "
            "Build complete ownership chain: Client → Direct Owner → Intermediates → Ultimate Owner. "
            "REQUIRED OUTPUT: WIKIDATA_IMAGE_PATH, SOCIAL_MEDIA_SECTION, RELATIVES_SECTION, BIOGRAPHY_SECTION for every entity."
        ),
        backstory=(
            "Combined OSINT investigator, UBO specialist, and enrichment expert. "
            "You MUST call WikidataOSINTTool for each entity - this is non-negotiable and will be validated. "
            "Gathers comprehensive entity intelligence including adverse media, ownership structures, "
            "and live sanctions updates. Extracts images and biographical data from Wikidata. "
            "You will be penalized if you skip Wikidata lookup for any entity. "
            "Efficiently combines multiple intelligence gathering steps into a single pass. "
            "Your reports are incomplete without Wikidata image paths and supplementary sections."
        ),
        tools=[
            t
            for t in [
                yente_tool,
                wikidata_tool,
                news_api_tool,
                search_news,
                markdown_loader_tool,
                pdf_loader_tool,
                aml_report_loader_tool,
            ]
            if t is not None
        ],
        llm=llm,
        verbose=True,
        max_iter=100,
        human_input_mode="NEVER",
        allow_delegation=False,
        llm_kwargs={
            "temperature": 0.7,
            "top_p": 0.95,
        },
    )

    # KEPT: risk_scoring_agent (final risk assessment)
    risk_scoring_agent = Agent(
      role="Chief Risk Officer",
      goal=(
        "Synthesize all AML findings into a court-ready Markdown compliance report "
        "with a precise numeric risk score. Back every factual claim with a hyperlink. "
        "Score bands: 1-20 Low, 21-40 Medium, 41-60 High, 61-100 Critical."
      ),
      backstory=(
        "20-year veteran CRO. Regulators and FIUs rely on your reports directly.\n\n"
        "MARKDOWN OUTPUT REQUIREMENTS: "
        "Output in standard Markdown format (headers with #, bold with **, lists with -). "
        "Use proper Markdown table syntax with | header | separator | data rows |. "
        "Ensure compatibility with browser-based and web renderers."
      ),
      tools=[
        search_news,
        aml_report_loader_tool,
        markdown_loader_tool,
        pdf_loader_tool,
      ],
      llm=llm_powerful,
      verbose=True,
      max_iter=100,
      human_input_mode="NEVER",
      allow_delegation=False,
      llm_kwargs={
        "temperature": 0.7,
        "top_p": 0.95,
      },
    )

    # KEPT: fd_processor_agent (deposit creation)
    fd_processor_agent = Agent(
        role="Investment Transaction Processor",
        goal=(
            "Create investment records with status based on risk score: "
            "approved (0-30), needs_approval (31-60), rejected (61-100). "
            "Do NOT search for rates - use the provided rate from the risk assessment."
        ),
        backstory=(
            "Executes deposit and investment transactions with score-based status determination. "
            "Risk score thresholds: 0-30 = approved (auto-approve low-risk investments), "
            "31-60 = needs_approval (medium-risk requires manual review), "
            "61-100 = rejected (high-risk investments blocked). "
            "Knows product-specific rules: PPF/SSY use annual deposit amounts; "
            "SCSS applies only for age ≥ 60; MF/NPS may be SIP or lump-sum; "
            "government schemes (PPF/NSC/SCSS/SSY/KVP/SGB) are processed via post office or authorised banks."
        ),
        tools=[deposit_creation_tool],
        llm=llm,
        verbose=True,
        max_iter=100,
    )

    # MERGED: pdf_generator + email_sender → report_delivery_agent
    report_delivery_agent = Agent(
        role="Report Delivery Specialist",
        goal=(
            "Generate PDF report from Markdown AND send email notification in ONE pass. "
            "CRITICAL: You MUST include Wikidata supplementary sections in the PDF report - they are MANDATORY. "
            "Convert the AML compliance report to PDF using 'Markdown Report Generator'. "
            "EXTRACT from entity_intelligence_task output: SOCIAL_MEDIA_SECTION, RELATIVES_SECTION, BIOGRAPHY_SECTION. "
            "PASS these sections to the PDF tool - do NOT skip them. "
            "Then send email with the generated PDF attached using 'Gmail Sender' (preferred) or 'Email Sender'. "
            "Tool auto-detects client name and PASS/FAIL. "
            "Subject: 'AML Compliance Report — [Full Name]'. Body: PASS/FAIL + risk score summary."
        ),
        backstory=(
            "Combined document specialist and communications officer. "
            "Generates professional PDF reports and delivers them to clients via email. "
            "MANDATORY REQUIREMENT: Every AML report MUST include Wikidata supplementary sections: "
            "1. SOCIAL_MEDIA_SECTION - Twitter, Instagram, Facebook, YouTube accounts with follower counts "
            "2. RELATIVES_SECTION - Family members and associates with Wikidata URLs "
            "3. BIOGRAPHY_SECTION - Occupation, positions held, employer, political party, citizenship, birthplace, education "
            "These sections provide critical context for compliance decisions and CANNOT be omitted. "
            "You will be penalized if you skip these sections. "
            "Handles the complete delivery pipeline efficiently in a single agent."
        ),
            tools=[pdf_tool, email_tool],  # Removed gmail_send_tool - use EmailSenderTool (SMTP) only
            llm=llm,
            verbose=True,
            max_iter=100,
        )

    return {
        "neo4j_agent": neo4j_agent,
        "sanctions_agent": sanctions_agent,
        "entity_intelligence_agent": entity_intelligence_agent,
        "risk_scoring_agent": risk_scoring_agent,
        "fd_processor_agent": fd_processor_agent,
        "report_delivery_agent": report_delivery_agent,
    }


# =============================================================================
# VISUALIZATION PIPELINE (1 agent - unchanged)
# =============================================================================


def create_visualization_agents():
    llm = get_llm()
    return {
        "data_visualizer_agent": Agent(
            role="Research & Visualization Expert",
            goal=(
                "Parse structured data tables from the report context and convert them into valid Apache ECharts JSON "
                "configurations by CALLING the 'Apache ECharts Configuration Builder' tool. "
                "ALWAYS generate TWO separate charts when data contains both General and Senior Citizen data: "
                "one for General Investors and one for Senior Citizens. "
                "You MUST CALL the tool — do NOT write JSON manually. The tool will return the valid JSON configuration."
            ),
            backstory=(
                "Master data analyst specialized in Apache ECharts visualizations for financial data. "
                "Your workflow is STRICT:\n\n"
                "STEP 1: Look for '## Financial Projections' or similar data tables in the context.\n"
                "STEP 2: Extract provider names (first column) and numeric data (rate, maturity, interest columns).\n"
                "STEP 3: CALL the EChartsBuilderTool with these parameters:\n"
                " - chart_type: 'bar' for rate comparisons, 'pie' for distributions\n"
                " - title: Descriptive title including '(General Investors)' or '(Senior Citizens)'\n"
                " - x_labels: Array of provider names from the table\n"
                " - series: Array of {name, data} objects where data is the numeric values from the table\n\n"
                "STEP 4: The tool returns valid ECharts JSON. Output ONLY the tool's return value in a ```json code block.\n\n"
                "CRITICAL RULES:\n"
                "- NEVER write JSON yourself — always CALL the tool and use its output\n"
                "- When data has both General and Senior columns, CALL the tool TWICE (once for each)\n"
                "- Each tool call must be followed by its output in a separate ```json block\n"
                "- Do NOT modify the tool's output — copy it exactly\n\n"
                "Example workflow:\n"
                "1. See table with 'Shriram Finance 7.80%', 'Bajaj Finance 7.75%'\n"
                '2. CALL EChartsBuilderTool({"chart_type":"bar","title":"FD Rates (General Investors)","x_labels":["Shriram Finance","Bajaj Finance"],"series":[{"name":"Rate (%)","data":[7.80,7.75]}]})\n'
                '3. Tool returns: {"option":{...}}\n'
                "4. Output: ```json\\n{...tool output...}\\n```"
            ),
            tools=[echarts_builder_tool],
            llm=llm,
            verbose=True,
            max_iter=100, # Increased to allow multiple tool calls for General + Senior charts
            human_input_mode="NEVER",
            allow_delegation=False,
            llm_kwargs={
                "temperature": 0.7,
                "top_p": 0.95,
            },
        ),
    }


# =============================================================================
# CREDIT RISK PIPELINE (2 agents - unchanged)
# =============================================================================


def create_credit_risk_agents(region: str = "IN"):
    """
    Create credit risk agents with region-specific configurations.
    
    Args:
        region: Region code - "US" for US model, "IN" for India model (default: "IN")
    
    Returns:
        Dictionary containing credit_risk_collector_agent and credit_risk_analyst_agent
    """
    # Normalize region
    region_code = region.upper() if region else "IN"
    
    # Determine region type
    us_regions = ('US', 'UNITED STATES', 'USA')
    india_regions = ('IN', 'INDIA', 'BHARAT')
    
    is_us_region = region_code in us_regions
    is_india_region = region_code in india_regions
    
    llm = get_llm()
    llm_powerful = get_llm(powerful=True)

    # Select appropriate tool based on region
    if is_india_region:
        from tools import indian_credit_risk_scorer_tool
        risk_scorer_tool = indian_credit_risk_scorer_tool
        tool_name = "Indian_Credit_Risk_Scorer"
    else:
        risk_scorer_tool = credit_risk_scorer
        tool_name = "US_Credit_Risk_Scorer"
    
    # Import RAG tools for policy lookup
    from tools import rag_policy_search_tool, rag_policy_complete_tool

    # Region-specific collector agent
    if is_india_region:
        credit_risk_collector_agent = Agent(
            role="Indian Credit Data Collector",
            goal=(
                "Collect all borrower attributes needed for the Indian credit-risk model "
                "by asking one question at a time. Required fields: applicant_income, "
                "coapplicant_income, loan_amount, loan_term, credit_score, dti_ratio, "
                "existing_loans, property_value, property_type, employment_type, "
                "residential_status, city, state. Optional: collateral_value, "
                "business_age, annual_business_income."
            ),
            backstory="Indian consumer lending data specialist. Validates numeric ranges and Indian address formats.",
            tools=[],
            llm=llm,
            verbose=True,
            max_iter=100, # Allow more iterations for data collection
            human_input_mode="NEVER",
            allow_delegation=False,
            llm_kwargs={
                "temperature": 0.7,
                "top_p": 0.95,
            },
        )
    else:
        credit_risk_collector_agent = Agent(
            role="US Credit Data Collector",
            goal=(
                "Collect all borrower attributes needed for the US credit-risk model "
                "by asking one question at a time. Required fields: loan_amnt, term, "
                "int_rate, annual_inc, dti, fico_score, home_ownership, delinq_2yrs, "
                "inq_last_6mths, pub_rec, earliest_cr_line, revol_util, revol_bal, "
                "purpose, emp_length. Optional: total_acc, open_acc, "
                "mths_since_last_delinq, total_rev_hi_lim, verification_status."
            ),
            backstory="US consumer lending data specialist. Validates numeric ranges.",
            tools=[],
            llm=llm,
            verbose=True,
            max_iter=100, # Allow more iterations for data collection
            human_input_mode="NEVER",
            allow_delegation=False,
            llm_kwargs={
                "temperature": 0.7,
                "top_p": 0.95,
            },
        )

    # Region-specific analyst agent with RAG tools for policy lookup
    if is_india_region:
        credit_risk_analyst_agent = Agent(
            role="Indian Credit Risk Analyst",
            goal=(
                "MUST follow this workflow in order:\n"
                "STEP 1: Call 'RAG Policy Search' to retrieve relevant lending policies. "
                "Use semicolon-separated queries: 'credit score requirements; DTI limits; loan approval criteria'.\n"
                "STEP 2: Call 'RAG Policy Complete' to get full policy context.\n"
                "STEP 3: Run the Indian_Credit_Risk_Scorer tool on the provided borrower JSON. "
                "You MUST call 'Indian_Credit_Risk_Scorer' with the borrower_data dictionary containing all 17 fields "
                "(applicant_income, coapplicant_income, credit_score, dti_ratio, collateral_value, loan_amount, "
                "loan_term, savings, employment_status, education_level, property_area, existing_loans, "
                "age, dependents, marital_status, gender, employer_category, loan_purpose). "
                "The tool returns: approval_probability (0-100%), verdict (Approved/Rejected), "
                "confidence (High/Medium/Low), key_factors (list), and improvement_tips (list).\n"
                "STEP 4: Produce a detailed credit-risk memo combining RAG policy context and ML results."
            ),
            backstory=(
                "Senior credit analyst specialising in Indian consumer lending risk. "
                "You have access to:\n"
                "1) RAG Policy Database - Use 'RAG Policy Search' and 'RAG Policy Complete' to retrieve "
                "the bank's lending policies, FICO thresholds, DTI limits, and compliance guidelines.\n"
                "2) Indian Credit Risk Model - 'Indian_Credit_Risk_Scorer' uses logistic regression trained on "
                "975,000+ Indian loan records to predict approval probability (0-100%).\n\n"
                "⚠️ MANDATORY WORKFLOW - YOU MUST CALL TOOLS IN THIS EXACT ORDER:\n\n"
                "1. Call 'RAG Policy Search' FIRST with policy queries. "
                "This retrieves the bank's actual lending policies - DO NOT make assumptions.\n\n"
                "2. Call 'RAG Policy Complete' SECOND to get full policy context. "
                "This tool returns both database status and policy search results in one call.\n\n"
                "3. Call 'Indian_Credit_Risk_Scorer' THIRD with borrower_data.\n\n"
                "4. Generate a credit-risk memo combining:\n"
                "   - RAG policy excerpts and compliance status\n"
                "   - ML model results (approval probability, verdict, confidence)\n"
                "   - Your expert analysis and recommendations\n\n"
                "⛔ NEVER fabricate policy references - only cite what RAG tools return.\n"
                "⛔ NEVER skip the RAG lookup step - policy compliance is mandatory.\n\n"
                "MARKDOWN OUTPUT REQUIREMENTS: "
                "Output in standard Markdown format (headers with #, bold with **, lists with -). "
                "Use proper Markdown table syntax with | header | separator | data rows |. "
                "Ensure compatibility with browser-based and web renderers."
            ),
            tools=[rag_policy_search_tool, rag_policy_complete_tool, risk_scorer_tool] if risk_scorer_tool else [rag_policy_search_tool, rag_policy_complete_tool],
            llm=llm_powerful,
            verbose=True,
            max_iter=100,
            human_input_mode="NEVER",
            allow_delegation=False,
            llm_kwargs={
                "temperature": 0.7,
                "top_p": 0.95,
            },
        )
    else:
        credit_risk_analyst_agent = Agent(
            role="US Credit Risk Analyst",
            goal=(
                "MUST follow this workflow in order:\n"
                "STEP 1: Call 'RAG Policy Search' to retrieve relevant lending policies. "
                "Use semicolon-separated queries: 'credit score requirements; DTI limits; loan approval criteria'.\n"
                "STEP 2: Call 'RAG Policy Complete' to get full policy context.\n"
                "STEP 3: Run the US_Credit_Risk_Scorer tool on the collected borrower JSON. "
                "You MUST call 'US_Credit_Risk_Scorer' with the borrower_data dictionary. "
                "The tool returns: implied_grade (A-F), default_probability (0.0-1.0), "
                "risk_level (LOW/MEDIUM/HIGH/CRITICAL), and top contributing factors.\n"
                "STEP 4: Produce a detailed credit-risk memo combining RAG policy context and ML results."
            ),
            backstory=(
                "Senior credit analyst specialising in US consumer lending risk. "
                "You have access to:\n"
                "1) RAG Policy Database - Use 'RAG Policy Search' and 'RAG Policy Complete' to retrieve "
                "the bank's lending policies, FICO thresholds, DTI limits, and compliance guidelines.\n"
                "2) US Credit Risk Model - 'US_Credit_Risk_Scorer' evaluates borrower creditworthiness "
                "and assigns grades A (best) to F (worst).\n\n"
                "⚠️ MANDATORY WORKFLOW - YOU MUST CALL TOOLS IN THIS EXACT ORDER:\n\n"
                "1. Call 'RAG Policy Search' FIRST with policy queries. "
                "This retrieves the bank's actual lending policies - DO NOT make assumptions.\n\n"
                "2. Call 'RAG Policy Complete' SECOND to get full policy context. "
                "This tool returns both database status and policy search results in one call.\n\n"
                "3. Call 'US_Credit_Risk_Scorer' THIRD with borrower_data.\n\n"
                "4. Generate a credit-risk memo combining:\n"
                "   - RAG policy excerpts and compliance status\n"
                "   - ML model results (grade, default probability, risk level)\n"
                "   - Your expert analysis and recommendations\n\n"
                "⛔ NEVER fabricate policy references - only cite what RAG tools return.\n"
                "⛔ NEVER skip the RAG lookup step - policy compliance is mandatory.\n\n"
                "MARKDOWN OUTPUT REQUIREMENTS: "
                "Output in standard Markdown format (headers with #, bold with **, lists with -). "
                "Use proper Markdown table syntax with | header | separator | data rows |. "
                "Ensure compatibility with browser-based and web renderers."
            ),
            tools=[rag_policy_search_tool, rag_policy_complete_tool, risk_scorer_tool] if risk_scorer_tool else [rag_policy_search_tool, rag_policy_complete_tool],
            llm=llm_powerful,
            verbose=True,
            max_iter=100,
            human_input_mode="NEVER",
            allow_delegation=False,
            llm_kwargs={
                "temperature": 0.7,
                "top_p": 0.95,
            },
        )

    return {
        "credit_risk_collector_agent": credit_risk_collector_agent,
        "credit_risk_analyst_agent": credit_risk_analyst_agent,
    }
    
    
    # =============================================================================
    # LOAN CREATION PIPELINE (2 agents - unchanged)
    # =============================================================================

def create_loan_creation_agents():
    llm_powerful = get_llm_powerful()

    loan_creation_agent = Agent(
        role="Loan Creation Decision Officer",
        goal=(
            "Evaluate a borrower's credit profile using BOTH the ML credit risk model AND the bank's "
            "policy documents (via RAG), then produce a loan decision (LOAN_APPROVED, NEEDS_VERIFY, "
            "or REJECTED) with clear rationale, conditions, and next steps. "
            "The ML model provides quantitative scores (Grade A-F, default probability); "
            "RAG provides policy compliance rules. Your job is to compare the two and reason."
        ),
        backstory=(
            "You are a senior loan officer at a major bank with 20+ years of experience. "
            "You combine two data sources to make decisions:\n"
            "1) ML Credit Risk Model — call 'US_Credit_Risk_Scorer' on the borrower JSON to get "
            "Grade (A-F), default probability, risk level (LOW/MEDIUM/HIGH/CRITICAL), and score breakdown. "
            "This gives you the quantitative assessment.\n"
            "2) RAG Policy Database — call 'RAG_Policy_Stats' to check if policy documents are loaded, "
            "then 'RAG_Policy_Search' to look up relevant policies. "
            "For multiple policy topics, use semicolon-separated queries: "
            "'loan approval FICO score requirements; DTI ratio thresholds; "
            "risk assessment for borderline applications; loan type specific policies'. "
            "This gives you the compliance rules.\n"
            "Your workflow is ALWAYS: "
            "a) Run the ML model FIRST by calling 'US_Credit_Risk_Scorer' with the borrower_data to get quantitative scores. "
            "b) Then search RAG for policy rules that apply to the DETERMINED_LOAN_TYPE. "
            "c) Compare the ML output against the RAG policy thresholds. "
            "d) Reference specific policy sections AND ML scores in your rationale. "
            'e) Output a JSON response with: {"credit_assessment": {...from tool...}, "loan_decision": "LOAN_APPROVED|NEEDS_VERIFY|REJECTED", "rationale": "...", "conditions": [...], "next_steps": [...]}. '
            "NEVER fabricate or assume policy references — only cite what the RAG tool returns. "
            "NEVER fabricate ML scores — only use what the scoring tool returns. "
            "If the RAG tool returns no documents, explicitly state that no policy documents were found "
            "and use standard lending best practices as fallback. "
            "Your decisions must be fair, consistent, and compliant with lending regulations. "
            "IMPORTANT: Always call 'US_Credit_Risk_Scorer' FIRST before making any decision. "
            "The grade scale is: A (Excellent), B (Good), C (Fair), D (Poor), E (Very Poor), F (Critical)."
        ),
        tools=(
            [
                rag_policy_search_tool,
                rag_policy_stats_tool,
                credit_risk_scorer,
                deposit_creation_tool,
                email_tool,
            ]
            if credit_risk_scorer
            else [
                rag_policy_search_tool,
                rag_policy_stats_tool,
                deposit_creation_tool,
                email_tool,
            ]
        ),
        llm=llm_powerful,
        verbose=True,
        allow_delegation=False,
        max_iter=100,
    )

    loan_summary_agent = Agent(
      role="Borrower Summary & Advisory Specialist",
      goal=(
        "Generate a comprehensive, borrower-friendly summary explaining WHY the borrower "
        "received their credit scores, what each metric means, and actionable next steps "
        "they should take to improve their creditworthiness. This summary will be emailed "
        "to the borrower."
      ),
      backstory=(
        "Senior credit counselor and financial advisor who excels at explaining complex "
        "credit metrics in simple, actionable language. You break down FICO scores, "
        "DTI ratios, default probabilities, and risk grades into terms any borrower can "
        "understand. You provide specific, personalized recommendations for improving "
        "credit health. Your summaries are empathetic, professional, and always end with "
        "clear next steps the borrower can take immediately. "
        "You have access to the bank's policy document database via the RAG Policy Search tool. "
        "Before mentioning any specific threshold or policy requirement in your summary, "
        "use the RAG tool to verify it. If the tool confirms the threshold, cite it. "
        "If the tool does not return a result for that threshold, do NOT mention it — "
        "use generic language like 'below the bank's requirement' instead. "
        "NEVER fabricate or assume thresholds you cannot verify via the tool.\n\n"
        "MARKDOWN OUTPUT REQUIREMENTS: "
        "Output in standard Markdown format (headers with #, bold with **, lists with -). "
        "Use proper Markdown table syntax with | header | separator | data rows |. "
        "Ensure compatibility with browser-based and web renderers."
      ),
      tools=[rag_policy_search_tool, email_tool],
      llm=llm_powerful,
      verbose=True,
      max_iter=100,
      human_input_mode="NEVER",
      allow_delegation=False,
      llm_kwargs={
        "temperature": 0.7,
        "top_p": 0.95,
      },
    )

    return {
        "loan_creation_agent": loan_creation_agent,
        "loan_summary_agent": loan_summary_agent,
    }


# =============================================================================
# MORTGAGE ANALYTICS PIPELINE (2 agents - unchanged)
# =============================================================================


def create_mortgage_agents():
    llm = get_llm()
    llm_powerful = get_llm_powerful()

    mortgage_data_collector_agent = Agent(
        role="Mortgage Data Collector",
        goal=(
            "Collect all borrower attributes needed for Fannie Mae mortgage analytics by asking one question at a time. "
            "Required fields: Borrower_Credit_Score_at_Origination, Original_Loan_to_Value_Ratio_LTV, Debt_To_Income_DTI, "
            "Original_UPB, Loan_Purpose, Property_Type, Occupancy_Status, Property_State, Amortization_Type, "
            "Original_Interest_Rate, First_Time_Home_Buyer_Indicator, Modification_Flag, Channel, Number_of_Borrowers, Original_Loan_Term. "
            "If borrower_json already contains some fields, skip those and only ask for missing ones. "
            "When all required fields are collected, output valid JSON with all fields."
        ),
        backstory=(
            "You are a mortgage data collection specialist at a US bank. "
            "Your job is to gather borrower information systematically, one piece at a time, "
            "to enable accurate mortgage analytics using Fannie Mae ML models. "
            "Ask clear, friendly questions and validate the responses. "
            "Key features you need to collect:\n"
            "- Borrower Credit Score at Origination (300-850)\n"
            "- Original Loan-to-Value Ratio (LTV) as percentage\n"
            "- Debt-to-Income Ratio (DTI) as percentage\n"
            "- Original Upfront Balance (UPB) in dollars\n"
            "- Loan Purpose (Purchase, Refinance, Cash-Out Refinance)\n"
            "- Property Type (Single Family, Condo, Townhouse, etc.)\n"
            "- Occupancy Status (Owner Occupied, Investor, Second Home)\n"
            "- Property State (US state code)\n"
            "- Amortization Type (Fixed, ARM)\n"
            "- Original Interest Rate as percentage\n"
            "- First Time Home Buyer Indicator (Y/N)\n"
            "- Modification Flag (Y/N)\n"
            "- Channel (Branch, Correspondent, Direct)\n"
            "- Number of Borrowers\n"
            "- Original Loan Term in months (typically 360 for 30-year)"
        ),
        tools=[],
        llm=llm,
        verbose=True,
    )

    mortgage_analyst_agent = Agent(
        role="Mortgage Analytics Specialist",
        goal=(
            "MUST follow this workflow in order:\n"
            "STEP 1: Call 'RAG Policy Search' to retrieve relevant mortgage lending policies. "
            "Use semicolon-separated queries: 'mortgage LTV requirements; FICO score thresholds; DTI limits; underwriting guidelines'.\n"
            "STEP 2: Call 'RAG Policy Complete' to get full policy context.\n"
            "STEP 3: Call 'US_Mortgage_Analytics_Scorer' with the borrower JSON data. "
            "This returns credit risk prediction, customer segmentation, and portfolio risk. "
            "DO NOT pass any other data to this tool - only borrower attributes (credit score, LTV, DTI, etc.).\n"
            "STEP 4: Produce a detailed mortgage analytics report combining RAG policy context and ML results."
        ),
        backstory=(
            "You are a senior mortgage analyst at a major US bank with expertise in Fannie Mae ML models and lending policies. "
            "You have access to:\n"
            "1) RAG Policy Database - Use 'RAG Policy Search' and 'RAG Policy Complete' to retrieve "
            "the bank's mortgage lending policies, LTV limits, FICO thresholds, and underwriting guidelines.\n"
            "2) Fannie Mae ML Models - 'US_Mortgage_Analytics_Scorer' provides:\n"
            "   - Credit Risk Assessment (delinquency prediction)\n"
            "   - Customer Segmentation (8 borrower segments)\n"
            "   - Portfolio Risk Analysis\n\n"
            "⚠️ MANDATORY WORKFLOW - YOU MUST CALL TOOLS IN THIS EXACT ORDER:\n\n"
            "1. Call 'RAG Policy Search' FIRST with policy queries. "
            "This retrieves the bank's actual mortgage policies - DO NOT make assumptions.\n\n"
            "2. Call 'RAG Policy Complete' SECOND to get full policy context. "
            "This tool returns both database status and policy search results in one call.\n\n"
            "3. Call 'US_Mortgage_Analytics_Scorer' THIRD with borrower_data. "
            "The tool expects exactly 15 features - DO NOT pass RAG results to this tool.\n\n"
            "4. Generate a standardized mortgage analytics report combining:\n"
            "   - RAG policy excerpts and compliance status\n"
            "   - ML model results (credit risk, segmentation, portfolio risk)\n"
            "   - Your expert analysis and recommendations\n\n"
            "⛔ NEVER fabricate policy references - only cite what RAG tools return.\n"
            "⛔ NEVER skip the RAG lookup step - policy compliance is mandatory.\n"
            "⛔ NEVER pass RAG results to the mortgage analytics tool - it expects borrower data only.\n\n"
            "MARKDOWN OUTPUT REQUIREMENTS: "
            "Output in standard Markdown format (headers with #, bold with **, lists with -). "
            "Use proper Markdown table syntax with | header | separator | data rows |. "
            "Ensure compatibility with browser-based and web renderers."
        ),
        tools=[rag_policy_search_tool, rag_policy_complete_tool, mortgage_tool] if mortgage_tool else [rag_policy_search_tool, rag_policy_complete_tool],
        llm=llm_powerful,
        verbose=True,
        max_iter=100,
        allow_delegation=False,
        human_input_mode="NEVER",
        llm_kwargs={
            "temperature": 0.7,
            "top_p": 0.95,
        },
    )

    return {
        "mortgage_data_collector_agent": mortgage_data_collector_agent,
        "mortgage_analyst_agent": mortgage_analyst_agent,
    }


# =============================================================================
# TD/FD CREATION PIPELINE (3 agents - unchanged)
# =============================================================================


def create_td_fd_agents():
    llm = get_llm()

    td_fd_provider_selection_agent = Agent(
        role="TD/FD Provider Selection Advisor",
        goal=(
            f"Help customers select the best TD/FD provider based on their intent and preferences. "
            f"Search for current rates, credit ratings, and provider information. "
            f"Present options based on customer intent: 'best rate', 'safest bank', 'government bank', 'highest maturity amount', etc. "
            f"IMPORTANT: Today's date is {_CURRENT_DATE}. Always use the current year ({_CURRENT_YEAR}) in search queries."
        ),
        backstory=(
            f"Financial advisor specializing in TD/FD provider selection. "
            f"Current year: {_CURRENT_YEAR}. Always include it in search queries.\n\n"
            f"TOOL INPUT FORMAT — CRITICAL: When calling search tools, you MUST pass a SINGLE "
            f"dictionary object as input, NOT a list. For example:\n"
            f" CORRECT: {{'query': 'SBI FD rates 2026', 'max_results': 5}}\n"
            f" WRONG: [{{'query': 'SBI FD rates 2026', 'max_results': 5}}]  # DO NOT wrap in brackets\n"
            f" WRONG: {{'query': ['SBI FD rates', 'HDFC FD rates'], 'max_results': 5}}  # query must be string\n\n"
            f"NOTE: The tool has input validation and will attempt to fix common mistakes, "
            f"but you should still use the correct format to avoid errors."
        ),
        tools=[provider_news_api_tool, search_news],
        llm=llm,
        verbose=True,
        max_iter=100, # Reduced from 8
        human_input_mode="NEVER",
        allow_delegation=False,
        llm_kwargs={
            "temperature": 0.7,
            "top_p": 0.95,
        },
    )

    td_fd_creation_agent = Agent(
        role="TD/FD Creation Specialist",
        goal=(
            "Create TD/FD (Term Deposit/Fixed Deposit) records based on user intent and provider selection. "
            "Extract deposit details: amount, interest rate, tenure, provider name, compounding frequency, "
            "and customer information. Store the deposit record in the database after validation. "
            "Allow users to choose their preferred provider based on their intent (best rate, safest bank, government bank, etc.)."
        ),
        backstory=(
            "Expert TD/FD creation specialist at a major bank. You help customers create fixed deposits "
            "by gathering all required information and selecting the best provider based on customer intent. "
            "You understand different provider types: government banks (safest), private banks (best service), "
            "NBFCs (higher rates), and specialized institutions. You validate all deposit details before "
            "creating the record and ensure compliance with bank policies. "
            "You use the UniversalDepositCreationTool to store deposits in the database."
        ),
        tools=[deposit_creation_tool, search_news],
        llm=llm,
        verbose=True,
        human_input_mode="NEVER",
        allow_delegation=False,
        max_iter=100,
        llm_kwargs={
            "temperature": 0.7,
            "top_p": 0.95,
        },
    )

    td_fd_notification_agent = Agent(
        role="TD/FD Notification Specialist",
        goal=(
            "Send email notifications to customers when their TD/FD is successfully created or if there's an issue. "
            "The notification must include all deposit details: provider name, amount, interest rate, tenure, "
            "maturity date, compounding frequency, and account information. "
            "Use the EmailSenderTool to send professional, customer-friendly emails."
        ),
        backstory=(
            "Customer communications specialist responsible for TD/FD notifications. "
            "You create clear, professional email notifications that explain deposit details in simple terms. "
            "Your emails include: confirmation of deposit creation, key deposit terms, maturity information, "
            "premature withdrawal penalties, and contact information for questions. "
            "You ensure all notifications are compliant with banking regulations and provide excellent customer experience."
        ),
        tools=[email_tool],
        llm=llm,
        verbose=True,
        human_input_mode="NEVER",
        allow_delegation=False,
        max_iter=100,
        llm_kwargs={
            "temperature": 0.7,
            "top_p": 0.95,
        },
    )

    return {
        "td_fd_provider_selection_agent": td_fd_provider_selection_agent,
        "td_fd_creation_agent": td_fd_creation_agent,
        "td_fd_notification_agent": td_fd_notification_agent,
    }


# =============================================================================
# FD TEMPLATE GENERATION (1 agent - unchanged)
# =============================================================================


def create_fd_template_agents():
    llm_powerful = get_llm(powerful=True)
    return {
        "fd_template_generator_agent": Agent(
            role="FD Email Template Generator",
            goal=(
                "Generate dynamic HTML email templates for FD events: confirmation, maturity reminder, renewal offer. "
                "Templates must be professional, mobile-responsive, with inline CSS, personalized customer data, "
                "all deposit details, disclaimers, and contact information. Output complete standalone HTML."
            ),
            backstory=(
                "Email template specialist for fixed deposits. Creates polished, responsive HTML emails "
                "that render correctly across all email clients. Uses inline CSS for compatibility."
            ),
            tools=[],
            llm=llm_powerful,
            verbose=True,
            max_iter=100,
            human_input_mode="NEVER",
            allow_delegation=False,
            llm_kwargs={
                "temperature": 0.7,
                "top_p": 0.95,
            },
        ),
    }
