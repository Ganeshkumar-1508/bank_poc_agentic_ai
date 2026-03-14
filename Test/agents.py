# agents.py
import os
from crewai import Agent
from langchain_nvidia import NVIDIA
from langfuse_instrumentation import instrument_crewai, get_langfuse_client, get_langfuse_callback_handler
from dotenv import load_dotenv
from tools import (
    search_news,
    calculate_deposit,
    MarkdownPDFTool,
    EmailSenderTool,
    UniversalDepositCreationTool,
    BankDatabaseTool,
    Neo4jQueryTool,
    YenteEntitySearchTool,
    WikidataOSINTTool,
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

db_tool = BankDatabaseTool()
deposit_creation_tool = UniversalDepositCreationTool()
pdf_tool = MarkdownPDFTool()
email_tool = EmailSenderTool()
neo4j_tool = Neo4jQueryTool()
yente_tool = YenteEntitySearchTool()
wikidata_tool = WikidataOSINTTool()

def create_agents():
    llm = get_llm()
    llm_powerful = get_llm_powerful()

    query_parser_agent = Agent(
        role="Financial Query Analyzer",
        goal="Extract investment type (FD/RD), amount, tenure, and compounding preference from user queries.",
        backstory="Expert at parsing user intent for Fixed and Recurring Deposit requests.",
        llm=llm, verbose=True
    )

    search_agent = Agent(
        role="Deposit Rate Researcher",
        goal="Find top FD or RD interest rates for specific tenures.",
        backstory="Expert at searching the web for current financial product rates.",
        tools=[search_news],
        llm=llm, verbose=True
    )

    research_agent = Agent(
        role="Financial Researcher",
        goal="Gather credit ratings and news for each deposit provider.",
        backstory="Skilled at researching financial institutions for rates and safety data.",
        tools=[search_news],
        llm=llm, verbose=True
    )

    safety_agent = Agent(
        role="Risk Analyst",
        goal="Categorize providers as Safe, Moderate, or Risky based on credit ratings and news.",
        backstory="Expert in assessing the safety of financial institutions using public ratings.",
        tools=[search_news],
        llm=llm, verbose=True
    )

    projection_agent = Agent(
        role="Deposit Projection Specialist",
        goal="Calculate projected maturity amounts for FD and RD with dynamic compounding.",
        backstory="Expert financial calculator for both Fixed and Recurring Deposits.",
        tools=[calculate_deposit],
        llm=llm, verbose=True
    )

    summary_agent = Agent(
        role="Senior Investment Strategist",
        goal="Synthesize financial data and projections into a professional Markdown investment thesis.",
        backstory="Veteran Chief Investment Strategist with expertise in FD/RD product analysis.",
        llm=llm_powerful, verbose=True
    )

    # --- Research Pipeline ---
    provider_search_agent = Agent(
        role="Market Scanner",
        goal="Identify top Fixed Deposit providers in the current market.",
        backstory="Broad view of the financial market for scanning top FD/RD providers.",
        tools=[search_news],
        llm=llm, verbose=True
    )

    deep_research_agent = Agent(
        role="Senior Financial Investigator",
        goal="Conduct exhaustive research on financial institutions including rates, ratings, and news.",
        backstory="Investigative specialist in finance with deep research skills.",
        tools=[search_news],
        llm=llm, verbose=True
    )

    research_compilation_agent = Agent(
        role="Research Editor",
        goal="Compile detailed findings into a structured, complete Markdown report.",
        backstory="Editor who ensures all critical details are clearly presented.",
        llm=llm, verbose=True
    )

    # --- Database Pipeline ---
    db_agent = Agent(
        role="Bank Database Administrator",
        goal="Answer questions about bank data by generating and executing accurate SQL queries.",
        backstory="Expert SQL developer with read-only access to the bank database.",
        tools=[db_tool],
        llm=llm, verbose=True
    )

    # --- Visualization ---
    data_visualizer_agent = Agent(
        role="Research & Visualization Expert",
        goal="Fetch data and convert it into valid Apache ECharts JSON configuration.",
        backstory=(
            "Master data analyst specialized in Apache ECharts. "
            "You have access to a search tool to find external benchmarks (like Repo Rate or Inflation) if needed. "
            "You ALWAYS output a valid JSON list of chart configurations. Never output plain text."
        ),
        tools=[search_news],
        llm=llm, 
        verbose=True
    )

    # --- Onboarding Pipeline ---
    onboarding_data_agent = Agent(
        role="Client Data Coordinator",
        goal="Collect all KYC and Deposit Preference details by asking one question at a time.",
        backstory=(
            "Friendly bank interface. Determines FD vs RD, collects Amount, Tenure, Compounding, "
            "Name, Email, Address, PIN, Mobile, KYC documents, and Bank Name. Does NOT run AML checks."
        ),
        tools=[search_news],
        llm=llm, verbose=True
    )
    cypher_generator_agent = Agent(
        role="Neo4j Client Network Mapper",
        goal="Generate a Cypher query to find a client's network using their full name.",
        backstory="Neo4j expert. Extracts first_name and last_name from JSON and builds case-insensitive Cypher queries.",
        tools=[],
        llm=llm, verbose=True
    )

    ubo_investigator_agent = Agent(
        role="Ultimate Beneficial Owner (UBO) Specialist",
        goal="Identify hidden owners, shareholders, and controllers behind corporate entities.",
        backstory="Forensic accountant specializing in corporate veil piercing and UBO identification.",
        tools=[yente_tool, search_news],
        llm=llm, verbose=True
    )

    aml_investigator_agent = Agent(
        role="Forensic AML Investigator",
        goal="Perform deep checks using Neo4j, Yente/OpenSanctions, and OSINT. Include graph image path in output.",
        backstory="Digital detective querying Neo4j and OpenSanctions, producing clean Markdown AML reports.",
        tools=[neo4j_tool, yente_tool, search_news, wikidata_tool],
        llm=llm, verbose=True
    )

    risk_scoring_agent = Agent(
        role="Chief Risk Officer",
        goal=(
            "Analyze all AML investigation findings and produce a single, definitive, court-ready "
            "Markdown compliance report with a precise numeric risk score. "
            "Actively use search and sanctions tools to enrich every section with live evidence — "
            "every factual claim must be backed by a hyperlink or tool citation. "
            "The report must include the client's full name, the exact current date and time, "
            "and preserve every data point verbatim — nothing may be summarised away."
        ),
        backstory=(
            "20-year veteran Chief Risk Officer and compliance documentation specialist. "
            "You combine forensic financial analysis with court-ready report writing. "
            "Score bands you enforce: 1-20 Low, 21-40 Medium, 41-60 High, 61-100 Critical. "
            "You are renowned for exhaustive, citation-rich Markdown reports that merge "
            "graph intelligence, live sanctions data, OSINT, and media findings into one immutable record. "
            "Regulators, FIUs, and board risk committees rely on your output directly."
        ),
        tools=[search_news, yente_tool, wikidata_tool],
        llm=llm_powerful, verbose=True
    )

    fd_processor_agent = Agent(
        role="Transaction Processor",
        goal="Create the FD or RD in the database if the risk decision is PASS.",
        backstory="Executes deposit transactions using the Deposit Creator tool after confirming PASS status.",
        tools=[deposit_creation_tool, search_news],
        llm=llm, verbose=True
    )

    success_handler_agent = Agent(
        role="Success Specialist",
        goal="Read the compliance decision, then generate the correct PDF and send exactly one email.",
        backstory=(
            "Final handler. Sends a success email (with deposit details) on PASS/APPROVE, "
            "or a rejection email on FAIL/REJECT. Never sends both."
        ),
        tools=[pdf_tool, email_tool, deposit_creation_tool, search_news],
        llm=llm, verbose=True
    )

    rejection_handler_agent = Agent(
        role="Rejection Specialist",
        goal="Generate a rejection PDF and send a polite decline email.",
        backstory="Handles declined applications with professionalism.",
        tools=[pdf_tool, email_tool],
        llm=llm, verbose=True
    )

    manager_agent = Agent(
        role="Workflow Manager",
        goal="Identify user intent and delegate to the appropriate team member using exact role names.",
        backstory=(
            "Senior manager at a financial firm. Delegates to these exact role names:\n"
            "1. 'Neo4j Client Network Mapper'\n"
            "2. 'Forensic AML Investigator'\n"
            "3. 'Ultimate Beneficial Owner (UBO) Specialist'\n"
            "4. 'Chief Risk Officer'\n"
            "5. 'Transaction Processor'\n"
            "6. 'Success Specialist'\n"
            "7. 'Rejection Specialist'\n"
            "8. 'Client Data Coordinator'"
        ),
        llm=llm, verbose=True
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
        "data_visualizer_agent": data_visualizer_agent,
        "onboarding_data_agent": onboarding_data_agent,
        "aml_investigator_agent": aml_investigator_agent,
        "risk_scoring_agent": risk_scoring_agent,
        "fd_processor_agent": fd_processor_agent,
        "success_handler_agent": success_handler_agent,
        "ubo_investigator_agent": ubo_investigator_agent,
        "rejection_handler_agent": rejection_handler_agent,
        "cypher_generator_agent": cypher_generator_agent,
        "manager_agent": manager_agent,
    }