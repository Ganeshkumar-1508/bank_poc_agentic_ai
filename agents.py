import pandas as pd
from crewai import Agent, Crew, Task, Process
from langchain_nvidia_ai_endpoints import ChatNVIDIA
from crewai.tools import BaseTool
from typing import Type
from pydantic import BaseModel, Field
import requests
from config import llm, llm_2
from langchain_community.tools import DuckDuckGoSearchRun, DuckDuckGoSearchResults
from langchain_community.utilities import DuckDuckGoSearchAPIWrapper

wrapper = DuckDuckGoSearchAPIWrapper(time="y", max_results=5)

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

class DDGSearchTool(BaseTool):
    name: str = "Internet Search"
    description: str = "Search the internet for current information, CRISIL ratings, and recent news about banks."
    
    def _run(self, query: str) -> str:
        search = DuckDuckGoSearchResults(
            api_wrapper=wrapper,
        ) #DuckDuckGoSearchRun() 
        return search.run(query)

ddg_search_tool = DDGSearchTool()

class RiskAnalysisInput(BaseModel):
    query: str = Field(description="The user's specific query about a bank's risk or rating")

class RunRiskAnalysisTool(BaseTool):
    name: str = "Trigger Risk Analysis"
    description: str = "Executes the risk analysis agent to search for CRISIL ratings and recent news for a specific bank. Use this when the user asks about 'risk', 'safety', 'CRISIL rating', 'stability', or 'news' for a specific bank."
    args_schema: Type[BaseModel] = RiskAnalysisInput

    def _run(self, query: str) -> str:
        task = Task(
            description=(
                f"Analyze the following user query regarding a specific bank: '{query}'.\n"
                "Use the search tool to find:\n"
                "1. The bank's current CRISIL rating.\n"
                "2. Recent news (last few months) about the bank's financial health or FD schemes.\n"
                "Provide the sources of your information."
                "Provide a concise summary of the risk level based on the findings."
                "3. **IMPORTANT**: You must conclude with a single-word safety status: 'Safe', 'Neutral', or 'Not safe'."
            ),
            expected_output="A brief summary of the bank's CRISIL rating and recent news affecting its stability and cite the Sources in the End.",
            agent=risk_analysis_agent
        )
        
        crew = Crew(
            agents=[risk_analysis_agent],
            tasks=[task],
            process=Process.sequential,
            verbose=True
        )
        
        result = crew.kickoff()
        return result.raw

risk_trigger_tool = RunRiskAnalysisTool()

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
    allow_delegation=False,
    #max_iter=2
)

risk_analysis_agent = Agent(
    role="Financial Risk Analyst",
    goal="Analyze the stability and recent news of a specific bank using search tools to find CRISIL ratings and recent events.",
    backstory=(
        "You are a financial expert specializing in banking risk. "
        "When given a specific bank name, you search for their CRISIL ratings and any significant recent news about that Bank. "
        "You summarize the findings clearly for the user."
    ),
    tools=[ddg_search_tool],
    verbose=True,
    llm=llm_2,
    #max_iter=3,
    allow_delegation=False
)

intent_agent = Agent(
    role="Banking Intent Orchestrator",
    goal="Identify the user's intention and route the request to the correct tool.",
    backstory=(
        "You are a helpful banking assistant. You analyze user queries.\n"
        "1. If the user asks for 'rates', 'FD', 'interest', or specific tenures, you MUST use the 'Trigger FD Scraper' tool.\n"
        "2. If the user asks for 'risk', 'safety', 'CRISIL', 'rating', 'news', or 'stability' for a bank, you MUST use the 'Trigger Risk Analysis' tool.\n"
        "Do not make up data; rely on the tools."
        "CRITITCAL: if triggering 'Trigger Risk Analysis' tool, make sure you show the Exact Output from the tool to the user"
    ),
    tools=[scraper_trigger_tool, risk_trigger_tool],
    verbose=True,
    llm=llm,
    allow_delegation=False
)