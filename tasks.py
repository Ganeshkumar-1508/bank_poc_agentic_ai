from crewai import Task
from agents import data_scraper_agent, bankbazaar_scraper_tool


scraping_task = Task(
    description=(
        "Use the 'BankBazaar Table Scraper' tool to get data from 'https://www.bankbazaar.com/fixed-deposit-rate.html'. "
        "The tool will return raw table text. "
        "Analyze this text and construct a CSV with columns: Bank, Tenure, General Rate, Senior Rate. "
        "CRITICAL RULES: "
        "1. Map 'General Citizens' rates to 'General Rate' and 'Senior Citizens' to 'Senior Rate'. "
        "2. The 'Tenure' column MUST strictly contain time periods (e.g., '7 Days','1 Year', '2 Years','5 Years'). "
        "   DO NOT put interest rate percentages (like '7.0%') in the 'Tenure' column. "
        "3. If a row has only a Bank name, look for the rates in subsequent rows. "
        "4. If rates are ranges (e.g., '6.5-7.0'), keep them as is. "
        "5. DO NOT include any introductory text. "
        "6. Output MUST start with the header row: Bank,Tenure,General Rate,Senior Rate"
    ),
    expected_output="A raw CSV string starting with headers. No markdown code blocks.",
    agent=data_scraper_agent,
    tools=[bankbazaar_scraper_tool]
)