# tasks.py
from crewai import Task
from tools import graph

DB_SCHEMA_INFO = """
Database Schema for 'bank_poc.db':
1. Table 'users': user_id, first_name, last_name, account_number, email, is_account_active
2. Table 'address': address_id, user_id, user_address, pin_number, mobile_number, mobile_verified
3. Table 'kyc_verification': kyc_id, user_id, address_id, account_number, kyc_details_1, kyc_details_2, kyc_status, verified_at, created_at, updated_at
   NOTE: kyc_details_1 and kyc_details_2 store KYC docs as 'TYPE-VALUE' (e.g. 'PAN-ABCDE1234F', 'AADHAAR-1234-5678-9012')
4. Table 'accounts': account_id, user_id, account_number, account_type, balance, email, created_at
5. Table 'fixed_deposit': fd_id, user_id, initial_amount, bank_name, tenure_months, interest_rate, maturity_date, premature_penalty_percent, fd_status, product_type, monthly_installment, compounding_freq
"""

# ---------------------------------------------------------------------------
# ANALYSIS PIPELINE
# ---------------------------------------------------------------------------

def create_analysis_tasks(agents, user_query: str, region: str = "India"):

    parse_task = Task(
        description=(
            f"Analyze: '{user_query}'.\n"
            "1. Product Type: 'FD' (default) or 'RD' (keywords: recurring/monthly deposit/save every month).\n"
            "2. Amount: convert 'k'→×1000, 'L'→×100000. RD amount = monthly installment; FD = principal.\n"
            "3. Tenure: convert years→months.\n"
            "4. Compounding: monthly/quarterly/yearly. Default: quarterly.\n"
            "Output strictly: 'Type: [FD/RD], Amount: [Int], Tenure: [Int], Compounding: [String]'"
        ),
        expected_output="'Type: [Value], Amount: [Value], Tenure: [Value], Compounding: [Value]'",
        agent=agents["query_parser_agent"],
    )

    search_task = Task(
        description=(
            "Use the parsed deposit parameters from context.\n"
            f"Search: 'Best [FD/RD] interest rates {region} current year' (use type from context).\n"
            "Find BOTH General Rate and Senior Citizen Rate per provider (use general if senior unavailable).\n"
            "Make multiple searches if needed (e.g., banks then NBFCs) to reach exactly 10 providers.\n"
            "Output format — one line per provider:\n"
            "'Provider: [Name], General Rate: [X.X]%, Senior Rate: [Y.Y]%'"
        ),
        expected_output="Exactly 10 providers with General and Senior interest rates.",
        agent=agents["search_agent"],
        context=[parse_task],
    )

    research_task = Task(
        description=(
            "For each provider in context, run ONE combined search:\n"
            "  '[Provider Name] credit rating S&P Moody Fitch'\n\n"
            "RATING AGENCIES TO LOOK FOR (in priority order):\n"
            "  International: S&P Global (AAA/AA/A/BBB/BB/B/CCC), "
            "Moody's (Aaa/Aa/A/Baa/Ba/B/Caa), Fitch (AAA/AA/A/BBB/BB/B/CCC)\n"
            "  Regional/Local (use if international not available): AM Best, DBRS Morningstar, "
            "JCR (Japan), RAM/MARC (Malaysia), PEFINDO (Indonesia), TRIS (Thailand), "
            "PhilRatings (Philippines), CRISIL/ICRA/CARE (India), GCR (Africa), "
            "SR Rating (Brazil), Verum/Expert RA (Russia), ECAI (EU-recognised), "
            "or any nationally recognised rating body for that region.\n\n"
            "Always prefer an international agency rating. Only fall back to local/regional "
            "if no international rating exists for that provider.\n\n"
            "URL RULE: Copy URLs exactly as they appear in tool output ('URL: https://...'). "
            "Never invent or guess URLs. Write 'No Link Found' if absent.\n\n"
            "Output per provider (blank line between each):\n"
            "Provider: [Name]\n"
            "Credit Rating: [Agency - Grade, or 'Not Found']\n"
            "News: [Headline] | URL: [Exact URL]\n"
        ),
        expected_output="All 10 providers with credit ratings (international preferred, local fallback) and news headlines with real URLs.",
        agent=agents["research_agent"],
        context=[search_task],
    )

    safety_task = Task(
        description=(
            "Using the research context, categorize each provider as Safe, Moderate, or Risky.\n"
            "Scoring rules (apply to any rating agency — S&P, Moody's, Fitch, or local equivalent):\n"
            "  Safe:     Investment-grade: S&P/Fitch AAA–BBB- | Moody's Aaa–Baa3 | "
            "equivalent local grade. Also: government-owned banks or systemically important banks.\n"
            "  Moderate: Lower investment-grade or upper sub-investment: S&P/Fitch BB+–BB- | "
            "Moody's Ba1–Ba3 | newer private bank with limited public rating data.\n"
            "  Risky:    Sub-investment / speculative: S&P/Fitch B+ and below | "
            "Moody's B1 and below | NBFC with negative news | no rating found.\n"
            "If rating is 'Not Found' in research context, mark as Risky — do NOT search again.\n"
            "Format: 'Provider: [Name], Category: [Safe/Moderate/Risky], Rating: [Agency-Grade or Not Found], Reason: [Evidence]'"
        ),
        expected_output="Safety categorization for all 10 providers using internationally comparable rating criteria.",
        agent=agents["safety_agent"],
        context=[research_task],
    )

    projection_task = Task(
        description=(
            "Calculate maturity projections using the search context rates.\n\n"
            "STEP 1 — Select providers:\n"
            "  Pick the TOP 5 providers that have a confirmed numeric General Rate in the search context.\n"
            "  SKIP any provider whose rate is listed as 'N/A', 'not available', 'undisclosed', or missing.\n"
            "  If fewer than 5 providers have confirmed rates, use however many do.\n\n"
            "STEP 2 — Run calculator:\n"
            "  For each selected provider, call 'Universal Deposit Calculator' TWICE:\n"
            "    Call 1: use General Rate\n"
            "    Call 2: use Senior Rate (if unavailable, reuse General Rate + 0.25)\n"
            "  Pass: deposit_type, amount, rate, tenure_months, compounding_freq — all from parse context.\n\n"
            "STEP 3 — Output strict CSV (no extra text before or after):\n"
            "  Header line (exact):\n"
            "  Provider,Type,Compounding,General Rate (%),Senior Rate (%),General Maturity,Senior Maturity,General Interest,Senior Interest\n"
            "  One data row per provider. Rules:\n"
            "  - All numeric values must be actual numbers (e.g. 125000.50), never 'N/A' or blank.\n"
            "  - No currency symbols, no commas inside numbers, no markdown fences.\n"
            "  - If a provider has no confirmed rate, omit that row entirely."
        ),
        expected_output=(
            "A clean CSV table with one row per provider (only those with confirmed rates). "
            "All numeric columns contain real numbers, never N/A."
        ),
        agent=agents["projection_agent"],
        context=[parse_task, search_task],
    )

    summary_task = Task(
        description=(
            "Produce a professional, globally applicable investment research report from the context data.\n"
            "Use ONLY ASCII spaces (no Unicode whitespace). Use EXACT URLs from context — never fabricate.\n"
            "Cover ALL 10 providers. Write ≥ 150 words per provider subsection.\n"
            "Reference the user's exact amount and tenure throughout (e.g. 'For your 100,000 over 24 months...').\n"
            "Do NOT mention rupees or India-specific terms unless the region is actually India.\n"
            "Use the local currency from context throughout.\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "REQUIRED STRUCTURE (strict Markdown, exact order):\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "# Fixed Deposit Investment Analysis Report\n"
            "**Region:** [Region from context]  \n"
            "**Deposit Type:** [FD/RD]  \n"
            "**Principal / Installment:** [Amount]  \n"
            "**Tenure:** [N months]  \n"
            "**Compounding:** [Frequency]  \n"
            "**Report Date:** [Today's date]\n\n"
            "---\n\n"
            "## 1. Executive Summary\n"
            "- Quick overview: deposit type, amount, tenure, compounding.\n"
            "- **Top 3 picks — General investors** (ranked by projected maturity).\n"
            "- **Top 3 picks — Senior citizens** (ranked by projected maturity).\n"
            "- Highest-yield option vs safest option: name both and state the trade-off.\n\n"
            "## 2. Provider Analysis\n"
            "For EACH of the 10 providers, one subsection:\n\n"
            "### [Provider Name]\n"
            "| Field | Detail |\n"
            "| --- | --- |\n"
            "| Interest Rate (General) | X.XX% |\n"
            "| Interest Rate (Senior) | X.XX% |\n"
            "| Credit Rating | Agency — Grade |\n"
            "| Safety Profile | Safe / Moderate / Risky |\n"
            "| Projected Maturity (General) | [Amount] |\n"
            "| Projected Maturity (Senior) | [Amount] |\n"
            "| Interest Earned (General) | [Amount] |\n"
            "| Interest Earned (Senior) | [Amount] |\n\n"
            "Follow the table with 2–3 sentences covering: recent news, any risks, and why this provider\n"
            "ranks where it does. Embed exact hyperlinks from context (format: [Headline](URL)).\n\n"
            "## 3. Comparative Projection Table\n"
            "Reproduce the full projection CSV data as a Markdown table.\n"
            "Add two analysis rows below:\n"
            "- **Best vs Worst spread**: highest maturity minus lowest maturity (absolute + %).\n"
            "- **Senior premium**: average extra interest earned by senior citizens across all providers.\n\n"
            "## 4. Risk vs. Return Matrix\n"
            "A 3×2 Markdown table:\n"
            "| Strategy | Best General Option | Best Senior Option |\n"
            "| --- | --- | --- |\n"
            "| Maximum Safety | ... | ... |\n"
            "| Maximum Yield | ... | ... |\n"
            "| Balanced (Risk-Adjusted) | ... | ... |\n\n"
            "## 5. Strategic Recommendations\n"
            "Three clearly labelled options, each ≥ 3 sentences:\n"
            "- **Option A — Conservative**: lowest-risk provider with confirmed investment-grade rating.\n"
            "- **Option B — Growth**: highest-rate provider; quantify extra return vs Option A.\n"
            "- **Option C — Balanced**: best risk-adjusted pick; explain the reasoning.\n\n"
            "## 6. Market Context & Risks\n"
            "- Current interest-rate environment in the region (use search context data).\n"
            "- Key risks: credit risk, liquidity risk, early-withdrawal penalties.\n"
            "- Any regulatory or macro factors relevant to this region.\n\n"
            "## 7. Conclusion\n"
            "4–6 sentences that directly reference the user's specific amount, tenure, and region.\n"
            "End with a clear action step.\n\n"
            "---\n"
            "*Disclaimer: AI-generated for informational purposes only. "
            "Verify rates directly with providers before investing.*"
        ),
        expected_output=(
            "A complete, professionally structured Markdown investment report covering all 10 providers. "
            "Includes per-provider tables, projection comparison, risk matrix, three strategy options, "
            "market context, and a region-appropriate conclusion with real hyperlinks."
        ),
        agent=agents["summary_agent"],
        context=[research_task, safety_task, projection_task],
    )

    return [parse_task, search_task, research_task, safety_task, projection_task, summary_task]


# ---------------------------------------------------------------------------
# RESEARCH PIPELINE
# ---------------------------------------------------------------------------

def create_research_tasks(agents, user_query: str, region: str = "India"):

    identify_providers_task = Task(
        description=(
            f"Query: '{user_query}'.\n"
            f"Identify the TOP 10 Fixed Deposit providers (Banks & NBFCs) in {region}.\n"
            "Output a simple numbered list of 10 distinct provider names."
        ),
        expected_output="A numbered list of 10 top FD provider names.",
        agent=agents["provider_search_agent"],
    )

    deep_research_task = Task(
        description=(
            "For EVERY provider in the list from context, search:\n"
            "'[Provider Name] credit rating S&P Moody Fitch '\n\n"
            "Find for each provider:\n"
            "1. Credit rating — prefer international agencies first:\n"
            "   S&P Global, Moody's, Fitch. If unavailable, use the relevant regional agency\n"
            "   (e.g. DBRS for Canada/EU, JCR for Japan, RAM/MARC for Malaysia, PEFINDO for\n"
            "   Indonesia, TRIS for Thailand, GCR for Africa, CRISIL/ICRA/CARE for India,\n"
            "   SR Rating for Brazil, or any ECAI-recognised local body).\n"
            "2. Interest rate ranges (General vs Senior) for 1yr, 2yr, 5yr tenures.\n"
            "3. Recent news headlines (last 6 months) with exact URLs from tool output.\n"
            "4. Financial health indicators (NPA ratio, Capital Adequacy Ratio) if available.\n\n"
            "URL RULE: Copy URLs exactly from 'URL: ...' in tool output. Never invent URLs.\n"
            "Cover all 10 providers."
        ),
        expected_output="Structured data for all 10 providers with international credit ratings (local fallback if needed) and real URLs.",
        agent=agents["deep_research_agent"],
        context=[identify_providers_task],
    )

    compile_report_task = Task(
        description=(
            "Compile the research context into a final Markdown report.\n\n"
            "## Analysis of Top FD Providers\n\n"
            "For EACH of the 10 providers:\n"
            "### [Provider Name]\n"
            "- **Credit Rating**: [Agency - Grade]\n"
            "- **Interest Rates**: [General and Senior ranges]\n"
            "- **Recent News**: [Summaries with exact clickable links from context]\n"
            "- **Financial Health**: [Stability summary]\n\n"
            "RULES: Include all 10 providers. Use only URLs found in context — never fabricate."
        ),
        expected_output="Complete Markdown report covering all 10 providers with real news links.",
        agent=agents["research_compilation_agent"],
        context=[deep_research_task],
    )

    return [identify_providers_task, deep_research_task, compile_report_task]


# ---------------------------------------------------------------------------
# DATABASE PIPELINE
# ---------------------------------------------------------------------------

def create_database_tasks(agents, user_query: str):
    query_task = Task(
        description=(
            f"User request: '{user_query}'.\n"
            f"Schema:\n{DB_SCHEMA_INFO}\n"
            "1. Identify the needed data.\n"
            "2. Use 'Bank Database Query Tool' to write and run the SQL query.\n"
            "   Start with SELECT * FROM ... LIMIT 5 if unsure of structure.\n"
            "3. Return a clear, human-readable answer."
        ),
        expected_output="A clear answer based on SQL query results.",
        agent=agents["db_agent"],
    )
    return [query_task]


# ---------------------------------------------------------------------------
# ONBOARDING DATA COLLECTION
# ---------------------------------------------------------------------------

def create_data_collection_task(agents, conversation_history: str,
                                 country_name: str = "India",
                                 kyc_doc1: str = "", kyc_doc2: str = ""):
    """
    kyc_doc1 / kyc_doc2 are pre-fetched and cached by app.py.
    When provided, skip the KYC search step entirely to save one tool call per turn.
    """
    if kyc_doc1 and kyc_doc2:
        kyc_instructions = (
            f"KYC documents for {country_name} are already known: '{kyc_doc1}' and '{kyc_doc2}'.\n"
            "Skip the KYC search. Proceed directly to STEP 2."
        )
    else:
        kyc_instructions = (
            f"STEP 1: Search 'primary KYC documents required for bank account opening in {country_name}'.\n"
            "Identify the TOP 2 mandatory government IDs."
        )

    task = Task(
        description=(
            f"Conversation History:\n{conversation_history}\n\n"
            f"User Country: {country_name}\n\n"
            f"{kyc_instructions}\n\n"
            "STEP 2: Check if ALL these fields are collected:\n"
            "Name, Email, Address, PIN, Mobile, Bank Name, Product Type (FD/RD), Amount, Tenure, "
            f"Compounding, {kyc_doc1 or 'KYC Doc 1'}, {kyc_doc2 or 'KYC Doc 2'}.\n\n"
            "STEP 3: If anything is missing, ask for it. One question at a time.\n"
            "Output: 'QUESTION: [Your question]'\n\n"
            "STEP 4: If ALL fields are present, output:\n"
            'DATA_READY: {"first_name": "...", "last_name": "...", "email": "...", "user_address": "...", '
            '"pin_number": "...", "mobile_number": "...", "bank_name": "...", '
            '"product_type": "FD/RD", "initial_amount": ..., "tenure_months": ..., "compounding_freq": "...", '
            '"kyc_details_1": "DOC_NAME-DOC_VALUE", "kyc_details_2": "DOC_NAME-DOC_VALUE"}'
        ),
        expected_output="Either 'QUESTION: ...' or 'DATA_READY: {...}'",
        agent=agents["onboarding_data_agent"],
    )
    return task


# ---------------------------------------------------------------------------
# AML EXECUTION (Hierarchical)
# ---------------------------------------------------------------------------

def create_aml_execution_tasks(agents, client_data_json: str):

    generate_cypher_task = Task(
        description=(
            f"Client Data:\n{client_data_json}\n\n"
            "1. Extract 'first_name' and 'last_name'. Combine: '<first_name> <last_name>'.\n"
            "2. Build this Cypher query (use toLower for case-insensitive match):\n\n"
            "MATCH (p:Officer)-[r*1..3]-(connected)\n"
            "WHERE toLower(p.name) CONTAINS toLower('<Combined Name>')\n"
            "RETURN p, r, connected\n"
            "LIMIT 50\n\n"
            "Output ONLY the raw Cypher string. No markdown ticks."
        ),
        expected_output="A single raw Cypher query string.",
        agent=agents["cypher_generator_agent"],
    )

    aml_check_task = Task(
        description=(
            f"Client Data:\n{client_data_json}\n\n"
            "STEP 1 — Graph Query:\n"
            "Run the Cypher query from context using 'Neo4j Graph Query'.\n"
            "Record GRAPH_IMAGE_PATH from the output.\n\n"
            "STEP 2 — Yente Screening:\n"
            'Build JSON: {"schema": "Person", "name": "...", "birth_date": "...", "nationality": "..."}\n'
            "Pass to 'Deep Entity Enrichment (Yente/OpenSanctions)'. Trust only score > 0.5.\n"
            "Report: risk_flags, topics, sanctions_programs, related_entities, match_score.\n\n"
            "STEP 3 — OSINT:\n"
            "Pass the full Yente output text to 'Wikidata Subject Image Fetcher' (it reads the ENTITY_NAME: line). "
            "If a username is found, run 'Maigret OSINT'.\n\n"
            "STEP 4 — News:\n"
            "Search for '[Client Name] sanctions or crime' using DuckDuckGo.\n\n"
            "Compile full report including GRAPH_IMAGE_PATH."
        ),
        expected_output="AML report with Neo4j graph, Yente sanctions/PEP, OSINT, news, and GRAPH_IMAGE_PATH.",
        agent=agents["aml_investigator_agent"],
        context=[generate_cypher_task],
    )

    ubo_task = Task(
        description=(
            f"Client Data:\n{client_data_json}\n\n"
            "Review the AML report from context. Identify Ultimate Beneficial Owners (UBOs):\n"
            "- If client is a COMPANY: Search for directors/shareholders via 'Deep Entity Enrichment'. Check if sanctioned.\n"
            "- If client is a PERSON: Find companies they are 'officer_of' in the Neo4j graph. Check those companies.\n"
            "List all UBOs and their individual risk status."
        ),
        expected_output="List of UBOs with individual risk assessments.",
        agent=agents["ubo_investigator_agent"],
        context=[aml_check_task],
    )

    risk_scoring_task = Task(
        description=(
            "You are the Chief Risk Officer. Produce the single, definitive, court-ready AML compliance "
            "report from all investigation data in context. This is the final document — it goes directly "
            "into the PDF. Be exhaustive: omit nothing.\n\n"
            f"Client Data:\n{client_data_json}\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "STRICT RULES — FOLLOW IN ORDER:\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "1. HEADER: Extract the client's full name from client data. Write the current date and "
            "   time (YYYY-MM-DD HH:MM:SS) as the generation timestamp.\n\n"
            "2. VERBATIM PRESERVATION: Every figure, score, flag, entity name, relationship type, "
            "   sanction program ID, match score, and graph path from context must appear in full — "
            "   nothing may be omitted, paraphrased away, or shortened.\n\n"
            "3. LIVE ENRICHMENT — run these tools before writing:\n"
            "   a) For each entity and sanction flag in context, run 'DuckDuckGo News Search' "
            "      (query: '[Entity Name] sanctions fraud investigation'). Embed every returned URL "
            "      as a Markdown hyperlink: [Headline](URL). Never invent URLs.\n"
            "   b) Re-run 'Deep Entity Enrichment (Yente/OpenSanctions)' for the primary client and "
            "      each related entity flagged in context. Append any new sanctions programs, aliases, "
            "      or positions discovered.\n"
            "   c) Pass the Yente output to 'Wikidata Subject Image Fetcher'. The tool returns a line starting with WIKIDATA_IMAGE_PATH: — extract that path exactly.\n\n"
            "4. SCORE TABLE: Build a 4-column table — "
            "   Risk Factor | Points | Rationale | Evidence Link — "
            "   with a hyperlink in the Evidence Link column for every row. "
            "   Final row: **Total | [N] | [Band] | —**\n\n"
            "5. GRAPH: Re-state GRAPH_IMAGE_PATH from context exactly as-is. Do not alter the path.\n\n"
            "6. OUTPUT: Pure Markdown only. Use ##/### headers, bold, tables, bullet lists throughout. "
            "   No unstructured prose blocks.\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "REQUIRED SECTIONS (exact order):\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "# AML Compliance Report — [Client Full Name]\n"
            "**Generated:** [YYYY-MM-DD HH:MM:SS]  \n"
            "**Prepared by:** Chief Risk Officer — Automated Compliance System  \n"
            "**Classification:** CONFIDENTIAL\n\n"
            "---\n\n"
            "## Executive Summary\n"
            "- Final Risk Score, band, and one-line verdict.\n"
            "- Decision block (verbatim):\n"
            "  DECISION: [PASS or FAIL]  \n"
            "  SCORE: [N]  \n"
            "  REASONING: [1 sentence]\n\n"
            "## 1. Subject Identity Profile\n"
            "- Full legal name and all known aliases.\n"
            "- Date of birth, nationality, country code submitted.\n"
            "- KYC document types and values provided.\n"
            "- Verified name from OpenSanctions vs submitted — mismatch analysis with confidence band.\n"
            "- Match score.\n\n"
            "## 2. Sanctions & PEP Status\n"
            "- All sanctions programs verbatim (program ID + description).\n"
            "- PEP level and basis.\n"
            "- Newly discovered programs from Yente re-query.\n"
            "- Hyperlinked news result for each program.\n\n"
            "## 3. Neo4j Graph Analysis\n"
            "- Total nodes and edges.\n"
            "- Full entity table: Entity Name | Type | Relationship | Risk Note.\n"
            "- Network topology description.\n"
            "- `GRAPH_IMAGE_PATH: [exact path from context]`\n\n"
            "## 4. UBO (Ultimate Beneficial Owner) Analysis\n"
            "- Table: Entity Name | Type | Relationship | Sanctions Status | Risk Level | Source Link.\n"
            "- Each entity's OffshoreLeaks / OpenSanctions reference as a hyperlink.\n\n"
            "## 5. OSINT & Media Intelligence\n"
            "- Social media profiles found (each as a hyperlink).\n"
            "- Negative media timeline — date-sorted newest first, each headline hyperlinked.\n"
            "- Positive/neutral findings (if any).\n\n"
            "## 6. Risk Score Breakdown\n"
            "4-column table: Risk Factor | Points | Rationale | Evidence Link\n"
            "Final row bold total.\n\n"
            "## 7. Recommendations\n"
            "Numbered list — expand each from context with: specific next step, responsible party, "
            "and regulatory reference (e.g. FATF Recommendation 10, AML Directive Article 18).\n\n"
            "## 8. Data Sources & Tool Audit\n"
            "- List every tool used (Neo4j, Yente, DDG, OSINT), the exact query run, and result summary.\n"
            "- All external URLs cited.\n\n"
            "---\n"
            "*Auto-generated by the Compliance AI System. Internal use only. Not legal advice.*"
        ),
        expected_output=(
            "A complete, court-ready Markdown AML compliance report containing: client full name and "
            "live timestamp in the header; all risk data verbatim; live DDG hyperlinks per claim; "
            "Yente re-query results; OSINT profile URLs; 4-column score table; expanded recommendations "
            "with FATF references; full tool audit trail; and GRAPH_IMAGE_PATH preserved exactly."
        ),
        agent=agents["risk_scoring_agent"],
        context=[aml_check_task, ubo_task],
    )

    create_deposit_task = Task(
        description=(
            "Check the risk decision from context.\n"
            "- If 'DECISION: FAIL': output 'STOP: Application Rejected.' and stop.\n"
            "- If 'DECISION: PASS': proceed.\n\n"
            f"Client Data:\n{client_data_json}\n\n"
            "1. Search for current interest rate for the specified bank and product type.\n"
            "2. Use 'Deposit Creator' tool to create the FD/RD."
        ),
        expected_output="Deposit ID and Maturity Date, or a STOP message.",
        agent=agents["fd_processor_agent"],
        context=[risk_scoring_task],
    )

    final_email_task = Task(
        description=(
            "Read the risk decision from context.\n\n"
            f"Client Data (extract recipient email from here):\n{client_data_json}\n\n"
            "IF 'DECISION: FAIL':\n"
            "1. Use the FULL Markdown text from the risk_scoring_task output in context as 'markdown_content'.\n"
            "   Extract GRAPH_IMAGE_PATH from context and pass as 'graph_image_path'.\n"
            "   Extract the path from the WIKIDATA_IMAGE_PATH: line in context and pass as 'subject_image_path'.\n"
            "2. Generate rejection PDF via 'Markdown Report Generator' with:\n"
            "   title='Application Rejection Report', markdown_content=<full report>, graph_image_path=<path if found>, subject_image_path=<wikidata path if found>\n"
            "3. Send rejection email via 'Email Sender':\n"
            "   Subject: 'Application Update'\n"
            "   Body: 'We are unable to proceed due to compliance risk assessment. Please contact us.'\n"
            "   Attach the generated PDF.\n\n"
            "IF 'DECISION: PASS':\n"
            "1. Use the FULL Markdown text from the risk_scoring_task output in context as 'markdown_content'.\n"
            "   Extract GRAPH_IMAGE_PATH from context and pass as 'graph_image_path'.\n"
            "   Extract the path from the WIKIDATA_IMAGE_PATH: line in context and pass as 'subject_image_path'.\n"
            "2. Generate success PDF via 'Markdown Report Generator' with:\n"
            "   title='Application Approval & Compliance Report', markdown_content=<full report>, graph_image_path=<path if found>, subject_image_path=<wikidata path if found>\n"
            "3. Send success email via 'Email Sender':\n"
            "   Subject: 'Deposit Created & Compliance Report'\n"
            "   Body: 'Congratulations! Your deposit has been created. Please find your compliance report attached.'\n"
            "   Attach the generated PDF.\n\n"
            "IMPORTANT: Send exactly ONE email."
        ),
        expected_output="Confirmation of exactly one email sent (rejection or success) with the detailed PDF attached.",
        agent=agents["success_handler_agent"],
        context=[create_deposit_task, risk_scoring_task],
    )

    return [generate_cypher_task, aml_check_task, ubo_task, risk_scoring_task,
            create_deposit_task, final_email_task]


# ---------------------------------------------------------------------------
# SEQUENTIAL COMPLIANCE INVESTIGATION
# ---------------------------------------------------------------------------

def create_compliance_investigation_tasks(agents, client_data_json: str):

    identity_task = Task(
        description=(
            f"Client Data:\n{client_data_json}\n\n"
            "1. Extract full name, birth date, nationality, ID numbers.\n"
            '2. Build JSON: {"schema": "Person", "name": "...", "birth_date": "...", "nationality": "..."}\n'
            "   More fields = more accurate match scoring.\n"
            "3. Pass to 'Deep Entity Enrichment (Yente/OpenSanctions)'. Trust only score > 0.5.\n"
            "4. The tool returns a compact summary. Report all fields as-is:\n"
            "   Risk Flags, Match Score, Topics, Sanctions, Nationalities, Positions, Related Entities, Sources.\n"
            "   The output also contains an 'ENTITY_NAME:' line — preserve it exactly in your output."
        ),
        expected_output="Risk summary with all Yente fields including the ENTITY_NAME line preserved.",
        agent=agents["identity_agent"],
    )

    graph_task = Task(
        description=(
            f"Client Data:\n{client_data_json}\n\n"
            "1. Extract 'first_name' + 'last_name'. Combine into '<first_name> <last_name>'.\n"
            "2. Build and execute this Cypher query via 'Neo4j Graph Query':\n\n"
            "MATCH (p:Officer)-[r*1..3]-(connected)\n"
            "WHERE toLower(p.name) CONTAINS toLower('<Combined Name>')\n"
            "RETURN p, r, connected\n"
            "LIMIT 50\n\n"
            "3. Summarize all nodes/relationships found and record GRAPH_IMAGE_PATH from output."
        ),
        expected_output="Graph findings summary with GRAPH_IMAGE_PATH.",
        agent=agents["graph_analyst_agent"],
    )

    osint_task = Task(
        description=(
            "You have the Identity Analyst's report in context.\n\n"
            "STEP 1 — Extract from context: Full Name, DOB, Nationality.\n"
            "Locate the line 'ENTITY_NAME: <name>' and extract the name — "
            "pass the entire Yente output block to 'Wikidata Subject Image Fetcher'.\n\n"
            "STEP 2 — Web OSINT: The tool will search for social media profiles.\n"
            "Record ALL social media URLs, Wikipedia descriptions, and organizations found.\n\n"
            "STEP 3 — Maigret: Parse usernames from URLs in Step 2 "
            "(e.g., twitter.com/username → 'username').\n"
            "For each username, run 'Maigret OSINT' and list every site/URL found.\n\n"
            "STEP 4 — Output a Markdown report:\n"
            "1. Confirmed Identity (Name, DOB, Nationality).\n"
            "2. Social Media Profiles (all links found).\n"
            "3. Maigret Results (platforms/URLs per username, PDF paths)."
        ),
        expected_output="OSINT Markdown report with social media profiles and Maigret username results.",
        agent=agents["osint_specialist_agent"],
        context=[identity_task],
    )

    synthesis_task = Task(
        description=(
            "Synthesize all investigation reports from context into a final compliance report.\n\n"
            "# AML Compliance Report: [Client Name]\n"
            "Generated: [Timestamp]\n\n"
            "## Executive Summary & Score\n"
            "Final Risk Score: [N] / 100 — [LOW/MEDIUM/HIGH/CRITICAL] RISK\n"
            "Narrative summary.\n\n"
            "DECISION: [APPROVE/REJECT]\nSCORE: [N]\nREASONING: [1 sentence]\n\n"
            "## 1. Identity Verification\n"
            "KYC vs verified data. Mismatches. Conclusion on integrity.\n\n"
            "## 2. Neo4j Graph Analysis\n"
            "Matches found. Key nodes/relationships. Network topology.\n"
            "Include: `GRAPH_IMAGE_PATH: [Path from context]`\n\n"
            "## 3. UBO Analysis\n"
            "Beneficial owners and risk implications.\n\n"
            "## 4. Sanctions / PEP Status\n"
            "PEP level, sanctions status, contextual risk.\n\n"
            "## 5. OSINT Findings\n"
            "Positive and negative findings.\n\n"
            "## 6. Score Justification\n"
            "| Risk Factor | Points | Rationale |\n"
            "| --- | --- | --- |\n"
            "| [Factor] | [+/- N] | [Reason] |\n"
            "| **Total** | **[N]** | **[Level]** |\n\n"
            "## Recommendations\n"
            "1. Immediate action. 2. EDD. 3. Board Notification. 4. Monitoring. 5. FIU Referral."
        ),
        expected_output="Comprehensive Markdown compliance report with score table and DECISION/SCORE/REASONING.",
        agent=agents["compliance_reporter_agent"],
        context=[identity_task, graph_task, osint_task],
    )

    decision_task = Task(
        description=(
            "Review the Compliance Report from context.\n\n"
            f"Client Data:\n{client_data_json}\n\n"
            "IF 'DECISION: REJECT' or Risk Score > 50:\n"
            "1. Generate rejection PDF via 'Markdown Report Generator'.\n"
            "2. Send rejection email via 'Email Sender'. Do NOT create a deposit.\n\n"
            "IF 'DECISION: APPROVE' and Risk Score <= 50:\n"
            "1. Search current rate for the bank.\n"
            "2. Create FD/RD via 'Deposit Creator'.\n"
            "3. Generate success PDF via 'Markdown Report Generator'.\n"
            "4. Send success email via 'Email Sender'.\n\n"
            "Send exactly ONE email."
        ),
        expected_output="Confirmation of deposit creation or rejection email sent.",
        agent=agents["success_handler_agent"],
        context=[synthesis_task],
    )

    return [identity_task, graph_task, osint_task, synthesis_task, decision_task]


# ---------------------------------------------------------------------------
# VISUALIZATION
# ---------------------------------------------------------------------------

def create_visualization_task(agents, user_query: str, data_context: str):
    has_context = bool(data_context and data_context != "null" and len(data_context) > 50)

    # Dynamic instruction based on data availability
    context_instruction = (
        "PRIMARY DATA: Use the provided Data Context for the FD/RD providers.\n"
        "SUPPLEMENTAL DATA: If the user asks for external benchmarks (like 'Repo Rate', 'Inflation', 'Gold Price') "
        "or if the context is missing specific details needed for the chart, "
        "use 'DuckDuckGo News Search' to fetch that specific missing value.\n"
        "Do NOT search for data you already have in the context."
        if has_context
        else "DATA CONTEXT IS EMPTY — use 'DuckDuckGo News Search' to fetch all necessary data."
    )

    return Task(
        description=(
            f"Query: '{user_query}'\n"
            f"Data Context: {data_context if has_context else 'None'}\n\n"
            
            f"--- INSTRUCTIONS ---\n"
            f"1. DATA STRATEGY:\n"
            f"{context_instruction}\n\n"
            
            f"2. SCOPE:\n"
            f"Use ONLY the TOP 10 providers sorted by General Rate.\n\n"
            
            f"3. CHART TYPE SELECTION:\n"
            f"Decide the best Apache ECharts chart type based on the user's query:\n"
            f"- Comparisons (Rates/Maturity): Use 'bar' (vertical or horizontal).\n"
            f"- Trends over time: Use 'line' or 'area'.\n"
            f"- Proportions/Share: Use 'pie' or 'donut'.\n"
            f"- Multi-dimensional profiles: Use 'radar'.\n"
            f"- Single KPI/Benchmark: Use 'gauge'.\n"
            f"- Correlations: Use 'scatter'.\n"
            f"**HONOR THE USER'S EXPLICIT CHART REQUEST** (e.g., if they ask for 'radar', use radar).\n\n"
            
            f"4. GENERATION RULES:\n"
            f"- Generate MULTIPLE charts if needed to cover different aspects (e.g., one for Rates, one for Maturity).\n"
            f"- Default to a comprehensive set (e.g., 4 charts: General Rate, Senior Rate, Maturity, Interest Spread) if the query is broad.\n"
            f"- For Pie/Donut: Data must be in `{{name: 'Provider', value: 100}}` format.\n"
            f"- Always include `title`, `tooltip`, and `legend`.\n"
            f"- Handle external benchmarks (e.g., draw a 'markLine' for Repo Rate if searched).\n\n"
            
            f"5. OUTPUT FORMAT:\n"
            f"Return a RAW JSON list containing one or more ECharts option objects.\n"
            f"Example: `[{{\"title\": {{\"text\": \"...\"}}, ...}}, {{...}}]`\n"
            f"NO MARKDOWN WRAPPERS (```json). NO extra text."
        ),
        expected_output="A JSON list of valid ECharts configuration objects.",
        agent=agents["data_visualizer_agent"],
    )


# ---------------------------------------------------------------------------
# ROUTING
# ---------------------------------------------------------------------------

def create_routing_task(agents, user_query: str):
    return Task(
        description=(
            f"Classify this query into exactly ONE label.\n"
            f"QUERY: \"{user_query}\"\n\n"
            "LABELS:\n"
            "ANALYSIS — user wants to compare/calculate deposit returns. "
            "Signals: amount + tenure + words like options/rates/compare/returns/maturity. "
            "Examples: 'Best FD rates for 1L 2 years', 'Compare SBI vs HDFC for 3yr FD', "
            "'What will 10000 earn at 7% for 1 year', 'FD rates for senior citizens'.\n\n"
            "RESEARCH — user wants general info about FD/RD products, no calculation. "
            "Signals: tell me about / explain / what is / how does. "
            "Examples: 'What is the difference between FD and RD', 'How does compound interest work'.\n\n"
            "DATABASE — user asks about existing records in the system. "
            "Signals: my account / my FD / show me / list / check status / account number. "
            "Examples: 'Show all active FDs', 'KYC status of account 123456'.\n\n"
            "ONBOARDING — user explicitly wants to open/create/apply for an account RIGHT NOW. "
            "Signals: open an account / create a FD / apply for RD / sign me up / register me. "
            "Note: 'I have 500k to deposit' = ANALYSIS, not ONBOARDING. "
            "Wanting to invest ≠ wanting to apply. When in doubt → ANALYSIS.\n\n"
            "Respond with ONLY one word: ANALYSIS, RESEARCH, DATABASE, or ONBOARDING"
        ),
        expected_output="Single word: ANALYSIS, RESEARCH, DATABASE, or ONBOARDING",
        agent=agents["manager_agent"],
    )