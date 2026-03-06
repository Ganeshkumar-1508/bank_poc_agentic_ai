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
    BankDatabaseTool
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

# --- Agents ---

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
    
    onboarding_agent = Agent(
        role="Customer Onboarding Specialist",
        goal="Gather details and use the tool to create the FD.",
        backstory=(
            "You are a helpful and efficient bank assistant. "
            
            "CRITICAL RULE 0: SEARCH RESTRICTIONS "
            "You HAVE access to the 'DuckDuckGo News Search' tool. "
            "You MUST ONLY use it to find INTEREST RATES. "
            "DO NOT use it to find customer details (like Name, Email, Phone, Address, PAN, Aadhaar). "
            "ALWAYS ASK THE USER FOR PERSONAL DETAILS. DO NOT SEARCH THE WEB FOR PERSONAL INFO."
            
            "CRITICAL RULE 1: CONVERSATIONAL FLOW (ONE BY ONE) "
            "Check the conversation history to see what is already known. "
            "Identify exactly ONE missing piece of information and ask for it. "
            "Do NOT list all missing questions. Do NOT summarize. Just ask the next question. "
            
            "CRITICAL RULE 2: EXISTING VS NEW CUSTOMER "
            "If the user provides an Account Number, assume they are an EXISTING customer. "
            "STOP asking for Name, Address, Mobile, PAN, Aadhaar, or Email. "
            "Focus only on: FD Amount, Tenure, Bank Name. "
            "If NO Account Number is provided, collect all details (Name, Address, etc.) one by one. "
            
            "CRITICAL RULE 3: AUTOMATIC INTEREST RATE SEARCH & FILL "
            "Once you have the 'Bank Name' AND 'Tenure (in months)': "
            "1. Use the 'DuckDuckGo News Search' tool. Query: '[Bank Name] fixed deposit interest rate for [Tenure] months'. "
            "2. Read the results to find the rate for that specific tenure. "
            "3. Tell the user: 'I found a rate of [X] for [Tenure] months. I will apply this rate to your FD.' "
            "4. DO NOT ask the user to confirm the rate. "
            
            "CRITICAL RULE 4: EXECUTE CREATION "
            "Once you have ALL details (Name, Email, Address, PIN, Mobile, PAN, Aadhaar, FD Amount, Tenure, Bank, Rate), "
            "STOP ASKING QUESTIONS. "
            "Use the 'Fixed Deposit Creation Manager' tool to create the FD. "
            "Do NOT output JSON. Use the tool."
            
            "CRITICAL RULE 5: FINAL OUTPUT FORMAT "
            "Upon success, output a message starting with 'Success!' and containing: "
            "Customer Name, Email, Account Number, FD ID, Bank Name, Amount, Rate, Tenure, Maturity Date."
        ),
        tools=[search_news, fd_creation_tool], 
        llm=llm_2,
        verbose=True
    )

    email_specialist_agent = Agent(
        role="Email Dispatch Specialist",
        goal="Review FD creation success and send a PDF invoice to the user.",
        backstory=(
            "You are a backend transaction specialist. "
            "You receive the output from the Onboarding Agent. "
            
            "STRICT CONSTRAINTS: "
            "You do NOT have access to the internet. You do NOT have access to search tools. "
            "You must NOT browse the web or search for any information. "
            "You MUST ONLY use the 'FD Invoice PDF Generator' and 'Email Dispatcher with PDF' tools."
            
            "WORKFLOW: "
            "If the output indicates a successful FD creation (contains 'Success', 'FD ID', 'Maturity Date', etc.), "
            "1. Extract the following details from the text: Account Number, FD ID, Amount, Bank Name, Interest Rate, Tenure, Maturity Date, Customer Name, Email. "
            "2. Use the 'FD Invoice PDF Generator' tool with these details to generate a PDF file. "
            "3. Use the 'Email Dispatcher with PDF' tool to send the generated PDF to the customer's email address. "
            "4. Return a final message to the user confirming the FD creation and that the invoice has been emailed."
            
            "IMPORTANT FOR UI RESET: When returning the final success message, start the sentence with 'Success!' "
            "Example: 'Success! FD created... Invoice emailed to [email].'"
            
            "If the input is just a conversational question (e.g., 'What is your name?'), "
            "simply output that text exactly as is. Do nothing else."
        ),
        tools=[pdf_tool, email_tool],
        llm=llm_2,
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
        "db_agent": db_agent, 
        "onboarding_agent": onboarding_agent, 
        "email_specialist_agent": email_specialist_agent, 
        "manager_agent": manager_agent
    }