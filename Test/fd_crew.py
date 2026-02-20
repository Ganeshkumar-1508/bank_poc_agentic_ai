import os
from typing import Union
from crewai import Agent, Task, Crew, Process, CrewOutput
from crewai.tools import BaseTool, tool  # Ensure 'tool' is imported
from pydantic import Field
from langchain_community.tools import DuckDuckGoSearchResults
from langchain_community.utilities import DuckDuckGoSearchAPIWrapper
from langchain_nvidia import NVIDIA, ChatNVIDIA
from dotenv import load_dotenv

load_dotenv()  

if 'NVIDIA_API_KEY' not in os.environ:
    raise ValueError("Please set the NVIDIA_API_KEY environment variable.")

def get_llm():
    return NVIDIA(model="qwen/qwen3-next-80b-a3b-instruct") 

def get_llm_2():
    return NVIDIA(model="qwen/qwen3-next-80b-a3b-instruct")

# ==========================================
# TOOL CONFIGURATION
# ==========================================

# 1. Configure the underlying LangChain API Wrapper for News
ddg_news_wrapper = DuckDuckGoSearchAPIWrapper(
    source="news",      # Fetches news articles
    max_results=5,      # Number of articles
    region="in-in",     # India region
    time="m"            # Last month
)

# 2. Initialize the LangChain Tool
langchain_ddg_tool = DuckDuckGoSearchResults(
    api_wrapper=ddg_news_wrapper,
    output_format="list" # Returns a list of dicts (title, link, snippet)
)

# 3. Wrap it in a CrewAI Tool to pass validation
@tool("DuckDuckGo News Search")
def search_news(query: str) -> str:
    """
    Search for recent news articles using DuckDuckGo.
    The input should be a search query string.
    Returns a string representation of the results including title, link, and snippet.
    """
    # Invoke the LangChain tool
    results = langchain_ddg_tool.invoke(query)
    # Return the string representation so the Agent can read it
    return str(results)

# Keep the existing projection tool
@tool("Fixed Deposit Projection Calculator")
def fd_projection(principal: float, rate: float, tenure: int) -> str:
    """Calculate fixed deposit maturity amount and interest earned assuming quarterly compounding."""
    r = rate / 100
    n = 4  # Quarterly compounding
    t = tenure
    amount = principal * (1 + r/n)**(n*t)
    interest = amount - principal
    return f"Maturity Amount: {amount:.2f}, Interest Earned: {interest:.2f}"


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
        tools=[search_news], # Use the wrapped tool
        llm=llm_2,
        verbose=True
    )

    research_agent = Agent(
        role="Financial Researcher",
        goal="Gather detailed information and recent news for each fixed deposit provider.",
        backstory="You are skilled at researching financial institutions and finding recent articles.",
        tools=[search_news], # Use the wrapped tool
        llm=llm_2,
        verbose=True
    )

    safety_agent = Agent(
        role="Risk Analyst",
        goal="Categorize each fixed deposit provider by safety based on credit ratings and news.",
        backstory="You have expertise in assessing the safety of financial institutions.",
        tools=[search_news], # Use the wrapped tool
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

    # --- Deep Research Crew Agents ---
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
        "manager_agent": manager_agent
    }

# ==========================================
# TASK DEFINITIONS
# ==========================================

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

            "Your report must be professionally formatted in Markdown and strictly follow this structure:\n\n"

            "# Comprehensive Fixed Deposit Analysis Report\n\n"

            "## 1. Executive Summary\n"
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
            f"Identify and list the top 10 Fixed Deposit providers (Banks & NBFCs) in India. "
            f"Output a simple list of 10 names."
        ),
        expected_output="A list of 10 top Fixed Deposit provider names.",
        agent=agents["provider_search_agent"]
    )

    deep_research_task = Task(
        description=(
            "For every provider in the list: {identify_providers_task.output}, perform exhaustive research. "
            "You must find the following for EACH provider:\n"
            "1. Credit Ratings.\n"
            "2. Interest Rate ranges (General vs Senior).\n"
            "3. Recent News.\n"
            "4. Financial Health indicators."
        ),
        expected_output="Detailed structured data for each provider.",
        agent=agents["deep_research_agent"],
        context=[identify_providers_task]
    )

    compile_report_task = Task(
        description=(
            "Compile findings from: {deep_research_task.output} into a final report. "
            "Structure it as:\n"
            "## Analysis of Top FD Providers\n"
            "Subheadings for each provider."
        ),
        expected_output="A structured markdown report.",
        agent=agents["research_compilation_agent"],
        context=[deep_research_task]
    )

    return [identify_providers_task, deep_research_task, compile_report_task]

# ==========================================
# CREW & ROUTER LOGIC
# ==========================================

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

def run_crew(user_query: str):
    agents = create_agents()
    manager = agents["manager_agent"]
    
    routing_task = Task(
        description=(
            f"Analyze the user query: '{user_query}'\n\n"
            f"Determine the intent:\n"
            f"- If the user asks for calculations, maturity amounts, or comparisons, respond with 'ANALYSIS'.\n"
            f"- If the user asks for general info or detailed reports without calculations, respond with 'RESEARCH'.\n\n"
            f"Respond with ONLY one word: ANALYSIS or RESEARCH."
        ),
        expected_output="Single word: ANALYSIS or RESEARCH",
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
    else:
        crew = get_research_crew(user_query)
        
    result = crew.kickoff()
    return result