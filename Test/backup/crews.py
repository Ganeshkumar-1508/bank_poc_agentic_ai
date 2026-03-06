# crews.py
from crewai import Crew, Process
from agents import create_agents
from tasks import (
    create_analysis_tasks, 
    create_research_tasks, 
    create_database_tasks, 
    create_onboarding_tasks,
    create_routing_task
)

class FixedDepositCrews:
    def __init__(self):
        self.agents = create_agents()

    def get_router_crew(self, user_query: str):
        """Simple sequential crew for routing decision."""
        routing_task = create_routing_task(self.agents, user_query)
        return Crew(
            agents=[self.agents["manager_agent"]],
            tasks=[routing_task],
            process=Process.sequential,
            verbose=True
        )

    def get_onboarding_crew(self, conversation_history: str):
        """
        Hierarchical Crew for Onboarding.
        Manager delegates to Onboarding Agent, then to Email Specialist.
        """
        tasks = create_onboarding_tasks(self.agents, conversation_history)
        return Crew(
            agents=[self.agents["onboarding_agent"], self.agents["email_specialist_agent"]],
            tasks=tasks,
            process=Process.hierarchical,
            manager_agent=self.agents["manager_agent"],
            verbose=True
        )

    def get_analysis_crew(self, user_query: str):
        """
        Hierarchical Crew for Analysis.
        Manager ensures the dependency chain (Parse -> Search -> Research -> Safety -> Projection -> Summary) is respected.
        """
        tasks = create_analysis_tasks(self.agents, user_query)
        return Crew(
            agents=[
                self.agents["query_parser_agent"], 
                self.agents["search_agent"], 
                self.agents["research_agent"], 
                self.agents["safety_agent"], 
                self.agents["projection_agent"], 
                self.agents["summary_agent"]
            ],
            tasks=tasks,
            process=Process.hierarchical,
            manager_agent=self.agents["manager_agent"],
            verbose=True
        )

    def get_research_crew(self, user_query: str):
        """
        Hierarchical Crew for General Research.
        """
        tasks = create_research_tasks(self.agents, user_query)
        return Crew(
            agents=[
                self.agents["provider_search_agent"], 
                self.agents["deep_research_agent"], 
                self.agents["research_compilation_agent"]
            ],
            tasks=tasks,
            process=Process.hierarchical,
            manager_agent=self.agents["manager_agent"],
            verbose=True
        )

    def get_database_crew(self, user_query: str):
        """
        Hierarchical Crew for Database queries.
        """
        tasks = create_database_tasks(self.agents, user_query)
        return Crew(
            agents=[self.agents["db_agent"]],
            tasks=tasks,
            process=Process.hierarchical,
            manager_agent=self.agents["manager_agent"],
            verbose=True
        )

# Helper function for backward compatibility in app.py logic
def run_crew(user_query: str):
    crews = FixedDepositCrews()
    
    # 1. Route
    router_crew = crews.get_router_crew(user_query)
    route_result = router_crew.kickoff()
    decision = route_result.raw.strip().upper()
    
    # 2. Execute based on route
    if "ANALYSIS" in decision:
        crew = crews.get_analysis_crew(user_query)
        return crew.kickoff()
    elif "DATABASE" in decision:
        crew = crews.get_database_crew(user_query)
        return crew.kickoff()
    elif "ONBOARDING" in decision:
        # Returns a simple object to signal the app to switch flow
        return type('obj', (object,), {'raw': 'ONBOARDING'})()
    else:
        # Default to RESEARCH
        crew = crews.get_research_crew(user_query)
        return crew.kickoff()

def get_onboarding_crew(conversation_history: str):
    crews = FixedDepositCrews()
    return crews.get_onboarding_crew(conversation_history)