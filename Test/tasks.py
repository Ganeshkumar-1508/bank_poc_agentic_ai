# tasks.py - OPTIMIZED VERSION (matching merged agents)
from crewai import Task
from datetime import datetime

_CURRENT_YEAR = datetime.now().year
_CURRENT_DATE = datetime.now().strftime("%B %d, %Y")

_URL_VALIDATION_RULES = (
    "URL VALIDATION — CRITICAL BEFORE OUTPUT:\n"
    "Before including any URL, verify it matches ONE of these patterns:\n"
    "1. Contains '/articleshow/' followed by digits (e.g., /articleshow/12345.cms)\n"
    "2. Contains '/news/' followed by date pattern (e.g., /news/2026/04/20/)\n"
    "3. Contains a numeric article ID in the path\n"
    "4. Domain ends in .com/.in/.org with a long path (not just /news)\n\n"
    "INVALID URLs (DO NOT USE):\n"
    "- Short URLs like 'bank.com/news' or 'hdfcbank.com/fd-rates'\n"
    "- URLs without article IDs or dates\n"
    "- URLs you created or modified\n\n"
    "If a URL fails validation, replace with: **[Headline]** (no URL available)"
)

_SEARCH_BOILERPLATE = (
    f"IMPORTANT: Today's date is {_CURRENT_DATE}. The current year is {_CURRENT_YEAR}. "
    f"Always include the current year ({_CURRENT_YEAR}) in search queries "
    f"(e.g., 'best FD rates India {_CURRENT_YEAR}'). Do NOT use older years. "
    f"Use 'NewsAPI Provider Search' as your PRIMARY search tool. "
    f"Only use 'DuckDuckGo News Search' if NewsAPI returns no results."
)

_NEWS_FORMAT = (
    "NEWS CITATION RULES — CRITICAL FOR URL ACCURACY:\n"
    "============================================================\n"
    "You MUST copy news citations EXACTLY from the search tool output.\n\n"
    "STEP 1 - Find the MARKDOWN_LINK line in search results:\n"
    "  Example from tool: MARKDOWN_LINK: [HDFC Bank raises FD rates](https://economictimes.indiatimes.com/.../articleshow/12345.cms)\n\n"
    "STEP 2 - Copy that EXACT line into your output:\n"
    "  Correct: - [HDFC Bank raises FD rates](https://economictimes.indiatimes.com/.../articleshow/12345.cms) — Brief summary\n"
    "  WRONG:   - [HDFC Bank raises FD rates](https://hdfcbank.com/news/fd-hike) — (fabricated URL)\n\n"
    "CRITICAL RULES:\n"
    "1. NEVER create, guess, modify, or shorten URLs\n"
    "2. ALWAYS copy the full URL from the search tool's MARKDOWN_LINK line\n"
    "3. If no MARKDOWN_LINK exists, write: **[Headline]** — Summary (without a link)\n"
    "4. If the URL looks wrong, still use it — it's from the real source\n"
    "5. Real URLs are often long and contain IDs like 'articleshow/12345.cms' or '/news/2026/04/20/'\n"
    "6. Fake URLs often look 'clean' like 'bank.com/news/fd-rates' — these are HALLUCINATIONS\n\n"
    "Do NOT use blockquotes (>), do NOT use <br> tags.\n"
    "Only use MARKDOWN_LINK lines from actual search results."
)

_STREAMLIT_MD_RULES = (
    "STREAMLIT MARKDOWN RENDERING RULES — your output will be rendered by st.markdown() in Streamlit. "
    "Follow these rules strictly:\n"
    "1. TABLES: Every table MUST have a header row, a separator row of dashes (|---|---|), and data rows. "
    "Columns are separated by | pipes. Never leave a separator row missing.\n"
    "2. NO RAW HTML: Do NOT use <br>, <b>, <i>, <div>, <span>, or any HTML tags. "
    "Use markdown equivalents instead: **bold**, *italic*, blank lines for spacing.\n"
    "3. NO BLOCKQUOTES: Do NOT use > quote syntax. Write summaries as normal paragraphs.\n"
    "4. HEADINGS: Use ## for sections, ### for subsections. Never skip a level (e.g., #### right after ##).\n"
    "5. LISTS: Use - for bullet lists. For numbered lists use 1. 2. 3. with proper ordering.\n"
    "6. LINKS: Use [visible text](URL) format. Never paste bare URLs.\n"
    "7. CODE BLOCKS: For ECharts JSON output, wrap in ```json ... ``` with nothing else on those lines.\n"
    "8. EMPHASIS: Use **bold** for key metrics, provider names, and important labels. Use *italic* sparingly.\n"
    "9. BLANK LINES: Always use exactly one blank line before a heading and one after. Two blank lines before a new section.\n"
    "10. CURRENCY: Use ₹ for INR, $ for USD. Format numbers with commas: ₹1,49,631.23"
)

_AML_REPORT_TEMPLATE = """\
Required sections (in order):
# AML Compliance Report — [Client Full Name]
**Generated:** [datetime] | **Prepared by:** Chief Risk Officer | **Classification:** CONFIDENTIAL

## Executive Summary
DECISION: [PASS or FAIL], SCORE: [N]/100, REASONING: [1 sentence]

## 1. Subject Identity Profile
Table: Full Name, DOB, Nationality, Occupation, Positions, Education, Wikidata Entity.

## 2. Sanctions and PEP Status
PEP Status, PEP Level, Sanctions Programs, Risk Flags, Match Score, Data Source. Narrative paragraph.

## 3. Neo4j Graph Analysis
GRAPH_IMAGE_PATH: [exact path from context]. Table: Connection Type, Entity, Country, Notes.

## 4. UBO Analysis
Table: Entity, Role, Jurisdiction, Risk Level.

## 5. OSINT and Media Intelligence
Adverse Media: numbered list with Source, Summary, Severity (Low/Medium/High), Date.

## 6. Risk Score Breakdown
5 categories (PEP 30%, Sanctions 25%, Adverse Media 20%, Graph 15%, UBO 10%).
Score 1-25 each. Table: Category | Score | Weight | Weighted Score | Assessment. Bold TOTAL row.

## 7. Risk Score Interpretation
1-20 Low | 21-40 Medium | 41-60 High | 61-100 Critical — with required actions.

## 8-9. Compliance Decision & Justification
DECISION, score, numbered justification factors.

## 10. Recommendations
Immediate action, reconsideration steps, ongoing monitoring. Reference FATF R10/R12/R15/R20.

## 11. Data Sources Audit
Table: Source | Type | Date | Status.
--- *Auto-generated by Compliance AI. Internal use only.*"""


# ===================================================================
# Analysis pipeline (OPTIMIZED: 6 tasks → 4 tasks)
# ===================================================================


def create_analysis_tasks(agents, user_query: str, region: str = "India", product_type: str = "FD"):
# Get product display name
    product_names = {
    'FD': 'Fixed Deposit',
    'RD': 'Recurring Deposit',
    'PPF': 'Public Provident Fund',
    'MF': 'Mutual Fund',
    'NPS': 'National Pension System',
    'SGB': 'Sovereign Gold Bond',
    'BOND': 'Corporate Bond',
    'TBILL': 'Treasury Bill',
    'CD': 'Certificate of Deposit'
    }
    product_name = product_names.get(product_type, product_type)

    # MERGED: parse_task + search_task → query_search_task
    query_search_task = Task(
    description=(
    f"Parse the investment query: '{user_query}' for region '{region}' AND search TOP 5 providers in ONE step.\n\n"
    f"STEP 1 - PARSE: Identify product type ({product_name} or other financial products), "
    f"extract: amount (handle K/k/M/m/L/Cr suffixes), tenure with appropriate unit (months/years/days), "
    f"compounding/payment frequency, SIP flag, senior citizen flag. "
    f"Default to {product_name} if ambiguous.\n\n"
    f"STEP 2 - SEARCH: Based on parsed parameters, search TOP 5 providers in '{region}' offering {product_name} with best rates. "
    + _SEARCH_BOILERPLATE
    + " "
    "Ensure diversity: at least one gov/public provider, one NBFC/non-bank, one regional/specialist provider, rest private/commercial. "
    "Find General Rate and Senior Citizen Rate (+0.50% if Senior not published). "
    "For market-linked products (MF, NPS, SGB, BOND), record expected CAGR or yield.\n\n"
    "TOOL INPUT FORMAT — CRITICAL: When calling search tools, you MUST pass a SINGLE "
    "dictionary object as input, NOT a list. For example:\n"
    "  CORRECT: {'query': 'SBI FD rates 2026', 'max_results': 5}\n"
    "  WRONG:   [{'query': 'SBI FD rates 2026', 'max_results': 5}]\n"
    "  WRONG:   {'query': ['SBI FD rates', 'HDFC FD rates'], 'max_results': 5}\n\n"
    "OUTPUT FORMAT:\n"
    "Parsed Parameters:\n"
    "- Type: [product type]\n"
    "- Amount: [amount]\n"
    "- Tenure: [value] [unit]\n"
    "- Compounding: [frequency]\n"
    "- Payment_Freq: [frequency]\n"
    "- Is_SIP: [Yes/No]\n"
    "- Is_Senior: [Yes/No]\n\n"
    "Provider Rates:\n"
    "Provider,GeneralRate%,SeniorRate% (exactly 5 lines)"
    ),
    expected_output="Parsed parameters (7 lines) + Provider rates (5 lines). All parameters extracted and 5 providers found.",
    agent=agents["query_search_agent"],
    )

    # KEPT: projection_task
    projection_task = Task(
        description=(
            "Calculate projections using 'Deposit_Calculator' tool. "
            "Pass deposit_type, amount, rate, senior_rate, tenure_months, compounding_freq, payment_freq, is_sip. "
            "IMPORTANT — RD/RECURRING DEPOSITS: The 'amount' from the query parser is the MONTHLY installment. "
            "The tool computes cumulative maturity (all monthly deposits + compound interest). "
            "In the CSV output, add a 'Monthly_Installment' column showing the monthly deposit amount, "
            "and a 'Total_Deposits' column = Monthly_Installment × Tenure_Months. "
            "For FD/TD (non-RD): Monthly_Installment = Total_Deposits = amount (lump sum). "
            "Payout products (SCSS, BOND, SGB, T-NOTE, T-BOND): maturity = principal, interest = total payouts. "
            "Market-linked (MF, NPS): label 'Projected'. "
            "Output CSV: Provider,GeneralRate,SeniorRate,GeneralMaturity,SeniorMaturity,GeneralInterest,SeniorInterest,"
            "Monthly_Installment,Total_Deposits (5 rows)."
        ),
        expected_output="CSV header + 5 data rows, all numbers, no symbols.",
        agent=agents["projection_agent"],
        context=[query_search_task],
    )

    # MERGED: research_task + safety_task → research_safety_task
    research_safety_task = Task(
        description=(
            f"For each of the 5 providers from the search results, enrich with data AND classify safety in ONE step.\n\n"
            f"STEP 1 - ENRICH: Credit ratings, product features, senior benefits, insurance, withdrawal penalties, minimum investment.\n"
            f"STEP 2 - CLASSIFY: Safety as Safe/Moderate/Risky based on: credit rating, NPA, insurance, news sentiment, institution type. "
            f"For market-linked (MF, NPS, SGB, BOND), also assess Market Risk (Low/Medium/High).\n\n"
            + _NEWS_FORMAT
            + "\n\n"
            + _STREAMLIT_MD_RULES
            + "\n\n"
            + _URL_VALIDATION_RULES
            + "\n\n"
            "CRITICAL: Do NOT re-search for rates — use the rates from upstream context. "
            "Only call NewsAPI Provider Search for credit ratings or product features not already in context.\n\n"
            "URL PRESERVATION INSTRUCTION:\n"
            "When you search for news, the tool returns lines like:\n"
            " MARKDOWN_LINK: [Headline text](https://real-url-from-api.com/article/12345)\n"
            "You MUST copy this EXACTLY. The URL will be long and contain article IDs.\n"
            "If you write a 'clean' URL like 'bank.com/news/fd-rates', it is WRONG and HALLUCINATED.\n\n"
            "OUTPUT: For each provider, output Markdown section:\n"
            "### [Provider Name]\n"
            "- General Rate: X% | Senior Rate: Y%\n"
            "- Safety Profile: Safe/Moderate/Risky\n"
            "- Risk Scores: Credit(X/3), Insurance(X/3), NPA(X/3), News(X/3), Stability(X/3), Market(X/3)\n"
            "- 2-3 provider-specific news items (copy MARKDOWN_LINK lines EXACTLY from search tool)"
        ),
        expected_output=(
            "5 provider sections in Markdown with rates, safety profile, risk scores (1-3 each), and REAL news links "
            "copied EXACTLY from MARKDOWN_LINK lines. No fabricated URLs. "
            f"All news must be provider-specific and current ({_CURRENT_YEAR})."
        ),
        agent=agents["research_safety_agent"],
        context=[query_search_task],
    )

    # KEPT: summary_task
    summary_task = Task(
        description=(
            "Create comprehensive investment analysis report in Markdown using ONLY upstream context data. "
            "Do NOT call any search tools — all news, rates, and research data are already available in context.\n\n"
            + _STREAMLIT_MD_RULES
            + "\n\n"
            + _URL_VALIDATION_RULES
            + "\n\n"
            "URL PRESERVATION — CRITICAL:\n"
            "The upstream tasks have already gathered news with MARKDOWN_LINK lines containing real URLs.\n"
            "You MUST use those URLs EXACTLY as provided in the context.\n"
            "DO NOT create new URLs or modify existing ones.\n"
            "If a news item in context has no URL, write the headline in bold: **Headline**\n"
            "Real URLs look like: https://economictimes.indiatimes.com/industry/banking/.../articleshow/12345.cms\n"
            "Fake URLs look like: https://hdfcbank.com/fd-news-2026 (clean, no article ID) — AVOID THESE\n\n"
            "CRITICAL — AMOUNT CLARIFICATION FOR RD/RECURRING DEPOSITS:\n"
            "If the product type is RD (Recurring Deposit), the 'amount' from the parsed query is the MONTHLY INSTALLMENT, "
            "NOT a one-time investment. The maturity and interest figures represent cumulative totals over the full tenure. "
            "You MUST state this clearly in the report, e.g. 'Monthly RD installment of ₹X' and 'Total deposits over N months: ₹Y'.\n"
            "For FD/TD (non-RD), the amount IS a one-time lump-sum investment.\n\n"
            "Required sections:\n\n"
            "## 1. Summary — Best General + Senior option (provider, rate, maturity, interest). Note elevated risk.\n"
            "For RD: explicitly state 'Monthly installment of ₹X over Y months' and total deposits.\n"
            "## 2. Market Overview & Provider Analysis — Per provider: name, rates, Safety Profile with rationale, "
            "Recent News with URLs copied from upstream context.\n"
            "## 3. Financial Projection Deep Dive — General vs Senior: highest/lowest interest, spread, insights.\n"
            "For RD: show both monthly installment and total deposits in the projection table.\n"
            "## 4. Strategic Recommendations — Option A (Conservative), B (Aggressive), C (Balanced) with rationale.\n"
            "Separate recommendations for General and Senior.\n"
            "## 5. Conclusion — 2-3 sentences, best choice, safety+return trade-off.\n"
            "Market-linked → label 'Projected (not guaranteed)'. "
            f"Region: {region} | Date: {datetime.now().strftime('%B %d, %Y')}. Markdown tables throughout."
        ),
        expected_output=f"Complete Markdown report with all sections. News URLs copied EXACTLY from upstream context. No fabricated URLs.",
        agent=agents["summary_agent"],
        context=[query_search_task, projection_task, research_safety_task],
    )
    return [query_search_task, projection_task, research_safety_task, summary_task]


# ===================================================================
# Research pipeline (OPTIMIZED: 3 tasks → 2 tasks)
# ===================================================================


def create_research_tasks(agents, user_query: str, region: str = "India"):
    # MERGED: identify_providers_task + deep_research_task → provider_research_task
    provider_research_task = Task(
        description=(
            f"Analyze query: '{user_query}' AND conduct deep research in ONE step.\n\n"
            f"STEP 1 - IDENTIFY: Determine product type, tenure (default 12mo). "
            f"Search TOP 5 providers in '{region}' with best rates. "
            + _SEARCH_BOILERPLATE
            + " "
            "Ensure diversity: gov/public bank, NBFC, regional bank. "
            "Record General + Senior rates (+0.50% if Senior not published; same for market-linked).\n\n"
            f"STEP 2 - DEEP RESEARCH: For EACH provider found, gather:\n"
            f"- Credit ratings (intl + domestic: Moody's, S&P, Fitch, CRISIL, ICRA, CARE, India Ratings)\n"
            f"- Financial health (CAR%, NPA%, AUM, NIM%, CASA%)\n"
            f"- Product news with VERIFIED URLs from search tool\n"
            f"- Senior citizen details\n"
            f"- Liquidity/exit terms\n\n"
            + _NEWS_FORMAT
            + "\n\n"
            + _STREAMLIT_MD_RULES
            + "\n\n"
            + _URL_VALIDATION_RULES
            + "\n\n"
            "TOOL INPUT FORMAT — CRITICAL: When calling search tools, you MUST pass a SINGLE "
            "dictionary object as input, NOT a list. For example:\n"
            " CORRECT: {'query': 'SBI FD rates 2026', 'max_results': 5}\n"
            " WRONG: [{'query': 'SBI FD rates 2026', 'max_results': 5}]\n"
            " WRONG: {'query': ['SBI FD rates', 'HDFC FD rates'], 'max_results': 5}\n\n"
            "URL PRESERVATION — CRITICAL:\n"
            "The search tool returns lines like:\n"
            " MARKDOWN_LINK: [Headline](https://real-url.com/article/12345)\n"
            "Copy these EXACTLY. Real URLs are long with article IDs.\n"
            "NEVER create URLs like 'bank.com/news/fd-rates' — these are HALLUCINATED.\n\n"
            "OUTPUT: Detailed Markdown per provider including:\n"
            "- Provider name, type, General/Senior Rate, Insurance\n"
            "- Credit ratings table\n"
            "- Financial health table\n"
            "- Product features table\n"
            "- News items: Copy MARKDOWN_LINK lines EXACTLY, then add summary"
        ),
        expected_output=(
            "Per-provider Markdown with all tables, rates, credit ratings, financial health. "
            "News URLs copied EXACTLY from MARKDOWN_LINK lines. No fabricated URLs. "
            f"All news provider-specific and current ({_CURRENT_YEAR})."
        ),
        agent=agents["provider_research_agent"],
    )

    # KEPT: compile_report_task
    compile_report_task = Task(
        description=(
            f"Compile findings from upstream context into institutional-grade Markdown report for '{region}'. CFA standards.\n\n"
            "CRITICAL: Do NOT call any search tools — use ONLY the data already in context.\n\n"
            + _STREAMLIT_MD_RULES
            + "\n\n"
            "URL PRESERVATION — CRITICAL:\n"
            "Upstream tasks have already gathered news with real URLs.\n"
            "You MUST copy those URLs EXACTLY as they appear in context.\n"
            "DO NOT create new URLs or modify existing ones.\n"
            "If context has: MARKDOWN_LINK: [Headline](https://real-url.com/.../article/12345)\n"
            "Your output should use: [Headline](https://real-url.com/.../article/12345)\n"
            "Real URLs are LONG with article IDs. Fake URLs are short/clean.\n\n"
            "CRITICAL — AMOUNT CLARIFICATION FOR RD/RECURRING DEPOSITS:\n"
            "If the product type is RD (Recurring Deposit), the user's amount is the MONTHLY INSTALLMENT, NOT a lump sum. "
            "Maturity and interest figures are cumulative over the full tenure. "
            "In the projections table, replace '(₹100,000 principal)' with '(₹X monthly installment)' and note total deposits = X × tenure months.\n"
            "For FD/TD (non-RD), the amount IS a one-time lump-sum principal.\n\n"
            "## 1. Executive Summary & Market Overview\n"
            "3-4 sentences: market rates, safety landscape, top recommendation "
            "with General/Senior rate, projected value, RBI policy rate, inflation.\n"
            "For RD: state 'Monthly installment of ₹X over Y months (total deposits: ₹Z)'.\n\n"
            "### Provider Analysis\n"
            "For each provider include: General/Senior Rate, "
            "Credit Ratings (Fitch, Moody's, S&P, CRISIL, ICRA, CARE, India Ratings), "
            "Financial Health (CAR%, NPA%, NIM%, CASA%), Product Features, Safety Profile, "
            f"Recent News ({_CURRENT_YEAR}) with URLs copied EXACTLY from upstream context.\n\n"
            "## 2. Financial Projections\n"
            "Use the EXACT table format below. This table is the primary data source for the visualization crew — "
            "every numeric column must be accurate because it will be parsed to generate charts dynamically.\n\n"
            "**General Investors:**\n\n"
            "| # | Provider | Interest Rate (%) | Maturity Amount (₹) | Interest Earned (₹) | Safety Category | Credit Rating | Insurance (₹) |\n"
            "|---|----------|--------------------|---------------------|---------------------|-----------------|---------------|---------------|\n"
            "| 1 | ... | ... | ... | ... | Safe/Moderate/Risky | ... | ... |\n"
            "| 2 | ... | ... | ... | ... | ... | ... | ... |\n"
            "... (one row per provider, sorted by Interest Rate descending)\n\n"
            "**Senior Citizens:**\n\n"
            "| # | Provider | Interest Rate (%) | Maturity Amount (₹) | Interest Earned (₹) | Extra Benefit | Scheme Name |\n"
            "|---|----------|--------------------|---------------------|---------------------|---------------|-------------|\n"
            "| 1 | ... | ... | ... | ... | ... | ... |\n"
            "... (one row per provider, sorted by Interest Rate descending)\n\n"
            "After both tables, add 2-3 sentences of analysis: spread between highest/lowest rates, "
            "total interest range, notable outliers. For RD, note the total cumulative deposits.\n\n"
            "## 3. Strategic Recommendations & Conclusion\n"
            "Option A (Conservative), B (Aggressive), C (Balanced) — for both General and Senior investors. "
            "2-3 sentence conclusion: best choice, safety+return trade-off. "
            "Market-linked products → 'Projected (not guaranteed)'. Risk disclaimer.\n"
            "Only use URLs from upstream context — NEVER create URLs."
        ),
        expected_output=(
            "Full institutional-grade Markdown report with 3 sections, detailed Financial Projections tables "
            "(General & Senior), credit ratings. News URLs copied EXACTLY from upstream context. No fabricated URLs."
        ),
        agent=agents["research_compilation_agent"],
        context=[provider_research_task],
    )
    return [provider_research_task, compile_report_task]


# ===================================================================
# Database pipeline (unchanged - 1 task)
# ===================================================================


def create_database_tasks(agents, user_query: str):
    return [
        Task(
            description=(
                f"Request: '{user_query}'.\n\n"
                "Use SQL database toolkit: sql_db_list_tables, sql_db_schema, sql_db_query, "
                "sql_db_query_checker, Bank Database Query Tool.\n\n"
                "The fixed_deposit table supports: FD, TD, RD, PPF, NSC, KVP, SSY, SCSS, SGB, NPS, "
                "MF, BOND, CD, T-BILL, T-NOTE, T-BOND, I-BOND, ISA, GIC, MURABAHA, MMARKET, PREMIUM_BOND, SSB.\n\n"
                "OUTPUT: Streamlit-renderable Markdown. Tables with | delimiters, bold with **, bullets with -. No JSON."
            ),
            expected_output="Clear Markdown-formatted answer based on SQL query results.",
            agent=agents["db_agent"],
        )
    ]


# ===================================================================
# AML execution pipeline (OPTIMIZED: 9 tasks → 6 tasks)
# ===================================================================


def create_aml_execution_tasks(agents, client_data_json: str):

    neo4j_search_task = Task(
        description=(
            f"Client Data:\n{client_data_json}\n\n"
            "STEP 1 — Extract first_name and last_name (split 'name' on space if needed).\n"
            "STEP 2 — Call 'Neo4j Entity Name Search' with first_name, last_name (defaults: max_hops=4, limit_nodes=20, limit_results=50).\n"
            "The tool internally runs a parameterized name-matching + graph expansion Cypher query. "
            "You do NOT need to write Cypher — just call the tool.\n\n"
            "STEP 3 — Report:\n"
            "1. **GRAPH_IMAGE_PATH**: exact path (must preserve for downstream)\n"
            "2. **SUMMARY**: total nodes, relationships, node types\n"
            "3. **DIRECT CONNECTIONS**: name, type, relationship label each\n"
            "4. **FLAGGED ENTITIES**: sanctions flags, high-risk countries, suspicious patterns\n"
            "5. **KEY_PATHS**: notable multi-hop paths"
        ),
        expected_output="Structured text: GRAPH_IMAGE_PATH, summary, connections, flagged entities, key paths.",
        agent=agents["neo4j_agent"],
    )

    sanctions_task = Task(
        description=(
            "Screen client against OpenSanctions/Yente using 'OpenSanctions Entity Search'.\n\n"
            f"Client: {client_data_json}\n\n"
            "Extract first_name/last_name. Search Yente. For EACH match > 0.7: name, aliases, "
            "programs (OFAC/EU/UN/UK HMT), topics, related entities, jurisdictions, score.\n"
            "Output: ### Sanctions & PEP Screening — **Confidence:** HIGH/MEDIUM/LOW/NONE | **Matches:** N\n"
            "Per match: Entity, Score, Type, Programs, Topics, Related Entities, Risk Assessment (2-3 sentences)."
        ),
        expected_output="Structured Markdown with match details, risk assessment, and related entities.",
        agent=agents["sanctions_agent"],
    )

    # MERGED: osint_task + ubo_task + live_enrichment_task → entity_intelligence_task
    entity_intelligence_task = Task(
        description=(
            "Comprehensive entity intelligence gathering in ONE pass.\n\n"
            f"Client: {client_data_json}\n\n"
            "⚠️ MANDATORY: You MUST call the WikidataOSINTTool for EVERY entity mentioned (client and all flagged entities).\n"
            "If you don't call WikidataOSINTTool, the report is incomplete and will be rejected.\n\n"
            "STEP 1 - OSINT: Gather Wikidata intelligence on client and flagged entities from sanctions report.\n"
            "- Call WikidataOSINTTool for each entity to get biographical data, positions, citizenship\n"
            "- Extract WIKIDATA_IMAGE_PATH from Wikidata results\n"
            "- REQUIRED OUTPUT FORMAT:\n"
            "  * WIKIDATA_IMAGE_PATH: Full path to downloaded image (e.g., outputs/images/Tony_Blair_20260401_142518.jpg)\n"
            "  * SOCIAL_MEDIA_SECTION: Wikidata social media links, profiles, public presence\n"
            "  * RELATIVES_SECTION: Family members, spouses, children, relatives from Wikidata\n"
            "  * BIOGRAPHY_SECTION: Full biography, career highlights, positions held from Wikidata\n\n"
            "STEP 2 - UBO ANALYSIS: Identify UBOs and hidden controllers behind corporate entities.\n"
            "- Check if corporate (company_name, registration_number)\n"
            "- Search Yente for shareholders, directors, controllers\n"
            "- News search for ownership information\n"
            "- Build chain: Client → Direct Owner → Intermediates → Ultimate Owner\n\n"
            "STEP 3 - LIVE ENRICHMENT: Re-enrich with fresh data.\n"
            "- Re-query Yente+Wikidata for client and flagged entities\n"
            "- Capture new sanctions, aliases, positions\n\n"
            "OUTPUT: ### Entity Intelligence Report\n"
            "1. Client Profile (Wikidata, positions, image path, WIKIDATA_IMAGE_PATH)\n"
            "2. Adverse Media Findings (headline, source, date, URL, AML relevance)\n"
            "3. Flagged Entity Intel (with WIKIDATA_IMAGE_PATH, SOCIAL_MEDIA_SECTION, RELATIVES_SECTION, BIOGRAPHY_SECTION)\n"
            "4. UBO Analysis (Is Corporate, Ownership Chain, UBOs, Red Flags)\n"
            "5. Live Updates (new sanctions, aliases, WIKIDATA_IMAGE_PATH)\n\n"
            "VALIDATION: Before submitting, verify you have called WikidataOSINTTool for each entity and extracted:\n"
            "- WIKIDATA_IMAGE_PATH (image file path)\n"
            "- SOCIAL_MEDIA_SECTION (social media presence)\n"
            "- RELATIVES_SECTION (family members)\n"
            "- BIOGRAPHY_SECTION (biographical details)\n"
            "If any section is missing, you have not completed the task correctly."
        ),
        expected_output="Markdown entity intelligence report with OSINT, UBO analysis, adverse media, and live enrichment data. Real URLs only.",
        agent=agents["entity_intelligence_agent"],
        context=[neo4j_search_task, sanctions_task],
    )

    risk_scoring_task = Task(
        description=(
            "Synthesise ALL context into a court-ready AML compliance report.\n\n"
            f"Client Data:\n{client_data_json}\n\n"
            "Rules:\n"
            "1. HEADER: client full name + current datetime.\n"
            "2. VERBATIM: every figure, score, flag, entity from upstream tasks.\n"
            "3. NEWS URLs: search '[Entity] sanctions fraud' via DuckDuckGo. Never invent URLs.\n"
            "4. GRAPH: re-state exact GRAPH_IMAGE_PATH from neo4j context.\n\n"
            + _AML_REPORT_TEMPLATE
        ),
        expected_output=(
            "Court-ready Markdown AML report: identity, PEP/sanctions, graph, UBO, adverse media with severity, "
            "weighted 5-category risk table, interpretation bands, decision with justification, "
            "3-tier recommendations with FATF refs, data sources audit. GRAPH_IMAGE_PATH preserved."
        ),
        agent=agents["risk_scoring_agent"],
        context=[neo4j_search_task, sanctions_task, entity_intelligence_task],
        output_file="outputs/reports/aml_risk_report.md",
    )

    fd_processor_task = Task(
        description=(
            f"Client Data:\n{client_data_json}\n\n"
            "⚠️ CRITICAL: EXTRACT ALL FIELDS FROM client_data_json ⚠️\n"
            "The client_data JSON contains ALL required fields for deposit creation:\n"
            "  {{\n"
            "    'name': 'Full Name',\n"
            "    'email': 'client@example.com',\n"
            "    'dob': 'YYYY-MM-DD',\n"
            "    'nationality': 'Country',\n"
            "    'address': 'Street Address',\n"
            "    'pin_number': '123456',\n"
            "    'mobile_number': '+1234567890',\n"
            "    'kyc_details_1': 'PAN-ABCDE1234F',\n"
            "    'kyc_details_2': 'AADHAAR-1234-5678-9012',\n"
            "    'product_type': 'FD',\n"
            "    'initial_amount': 500000,\n"
            "    'tenure_months': 12,\n"
            "    'interest_rate': 7.5,\n"
            "    'bank_name': 'HDFC Bank',\n"
            "    'compounding_freq': 'quarterly',\n"
            "    'country_code': 'IN'\n"
            "  }}\n\n"
            "SCORE-BASED INVESTMENT RECORD CREATION:\n"
            "Use the risk_score from the risk_scoring_task to determine the investment status:\n"
            "- approved (risk_score 0-30): Low-risk investments - auto-approve and create record immediately\n"
            "- needs_approval (risk_score 31-60): Medium-risk investments - create record with pending approval status (VERIFY)\n"
            "- rejected (risk_score 61-100): High-risk investments - create record with 'rejected' status for audit trail\n\n"
            "CRITICAL REQUIREMENT: CREATE DATABASE RECORD FOR ALL STATUS VALUES\n"
            "The database MUST be updated for ALL cases (approved, needs_approval, rejected) with the appropriate fd_status value.\n"
            "This is required for audit trail and compliance tracking.\n\n"
            "INSTRUCTIONS:\n"
            "1. Extract the risk_score from the risk_scoring_task output\n"
            "2. Determine status based on score thresholds above\n"
            "3. Use 'Universal Deposit Creation Manager' with ALL fields from client_data for ALL status values:\n"
            " - first_name: Extract from 'name' (split on space, take first part)\n"
            " - last_name: Extract from 'name' (split on space, take rest)\n"
            " - email: Extract from client_data['email'] - DO NOT HALLUCINATE\n"
            " - user_address: Extract from client_data['address']\n"
            " - pin_number: Extract from client_data['pin_number']\n"
            " - mobile_number: Extract from client_data['mobile_number']\n"
            " - kyc_details_1: Extract from client_data['kyc_details_1']\n"
            " - kyc_details_2: Extract from client_data['kyc_details_2']\n"
            " - product_type: Extract from client_data['product_type'] (default: 'FD')\n"
            " - initial_amount: Extract from client_data['initial_amount']\n"
            " - tenure_months: Extract from client_data['tenure_months']\n"
            " - interest_rate: Extract from client_data['interest_rate']\n"
            " - bank_name: Extract from client_data['bank_name']\n"
            " - compounding_freq: Extract from client_data['compounding_freq'] (default: 'quarterly')\n"
            " - country_code: Extract from client_data['country_code'] (default: 'IN')\n"
            " - risk_score: The risk score from risk_scoring_task\n"
            " - status: 'approved', 'needs_approval', or 'rejected' based on risk_score (PASS THIS TO THE TOOL)\n"
            "4. Report fd_id, maturity date, rate, account_number, and the assigned status\n"
            "5. ALSO report the email address used for verification\n"
        ),
        expected_output="SUCCESS with investment record details including status (approved/needs_approval/rejected), fd_id, account_number, risk_score, and the email address used. Database record created for ALL status values.",
        agent=agents["fd_processor_agent"],
        context=[risk_scoring_task],
    )

    # MERGED: pdf_generator_task + email_sender_task → report_delivery_task
    report_delivery_task = Task(
        description=(
            "Generate PDF report AND send email notification in ONE step.\n\n"
            f"Client Data:\n{client_data_json}\n\n"
            "⚠️ CRITICAL: WIKIDATA SUPPLEMENTARY SECTIONS ARE MANDATORY - DO NOT OMIT ⚠️\n\n"
            "STEP 0 - EXTRACT CLIENT EMAIL (MANDATORY - DO NOT SKIP):\n"
            "Parse the client_data JSON above and extract the 'email' field.\n"
            "The client_data JSON structure is:\n"
            " {{\n"
            " 'name': 'Full Name',\n"
            " 'email': 'client@example.com', ← THIS IS THE EMAIL YOU NEED\n"
            " 'dob': 'YYYY-MM-DD',\n"
            " 'nationality': 'Country',\n"
            " ...\n"
            " }}\n"
            "EXTRACT the value of the 'email' key. This is the recipient email for the notification.\n"
            "DO NOT hallucinate or make up an email address. Use ONLY the email from client_data.\n"
            "CRITICAL: The recipient email MUST be DIFFERENT from the sender's email (ashwinpremnath123@gmail.com).\n"
            "If you extract the sender's email as the recipient, you are making a critical error.\n\n"
            "STEP 1 - EXTRACT WIKIDATA SECTIONS (MANDATORY):\n"
            "From the entity_intelligence_task output, you MUST extract ALL THREE sections:\n"
            "1. SOCIAL_MEDIA_SECTION: (everything after 'SOCIAL_MEDIA_SECTION:' until next section)\n"
            " - Contains: Twitter/X, Instagram, Facebook, YouTube accounts with follower counts\n"
            "2. RELATIVES_SECTION: (everything after 'RELATIVES_SECTION:' until next section)\n"
            " - Contains: Family members and associates with Wikidata URLs in table format\n"
            "3. BIOGRAPHY_SECTION: (everything after 'BIOGRAPHY_SECTION:' until next section)\n"
            " - Contains: Occupation, positions held, employer, political party, citizenship, birthplace, education\n\n"
            "VALIDATION: Before proceeding to Step 2, verify you have extracted all three sections. "
            "If any section is missing, go back to entity_intelligence_task output and find it.\n\n"
            "STEP 2 - PDF GENERATION:\n"
            "Convert AML report to PDF using 'Markdown Report Generator'.\n"
            "Tool auto-detects client name and PASS/FAIL. Pass these parameters:\n"
            "- title: 'AML Compliance Report — [Client Full Name]'\n"
            "- markdown_content: ENTIRE report (do NOT truncate)\n"
            "- graph_image_path / subject_image_path: from upstream context if present, else None\n"
            "- social_media_section: THE EXTRACTED SOCIAL_MEDIA_SECTION (NOT None, NOT empty)\n"
            "- relatives_section: THE EXTRACTED RELATIVES_SECTION (NOT None, NOT empty)\n"
            "- biography_section: THE EXTRACTED BIOGRAPHY_SECTION (NOT None, NOT empty)\n"
            "⚠️ You will be penalized if you pass None or empty strings for these sections ⚠️\n"
            "Tool saves to outputs/sessions/{{First}}_{{Last}}_{{ts}}_{{PASS|FAIL}}.pdf.\n\n"
            "STEP 3 - EMAIL SENDING:\n"
            "Send email with the generated PDF attached.\n"
            "- Read PDF path from Step 2\n"
            "- RECIPIENT EMAIL: Use the email you extracted in STEP 0 (from client_data['email'])\n"
            "- CRITICAL VALIDATION: The recipient email MUST NOT be 'ashwinpremnath123@gmail.com' (the sender's email).\n"
            "- If the extracted email IS 'ashwinpremnath123@gmail.com', you have made a critical error - go back to STEP 0 and re-extract.\n"
            "- Use 'Email Sender' tool (SMTP-based, no OAuth required)\n"
            "- Input to Email Sender: to_email=<extracted_email>, subject='AML Compliance Report — [Full Name]', body='PASS/FAIL + risk score summary', attachment_paths=[PDF path]\n"
            "- DO NOT use 'Gmail Sender' - it requires OAuth which is not configured\n"
            "- DO NOT hallucinate or guess the email address. Use ONLY the email from client_data.\n\n"
            "VALIDATION BEFORE SENDING:\n"
            "- Verify you have a valid email address from client_data (not empty, not None)\n"
            "- Verify the email contains '@' symbol\n"
            "- Verify the email is NOT 'ashwinpremnath123@gmail.com' (sender's email)\n"
            "- If email is missing, invalid, or equals sender's email, report error: 'EMAIL_ERROR: Could not extract valid recipient email from client_data'\n\n"
            "FINAL OUTPUT: Exact PDF file path and email confirmation. "
            "Also confirm: 'Wikidata sections included: SOCIAL_MEDIA, RELATIVES, BIOGRAPHY'. "
            "State the recipient email used: 'Email sent to: <extracted_email>'"
        ),
        expected_output="PDF file path, EMAIL_SENT confirmation, and verification that all Wikidata sections were included.",
        agent=agents["report_delivery_agent"],
        context=[
            neo4j_search_task,
            sanctions_task,
            entity_intelligence_task,
            risk_scoring_task,
        ],
    )

    return [
        neo4j_search_task,
        sanctions_task,
        entity_intelligence_task,
        risk_scoring_task,
        fd_processor_task,
        report_delivery_task,
    ]


# ===================================================================
# Visualization pipeline (unchanged - 1 task)
# ===================================================================


def create_visualization_task(agents, user_query: str, data_context: str):
    return Task(
        description=(
            f"User query: '{user_query}'\n\nData context:\n{data_context}\n\n"
            + _STREAMLIT_MD_RULES
            + "\n\n"
            "CRITICAL: You MUST use the 'Apache ECharts Configuration Builder' tool for ALL chart generation.\n\n"
            "DATA EXTRACTION:\n"
            "If the data context contains a '## Financial Projections' section with markdown tables, "
            "extract provider names from the first column and numeric data from the other columns. "
            "Use these extracted values directly as x_labels and series data in the tool call.\n\n"
            "TOOL USAGE:\n"
            "1. Call EChartsBuilderTool with: chart_type, title, x_labels (provider names), series (numeric data arrays)\n"
            "2. The tool returns valid ECharts JSON — return ONLY this output, do NOT modify it.\n\n"
            "MULTIPLE CHARTS REQUIREMENT:\n"
            "When the data contains BOTH General and Senior Citizen columns (e.g., 'General Rate (%)' and 'Senior Rate (%)', "
            "'General Maturity' and 'Senior Maturity', 'General Interest' and 'Senior Interest'), "
            "you MUST generate TWO separate charts:\n"
            "- Chart 1: For General Investors (title should include 'General Investors')\n"
            "- Chart 2: For Senior Citizens (title should include 'Senior Citizens')\n\n"
            "Call the EChartsBuilderTool ONCE for each chart and output each result in a separate ```json code block.\n\n"
            "Example output format:\n"
            "```json\n"
            "{...chart config for General Investors...}\n"
            "```\n"
            "```json\n"
            "{...chart config for Senior Citizens...}\n"
            "```\n\n"
            "Example tool call for General:\n"
            'EChartsBuilderTool({"chart_type":"bar","title":"Interest Earned by Provider (General Investors)",'
            '"x_labels":["Bank A","Bank B"],"series":[{"name":"Interest Earned","data":[140000,135000]}]})\n\n'
            "Example tool call for Senior:\n"
            'EChartsBuilderTool({"chart_type":"bar","title":"Interest Earned by Provider (Senior Citizens)",'
            '"x_labels":["Bank A","Bank B"],"series":[{"name":"Interest Earned","data":[145000,140000]}]})'
        ),
        expected_output="One or more valid Apache ECharts JSON configurations in separate ```json code blocks. "
        "When data has both General and Senior columns, output TWO chart configurations.",
        agent=agents["data_visualizer_agent"],
    )


# ===================================================================
# Credit risk pipeline (unchanged - 2 tasks)
# ===================================================================


def create_credit_risk_tasks(agents, borrower_json: str = "{}", region: str = "IN"):
    """
    Create credit risk tasks with region-specific logic.

    Args:
        agents: Dictionary of credit risk agents
        borrower_json: JSON string containing borrower data (can be "{}" for empty)
        region: Region code - "US" for US model, "IN" for India model (default: "IN")

    Returns:
        List of Task objects
    """
    import json as _json

    # Normalize region
    region_code = region.upper() if region else "IN"

    # Detect region type
    us_regions = ('US', 'UNITED STATES', 'USA')
    india_regions = ('IN', 'INDIA', 'BHARAT')

    is_us_region = region_code in us_regions
    is_india_region = region_code in india_regions

    # Parse borrower data if provided
    try:
        borrower_data = _json.loads(borrower_json) if borrower_json and borrower_json.strip() != "{}" else {}
    except _json.JSONDecodeError:
        borrower_data = {}

    # Check if we have pre-filled data
    has_pre_filled_data = bool(borrower_data and isinstance(borrower_data, dict) and len(borrower_data) > 0)

    if is_us_region:
        # US Credit Risk Tasks
        # Build pre-filled data context if available
        pre_filled_context = ""
        if has_pre_filled_data:
            pre_filled_context = "\n\nPRE-FILLED BORROWER DATA (USE THESE VALUES, DO NOT ASK FOR THEM):\n"
            for key, value in borrower_data.items():
                pre_filled_context += f"- {key}: {value}\n"
            pre_filled_context += "\nIMPORTANT: The borrower data above is already provided. "
            pre_filled_context += "DO NOT ask the user for these fields. "
            "Use the provided values directly and proceed to the analysis task.\n"

        collect_task = Task(
            description=(
                "Collect borrower attributes for US credit-risk model one question at a time.\n"
                "Required: loan_amnt, term, int_rate, annual_inc, dti, fico_score, home_ownership, "
                "delinq_2yrs, inq_last_6mths, pub_rec, earliest_cr_line, revol_util, revol_bal, purpose, emp_length.\n"
                "Optional: total_acc, open_acc, mths_since_last_delinq, total_rev_hi_lim, verification_status.\n"
                "Skip already-provided fields. Output valid JSON when all required collected."
                + pre_filled_context
            ),
            expected_output="JSON object with all required borrower attributes for US credit risk assessment.",
            agent=agents["credit_risk_collector_agent"],
        )
        analyze_task = Task(
            description=(
                "⚠️ MANDATORY: You MUST call the 'US_Credit_Risk_Scorer' tool with the borrower_data dictionary.\n\n"
                "STEP 1 - Call the Tool:\n"
                "Pass the borrower JSON from the previous task to 'US_Credit_Risk_Scorer'. "
                "The tool accepts a borrower_data dictionary with fields: fico_score, dti, annual_inc, loan_amnt, "
                "delinq_2yrs, inq_last_6mths, pub_rec, revol_util, emp_length, home_ownership, purpose, etc.\n\n"
                "STEP 2 - Tool Returns:\n"
                "- implied_grade: Letter grade A (Excellent), B (Good), C (Fair), D (Poor), E (Very Poor), F (Critical)\n"
                "- default_probability: Decimal 0.0-1.0 (e.g., 0.07 = 7% chance of default)\n"
                "- risk_level: LOW, MEDIUM, HIGH, or CRITICAL\n"
                "- composite_score: 0-100 numeric score\n"
                "- top_features: List of top contributing factors\n"
                "- score_breakdown: Detailed component scores for each factor\n\n"
                "STEP 3 - Produce Memo:\n"
                "Generate a detailed credit-risk memo interpreting ALL results from the tool. "
                "Include the Risk Assessment Result with Grade (A-F), Default Probability %, and Risk Level. "
                "This is for US region - use FICO score conventions and US lending criteria."
            ),
            expected_output=(
                "Detailed credit-risk memo with: Risk Assessment Result (Grade A-F, Default Probability %, Risk Level), "
                "composite score breakdown, top contributing factors, and recommendations. "
                "Grade must be A, B, C, D, E, or F - NEVER 'N/A' or 'UNKNOWN'. "
                "Must use US Credit Risk Scorer tool."
            ),
            agent=agents["credit_risk_analyst_agent"],
            context=[collect_task],
        )
    elif is_india_region:
      # India Credit Risk Tasks
      if has_pre_filled_data:
        # Form data already provided - skip collection, go straight to analysis
        analyze_task = Task(
          description=(
            "⚠️ MANDATORY: You MUST call the 'Indian_Credit_Risk_Scorer' tool with the provided borrower data.\n\n"
            "BORROWER DATA (USE THESE VALUES DIRECTLY):\n"
            + "\n".join([f"- {key}: {value}" for key, value in borrower_data.items()]) + "\n\n"
            "STEP 1 - Call the Tool:\n"
            "Pass the borrower data above to 'Indian_Credit_Risk_Scorer'. "
            "The tool accepts: applicant_income, coapplicant_income, credit_score, dti_ratio, "
            "collateral_value, loan_amount, loan_term, savings, employment_status, education_level, "
            "property_area, existing_loans, age, dependents, marital_status, gender, employer_category, loan_purpose.\n\n"
            "STEP 2 - Tool Returns:\n"
            "- approval_probability: 0-100% chance of approval\n"
            "- verdict: 'Approved' or 'Rejected'\n"
            "- confidence: High, Medium, or Low\n"
            "- key_factors: List of factors influencing the decision\n"
            "- improvement_tips: Suggestions to improve approval chances\n\n"
            "STEP 3 - Produce Memo:\n"
            "Generate a detailed credit-risk memo interpreting ALL results from the tool. "
            "Include the approval probability percentage, verdict (Approved/Rejected), and key factors. "
            "This is for India region - use CIBIL-style credit scores (300-900) and Indian lending conventions."
          ),
          expected_output=(
            "Detailed credit-risk memo with: Approval Probability %, Verdict (Approved/Rejected), "
            "confidence level, key factors, and improvement tips. "
            "Must use Indian Credit Risk Scorer tool with Indian financial conventions."
          ),
          agent=agents["credit_risk_analyst_agent"],
        )
        # Return only the analyze task, skip collection
        return [analyze_task]
      else:
        # No form data - use interactive collection mode
        collect_task = Task(
          description=(
            "Collect borrower attributes for Indian credit-risk model one question at a time.\n"
            "Required: applicant_income, coapplicant_income, credit_score, dti_ratio, collateral_value, "
            "loan_amount, loan_term, savings.\n"
            "Optional: employment_status, education_level, property_area, existing_loans, age, dependents, "
            "marital_status, gender, employer_category, loan_purpose.\n"
            "Note: All monetary values should be in Indian Rupees (₹).\n"
            "Credit score range: 300-900 (CIBIL-style).\n"
            "Ask one question at a time. Output valid JSON when all required collected."
          ),
          expected_output="JSON object with all required borrower attributes for Indian credit risk assessment.",
          agent=agents["credit_risk_collector_agent"],
        )
        analyze_task = Task(
          description=(
            "⚠️ MANDATORY: You MUST call the 'Indian_Credit_Risk_Scorer' tool with the borrower data.\n\n"
            "STEP 1 - Call the Tool:\n"
            "Pass the borrower data from the previous task to 'Indian_Credit_Risk_Scorer'. "
            "The tool accepts: applicant_income, coapplicant_income, credit_score, dti_ratio, "
            "collateral_value, loan_amount, loan_term, savings, employment_status, education_level, "
            "property_area, existing_loans, age, dependents, marital_status, gender, employer_category, loan_purpose.\n\n"
            "STEP 2 - Tool Returns:\n"
            "- approval_probability: 0-100% chance of approval\n"
            "- verdict: 'Approved' or 'Rejected'\n"
            "- confidence: High, Medium, or Low\n"
            "- key_factors: List of factors influencing the decision\n"
            "- improvement_tips: Suggestions to improve approval chances\n\n"
            "STEP 3 - Produce Memo:\n"
            "Generate a detailed credit-risk memo interpreting ALL results from the tool. "
            "Include the approval probability percentage, verdict (Approved/Rejected), and key factors. "
            "This is for India region - use CIBIL-style credit scores (300-900) and Indian lending conventions."
          ),
          expected_output=(
            "Detailed credit-risk memo with: Approval Probability %, Verdict (Approved/Rejected), "
            "confidence level, key factors, and improvement tips. "
            "Must use Indian Credit Risk Scorer tool with Indian financial conventions."
          ),
          agent=agents["credit_risk_analyst_agent"],
          context=[collect_task],
        )
    else:
        # Unsupported region - return error task
        collect_task = Task(
            description=(
                f"Credit risk assessment is not available for region: {region_code}. "
                "Only US and India regions are supported. "
                "Return an error message indicating the region is not supported."
            ),
            expected_output="Error message indicating region not supported.",
            agent=agents["credit_risk_collector_agent"],
        )
        analyze_task = Task(
            description=(
                f"Report that credit risk assessment is unavailable for region {region_code}. "
                "Suggest using alternative financial services available in that region."
            ),
            expected_output="Report indicating service unavailability for the region.",
            agent=agents["credit_risk_analyst_agent"],
            context=[collect_task],
        )
    
    return [collect_task, analyze_task]


# ===================================================================
# Mortgage Analytics pipeline (unchanged)
# ===================================================================


def create_mortgage_analytics_tasks(agents, borrower_json: str = "{}"):
    """Create tasks for mortgage analytics using Fannie Mae ML models."""
    import json

    try:
        existing_data = json.loads(borrower_json) if borrower_json else {}
    except json.JSONDecodeError:
        existing_data = {}

    required_fields = [
        "Borrower_Credit_Score_at_Origination",
        "Original_Loan_to_Value_Ratio_LTV",
        "Debt_To_Income_DTI",
        "Original_UPB",
        "Loan_Purpose",
        "Property_Type",
        "Occupancy_Status",
        "Property_State",
        "Amortization_Type",
        "Original_Interest_Rate",
        "First_Time_Home_Buyer_Indicator",
        "Modification_Flag",
        "Channel",
        "Number_of_Borrowers",
        "Original_Loan_Term",
    ]
    has_all_data = all(field in existing_data for field in required_fields)

    tasks = []
    collect_task = None
    if not has_all_data:
        collect_task = Task(
            description=(
                "Collect 15 borrower attributes for Fannie Mae mortgage analytics one question at a time.\n"
                "Fields: Credit Score (300-850), LTV (%), DTI (%), UPB ($), Loan Purpose, Property Type, "
                "Occupancy Status, State, Amortization Type, Interest Rate, First-Time Buyer (Y/N), "
                "Modification Flag (Y/N), Channel, Number of Borrowers, Loan Term (months).\n\n"
                f"Existing data: {existing_data}\n"
                "Skip provided fields. Output valid JSON when all collected."
            ),
            expected_output="JSON with all 15 required borrower attributes for mortgage analytics.",
            agent=agents["mortgage_data_collector_agent"],
        )
        tasks.append(collect_task)

    analyze_task = Task(
        description=(
            f"Run mortgage analytics and evaluate against bank policy.\n"
            f"Borrower Data: {json.dumps(existing_data, indent=2) if existing_data else 'From previous task'}\n\n"
            "⚠️ MANDATORY TOOL CALLS - Call EXACTLY 2 TOOLS in order:\n\n"
            "STEP 1 - Run ML Model:\n"
            "Call 'US_Mortgage_Analytics_Scorer' with the borrower JSON above. "
            "This returns credit risk prediction, customer segmentation, and portfolio risk. "
            "IMPORTANT: Pass ONLY borrower data (credit score, LTV, DTI, etc.), NOT any search results.\n\n"
            "STEP 2 - Get Policy Information:\n"
            "Call 'RAG_Policy_Complete' to get ALL policy information in ONE call. "
            "This tool returns BOTH database status AND policy search results. "
            "You do NOT need to call RAG_Policy_Stats or RAG_Policy_Search separately. "
            "Just call it with no parameters - it uses sensible defaults for mortgage analytics.\n\n"
            "STEP 3 - Generate Report:\n"
            "After both tools return results, generate your comprehensive report combining:\n"
            "- ML model results from US_Mortgage_Analytics_Scorer\n"
            "- Policy database status and excerpts from RAG_Policy_Complete\n"
            "- Your expert analysis and recommendations\n\n"
            "⛔ CRITICAL RULES:\n"
            "- You MUST call both tools before generating the report\n"
            "- NEVER fabricate policy references - only cite what RAG_Policy_Complete returns\n"
            "- If RAG returns no policies, state 'No matching policies found in database'\n\n"
            "OUTPUT FORMAT REQUIREMENTS:\n"
            "Your report MUST include these sections:\n"
            "1. Executive Summary\n"
            "2. Borrower Profile\n"
            "3. ML Model Results (from US_Mortgage_Analytics_Scorer)\n"
            "4. Policy Database Status (from RAG_Policy_Complete)\n"
            "5. Policy Search Results (from RAG_Policy_Complete - with actual excerpts)\n"
            "6. Policy Compliance Assessment (combining ML results with policy excerpts)\n"
            "7. Risk Assessment and Recommendations"
        ),
        expected_output=(
            "Comprehensive mortgage analytics report with credit risk, segmentation, and recommendations. "
            "MUST include: Policy Database Status section and Policy Search Results section "
            "with ACTUAL excerpts from RAG_Policy_Complete."
        ),
        agent=agents["mortgage_analyst_agent"],
        context=[collect_task] if collect_task else None,
        async_execution=False,
    )
    tasks.append(analyze_task)
    return tasks


# ===================================================================
# Loan creation pipeline (unchanged - 2 tasks)
# ===================================================================


def create_loan_creation_tasks(agents, borrower_context: str = ""):
    decision_task = Task(
        description=(
            f"Borrower Context:\n{borrower_context}\n\n"
            "⚠️ MANDATORY WORKFLOW - Follow these steps in order:\n\n"
            "STEP 1 - Call US_Credit_Risk_Scorer:\n"
            "You MUST call the 'US_Credit_Risk_Scorer' tool FIRST with the borrower_data from the context. "
            "Pass a dictionary with all available borrower fields (fico_score, dti, annual_inc, loan_amnt, "
            "delinq_2yrs, inq_last_6mths, pub_rec, revol_util, emp_length, home_ownership, purpose, etc.). "
            "This tool returns:\n"
            "  - implied_grade: A letter grade (A, B, C, D, E, or F)\n"
            "  - default_probability: Likelihood of default (0.0-1.0)\n"
            "  - risk_level: LOW, MEDIUM, HIGH, or CRITICAL\n"
            "  - top_features: List of contributing factors\n"
            "  - score_breakdown: Detailed component scores\n\n"
            "STEP 2 - Check RAG Policy Database:\n"
            "Call 'RAG_Policy_Stats' to verify policy documents are loaded.\n"
            "Then call 'RAG_Policy_Search' with queries like: 'loan approval FICO score requirements; "
            "DTI ratio thresholds; risk assessment for borderline applications'.\n\n"
            "STEP 3 - Compare and Decide:\n"
            "Compare the ML grade and risk level against policy requirements.\n"
            "Grade A-B → Typically LOAN_APPROVED\n"
            "Grade C-D → Typically NEEDS_VERIFY\n"
            "Grade E-F → Typically REJECTED\n\n"
            "STEP 4 - Output JSON:\n"
            "Return a JSON object with this EXACT structure:\n"
            "{\n"
            '  "credit_assessment": {\n'
            '    "implied_grade": "<A-F>",\n'
            '    "default_probability": <float>,\n'
            '    "default_probability_pct": "<X.XX%>",\n'
            '    "risk_level": "<LOW|MEDIUM|HIGH|CRITICAL>",\n'
            '    "top_features": [<list of factors>]\n'
            "  },\n"
            '  "loan_decision": "LOAN_APPROVED|NEEDS_VERIFY|REJECTED",\n'
            '  "rationale": "<Clear explanation referencing ML scores AND policy rules>",\n'
            '  "conditions": ["<condition 1>", "<condition 2>", ...],\n'
            '  "next_steps": ["<step 1>", "<step 2>", ...]\n'
            "}\n\n"
            "CRITICAL RULES:\n"
            "- ALWAYS call US_Credit_Risk_Scorer FIRST - do NOT skip this step\n"
            "- Use ONLY the grade returned by the tool (A-F), never fabricate grades\n"
            "- Reference ACTUAL policy excerpts from RAG, never fabricate thresholds\n"
            "- If RAG returns no documents, state 'No policy documents found' and use ML scores\n"
            "- conditions and next_steps MUST be arrays of strings, NOT single strings"
        ),
        expected_output="JSON object with credit_assessment (grade A-F, default probability, risk level), loan_decision, rationale, conditions array, and next_steps array.",
        agent=agents["loan_creation_agent"],
    )
    summary_task = Task(
        description=(
            "Generate borrower-friendly credit summary explaining scores, metrics, next steps. "
            "Verify thresholds with 'RAG_Policy_Search' before citing. "
            "If unconfirmed, use 'below the bank's requirement'."
        ),
        expected_output="Borrower-friendly credit summary with explanations and improvement recommendations.",
        agent=agents["loan_summary_agent"],
        context=[decision_task],
    )
    notification_task = Task(
        description=(
            "STEP 1 - EXTRACT DATA FROM UPSTREAM CONTEXT:\n"
            "Extract the following from decision_task and summary_task outputs:\n"
            "- loan_decision: LOAN_APPROVED, NEEDS_VERIFY, or REJECTED\n"
            "- credit_assessment: implied_grade, default_probability, risk_level\n"
            "- rationale, conditions, next_steps\n"
            "- Borrower details: first_name, last_name, email, user_address, pin_number, mobile_number\n"
            "- KYC details: kyc_details_1, kyc_details_2\n"
            "- Loan details: loan_amnt (loan amount), loan_type, interest_rate, tenure_months\n\n"
            
            "STEP 2 - DATABASE INSERTION (LOAN_APPROVED CASE ONLY):\n"
            "IF loan_decision == 'LOAN_APPROVED':\n"
            "  Call 'Deposit Creator' tool to insert user details into database with:\n"
            "  - first_name, last_name, email, user_address, pin_number, mobile_number\n"
            "  - kyc_details_1, kyc_details_2\n"
            "  - product_type: Use 'LOAN' or map loan_type to appropriate product_type\n"
            "  - initial_amount: loan_amnt (loan amount)\n"
            "  - tenure_months: from loan details\n"
            "  - bank_name: 'Bank POC'\n"
            "  - interest_rate: from loan details\n"
            "  - compounding_freq: 'monthly' (default for loans)\n"
            "  - country_code: 'IN' (default)\n"
            "  - risk_score: Calculate from default_probability (e.g., risk_score = int(default_probability * 100))\n"
            "  - status: 'approved' (since loan_decision is LOAN_APPROVED)\n\n"
            
            "STEP 3 - EMAIL SENDING (BOTH LOAN_APPROVED AND REJECTED CASES):\n"
            "Call 'Email Sender' tool to send notification email:\n"
            "- to_email: borrower's email address\n"
            "- subject: 'Loan Application Decision — ' + ('APPROVED' if LOAN_APPROVED else 'REJECTED')\n"
            "- body: Include:\n"
            "  * Greeting with borrower's name\n"
            "  * Decision: LOAN APPROVED or LOAN REJECTED\n"
            "  * Credit assessment summary (grade, risk level, default probability)\n"
            "  * Rationale for the decision\n"
            "  * If APPROVED: Loan amount, interest rate, tenure, next steps for disbursement\n"
            "  * If REJECTED: Reasons for rejection, conditions that could improve future applications\n"
            "  * Contact information for questions\n"
            "- attachment_paths: None (unless summary PDF is available)\n\n"
            
            "CRITICAL RULES:\n"
            "- Database insertion ONLY happens when loan_decision == 'LOAN_APPROVED'\n"
            "- Email sending happens in BOTH LOAN_APPROVED and REJECTED cases\n"
            "- Extract all borrower details from the upstream context (decision_task and summary_task outputs)\n"
            "- If any required field is missing, use sensible defaults or mark as 'Not provided'\n"
            "- Email must be professional, clear, and actionable\n"
        ),
        expected_output=(
            "Database insertion result (if LOAN_APPROVED): 'Success! LOAN Created. ID: X, Account: Y...' or error message.\n"
            "Email sending result: 'EMAIL_SENT: Delivered to email@example.com. Attachments: none.' or error message.\n"
            "If loan_decision is REJECTED: Only email sending result (no database insertion)."
        ),
        agent=agents["loan_creation_agent"],
        context=[decision_task, summary_task],
    )
    return [decision_task, summary_task, notification_task]


# ===================================================================
# Routing (unchanged - 1 task)
# ===================================================================


def create_routing_task(agents, user_query: str, region: str = "India"):
    return Task(
        description=(
            f"Analyze query: '{user_query}' | Region: {region}\n\n"
            "Respond with EXACTLY ONE word:\n"
            "- CREDIT_RISK: credit assessment, scoring, default probability (US only; else closest)\n"
            "- LOAN_CREATION: loan approval, underwriting, FICO/DTI policy\n"
            "- MORTGAGE_ANALYTICS: mortgage rates, LTV, DTI calc, Fannie Mae (US only; else closest)\n"
            "- ANALYSIS: FD/TD calculations, maturity, rate comparisons, projections\n"
            "- VISUALIZATION: charts, graphs, visualizations, plot data, bar/pie/line charts\n"
            "- RESEARCH: provider comparisons, detailed reports (no calculations)\n"
            "- DATABASE: existing users, accounts, KYC status, current records\n"
            "- ONBOARDING: open account, create FD, start onboarding\n\n"
            "ONLY one word: CREDIT_RISK, LOAN_CREATION, MORTGAGE_ANALYTICS, ANALYSIS, VISUALIZATION, RESEARCH, DATABASE, ONBOARDING."
        ),
        expected_output="Single word: CREDIT_RISK, LOAN_CREATION, MORTGAGE_ANALYTICS, ANALYSIS, VISUALIZATION, RESEARCH, DATABASE, or ONBOARDING",
        agent=agents["manager_agent"],
    )


# ===================================================================
# FD Template Generation Pipeline (unchanged - 1 task)
# ===================================================================


def create_fd_template_tasks(
    agents, fd_data: dict, template_type: str = "confirmation"
):
    """Create tasks for generating FD email templates using LLM."""
    type_desc = {
        "confirmation": "FD creation confirmation",
        "maturity_reminder": "FD maturity reminder",
        "renewal_offer": "FD renewal offer",
    }
    return [
        Task(
            description=(
                f"Generate {type_desc.get(template_type, template_type)} email template using LLM.\n\n"
                f"FD Data:\n{fd_data}\n\n"
                "Create professional personalized HTML email: customer name/greeting, all deposit details "
                "(FD number, bank, amount, rate, tenure, maturity date/amount), disclaimers, contact info, "
                "inline CSS, mobile-responsive, icons. Generate dynamically — NOT hardcoded. "
                "Output: Complete HTML ready to send."
            ),
            expected_output="Complete HTML email template with inline CSS, standalone, renders in all clients.",
            agent=agents["fd_template_generator_agent"],
        )
    ]


# ===================================================================
# TD/FD Creation Pipeline (unchanged - 3 tasks)
# ===================================================================


def create_td_fd_tasks(
    agents, user_query: str = None, user_email: str = "", user_id: int = None,
    region: str = "India", tenure: int = 12
):
    """TD/FD creation: provider selection → deposit creation → email notification.
    
    Supports two calling patterns:
    1. FD creation workflow: create_td_fd_tasks(agents, user_query, user_email, user_id)
    2. FD advisor workflow: create_td_fd_tasks(agents, region=region, tenure=tenure_months)
    """
    
    # Build user query if not provided (for FD advisor workflow)
    if user_query is None:
        user_query = f"Find best FD rates in {region} for {tenure} months tenure"

    provider_selection_task = Task(
        description=(
            f"Analyze TD/FD request: '{user_query}'\n"
            f"Extract: deposit type (FD/TD/RD), amount, tenure, intent (best rate/safest/gov/highest maturity), preferences.\n\n"
            f"Search TOP 3 providers by intent. " + _SEARCH_BOILERPLATE + "\n"
            f"Output: Markdown table with Provider, Rate, Credit Rating, Safety Profile, Features, recommendation."
        ),
        expected_output="Markdown table: 3 providers with Rate, Credit Rating, Safety Profile, Features, recommendation.",
        agent=agents["td_fd_provider_selection_agent"],
    )
    td_fd_creation_task = Task(
        description=(
            "Create TD/FD using 'UniversalDepositCreationTool'.\n"
            "Params: user_id, user_email, product_type, bank_name, initial_amount, tenure_months, "
            "interest_rate, compounding_freq, currency_code ('INR'), country_code ('IN').\n"
            "Tool validates, finds/creates account, creates deposit+transaction records.\n"
            "Output: SUCCESS (fd_id, account_number, maturity_date, maturity_amount) or ERROR."
        ),
        expected_output="SUCCESS: fd_id, account_number, maturity_date, maturity_amount — or ERROR.",
        agent=agents["td_fd_creation_agent"],
        context=[provider_selection_task],
    )
    td_fd_notification_task = Task(
        description=(
            "Send TD/FD confirmation via 'EmailSenderTool'.\n"
            "To: customer email. Subject: 'Your Fixed Deposit has been Created Successfully!'\n"
            "Body: confirmation, FD number, bank, type, principal, rate, tenure, compounding, "
            "maturity date, expected amount, premature withdrawal penalty, contact info.\n"
            "If creation failed, send failure notification."
        ),
        expected_output="EMAIL_SENT confirmation or EMAIL_ERROR with details.",
        agent=agents["td_fd_notification_agent"],
        context=[td_fd_creation_task],
    )
    return [provider_selection_task, td_fd_creation_task, td_fd_notification_task]
