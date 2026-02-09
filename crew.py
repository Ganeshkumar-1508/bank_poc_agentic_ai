from crewai import Crew, Process
from agents import data_scraper_agent
from tasks import scraping_task

class FdCrew:
    def __init__(self):
        self.agents = [data_scraper_agent]
        self.tasks = [scraping_task]

    def crew(self):
        return Crew(
            agents=self.agents,
            tasks=self.tasks,
            process=Process.sequential,
            verbose=True
        )

my_crew = FdCrew().crew()