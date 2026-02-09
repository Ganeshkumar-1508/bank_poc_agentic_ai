import pandas as pd
from crewai import Agent
from langchain_nvidia_ai_endpoints import ChatNVIDIA
from crewai.tools import BaseTool
from typing import Type
from pydantic import BaseModel, Field
import requests
from config import llm,lammavl

class BankBazaarScraperInput(BaseModel):
    url: str = Field(description="The URL of the BankBazaar FD rates page")

class BankBazaarScraperTool(BaseTool):
    name: str = "BankBazaar Table Scraper"
    description: str = "Scrapes HTML tables specifically from BankBazaar FD rates page and returns them as text."
    args_schema: Type[BaseModel] = BankBazaarScraperInput

    def _run(self, url: str) -> str:
        try:
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
            response = requests.get(url, headers=headers)
            tables = pd.read_html(response.text)
            
            if not tables:
                return "No tables found on the page."
            
            output_csvs = []
            for i, table in enumerate(tables):
                cols = [str(c).lower() for c in table.columns]
                if 'interest' in ' '.join(cols) or 'tenure' in ' '.join(cols):
                    output_csvs.append(f"--- Table {i} ---\n{table.to_csv(index=False)}")
            
            return "\n\n".join(output_csvs) if output_csvs else "No relevant rate tables found."
            
        except Exception as e:
            return f"Error scraping website: {str(e)}"

bankbazaar_scraper_tool = BankBazaarScraperTool()

class ScraperTriggerInput(BaseModel):
    query: str = Field(description="The user's query requesting rate information")

class RunScraperCrewTool(BaseTool):
    name: str = "Trigger FD Scraper"
    description: str = "Executes the scraping crew to fetch the latest FD rates from BankBazaar. Use this when the user asks for current rates, market rates, or specific bank FD rates."
    args_schema: Type[BaseModel] = ScraperTriggerInput

    def _run(self, query: str) -> str:
        from crew import my_crew
        result = my_crew.kickoff()
        return result.raw

scraper_trigger_tool = RunScraperCrewTool()

data_scraper_agent = Agent(
    role="Financial Data Scraper",
    goal="Parse the extracted HTML tables and format them into a clean CSV for FD rates.",
    backstory=(
        "You are a meticulous data analyst. You receive raw table data from a scraping tool. "
        "Your job is NOT to browse the web, but to interpret the text provided by the tool. "
        "You must merge General and Senior citizen rates into a single row based on Tenure."
    ),
    tools=[bankbazaar_scraper_tool], 
    verbose=True,
    llm=llm,
    allow_delegation=False
)
intent_agent = Agent(
    role="Banking Intent Orchestrator",
    goal="Identify the user's intention. If they want FD rates, trigger the scraper tool and present the data.",
    backstory=(
        "You are a helpful banking assistant. You analyze user queries. "
        "If the user asks for 'rates', 'FD', 'interest', or specific tenures, "
        "you MUST use the 'Trigger FD Scraper' tool to get the latest data. "
        "Once you get the CSV data from the tool, format it nicely for the user."
    ),
    tools=[scraper_trigger_tool],
    verbose=True,
    llm=lammavl,
    allow_delegation=False
)