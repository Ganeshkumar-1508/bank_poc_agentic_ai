import os
import json
from typing import Union
from crewai import Agent, Task, Crew, Process, CrewOutput
from crewai.tools import BaseTool, tool
from pydantic import Field
from langchain_community.tools import DuckDuckGoSearchResults
from langchain_community.utilities import DuckDuckGoSearchAPIWrapper

# FIX 1: Correct import — the package is `langchain-nvidia-ai-endpoints`
#         and the only valid class is `ChatNVIDIA`. `NVIDIA` does not exist.
from langchain_nvidia_ai_endpoints import ChatNVIDIA

from opensanctions_tool import search_sanctions
from dotenv import load_dotenv

load_dotenv()

if 'NVIDIA_API_KEY' not in os.environ:
    raise ValueError("Please set the NVIDIA_API_KEY environment variable.")


# FIX 2: Changed NVIDIA(...) → ChatNVIDIA(...) in both helper functions.
def get_llm():
    return ChatNVIDIA(model="qwen/qwen3-next-80b-a3b-instruct")

def get_llm_2():
    return ChatNVIDIA(model="qwen/qwen3-next-80b-a3b-instruct")


# ==========================================
# TOOL CONFIGURATION
# ==========================================

ddg_news_wrapper = DuckDuckGoSearchAPIWrapper(
    source="news",
    max_results=5,
    region="in-in",
    time="m"
)

langchain_ddg_tool = DuckDuckGoSearchResults(
    api_wrapper=ddg_news_wrapper,
    output_format="list"
)

@tool("DuckDuckGo News Search")
def search_news(query: str) -> str:
    """
    Search for recent news articles using DuckDuckGo.
    The input should be a search query string.
    Returns a string representation of the results including title, link, and snippet.
    """
    results = langchain_ddg_tool.invoke(query)
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


def create_agents():
    llm = get_llm()
    llm_2 = get_llm_2()

    data_collector_agent = Agent(
        role="Strict KYC Compliance Officer",
        goal="Collect mandatory user details (Name, DOB, Address, PAN, Phone, Email, Account Number) before discussing investments.",
        backstory=(
            "You are a strict compliance officer at a bank. Your ONLY job is to collect personal details one at a time. "
            "You MUST NOT answer questions about Fixed Deposits, interest rates, or investments until ALL personal details are collected. "
            "If the user asks about finance, politely refuse and ask for the next missing field. "
            "After EVERY response you MUST append a line in this exact format with all currently known values "
            "(use null for fields not yet provided): "
            "PARTIAL_DATA: {\"name\": ..., \"dob\": ..., \"address\": ..., \"pan\": ..., \"phone\": ..., \"email\": ..., \"account_number\": ...} "
            "When ALL fields are filled (none are null), replace PARTIAL_DATA with COLLECTION_COMPLETE using the same JSON format."
        ),
        llm=llm_2,
        verbose=True
    )

    aml_agent = Agent(
        role="AML Compliance Officer",
        goal="Verify user identity against OpenSanctions to ensure they are not on sanctions lists.",
        backstory=(
            "You are a compliance officer. You use the search_sanctions tool to check names and PANs. "
            "You determine if the user is 'Safe', 'Suspicious', or 'High Risk' based on the search results."
        ),
        tools=[search_sanctions],
        llm=llm,
        verbose=True
    )

    manager_agent = Agent(
        role="Workflow Orchestrator",
        goal="Determine the current state of the user (KYC, AML, or Analysis) and route the request appropriately.",
        backstory=(
            "You are the system controller. You look at the 'Session State' provided in the task. "
            "If KYC is incomplete (kyc_complete=False), you MUST output 'ROUTE_KYC'. "
            "Else if AML is incomplete (aml_checked=False), you MUST output 'ROUTE_AML'. "
            "Else, you output 'ROUTE_ANALYSIS'. "
            "You strictly follow this order."
        ),
        llm=llm,
        verbose=True
    )

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

    return {
        "query_parser_agent": query_parser_agent,
        "search_agent": search_agent,
        "research_agent": research_agent,
        "safety_agent": safety_agent,
        "projection_agent": projection_agent,
        "summary_agent": summary_agent,
        "manager_agent": manager_agent,
        "data_collector_agent": data_collector_agent,
        "aml_agent": aml_agent
    }


# ==========================================
# TASK & CREW DEFINITIONS
# ==========================================

def get_kyc_crew(agents, current_data: str, user_prompt: str):
    collection_task = Task(
        description=(
            f"Current User Data: {current_data}\n"
            f"User Message: {user_prompt}\n\n"
            "Instructions:\n"
            "1. Check 'Current User Data' to see which fields are already filled.\n"
            "2. If the user's message contains a value for the field you last asked about, "
            "accept it and move on to the next missing field.\n"
            "3. Ask for exactly ONE missing field per response in this order: "
            "Name → DOB → Address → PAN → Phone → Email → Account Number.\n"
            "4. Do NOT re-ask for a field that already has a value in 'Current User Data'.\n"
            "5. If the user asks about FD or investments, ignore it and ask for the next missing field.\n"
            "6. At the end of your response, ALWAYS append on a new line:\n"
            "   PARTIAL_DATA: {\"name\": <value or null>, \"dob\": <value or null>, "
            "\"address\": <value or null>, \"pan\": <value or null>, \"phone\": <value or null>, "
            "\"email\": <value or null>, \"account_number\": <value or null>}\n"
            "7. When ALL fields are non-null, use COLLECTION_COMPLETE instead of PARTIAL_DATA."
        ),
        expected_output=(
            "A message asking for the next missing field, followed by "
            "PARTIAL_DATA: {json} or COLLECTION_COMPLETE: {json} on the last line."
        ),
        agent=agents["data_collector_agent"]
    )
    return Crew(
        agents=[agents["data_collector_agent"]],
        tasks=[collection_task],
        process=Process.sequential,
        verbose=True
    )


def get_aml_crew(agents, user_data: dict):
    aml_task = Task(
        description=(
            f"Verify the following user against sanctions lists:\n"
            f"Name: {user_data.get('name')}\n"
            f"PAN: {user_data.get('pan')}\n"
            "Use the search_sanctions tool. "
            "Report if the user is Clear or High Risk."
        ),
        expected_output="AML Check Result: Clear or Flagged.",
        agent=agents["aml_agent"]
    )
    return Crew(
        agents=[agents["aml_agent"]],
        tasks=[aml_task],
        process=Process.sequential,
        verbose=True
    )


def get_analysis_crew(agents, user_query: str):
    parse_task = Task(
        description=(
            f"Analyze the following user query: '{user_query}'. "
            "Extract the investment Amount (in INR) and Tenure (in years). "
            "Output strictly in the format: 'Amount: X, Tenure: Y'."
        ),
        expected_output="String format 'Amount: X, Tenure: Y'.",
        agent=agents["query_parser_agent"]
    )

    # FIX 4: Removed invalid Python variable references like `{parse_task.output}`
    #         from plain (non-f-string) task descriptions. These were being passed
    #         as literal text and not resolved. Tasks now rely on the `context`
    #         parameter to receive previous outputs, which is the correct CrewAI pattern.
    search_task = Task(
        description=(
            "Using the Amount and Tenure extracted by the previous task, "
            "search the web for the top 10 Fixed Deposit providers in India "
            "offering the highest interest rates for that tenure. "
            "Find both General and Senior Citizen rates."
        ),
        expected_output="List of 10 providers with General and Senior Citizen interest rates.",
        agent=agents["search_agent"],
        context=[parse_task]
    )

    research_task = Task(
        description=(
            "Using the list of FD providers from the previous task, "
            "research and gather recent news articles for each provider. "
            "Format output as: Provider: <name>, News: <headline>, URL: <url>"
        ),
        expected_output="Structured list of providers with recent news headlines and URLs.",
        agent=agents["research_agent"],
        context=[search_task]
    )

    safety_task = Task(
        description=(
            "Using the provider list and news from previous tasks, "
            "categorize each provider by safety level (High Safety / Medium Safety / Low Safety) "
            "based on credit ratings and any risk signals in the news. "
            "Format output as: Provider: <name>, Category: <safety_level>"
        ),
        expected_output="Safety categorization for each provider.",
        agent=agents["safety_agent"],
        context=[research_task]
    )

    projection_task = Task(
        description=(
            "Using the Amount and Tenure from the query parsing task and the provider "
            "rates from the search task, calculate the maturity amount and interest earned "
            "for each provider for both General and Senior Citizen categories. "
            "Output as CSV with columns: Provider, General Rate (%), Senior Rate (%), "
            "General Maturity, Senior Maturity, General Interest, Senior Interest."
        ),
        expected_output="CSV table of projections for all providers.",
        agent=agents["projection_agent"],
        context=[parse_task, search_task]
    )

    summary_task = Task(
        description=(
            "Compile a final, professional investment report in Markdown. "
            "Incorporate the provider rates, recent news, safety ratings, and maturity "
            "projections from all previous tasks. "
            "Include a recommendation section ranking providers by risk-adjusted return."
        ),
        expected_output="Detailed Markdown investment report.",
        agent=agents["summary_agent"],
        context=[research_task, safety_task, projection_task]
    )

    return Crew(
        agents=[
            agents["query_parser_agent"], agents["search_agent"], agents["research_agent"],
            agents["safety_agent"], agents["projection_agent"], agents["summary_agent"]
        ],
        tasks=[parse_task, search_task, research_task, safety_task, projection_task, summary_task],
        process=Process.sequential,
        verbose=True
    )


# ==========================================
# MASTER ROUTER
# ==========================================

def run_crew(user_query: str, session_state: dict):
    """
    Uses the Manager Agent to decide which crew to run based on Session State.
    Returns a tuple: (CrewOutput, tasks_output_list | None)
    """
    agents = create_agents()

    routing_task = Task(
        description=(
            f"Analyze the Session State and decide the route.\n\n"
            f"Session State:\n"
            f"- kyc_complete: {session_state.get('kyc_complete')}\n"
            f"- aml_checked: {session_state.get('aml_checked')}\n\n"
            f"Rules:\n"
            f"1. If kyc_complete is False -> Output strictly: 'ROUTE_KYC'\n"
            f"2. Else if aml_checked is False -> Output strictly: 'ROUTE_AML'\n"
            f"3. Else -> Output strictly: 'ROUTE_ANALYSIS'\n\n"
            f"Output ONLY the route keyword."
        ),
        expected_output="One of: ROUTE_KYC, ROUTE_AML, ROUTE_ANALYSIS",
        agent=agents["manager_agent"]
    )

    router_crew = Crew(agents=[agents["manager_agent"]], tasks=[routing_task], verbose=True)
    route_result = router_crew.kickoff()
    decision = route_result.raw.strip().upper()

    if "ROUTE_KYC" in decision:
        result = get_kyc_crew(agents, str(session_state.get('user_data')), user_query).kickoff()
        return result, None
    elif "ROUTE_AML" in decision:
        result = get_aml_crew(agents, session_state.get('user_data')).kickoff()
        return result, None
    elif "ROUTE_ANALYSIS" in decision:
        crew = get_analysis_crew(agents, user_query)
        result = crew.kickoff()
        # Return tasks_output so app.py can parse projection and news for visualization
        return result, result.tasks_output
    else:
        # Fallback to KYC
        result = get_kyc_crew(agents, str(session_state.get('user_data')), user_query).kickoff()
        return result, None