# tasks.py
from crewai import Task
from tools import graph # Import graph for schema access

DB_SCHEMA_INFO = """
Database Schema for 'bank_poc.db':
1. Table 'users': user_id, first_name, last_name, account_number, email, is_account_active
2. Table 'address': address_id, user_id, user_address, pin_number, mobile_number, mobile_verified
3. Table 'kyc_verification': kyc_id, user_id, address_id, account_number, pan_number, aadhaar_number, kyc_status, verified_at, created_at, updated_at
4. Table 'accounts': account_id, user_id, account_number, account_type, balance, email, created_at
5. Table 'fixed_deposit': fd_id, user_id, initial_amount, bank_name, tenure_months, interest_rate, maturity_date, premature_penalty_percent, fd_status
"""

# --- ORIGINAL TASKS (ANALYSIS, RESEARCH, DATABASE) ---

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

# --- NEW SPLIT ONBOARDING TASKS ---

def create_data_collection_task(agents, conversation_history: str):
    task = Task(
        description=(
            f"Conversation History:\n{conversation_history}\n\n"
            "Check if we have the following details: Name, Email, Address, PIN, Mobile, PAN, Aadhaar, FD Amount, Tenure, Bank Name.\n"
            
            "IF INFORMATION IS MISSING: "
            "Identify exactly ONE missing piece. Ask a polite question to get it. "
            "Output format: 'QUESTION: [Your question to the user]'\n\n"
            
            "IF ALL INFORMATION IS PRESENT: "
            "Output the data in this EXACT JSON format (do not add conversational text):\n"
            "DATA_READY: {\"first_name\": \"...\", \"last_name\": \"...\", \"email\": \"...\", \"user_address\": \"...\", "
            "\"pin_number\": \"...\", \"mobile_number\": \"...\", \"pan_number\": \"...\", \"aadhaar_number\": \"...\", "
            "\"account_number\": null, \"initial_amount\": ..., \"tenure_months\": ..., \"bank_name\": \"...\", \"interest_rate\": ...}"
        ),
        expected_output="Either a conversational question starting with 'QUESTION:' or a JSON block starting with 'DATA_READY:'",
        agent=agents["onboarding_data_agent"]
    )
    return task

def create_aml_execution_tasks(agents, client_data_json: str):
    
    # Fetch Schema
    try:
        database_schema = graph.schema
    except Exception as e:
        database_schema = f"Error retrieving schema: {str(e)}"

    # Task 1: Cypher Generation
    generate_cypher_task = Task(
        description=(
            f"Client Data:\n{client_data_json}\n\n"
            "DATABASE SCHEMA:\n"
            "---------------------------\n"
            f"{database_schema}\n"
            "---------------------------\n\n"
            "INSTRUCTIONS:\n"
            "1. Analyze the DATABASE SCHEMA. Identify relevant Node Labels (e.g., Entity, Officer, Intermediary).\n"
            "2. Extract the client's name from the Client Data.\n"
            "3. Write a Cypher query to find the client and their direct connections.\n\n"

            "CRITICAL RULES (STRICTLY ENFORCE):\n"
            
            "1. LABEL FILTERING (Performance):\n"
            "   - NEVER start with 'MATCH (n)' without a label. This causes a full database scan.\n"
            "   - You MUST specify labels in the MATCH clause: 'MATCH (n:Entity OR n:Officer ...)'\n\n"

            "2. CASE SENSITIVITY (Logic):\n"
            "   - If you use 'toLower(n.name)' for case-insensitive matching, you MUST also apply 'toLower' to the comparison string.\n"
            "   - VALID:   toLower(n.name) STARTS WITH toLower('Alfredo Cristiani')\n"
            "   - INVALID: toLower(n.name) STARTS WITH 'Alfredo Cristiani' (This will fail to match).\n"
            "   - NOTE: If case is consistent, prefer 'n.name STARTS WITH ...' for better index usage.\n\n"

            "3. SYNTAX:\n"
            "   - Aliases MUST be unquoted (e.g., AS SourceName, NOT AS 'Source Name').\n"
            "   - Use 'OPTIONAL MATCH' for relationships and filter with 'WHERE m IS NOT NULL'.\n\n"

            "EXAMPLE QUERY (Correct Logic & Syntax):\n"
            "for this example the user has given the entity name as 'Alfredo Félix Cristiani Burkard'"

            "MATCH path = (o:Officer)-[*1..2]-(connected)\n\n"
            "WHERE o.name CONTAINS 'Alfredo Félix Cristiani Burkard'. \n\n"
            "RETURN path"

            "CRITICAL: Output ONLY the raw Cypher query string. No markdown, no explanations."
        ),
        expected_output="A valid, optimized Cypher query string respecting label filtering and case logic.",
        agent=agents["cypher_generator_agent"]
    )

    # Task 2: AML Investigation
    aml_check_task = Task(
        description=(
            f"Client Data:\n{client_data_json}\n\n"
            "STEP 1: Execute Graph Query\n"
            "- You have been provided a Cypher query in the context: {generate_cypher_task.output}\n"
            "- Use the 'Neo4j Raw Query Executor' tool.\n"
            "- Pass the EXACT query string from the context into the tool.\n"
            "- Analyze the graph results.\n\n"

            "STEP 2: Perform Yente Check\n"
            "- Use 'Deep Entity Enrichment' to get the profile.\n"
            "- EXTRACT AND REPORT THE FOLLOWING FIELDS FROM THE JSON RESULT:\n"
            "  1. **Identity**: `caption` (Name), `properties.birthDate`, `properties.country`.\n"
            "  2. **Risk Flags**: `properties.topics` (look for 'sanction', 'pep', 'crime'), `properties.programId`.\n"
            "  3. **Details**: `properties.notes`, `properties.position`.\n"
            "  4. **Sources**: `properties.sourceUrl`.\n"
            "  5. **Verification**: `match_score`.\n\n"

            "STEP 3: OSINT Check (Wikidata Social Media)\n"
            "- Use the 'Wikidata OSINT (Social Media)' tool, passing the FULL JSON string returned by the Yente tool.\n"
            "- The tool will look for a Wikidata Q-ID and then extract any social media links (Facebook, Instagram, LinkedIn, X/Twitter, YouTube).\n"
            "- In your report, include a section 'OSINT – Social Media' listing each platform and URL found, or clearly state if none were found.\n\n"

            "STEP 4: News Check\n"
            "- Search for sanctions/Crime news.\n\n"

            "Compile an exhaustive report including:"
            "- Identity verification,"
            "- Graph findings,"
            "- Yente sanctions/PEP status,"
            "- OSINT social media profiles,"
            "- OSINT news findings."
        ),
        expected_output="Detailed AML report with identity, Neo4j graph, Yente sanctions/PEP, OSINT social media links, and OSINT news.",
        agent=agents["aml_investigator_agent"],
        context=[generate_cypher_task]
    )

    ubo_task = Task(
        description=(
            "Review the Client Data and the AML Investigator's findings.\n"
            "Client Data:\n" + client_data_json + "\n"
            "AML Findings:\n{aml_check_task.output}\n\n"
            "Your Goal: Identify Ultimate Beneficial Owners (UBOs).\n"
            "1. If the client is a COMPANY: Use 'Deep Entity Enrichment' to search for the company's directors, officers, and shareholders. "
            "Check if those individuals are sanctioned.\n"
            "2. If the client is a PERSON: Look for companies they are 'officer_of' in the Neo4j graph. Check those companies.\n"
            "3. List all identified UBOs and their risk status."
        ),
        expected_output="A list of identified UBOs (Directors, Shareholders) with their individual risk assessments.",
        agent=agents["ubo_investigator_agent"],
        context=[aml_check_task]
    )

    risk_scoring_task = Task(
        description=(
            "Review the AML investigation report: {aml_check_task.output}.\n"
            "Assign a Risk Score from 1 to 100.\n"
            "- 1-20: Very Low Risk (Clean record).\n"
            "- 21-40: Low Risk (Minor news, no sanctions).\n"
            "- 41-60: Medium Risk (Some negative news, requires review).\n"
            "- 61-100: High Risk (Sanctions, fraud, criminal links).\n\n"
            
            "Write an EXHAUSTIVE REPORT including:\n"
            "- Executive Summary & Score\n"
            "- Identity Verification: How you confirmed the client matches the database entity.\n"
            "- Neo4j Graph Analysis (List nodes and relationships found)\n"
            "- Sanctions/PEP Status (Cite specific datasets found in Yente profile)\n"
            "- OSINT Findings\n\n"
            
            "End strictly with this block:\n"
            "DECISION: [PASS or FAIL]\n"
            "SCORE: [Number]\n"
            "REASONING: [Brief justification]"
        ),
        expected_output="Exhaustive text report ending with the DECISION block.",
        agent=agents["risk_scoring_agent"],
        context=[aml_check_task]
    )

    create_fd_task = Task(
        description=(
            "The Risk Officer has PASSED this client (DECISION: PASS).\n"
            "Client Data:\n" + client_data_json + "\n\n"
            "CRITICAL STEP BEFORE CREATION:\n"
            "You have the Bank Name and Tenure from the client data. "
            "1. Use the 'DuckDuckGo News Search' tool to find the current interest rate for [Bank Name] FD for [Tenure] months.\n"
            "2. Extract the interest rate (e.g., 7.1).\n\n"
            "Then, use the 'FD Creator' tool to create the FD using ALL details including the Interest Rate you just found."
        ),
        expected_output="Success message with FD ID and Maturity Date.",
        agent=agents["fd_processor_agent"]
    )

    success_email_task = Task(
        description=(
            "FD was created successfully. Output from previous step: {create_fd_task.output}.\n"
            "Risk Report: {risk_scoring_task.output}.\n"
            "1. Use 'AML Report Generator'. Title: 'AML Report - [Name]'. Content: [Full Risk Report]. Filename: 'AML_Report_[Name].pdf'.\n"
            "2. Extract details (Account No, FD ID, Amount, etc.) from FD success output.\n"
            "3. Use 'FD Invoice PDF Generator' to create the invoice.\n"
            "4. Use 'Email Sender'. Attach BOTH PDFs. Subject: 'FD Created & Compliance Report'.\n"
            "5. Output: 'Success! FD created and reports emailed.'"
        ),
        expected_output="Confirmation of email sent.",
        agent=agents["success_handler_agent"],
        context=[create_fd_task, risk_scoring_task]
    )

    rejection_email_task = Task(
        description=(
            "The Risk Officer has REJECTED this client (DECISION: FAIL) due to high risk.\n"
            "Review: {risk_scoring_task.output}.\n"
            "Extract the client's email from the JSON data provided.\n"
            "1. Use 'AML Report Generator'. Title: 'AML Rejection Report - [Name]'. Content: [Full Risk Report]. Filename: 'Rejection_[Name].pdf'.\n"
            "2. Use 'Email Sender'. Attach Report. Subject: 'Application Update'. Body: 'We are unable to proceed with your application due to compliance/risk assessment.'\n"
            "3. Output: 'Application Rejected.'"
        ),
        expected_output="Confirmation of rejection email sent.",
        agent=agents["rejection_handler_agent"],
        context=[risk_scoring_task]
    )

    return [generate_cypher_task, aml_check_task, ubo_task, risk_scoring_task, create_fd_task, success_email_task, rejection_email_task]

def create_visualization_task(agents, user_query: str, data_context: str):
    """
    Generates an ECharts option JSON. Fetches data from web if context is empty.
    """
    # Determine if data context is useful
    has_context = bool(data_context and data_context != "null" and len(data_context) > 50)
    
    context_instruction = (
        "USE THE PROVIDED DATA CONTEXT. Do not search the web." if has_context
        else "THE DATA CONTEXT IS EMPTY OR INSUFFICIENT. YOU MUST USE THE 'DuckDuckGo News Search' TOOL TO FETCH THE DATA."
    )

    return Task(
        description=(
            f"User Query: '{user_query}'\n\n"
            f"Available Data Context: {data_context if has_context else 'None/Empty'}\n\n"
            
            "INSTRUCTIONS:\n"
            "1. Analyze the User Query to determine the desired chart type (e.g., 'bar', 'line', 'pie', 'donut', 'area', 'scatter').\n"
            f"2. {context_instruction}\n"
            "3. If you perform a web search:\n"
            "   - Look for specific numeric data points (e.g., rates, amounts, percentages) mentioned in the query.\n"
            "   - Extract the data carefully from the search snippets.\n"
            "4. If you use the provided context:\n"
            "   - Identify numeric columns (values) and string columns (labels/categories).\n"
            "5. Determine X and Y axes:\n"
            "   - Use String/Date columns for the X-axis (categories).\n"
            "   - Use Numeric columns for the Y-axis (series).\n"
            "   - If multiple numeric columns exist, create multiple series.\n"
            "6. Construct a valid Apache ECharts 'option' JSON object.\n"
            "   - Ensure the JSON structure is correct (xAxis, yAxis, series, tooltip, legend, title).\n"
            "   - For Pie/Donut charts, use 'name' and 'value' format in data.\n"
            "   - **CRITICAL FOR AREA CHARTS**: If the user asks for an 'area' chart, set `type: 'line'` in the series configuration and include `areaStyle: {}` to fill the color under the line.\n\n"
            
            "CRITICAL: Output ONLY the JSON string. Do not output markdown ```json ... ```."
        ),
        expected_output="A valid JSON string representing the ECharts configuration.",
        agent=agents["data_visualizer_agent"]
    )

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