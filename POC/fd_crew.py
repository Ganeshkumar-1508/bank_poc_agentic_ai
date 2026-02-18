import os
from typing import Union
from crewai import Agent, Task, Crew, Process, CrewOutput
from crewai.tools import BaseTool, tool
from pydantic import Field
from langchain_community.tools import DuckDuckGoSearchRun
from langchain_nvidia import NVIDIA,ChatNVIDIA
from dotenv import load_dotenv

load_dotenv()  

if 'NVIDIA_API_KEY' not in os.environ:
    raise ValueError("Please set the NVIDIA_API_KEY environment variable.")

def get_llm():
    return NVIDIA(model="qwen/qwen3-next-80b-a3b-instruct") #meta/llama-3.1-405b-instruct , qwen/qwen3-next-80b-a3b-instruct, qwen/qwen3-235b-a22b , qwen/qwen3-next-80b-a3b-thinking

def get_llm_2():
    return NVIDIA(model="qwen/qwen3-next-80b-a3b-instruct") #meta/llama-3.1-405b-instruct , qwen/qwen3-next-80b-a3b-instruct , qwen/qwen3-235b-a22b, qwen/qwen3-next-80b-a3b-thinking

# def get_llm_3():
#     return ChatNVIDIA(
#         model="meta/llama-4-maverick-17b-128e-instruct",
#         )

class DuckDuckGoSearchTool(BaseTool):
    name: str = "DuckDuckGo Search"
    description: str = "Useful for search queries about current events, financial data, or finding specific websites. Input should be a search query."
    search: DuckDuckGoSearchRun = Field(default_factory=DuckDuckGoSearchRun)

    def _run(self, query: str) -> str:
        """Execute the search query and return results"""
        try:
            return self.search.run(query)
        except Exception as e:
            return f"Error performing search: {str(e)}"

search_ddg = DuckDuckGoSearchTool()

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
    # llm_3 = get_llm_3()
    
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
        tools=[search_ddg],
        llm=llm_2,
        verbose=True
    )

    research_agent = Agent(
        role="Financial Researcher",
        goal="Gather detailed information about each fixed deposit provider.",
        backstory="You are skilled at researching financial institutions.",
        tools=[search_ddg],
        llm=llm_2,
        verbose=True
    )

    safety_agent = Agent(
        role="Risk Analyst",
        goal="Categorize each fixed deposit provider by safety based on credit ratings and news.",
        backstory="You have expertise in assessing the safety of financial institutions.",
        tools=[search_ddg],
        llm=llm,
        verbose=True
    )

    projection_agent = Agent(
        role="Financial Calculator",
        goal="Calculate projected maturity amounts precisely.",
        backstory="You are precise in financial calculations.",
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
        tools=[search_ddg],
        llm=llm_2,
        verbose=True
    )

    deep_research_agent = Agent(
        role="Senior Financial Investigator",
        goal="Conduct exhaustive research on specific financial institutions to find credit ratings, recent news, and financial health.",
        backstory="You are an investigative journalist specializing in finance.",
        tools=[search_ddg],
        #context=[provider_search_agent],
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

    # --- Manager Agent ---
    
    manager_agent = Agent(
        role="Crew Manager",
        goal="Identify the user's intent and delegate the task to the appropriate team.",
        backstory="You are a senior manager at a financial firm.",
        llm=llm,
        verbose=True
    )

    return {
        # Analysis
        "query_parser_agent": query_parser_agent,
        "search_agent": search_agent,
        "research_agent": research_agent,
        "safety_agent": safety_agent,
        "projection_agent": projection_agent,
        "summary_agent": summary_agent,
        # Research
        "provider_search_agent": provider_search_agent,
        "deep_research_agent": deep_research_agent,
        "research_compilation_agent": research_compilation_agent,
        # Manager
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
            "Return a list of the top 10 providers with their interest rates in the format: "
            "'Provider: [Name], Interest Rate: [X.X]%'"
        ),
        expected_output="A list of exactly 10 fixed deposit providers with interest rates.",
        agent=agents["search_agent"],
        context=[parse_task]
    )

    research_task = Task(
        description=(
            "For each provider in the list: {search_task.output}, "
            "research the provider thoroughly. Provide a brief summary and latest news. "
            "Format: 'Provider: [Name], Summary: [Summary], Latest News: [News]'"
        ),
        expected_output="A list of provider summaries with latest news.",
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
            "Calculate projections for each provider. "
            "Use amount from: {parse_task.output} and rates from: {search_task.output}. "
            "Output a table in strict CSV format: "
            "'Provider,Interest Rate,Maturity Amount,Interest Earned'"
        ),
        expected_output="A CSV-formatted table with projections.",
        agent=agents["projection_agent"],
        context=[parse_task, search_task]
    )

    summary_task = Task(
        description=(
            "Create a comprehensive, in-depth investment report using the data from:\n"
            "1. Research & News: {research_task.output}\n"
            "2. Safety Categorization: {safety_task.output}\n"
            "3. Financial Projections: {projection_task.output}\n\n"
            
            "Your report must be professionally formatted in Markdown and strictly follow this structure:\n\n"
            
            "#  Comprehensive Fixed Deposit Analysis Report\n\n"
            
            "## 1. Executive Summary\n"
            "- Provide a high-level overview of the best options found.\n"
            "- Highlight the highest yield and the safest option based on the data.\n\n"
            
            "## 2. Market Overview & Provider Analysis\n"
            "For EACH provider listed in the research data, provide a detailed subsection including:\n"
            "- **Provider Name & Interest Rate**\n"
            "- **Safety Profile**: (Safe/Moderate/Risky) and the specific reason why (credit ratings, news, etc.).\n"
            "- **Market Context**: Incorporate the 'Latest News' and 'Summary' from the research task. "
            "Explain any recent events that might impact their stability or rates.\n\n"
            
            "## 3. Financial Projection Deep Dive\n"
            "- Analyze the raw numbers. Discuss the Maturity Amount and Interest Earned.\n"
            "- Compare the compounding benefits across providers.\n\n"
            
            "## 4. Risk vs. Reward Assessment\n"
            "- Categorize the findings into three buckets: 'Maximum Safety', 'High Yield', and 'Balanced Choice'.\n"
            "- Discuss the trade-offs between choosing a higher rate (Risky/Moderate) vs. a lower rate (Safe).\n\n"
            
            "## 5. Strategic Recommendations\n"
            "Based on the user's query and the analysis, provide tailored advice:\n"
            "- **Option A (Conservative)**: Best for capital preservation.\n"
            "- **Option B (Aggressive)**: Best for maximizing returns.\n"
            "- **Option C (Balanced)**: Best mix of safety and return.\n\n"
            
            "## 6. Conclusion\n"
            "- A final wrapping sentence summarizing the best course of action.\n\n"
            
            "---\n"
            "*Disclaimer: This report is generated by AI for informational purposes only and does not constitute professional financial advice.*"
        ),
        expected_output="A highly detailed, structured Markdown report covering market news, risk analysis, and strategic financial recommendations.",
        agent=agents["summary_agent"],
        context=[research_task, safety_task, projection_task] 
        # CRITICAL: Added 'research_task' to context so the agent has access to news/summaries
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
            "1. Credit Ratings (CRISIL, ICRA, CARE, etc.).\n"
            "2. Interest Rate ranges.\n"
            "3. Recent News (last 6 months).\n"
            "4. Financial Health indicators.\n"
            "Format the output clearly for each provider."
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
            "Subheadings for each provider with Ratings, News, Financials, and Verdict."
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
            f"- If the user asks for calculations, maturity amounts, or comparisons based on a specific amount, respond with 'ANALYSIS'.\n"
            f"- If the user asks for general information, top providers, credit ratings, or detailed reports, respond with 'RESEARCH'.\n\n"
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
    
    print("--- Agent Deciding Route ---")
    route_result = router_crew.kickoff()
    decision = route_result.raw.strip().upper()
    print(f"--- Agent Decision: {decision} ---")
    
    if "ANALYSIS" in decision:
        print("Starting Analysis Crew...")
        crew = get_analysis_crew(user_query)
    else:
        print("Starting Deep Research Crew...")
        crew = get_research_crew(user_query)
        
    result = crew.kickoff()
    return result