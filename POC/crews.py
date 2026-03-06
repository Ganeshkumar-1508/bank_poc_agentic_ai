# crews.py
from crewai import Crew, Process
from agents import create_agents
from tasks import (
    create_analysis_tasks, 
    create_research_tasks, 
    create_database_tasks, 
    create_data_collection_task,
    create_aml_execution_tasks,
    create_visualization_task,
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

    # --- NEW: SPLIT ONBOARDING CREWS ---

    def get_data_collection_crew(self, conversation_history: str):
        """
        PHASE 1: Lightweight Sequential Crew. 
        Only checks for missing data. 
        Does NOT run AML checks.
        """
        task = create_data_collection_task(self.agents, conversation_history)
        return Crew(
            agents=[self.agents["onboarding_data_agent"]],
            tasks=[task],
            process=Process.sequential,
            verbose=True
        )

    def get_aml_execution_crew(self, client_data_json: str):
        """
        PHASE 2: Heavy Hierarchical Crew. 
        Runs ONLY after data is collected.
        Performs AML checks, Scoring, and FD Creation.
        """
        tasks = create_aml_execution_tasks(self.agents, client_data_json)
        
        return Crew(
            agents=[
                self.agents["aml_investigator_agent"],
                self.agents["risk_scoring_agent"],
                self.agents["fd_processor_agent"],
                self.agents["success_handler_agent"],
                self.agents["rejection_handler_agent"]
            ],
            tasks=tasks,
            process=Process.hierarchical,
            manager_agent=self.agents["manager_agent"],
            verbose=True
        )

    # --- ORIGINAL CREWS (Preserved) ---

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
    def get_visualization_crew(self, user_query: str, data_context: str):
        """
        Crew to generate visualization configuration.
        """
        task = create_visualization_task(self.agents, user_query, data_context)
        return Crew(
            agents=[self.agents["data_visualizer_agent"]],
            tasks=[task],
            process=Process.sequential,
            verbose=True
        )

# --- HELPER FUNCTION (Must be at the root level, NOT inside the class) ---

def run_crew(user_query: str):
    """
    Routes the query to the appropriate crew.
    This function is imported by app.py.
    """
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