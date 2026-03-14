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
    create_routing_task,
    create_compliance_investigation_tasks,
)


class FixedDepositCrews:
    def __init__(self):
        self.agents = create_agents()

    def get_router_crew(self, user_query: str):
        """Minimal sequential crew for routing — just the manager."""
        routing_task = create_routing_task(self.agents, user_query)
        return Crew(
            agents=[self.agents["manager_agent"]],
            tasks=[routing_task],
            process=Process.sequential,
            verbose=True,
        )

    def get_aml_execution_crew(self, client_data_json: str):
        """
        PHASE 2: Sequential AML crew.
        Performs AML checks, risk scoring, and deposit creation + single conditional email.
        Sequential is correct here — create_aml_execution_tasks already encodes the full
        execution order via context=[] dependencies on each task, so a hierarchical manager
        adds no value and causes role-name lookup failures when delegating.
        """
        tasks = create_aml_execution_tasks(self.agents, client_data_json)
        return Crew(
            agents=[
                self.agents["cypher_generator_agent"],
                self.agents["aml_investigator_agent"],
                self.agents["ubo_investigator_agent"],
                self.agents["risk_scoring_agent"],
                self.agents["fd_processor_agent"],
                self.agents["success_handler_agent"],
            ],
            tasks=tasks,
            process=Process.sequential,
            verbose=True,
        )

    def get_compliance_investigation_crew(self, client_data_json: str):
        """
        Sequential compliance investigation: Identity → Graph → OSINT → Report → Decision.
        Sequential is sufficient — each task has explicit context dependencies.
        """
        tasks = create_compliance_investigation_tasks(self.agents, client_data_json)
        return Crew(
            agents=[
                self.agents["identity_agent"],
                self.agents["graph_analyst_agent"],
                self.agents["osint_specialist_agent"],
                self.agents["compliance_reporter_agent"],
                self.agents["fd_processor_agent"],
                self.agents["success_handler_agent"],
            ],
            tasks=tasks,
            process=Process.sequential,
            verbose=True,
        )

    def get_analysis_crew(self, user_query: str, region: str = "India"):
        """
        OPTIMIZED: Sequential instead of hierarchical.
        Task context=[...] dependencies already encode the correct execution order.
        Saves manager planning tokens on every task step.
        """
        tasks = create_analysis_tasks(self.agents, user_query, region=region)
        return Crew(
            agents=[
                self.agents["query_parser_agent"],
                self.agents["search_agent"],
                self.agents["research_agent"],
                self.agents["safety_agent"],
                self.agents["projection_agent"],
                self.agents["summary_agent"],
            ],
            tasks=tasks,
            process=Process.sequential,
            verbose=True,
        )

    def get_research_crew(self, user_query: str, region: str = "India"):
        """
        OPTIMIZED: Sequential instead of hierarchical.
        Three-step linear chain needs no manager overhead.
        """
        tasks = create_research_tasks(self.agents, user_query, region=region)
        return Crew(
            agents=[
                self.agents["provider_search_agent"],
                self.agents["deep_research_agent"],
                self.agents["research_compilation_agent"],
            ],
            tasks=tasks,
            process=Process.sequential,
            verbose=True,
        )

    def get_database_crew(self, user_query: str):
        """
        OPTIMIZED: Sequential instead of hierarchical.
        Single-agent crew — hierarchical adds zero value here.
        """
        tasks = create_database_tasks(self.agents, user_query)
        return Crew(
            agents=[self.agents["db_agent"]],
            tasks=tasks,
            process=Process.sequential,
            verbose=True,
        )

    def get_data_collection_crew(self, conversation_history: str, country_name: str,
                                  kyc_doc1: str = "", kyc_doc2: str = ""):
        """
        PHASE 1: Lightweight sequential crew.
        kyc_doc1/kyc_doc2 are pre-fetched by app.py (cached) to avoid a search on every turn.
        """
        task = create_data_collection_task(
            self.agents, conversation_history, country_name, kyc_doc1, kyc_doc2
        )
        return Crew(
            agents=[self.agents["onboarding_data_agent"]],
            tasks=[task],
            process=Process.sequential,
            verbose=True,
        )

    def get_visualization_crew(self, user_query: str, data_context: str):
        """Single-agent sequential crew for chart generation."""
        task = create_visualization_task(self.agents, user_query, data_context)
        return Crew(
            agents=[self.agents["data_visualizer_agent"]],
            tasks=[task],
            process=Process.sequential,
            verbose=True,
        )


# --- HELPER FUNCTION ---

def run_crew(user_query: str, region: str = "India"):
    """
    Routes the query to the appropriate crew.
    Imported by app.py.
    """
    crews = FixedDepositCrews()

    router_crew = crews.get_router_crew(user_query)
    route_result = router_crew.kickoff()
    decision = route_result.raw.strip().upper()

    if "ANALYSIS" in decision:
        return crews.get_analysis_crew(user_query, region=region).kickoff()
    elif "DATABASE" in decision:
        return crews.get_database_crew(user_query).kickoff()
    elif "ONBOARDING" in decision:
        return type("obj", (object,), {"raw": "ONBOARDING"})()
    else:
        return crews.get_research_crew(user_query, region=region).kickoff()