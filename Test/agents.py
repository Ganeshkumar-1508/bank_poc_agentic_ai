# agents.py
import os
from crewai import Agent
from langchain_nvidia import NVIDIA
from tools import (
    search_news, 
    fd_projection, 
    FDInvoicePDFTool, 
    EmailSenderTool, 
    FixedDepositCreationTool, 
    BankDatabaseTool,
    # AML Tools
    SelfHealingNeo4jTool, 
    YenteEntitySearchTool, 
    AMLReportPDFTool,
    WikidataOSINTTool,
)

# --- LLM Setup ---
def get_llm():
    return NVIDIA(model="qwen/qwen3-next-80b-a3b-instruct") 

def get_llm_2():
    return NVIDIA(model="qwen/qwen3-next-80b-a3b-instruct")

# --- Tool Instances ---
db_tool = BankDatabaseTool()
fd_creation_tool = FixedDepositCreationTool()
pdf_tool = FDInvoicePDFTool()
email_tool = EmailSenderTool()

# AML Tool Instances
neo4j_tool = SelfHealingNeo4jTool() # Using the new raw executor
yente_tool = YenteEntitySearchTool() 
aml_pdf_tool = AMLReportPDFTool()

# --- Agents ---

def create_agents():
    llm = get_llm()
    llm_2 = get_llm_2()
    
    # --- ORIGINAL ANALYSIS / RESEARCH AGENTS ---

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

    osint_agent = Agent(
        role="Open Source Intelligence (OSINT) Specialist",
        goal="Enrich AML findings with OSINT data from Wikidata, especially social media profiles linked to the entity.",
        backstory=(
            "You are an OSINT specialist. You receive structured Yente/OpenSanctions profiles "
            "and use a Wikidata OSINT tool to find associated social media accounts (Facebook, Instagram, LinkedIn, X/Twitter, YouTube). "
            "You summarize the findings clearly and flag any concerning patterns (e.g., multiple profiles under different names)."
        ),
        tools=[WikidataOSINTTool()],  # import it or pass the instance from tools
        llm=llm,  # or llm_2 depending on your preference
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
        backstory=(
            "You are an expert SQL developer with full read-only access to the bank's internal SQLite database."
        ),
        tools=[db_tool],
        llm=llm,
        verbose=True
    )

    # --- NEW AML / ONBOARDING AGENTS ---

    onboarding_data_agent = Agent(
        role="Client Data Coordinator",
        goal="Collect KYC details (Name, Email, Address, PIN, Mobile, PAN, Aadhaar, FD Amount, Tenure, Bank). Ask ONE question at a time.",
        backstory=(
            "You are the friendly face of the bank. You gather data efficiently. "
            "You check the conversation history to see what is missing. "
            "You ask questions one by one. You do not perform AML checks; you only collect information."
        ),
        tools=[],
        llm=llm_2,
        verbose=True
    )

    # NEW: Cypher Generator Agent
    cypher_generator_agent = Agent(
        role="Neo4j Schema-Aware Query Writer",
        goal="Analyze the provided database schema and generate optimized Cypher queries.",
        backstory=(
            "You are a senior Neo4j architect. You are given a specific database schema every time you work. "
            "You do not guess property names or node labels; you strictly use what is defined in the schema provided in the task. "
            "You know that scanning large datasets with `CONTAINS` is bad practice, so you prefer `STARTS WITH` for string matching. "
            "You output ONLY the Cypher query string, ready for execution."
        ),
        tools=[], 
        llm=llm,
        verbose=True
    )

    ubo_investigator_agent = Agent(
        role="Ultimate Beneficial Owner (UBO) Specialist",
        goal="Identify hidden owners, shareholders, and controllers behind corporate entities.",
        backstory=(
            "You are a forensic accountant specializing in corporate veil piercing. "
            "When presented with a company, you don't just look at the name; you look for the people pulling the strings. "
            "You identify directors, shareholders, and family members who might be the real UBOs."
        ),
        tools=[
            YenteEntitySearchTool(), 
            search_news
        ],
        llm=llm,
        verbose=True
    )

    aml_investigator_agent = Agent(
        role="Forensic AML Investigator",
        goal="Perform deep checks using Neo4j, Local Yente/OpenSanctions, and OSINT. Find hidden UBOs and risks.",
        backstory=(
            "You are a digital detective. You receive a Cypher query from your expert colleague, execute it using the Raw Query tool, "
            "and then perform the rest of the analysis."
        ),
        tools=[
            SelfHealingNeo4jTool(), 
            YenteEntitySearchTool(), 
             WikidataOSINTTool(),
            search_news
        ],
        llm=llm,
        verbose=True
    )

    data_visualizer_agent = Agent(
        role="Research & Visualization Expert",
        goal="Fetch data from the web or provided context and convert it into valid Apache ECharts JSON configuration.",
        backstory=(
            "You are a master data analyst and visualizer. You understand the Apache ECharts library deeply. "
            "You are equipped with a web search tool. "
            "When a user asks for a chart (e.g., 'Show me a line chart for top banks'), you first check the provided data. "
            "If the data is missing or insufficient, you perform a web search to find the specific numbers (e.g., interest rates, statistics). "
            "You extract the numeric data from the search results and intelligently map them to X and Y axes. "
            "You output ONLY a valid JSON string representing the ECharts 'option' object. "
            "Do not include markdown code blocks."
        ),
        tools=[search_news], # <--- ADDED WEB SEARCH CAPABILITY
        llm=llm, 
        verbose=True
    )


    risk_scoring_agent = Agent(
        role="Chief Risk Officer",
        goal="Analyze findings and assign a Risk Score (1-100). Generate an exhaustive text report.",
        backstory=(
            "You decide the fate of applications. 1-20 is Low Risk. 21-40 is Medium. "
            "41-60 is High Risk (Review). 61-100 is Critical (Reject). "
            "You write detailed reports explaining the score and listing graph data."
        ),
        tools=[],
        llm=llm,
        verbose=True
    )

    fd_processor_agent = Agent(
        role="Transaction Processor",
        goal="Create the FD if Risk Score is PASS.",
        backstory="You execute the transaction in the database using the FD Creator tool.",
        tools=[fd_creation_tool,search_news],
        llm=llm_2,
        verbose=True
    )

    success_handler_agent = Agent(
        role="Success Specialist",
        goal="Generate Invoice PDF and AML Report PDF, then email them to the user.",
        backstory=(
            "You ensure the client gets their receipt and the compliance report. "
            "You use the PDF generators and Email dispatcher tools."
        ),
        tools=[pdf_tool, aml_pdf_tool, email_tool],
        llm=llm_2,
        verbose=True
    )

    rejection_handler_agent = Agent(
        role="Rejection Specialist",
        goal="Generate the AML Report PDF and send a polite rejection email.",
        backstory=(
            "You handle declined applications with professionalism. "
            "You generate the rejection report and email it to the applicant."
        ),
        tools=[aml_pdf_tool, email_tool],
        llm=llm_2,
        verbose=True
    )

    # --- MANAGER AGENT ---
    
    manager_agent = Agent(
        role="Workflow Manager",
        goal=(
            "Identify the user's intent and delegate the task to the appropriate team. "
            "If the intent is onboarding, you will manage the complex AML workflow."
        ),
        backstory="You are a senior manager at a financial firm ensuring compliance and efficiency.",
        llm=llm,
        verbose=True
    )

    return {
        # Original Agents
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
        
        # New AML/Onboarding Agents
        "onboarding_data_agent": onboarding_data_agent,
        "aml_investigator_agent": aml_investigator_agent,
        "risk_scoring_agent": risk_scoring_agent,
        "fd_processor_agent": fd_processor_agent,
        "success_handler_agent": success_handler_agent,
        "ubo_investigator_agent": ubo_investigator_agent,
        "rejection_handler_agent": rejection_handler_agent,
        "cypher_generator_agent": cypher_generator_agent,
        
        # Manager
        "manager_agent": manager_agent
    }