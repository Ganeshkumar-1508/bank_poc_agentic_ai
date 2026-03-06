# tasks.py
from crewai import Task

DB_SCHEMA_INFO = """
Database Schema for 'bank_poc.db':
1. Table 'users': user_id, first_name, last_name, account_number, email, is_account_active
2. Table 'address': address_id, user_id, user_address, pin_number, mobile_number, mobile_verified
3. Table 'kyc_verification': kyc_id, user_id, address_id, account_number, pan_number, aadhaar_number, kyc_status, verified_at, created_at, updated_at
4. Table 'accounts': account_id, user_id, account_number, account_type, balance, email, created_at
5. Table 'fixed_deposit': fd_id, user_id, initial_amount, bank_name, tenure_months, interest_rate, maturity_date, premature_penalty_percent, fd_status
"""

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
            "CRITICAL COUNT: Return a list of the TOP 10 providers. Do not stop at 5. "
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

            "LENGTH & COMPLETENESS: "
            "You must cover ALL 10 providers listed in the research data. "
            "Do not cut off the list or the report early. "
            "If you are running out of space, shorten the 'Strategic Recommendations' slightly, but ensure the 'Market Overview' contains every single provider.\n\n"

            "Your report must be professionally formatted in Markdown and strictly follow this structure:\n\n"

            "# Comprehensive Fixed Deposit Analysis Report\n\n"

            "## 1. Summary\n"
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
            f"Identify and list the TOP 10 Fixed Deposit providers (Banks & NBFCs) in India. "
            f"Ensure you find exactly 10 distinct providers. "
            f"Output a simple list of 10 names."
        ),
        expected_output="A list of 10 top Fixed Deposit provider names.",
        agent=agents["provider_search_agent"]
    )

    deep_research_task = Task(
        description=(
            "For EVERY provider in the list: {identify_providers_task.output}, perform exhaustive research. "
            "You must find the following for EACH of the 10 providers:\n"
            "1. Credit Ratings (CARE, ICRA, CRISIL, etc.).\n"
            "2. Interest Rate ranges (General vs Senior Citizen) for common tenures (1yr, 2yr, 5yr).\n"
            "3. Recent News (last 6 months) including headlines and links.\n"
            "4. Financial Health indicators (NPA, Capital Adequacy, or general stability) if available.\n"
            "Ensure you research all 10 providers listed in the previous step. Do not skip any."
        ),
        expected_output="Detailed structured data for all 10 providers.",
        agent=agents["deep_research_agent"],
        context=[identify_providers_task]
    )

    compile_report_task = Task(
        description=(
            "Compile findings from: {deep_research_task.output} into a comprehensive final report. "
            "STRUCTURE: ## Analysis of Top FD Providers\n\n"
            
            "For EACH provider, create a detailed subsection:\n"
            "### [Provider Name]\n"
            "- **Credit Rating**: [Rating Agency - Grade]\n"
            "- **Interest Rates**: [Range for General and Senior citizens]\n"
            "- **Recent News**: [Summaries with clickable links]\n"
            "- **Financial Health**: [Summary of stability]\n\n"

            "CRITICAL INSTRUCTION: "
            "You must include ALL 10 providers identified in the research. "
            "Do not stop halfway. The response must be complete. "
            "If the response is getting too long, reduce the word count of the descriptions slightly, but ensure every single provider from the input list appears in the output."
        ),
        expected_output="A structured markdown report covering all 10 found providers with detailed ratings and news.",
        agent=agents["research_compilation_agent"],
        context=[deep_research_task]
    )

    return [identify_providers_task, deep_research_task, compile_report_task]

def create_database_tasks(agents, user_query: str):
    query_task = Task(
        description=f"""
        Analyze the user's request: '{user_query}'.
        Based on the request, write a SQL query to fetch the required information from the database.
        Execute the query using the Bank Database Query Tool.
        Synthesize the results into a clear, human-readable answer.
        """,
        expected_output="A detailed answer based on the database records. If listing records, present them in a table format.",
        agent=agents["db_agent"]
    )
    return [query_task]

def create_onboarding_tasks(agents, conversation_history: str):
    onboarding_task = Task(
        description=(
            f"Conversation History:\n{conversation_history}\n\n"
            "Continue the onboarding process. Check what info is missing. "
            "If all info is present, use the 'Fixed Deposit Creation Manager' tool to create the FD."
        ),
        expected_output="Either a conversational question asking for missing details, or a result from the FD Creation Tool.",
        agent=agents["onboarding_agent"]
    )

    email_task = Task(
        description=(
            "Review the output from the previous Onboarding Task. "
            "If the output is a conversational question (e.g., asking for name, address, etc.), simply return the text EXACTLY as it is. Do not generate anything else."
            
            "If the output indicates a SUCCESSFUL FD creation (contains 'Success', 'FD ID', 'Maturity Date', etc.): "
            "1. Extract the following details from the text: Account Number, FD ID, Amount, Bank Name, Interest Rate, Tenure, Maturity Date, Customer Name, Email. "
            "2. Use the 'FD Invoice PDF Generator' tool with these details to generate a PDF file. "
            "3. Use the 'Email Dispatcher with PDF' tool to send the generated PDF to the customer's email address. "
            "4. Return a final message to the user confirming the FD creation and that the invoice has been emailed."
        ),
        expected_output="Either the original chat question, or a success message confirming the email was sent.",
        agent=agents["email_specialist_agent"],
        context=[onboarding_task]
    )
    return [onboarding_task, email_task]

def create_routing_task(agents, user_query: str):
    return Task(
        description=(
            f"Analyze the user query: '{user_query}'\n\n"
            f"Determine the intent:\n"
            f"- If the user asks about calculations, maturity amounts, or comparisons (external data), respond with 'ANALYSIS'.\n"
            f"- If the user asks for general info or detailed reports without calculations, respond with 'RESEARCH'.\n"
            f"- If the user asks about existing users, accounts, KYC status, or current FD records in the system (e.g. 'total tenure', 'list users'), respond with 'DATABASE'.\n"
            f"- If the user wants to open a new account, create a FD, or start onboarding (e.g. 'I want to open an account'), respond with 'ONBOARDING'.\n\n"
            f"Respond with ONLY one word: ANALYSIS, RESEARCH, DATABASE, or ONBOARDING."
        ),
        expected_output="Single word: ANALYSIS, RESEARCH, DATABASE, or ONBOARDING",
        agent=agents["manager_agent"]
    )