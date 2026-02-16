import os
from typing import Union
from crewai import Agent, Task, Crew, Process, CrewOutput
from crewai.tools import tool
from ddgs import DDGS
from langchain_nvidia_ai_endpoints import NVIDIA
from dotenv import load_dotenv

load_dotenv()  

if 'NVIDIA_API_KEY' not in os.environ:
    raise ValueError("Please set the NVIDIA_API_KEY environment variable.")

def get_llm():
    return NVIDIA(model="meta/llama-3.1-405b-instruct")

# Tool Definitions
@tool("DuckDuckGo Search")
def search_ddg(query: str) -> str:
    """Search DuckDuckGo and return top results as a string."""
    with DDGS() as ddgs:
        results = ddgs.text(query, max_results=10) 
        return str(results)

@tool("Fixed Deposit Projection Calculator")
def fd_projection(principal: float, rate: float, tenure: int) -> str:
    """Calculate fixed deposit maturity amount and interest earned assuming quarterly compounding."""
    r = rate / 100
    n = 4  # Quarterly compounding
    t = tenure
    amount = principal * (1 + r/n)**(n*t)
    interest = amount - principal
    return f"Maturity Amount: {amount:.2f}, Interest Earned: {interest:.2f}"

# Agent Definitions
def create_agents():
    llm = get_llm()
    
    search_agent = Agent(
        role="Fixed Deposit Rate Researcher",
        goal="Find the top 10 fixed deposit providers with the highest interest rates for the given tenure.",
        backstory="You are an expert at searching the web for financial products and extracting relevant information. You always provide accurate and up-to-date interest rate data.",
        tools=[search_ddg],
        llm=llm,
        verbose=True
    )

    research_agent = Agent(
        role="Financial Researcher",
        goal="Gather detailed information about each fixed deposit provider, including latest news and financial health.",
        backstory="You are skilled at researching financial institutions and summarizing key information. You focus on recent developments and company stability.",
        tools=[search_ddg],
        llm=llm,
        verbose=True
    )

    safety_agent = Agent(
        role="Risk Analyst",
        goal="Categorize each fixed deposit provider by safety based on credit ratings, financial health, and recent news.",
        backstory="You have expertise in assessing the safety of financial institutions. You consider multiple factors including credit ratings, regulatory compliance, and recent financial performance.",
        tools=[search_ddg],
        llm=llm,
        verbose=True
    )

    projection_agent = Agent(
        role="Financial Calculator",
        goal="Calculate the projected maturity amount and interest earned for each provider using precise financial formulas.",
        backstory="You are precise in financial calculations and always provide accurate projections. You ensure all calculations use the exact interest rates provided.",
        tools=[fd_projection],
        llm=llm,
        verbose=True
    )

    summary_agent = Agent(
        role="Financial Advisor",
        goal="Create a comprehensive, user-friendly report summarizing the top fixed deposit options with safety categories and projections.",
        backstory="You are a helpful financial advisor who provides clear and actionable advice. You structure information in an easy-to-understand format and highlight key insights.",
        llm=llm,
        verbose=True
    )

    return {
        "search_agent": search_agent,
        "research_agent": research_agent,
        "safety_agent": safety_agent,
        "projection_agent": projection_agent,
        "summary_agent": summary_agent
    }

# Task Definitions (Same as before)
def create_tasks(agents, amount: float, tenure: int):
    # Task 1: Search for top FD rates
    search_task = Task(
        description=(
            f"Search for top fixed deposit interest rates for {tenure} years. Use the query: "
            f"'fixed deposit interest rates for {tenure} years top banks India general citizens'. "
            "Return a list of the top 10 providers with their interest rates in the exact format: "
            "'Provider: [Name], Interest Rate: [X.X]%'. "
            "Ensure the interest rates are for general citizens."
        ),
        expected_output="A list of exactly 10 fixed deposit providers with interest rates in the specified format.",
        agent=agents["search_agent"]
    )

    # Task 2: Research each provider
    research_task = Task(
        description=(
            "For each provider in the list from the previous task: {search_task.output}, "
            "research the provider thoroughly. Provide a brief summary (2-3 sentences) about the bank/NBFC, "
            "and include the latest news (within the last 6 months) about the provider. "
            "Format each entry as: "
            "'Provider: [Name], Summary: [Summary], Latest News: [News]'"
        ),
        expected_output="A list of provider summaries with latest news in the specified format.",
        agent=agents["research_agent"],
        context=[search_task]
    )

    # Task 3: Safety categorization
    safety_task = Task(
        description=(
            "Based on the summaries and news: {research_task.output}, "
            "categorize each provider's safety for fixed deposit as 'Safe', 'Moderate', or 'Risky'. "
            "Format each entry as: "
            "'Provider: [Name], Category: [Safe/Moderate/Risky], Reason: [Brief reason]'"
        ),
        expected_output="A list of safety categorizations with reasons in the specified format.",
        agent=agents["safety_agent"],
        context=[research_task]
    )

    # Task 4: Financial projections
    projection_task = Task(
        description=(
            f"Calculate fixed deposit projections for each provider using the interest rates from the search results. "
            f"Principal amount: {amount} INR, tenure: {tenure} years. "
            "Use the fd_projection tool for each provider. "
            "Output a table in strict CSV format (no additional text, no markdown) as follows: "
            "'Provider,Interest Rate,Maturity Amount,Interest Earned' followed by each provider on a new line. "
            "Example: 'HDFC Bank,5.5%,55250.00,5250.00'."
        ),
        expected_output="A CSV-formatted table with projections for each provider.",
        agent=agents["projection_agent"],
        context=[search_task]
    )

    # Task 5: Final summary report
    summary_task = Task(
        description=(
            "Create a comprehensive, user-friendly markdown report with the following sections: "
            "## Top Fixed Deposit Options for [Tenure] Years\n"
            "### 1. Interest Rate Comparison Table\n"
            "### 2. Provider Details\n"
            "### 3. Projection Analysis\n"
            "### 4. Recommendations\n\n"
            "Use the following data sources:\n"
            "- Safety categories: {safety_task.output}\n"
            "- Projections: {projection_task.output}\n"
        ),
        expected_output="A comprehensive markdown report with all sections as specified.",
        agent=agents["summary_agent"],
        context=[safety_task, projection_task]
    )

    return [search_task, research_task, safety_task, projection_task, summary_task]

# Crew Assembly
def create_crew(amount: float, tenure: int):
    agents = create_agents()
    tasks = create_tasks(agents, amount, tenure)
    
    crew = Crew(
        agents=list(agents.values()),
        tasks=tasks,
        process=Process.sequential,
        memory=False,
        verbose=True
    )
    return crew

# Main Execution Function
def run_crew(amount: float, tenure: int):
    crew = create_crew(amount, tenure)
    result = crew.kickoff(inputs={'amount': amount, 'tenure': tenure})
    return result