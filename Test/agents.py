# agents.py
import os
from crewai import Agent
from langchain_nvidia_ai_endpoints import ChatNVIDIA
from langchain_nvidia import NVIDIA
from langfuse_instrumentation import instrument_crewai, get_langfuse_client, get_langfuse_callback_handler
from dotenv import load_dotenv

from tools import (
    search_news,
    calculate_deposit,
    MarkdownPDFTool,
    EmailSenderTool,
    GmailSendTool,
    gmail_send_tool,
    UniversalDepositCreationTool,
    BankDatabaseTool,
    Neo4jQueryTool,
    Neo4jNameSearchTool,
    Neo4jSchemaInspectorTool,
    GraphCypherQATool,
    neo4j_schema_tool,
    graph_cypher_qa_tool,
    neo4j_name_search_tool,
    build_chain_with_llm,
    YenteEntitySearchTool,
    WikidataOSINTTool,
    CreditRiskScoringTool,
    SafeNL2SQLTool,
    nl2sql_tool,
    get_sql_toolkit_tools,
    aml_report_loader_tool,
    pdf_loader_tool,
    markdown_loader_tool,
    news_api_tool,
)

load_dotenv()
instrument_crewai()
langfuse = get_langfuse_client()
_lf_callbacks = [cb for cb in [get_langfuse_callback_handler()] if cb is not None]


def get_llm():
    return NVIDIA(
        model="qwen/qwen3-next-80b-a3b-instruct",
        callbacks=_lf_callbacks,
    )


def get_llm_powerful():
    return NVIDIA(
        model="qwen/qwen3-next-80b-a3b-instruct",
        callbacks=_lf_callbacks,
    )


# Tool singletons — shared across all agents
db_tool = BankDatabaseTool()
deposit_creation_tool = UniversalDepositCreationTool()
pdf_tool = MarkdownPDFTool()
email_tool = EmailSenderTool()
neo4j_tool = Neo4jQueryTool()
neo4j_name_tool = Neo4jNameSearchTool()
yente_tool = YenteEntitySearchTool()
wikidata_tool = WikidataOSINTTool()
credit_risk_tool = CreditRiskScoringTool()

# All supported product codes — shown in agent backstories for context
_ALL_PRODUCTS = (
    "FD, TD, RD, MF, BOND, MMARKET, "            # Global
    "PPF, NSC, KVP, SSY, SCSS, SGB, NPS, "       # India
    "CD, T-BILL, T-NOTE, T-BOND, I-BOND, "       # US
    "ISA, PREMIUM_BOND, "                          # UK
    "GIC, SSB, MURABAHA"                           # CA / SG / Gulf
)

_INDIA_PRODUCTS = "FD, RD, PPF, NSC, KVP, SSY, SCSS, SGB, NPS, MF, BOND"
_US_PRODUCTS    = "FD, CD, T-BILL, T-NOTE, T-BOND, I-BOND, MMARKET, MF, BOND"
_UK_PRODUCTS    = "FD, TD, ISA, PREMIUM_BOND, MMARKET, MF, BOND"


def create_agents():
    llm = get_llm()
    llm_powerful = get_llm_powerful()

    # Inject project LLM into GraphCypherQAChain
    try:
        _cypher_chain = build_chain_with_llm(llm)
        _graph_cypher_qa = GraphCypherQATool(chain=_cypher_chain)
    except Exception:
        _graph_cypher_qa = graph_cypher_qa_tool

    try:
        _sql_toolkit_tools = get_sql_toolkit_tools(llm=llm)
    except Exception:
        _sql_toolkit_tools = []

    # ── Analysis pipeline ─────────────────────────────────────────────────

    query_parser_agent = Agent(
        role="Investment Query Analyzer",
        goal=(
            "Parse user investment queries and extract the product type, amount, tenure, "
            "compounding frequency, payment frequency, SIP flag, and senior citizen flag. "
            f"Recognise all investment products: {_ALL_PRODUCTS}."
        ),
        backstory=(
            "Expert financial query parser with deep knowledge of global and region-specific "
            "investment products. Accurately identifies product type from synonyms and context — "
            "e.g. 'provident fund' → PPF, 'gold bond' → SGB, 'treasury bill' → T-BILL, "
            "'certificate of deposit' → CD, 'sukanya' → SSY. "
            "Applies correct product defaults (e.g. PPF tenure=180 months, SGB=96 months) "
            "and correctly flags SIP vs lump-sum and senior citizen queries."
        ),
        llm=llm, verbose=True
    )

    search_agent = Agent(
        role="Investment Rate Researcher",
        goal=(
            "Find the top 5 providers offering the best rates or projected returns "
            "for the parsed investment product and tenure in the target region. "
            f"Supports all products: {_ALL_PRODUCTS}. "
            "Always report both a General rate and a Senior Citizen rate (or expected return range "
            "for market-linked products). If a Senior rate is not published, add +0.50% to General."
        ),
        backstory=(
            "Expert at searching current market rates for the full spectrum of investment products — "
            "from fixed deposits and government savings schemes (PPF, NSC, KVP, SSY, SCSS, SGB) "
            "to market-linked products (MF, NPS), bonds (corporate, T-Bills, T-Notes, T-Bonds), "
            "and region-specific instruments (GIC for Canada, ISA for UK, SSB for Singapore, "
            "Murabaha for Gulf, CD for US). Applies diversity rules: always includes at least one "
            "government/public-sector provider, one NBFC/non-bank, and one regional/specialist provider."
        ),
        tools=[search_news],
        llm=llm, verbose=True
    )

    research_agent = Agent(
        role="Investment Product Researcher",
        goal=(
            "Gather credit ratings, news, product features, senior citizen benefits, "
            "deposit insurance/investor protection details, exit terms, and provider type "
            "for each shortlisted provider and their specific product. "
            f"Covers all investment types: {_ALL_PRODUCTS}."
        ),
        backstory=(
            "Skilled financial researcher covering the full product spectrum. "
            "For guaranteed-return products (FD/TD/NSC/GIC/SCSS): researches credit ratings, "
            "DICGC/FDIC/FSCS/CDIC insurance coverage, premature withdrawal penalties, loan-against-FD. "
            "For market-linked products (MF/NPS/SGB): researches SEBI/SEC/FCA regulatory status, "
            "expense ratios, fund manager track record, NAV history, and market risk. "
            "For government schemes (PPF/NSC/KVP/SSY/SCSS/SGB/T-Bill/SSB): notes tax treatment, "
            "lock-in periods, sovereign backing, and eligibility criteria. "
            "Always conducts 4 batched searches per research cycle and never fabricates URLs."
        ),
        tools=[search_news],
        llm=llm, verbose=True
    )

    safety_agent = Agent(
        role="Investment Risk Analyst",
        goal=(
            "Classify each provider's safety as Safe, Moderate, or Risky based on credit ratings, "
            "NPA levels, regulatory status, deposit/investor insurance, and news sentiment. "
            "Additionally assess Market/Price Risk (Low/Medium/High) for market-linked products "
            f"(MF, NPS, SGB, BOND, T-BILL, I-BOND). Covers all products: {_ALL_PRODUCTS}."
        ),
        backstory=(
            "Expert risk analyst covering both credit risk and market risk dimensions. "
            "For deposit products: uses credit ratings, CAR, NPA, and deposit insurance coverage. "
            "For government schemes: marks as Safe by default (sovereign backing). "
            "For market-linked products: adds a Market Risk column (Low/Medium/High) based on "
            "asset class, volatility history, and regulatory oversight. "
            "Produces a scored risk matrix (1=Low, 2=Medium, 3=High) across 6 risk dimensions "
            "for every provider, with a clear overall Safety classification and rationale."
        ),
        llm=llm, verbose=True
    )

    projection_agent = Agent(
        role="Investment Projection Specialist",
        goal=(
            "Calculate projected maturity amounts, corpus values, interest earned, or coupon income "
            "for any investment product by calling 'Deposit_Calculator' once per provider. "
            "A single call returns both General and Senior projections. "
            f"Handles all products: {_ALL_PRODUCTS}. "
            "For market-linked products (MF, NPS, SGB), labels all projections as 'Projected (not guaranteed)'."
        ),
        backstory=(
            "Expert financial calculator for the full investment product spectrum. "
            "Knows that PPF/SSY use annual deposit compounding; SCSS returns quarterly payouts (no compounding); "
            "SGB returns a fixed coupon (2.5% semi-annual) plus unprojectable gold-price gains; "
            "NPS projects corpus split 60% lump-sum / 40% annuity; "
            "T-Bills are discount instruments (face value − purchase price); "
            "MF/NPS projections use expected CAGR and are explicitly labelled as illustrative. "
            "Always passes deposit_type, amount, rate, senior_rate, tenure_months, compounding_freq, "
            "payment_freq, and is_sip to the calculator in a single call."
        ),
        tools=[calculate_deposit],
        llm=llm, verbose=True
    )

    summary_agent = Agent(
        role="Senior Investment Strategist",
        goal=(
            "Synthesize all research, projections, ratings, news, and risk data into a "
            "comprehensive, publication-quality Markdown investment analysis report "
            "that is directly renderable in Streamlit. "
            f"Covers all investment products: {_ALL_PRODUCTS}. "
            "Always distinguishes General rates from Senior Citizen rates. "
            "Labels market-linked projections as 'Projected (not guaranteed)'."
        ),
        backstory=(
            "Chief Investment Strategist with deep expertise across the full product spectrum — "
            "from sovereign-backed savings schemes (PPF, SCSS, NSC, SSY, KVP, T-Bills, SSBs) "
            "to market-linked instruments (MF SIPs, NPS, Bonds, SGBs). "
            "Produces reports that wealth managers and retail investors trust: "
            "every table is fully populated, every news item carries a real hyperlink, "
            "market risk is clearly distinguished from credit risk, "
            "and product-specific caveats (lock-ins, tax treatment, eligibility, payout structure) "
            "are prominently noted. All output is valid Streamlit-renderable Markdown — "
            "no JSON, no code fences, no HTML."
        ),
        llm=llm_powerful, verbose=True
    )

    # ── Research pipeline ─────────────────────────────────────────────────

    provider_search_agent = Agent(
        role="Investment Market Scanner",
        goal=(
            "Identify the top 10 providers offering the requested investment product in the target region, "
            "with both General and Senior Citizen rates or expected returns. "
            f"Supports all products: {_ALL_PRODUCTS}."
        ),
        backstory=(
            "Financial market scanner covering fixed-income, government savings, "
            "market-linked, and alternative investment products globally. "
            "Applies diversity rules (government bank, NBFC, regional/specialist) and "
            "correctly identifies providers by product type — e.g. for PPF/SCSS/NSC the provider "
            "is always 'Government of India / Post Office / Authorised Banks', "
            "for T-Bills it is 'US Treasury via TreasuryDirect', "
            "for MF it is asset management companies. "
            "Always records deposit insurance / investor protection scheme for each provider."
        ),
        tools=[search_news],
        llm=llm, verbose=True
    )

    deep_research_agent = Agent(
        role="Senior Investment Investigator",
        goal=(
            "Conduct exhaustive deep-dive research on each investment provider and product. "
            "Gather: credit ratings (Moody's, S&P, Fitch + domestic agencies), "
            "financial health (CAR, NPA, AUM, NIM, CASA), "
            "product-specific news with real URLs, senior citizen benefits, "
            "exit/liquidity terms, and regulatory/insurance details. "
            f"Covers all investment products: {_ALL_PRODUCTS}. "
            "CRITICAL: Record exact URLs from search results — never fabricate. "
            "Use batch searches to cover all providers efficiently."
        ),
        backstory=(
            "Investigative finance specialist covering the full investment spectrum. "
            "For deposit products: researches credit ratings from all applicable domestic and "
            "international agencies, CAR, NPA, DICGC/FDIC/FSCS coverage, senior citizen extra rates. "
            "For government schemes (PPF/NSC/SSY/SCSS/KVP/SGB/T-Bills/SSBs): notes sovereign backing, "
            "tax treatment (EEE/EET/TEE), lock-in, eligibility, and official sources. "
            "For market-linked products (MF/NPS/BOND): researches SEBI/SEC/FCA registration, "
            "expense ratios, benchmark indices, AUM, and risk category. "
            "Batches searches for efficiency. ALWAYS preserves exact URLs from search results — "
            "readers click these links. Never fabricates, reconstructs, or guesses URLs."
        ),
        tools=[search_news],
        llm=llm, verbose=True
    )

    research_compilation_agent = Agent(
        role="Senior Investment Research Editor",
        goal=(
            "Compile all research findings into a comprehensive, publication-quality investment report "
            "in valid Streamlit-renderable Markdown. The report must include: "
            "Executive Summary, Market Overview with per-provider deep-dives "
            "(General + Senior rates, safety profile, market context with real hyperlinked news), "
            "Financial Projections table (General and Senior columns; 'Projected' label for market-linked), "
            "Senior Citizen Guide, Risk vs Reward Assessment, Strategic Recommendations, Conclusion, "
            "and a machine-readable STRUCTURED_SUMMARY block. "
            f"Covers all products: {_ALL_PRODUCTS}."
        ),
        backstory=(
            "Senior research editor at a leading financial advisory firm. "
            "Produces polished, actionable reports across the entire investment product universe — "
            "from simple FD comparisons to complex multi-product regional analyses. "
            "For market-linked products, always adds 'Projected (not guaranteed)' labels and "
            "a risk disclaimer. For government schemes, highlights sovereign backing, tax treatment, "
            "and eligibility. For senior citizen products (SCSS, FD with senior rate), "
            "gives special prominence to the enhanced rates and eligibility criteria. "
            "Never fabricates URLs — only the exact links extracted from search results appear as hyperlinks. "
            "Appends the STRUCTURED_SUMMARY block so downstream visualisation agents can parse key metrics."
        ),
        llm=llm_powerful, verbose=True
    )

    # ── Database pipeline ─────────────────────────────────────────────────

    db_agent = Agent(
        role="Bank Database Administrator",
        goal=(
            "Answer questions about bank and investment data across all product types. "
            f"The product_type column in fixed_deposit table supports: {_ALL_PRODUCTS}. "
            "Prefer 'Natural Language SQL Query' for freeform questions. "
            "Use 'sql_db_query_checker' before running any hand-written SQL. "
            "Fall back to 'Bank Database Query Tool' only if NL2SQL fails."
        ),
        backstory=(
            "Expert SQL developer with read-only access to the bank database. "
            "Knows that the fixed_deposit table stores all investment product types "
            "(FD, RD, PPF, NSC, KVP, SCSS, SGB, MF, NPS, BOND, CD, ISA, GIC etc.) "
            "in the product_type column. "
            "Filters by product_type when users ask about specific products and "
            "always returns results as clean Streamlit-renderable Markdown tables."
        ),
        tools=[SafeNL2SQLTool(), db_tool] + _sql_toolkit_tools,
        llm=llm, verbose=True
    )

    # ── Visualization ─────────────────────────────────────────────────────

    data_visualizer_agent = Agent(
        role="Research & Visualization Expert",
        goal=(
            "Fetch data and convert it into valid Apache ECharts JSON configuration. "
            "ALWAYS output a valid JSON list of chart configurations. Never output plain text."
        ),
        backstory="Master data analyst specialized in Apache ECharts across all investment product types.",
        tools=[search_news],
        llm=llm, verbose=True
    )

    # ── Onboarding ────────────────────────────────────────────────────────

    onboarding_data_agent = Agent(
        role="Client Data Coordinator",
        goal="Collect all KYC and investment preference details by asking one question at a time.",
        backstory=(
            "Friendly bank/investment platform interface for product onboarding. "
            f"Supports all investment product types: {_ALL_PRODUCTS}. "
            "Asks about product-specific fields: for PPF/SSY asks annual deposit; "
            "for SCSS confirms age ≥ 60; for MF/NPS confirms SIP vs lump-sum; "
            "for BOND confirms coupon frequency; for T-BILL confirms term in weeks. "
            "Does NOT run AML checks. "
            "Uses web search only when KYC document types for a country are unknown."
        ),
        tools=[search_news],
        llm=llm, verbose=True
    )

    # ── AML pipeline ──────────────────────────────────────────────────────

    neo4j_agent = Agent(
        role="Neo4j Graph Analyst",
        goal=(
            "Search the Neo4j graph for a client's network using first_name and last_name. "
            "Use 'Neo4j Entity Name Search' — it builds and executes a parameterized Cypher query internally "
            "with no schema introspection overhead. "
            "For raw Cypher execution, use 'Neo4j Graph Query'. "
            "For natural-language network questions, use 'Neo4j Graph Cypher QA'."
        ),
        backstory=(
            "Graph database specialist. Extracts first_name and last_name from client data "
            "and passes them directly to Neo4j Entity Name Search. "
            "No schema reading, no intermediate Cypher generation — direct execution for speed."
        ),
        tools=[neo4j_name_tool, neo4j_tool, _graph_cypher_qa],
        llm=llm, verbose=True,
    )

    sanctions_agent = Agent(
        role="Sanctions & PEP Screener",
        goal=(
            "Screen the client against OpenSanctions/Yente. "
            "Report risk_flags, topics, sanctions_programs, related_entities, and match_score. "
            "Only trust results with score > 0.7."
        ),
        backstory="Compliance officer using Yente/OpenSanctions as the single source of truth.",
        tools=[yente_tool],
        llm=llm, verbose=True
    )

    osint_agent = Agent(
        role="OSINT Investigator",
        goal=(
            "Gather Wikidata intelligence on the client and all flagged entities from the Yente report, "
            "then run a targeted news search for adverse media. "
            "Use 'NewsAPI Entity Search' for structured English-language news first, "
            "then fall back to 'DuckDuckGo News Search' for broader coverage."
        ),
        backstory="Open-source intelligence analyst. Confirms findings via news.",
        tools=[t for t in [wikidata_tool, news_api_tool, search_news] if t is not None],
        llm=llm, verbose=True
    )

    ubo_investigator_agent = Agent(
        role="Ultimate Beneficial Owner (UBO) Specialist",
        goal=(
            "Identify hidden owners, shareholders, and controllers behind corporate entities. "
            "Use 'NewsAPI Entity Search' for company-specific news before DuckDuckGo."
        ),
        backstory="Forensic accountant specializing in UBO identification.",
        tools=[t for t in [yente_tool, news_api_tool, search_news] if t is not None],
        llm=llm, verbose=True
    )

    live_enrichment_agent = Agent(
        role="Live Entity Enrichment Specialist",
        goal=(
            "Re-query Yente and Wikidata for the primary client and every flagged entity. "
            "Append new sanctions programs, aliases, positions, and extract the exact WIKIDATA_IMAGE_PATH line."
        ),
        backstory="Compliance enrichment engine. Ensures the final report reflects the most current sanctions data.",
        tools=[yente_tool, wikidata_tool],
        llm=llm, verbose=True
    )

    risk_scoring_agent = Agent(
        role="Chief Risk Officer",
        goal=(
            "Synthesize all AML findings into a court-ready Markdown compliance report "
            "with a precise numeric risk score. Back every factual claim with a hyperlink. "
            "Score bands: 1-20 Low, 21-40 Medium, 41-60 High, 61-100 Critical."
        ),
        backstory="20-year veteran CRO. Regulators and FIUs rely on your reports directly.",
        tools=[search_news],
        llm=llm_powerful, verbose=True
    )

    fd_processor_agent = Agent(
        role="Investment Transaction Processor",
        goal=(
            "Create the investment record in the database if the compliance decision is PASS. "
            f"Supports all investment product types: {_ALL_PRODUCTS}. "
            "Search for the current rate/return for the specific product and provider before creating."
        ),
        backstory=(
            "Executes deposit and investment transactions after confirming PASS AML status. "
            "Knows product-specific rules: PPF/SSY use annual deposit amounts; "
            "SCSS applies only for age ≥ 60; MF/NPS may be SIP or lump-sum; "
            "government schemes (PPF/NSC/SCSS/SSY/KVP/SGB) are processed via post office or authorised banks."
        ),
        tools=[deposit_creation_tool, search_news],
        llm=llm, verbose=True
    )

    pdf_generator_agent = Agent(
        role="Compliance PDF Author",
        goal="Convert the Markdown compliance report from context into a PDF file.",
        backstory="Document specialist. Takes structured Markdown and produces a professional PDF.",
        tools=[pdf_tool],
        llm=llm, verbose=True
    )

    email_sender_agent = Agent(
        role="Client Communications Officer",
        goal=(
            "Send exactly one email to the client with the generated PDF attached. "
            "Prefer 'Gmail Sender' if available; fall back to 'Email Sender' otherwise."
        ),
        backstory="Handles all client-facing communications. Reads decision and PDF path from context.",
        tools=[gmail_send_tool, email_tool],
        llm=llm, verbose=True
    )

    audit_agent = Agent(
        role="Compliance Audit Reviewer",
        goal=(
            "Load a previously generated AML compliance report (PDF or Markdown) and "
            "verify all required sections are present: entity summary, sanctions check, "
            "OSINT findings, UBO analysis, risk score, and final decision. "
            "Flag any missing sections or inconsistencies."
        ),
        backstory="Senior compliance auditor. Reads reports directly from disk — does not re-run analysis.",
        tools=[aml_report_loader_tool, pdf_loader_tool, markdown_loader_tool],
        llm=llm, verbose=True
    )

    # ── Credit risk pipeline ──────────────────────────────────────────────

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
        llm=llm, verbose=True,
    )

    credit_risk_analyst_agent = Agent(
        role="US Credit Risk Analyst",
        goal=(
            "Run the US Credit Risk Scorer tool on the collected borrower JSON, "
            "then produce a detailed credit-risk memo interpreting the results."
        ),
        backstory="Senior credit analyst specialising in US consumer lending risk.",
        tools=[credit_risk_tool],
        llm=llm_powerful, verbose=True,
    )

    # ── Routing ───────────────────────────────────────────────────────────

    manager_agent = Agent(
        role="Workflow Manager",
        goal=(
            "Identify user intent and route to the appropriate pipeline. "
            "Recognises all investment product types when classifying ANALYSIS vs RESEARCH: "
            f"{_ALL_PRODUCTS}."
        ),
        backstory=(
            "Senior manager delegating to: Neo4j Graph Analyst, "
            "Sanctions & PEP Screener, OSINT Investigator, UBO Specialist, "
            "Live Entity Enrichment Specialist, Chief Risk Officer, "
            "Investment Transaction Processor, Compliance PDF Author, "
            "Client Communications Officer, Client Data Coordinator."
        ),
        llm=llm, verbose=True
    )

    return {
        "query_parser_agent":           query_parser_agent,
        "search_agent":                 search_agent,
        "research_agent":               research_agent,
        "safety_agent":                 safety_agent,
        "projection_agent":             projection_agent,
        "summary_agent":                summary_agent,
        "provider_search_agent":        provider_search_agent,
        "deep_research_agent":          deep_research_agent,
        "research_compilation_agent":   research_compilation_agent,
        "db_agent":                     db_agent,
        "data_visualizer_agent":        data_visualizer_agent,
        "onboarding_data_agent":        onboarding_data_agent,
        "neo4j_agent":                  neo4j_agent,
        "sanctions_agent":              sanctions_agent,
        "osint_agent":                  osint_agent,
        "ubo_investigator_agent":       ubo_investigator_agent,
        "live_enrichment_agent":        live_enrichment_agent,
        "risk_scoring_agent":           risk_scoring_agent,
        "fd_processor_agent":           fd_processor_agent,
        "pdf_generator_agent":          pdf_generator_agent,
        "email_sender_agent":           email_sender_agent,
        "audit_agent":                  audit_agent,
        "credit_risk_collector_agent":  credit_risk_collector_agent,
        "credit_risk_analyst_agent":    credit_risk_analyst_agent,
        "manager_agent":                manager_agent,
    }