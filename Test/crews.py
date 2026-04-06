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
    create_credit_risk_tasks, 
    create_loan_creation_tasks,
)


class FixedDepositCrews:
    def __init__(self):
        self.agents = create_agents()

    def get_router_crew(self, user_query: str):
        """Single-task crew for routing — just the manager."""
        routing_task = create_routing_task(self.agents, user_query)
        return Crew(
            agents=[self.agents["manager_agent"]],
            tasks=[routing_task],
            process=Process.sequential,
            verbose=True,
        )

    def get_aml_execution_crew(self, client_data_json: str):
        """
        Sequential AML crew — 9 single-responsibility agents.

        Each agent owns exactly one concern:

          1  neo4j_agent       — search graph by first_name/last_name (direct, no schema read)
          2  sanctions_agent   — Yente/OpenSanctions        [yente_tool]
          3  osint_agent       — Wikidata + news            [wikidata_tool, search_news]
          4  ubo_investigator  — UBO tracing                [yente_tool, search_news]
          5  live_enrichment   — re-enrich flagged entities [yente_tool, wikidata_tool]
          6  risk_scoring      — compile report + news URLs [search_news]
          7  fd_processor      — create deposit on PASS     [deposit_creation_tool, search_news]
          8  pdf_generator     — render PDF (with images, social media, relatives, biography) [pdf_tool]
          9  email_sender      — dispatch email             [email_tool]
        """
        tasks = create_aml_execution_tasks(self.agents, client_data_json)
        return Crew(
            agents=[
                self.agents["neo4j_agent"],
                self.agents["sanctions_agent"],
                self.agents["osint_agent"],
                self.agents["ubo_investigator_agent"],
                self.agents["live_enrichment_agent"],
                self.agents["risk_scoring_agent"],
                self.agents["fd_processor_agent"],
                self.agents["pdf_generator_agent"],
                self.agents["email_sender_agent"],
            ],
            tasks=tasks,
            process=Process.sequential,
            verbose=True,
        )

    def get_analysis_crew(self, user_query: str, region: str = "India"):
        """
        Sequential analysis crew.
        Task order: parse -> search -> projection -> research -> safety -> summary.
        Projection is placed before research so it starts as soon as search finishes,
        without waiting for the 10-provider rating search to complete.
        """
        tasks = create_analysis_tasks(self.agents, user_query, region=region)
        return Crew(
            agents=[
                self.agents["query_parser_agent"],
                self.agents["search_agent"],
                self.agents["projection_agent"],
                self.agents["research_agent"],
                self.agents["safety_agent"],
                self.agents["summary_agent"],
            ],
            tasks=tasks,
            process=Process.sequential,
            verbose=True,
        )

    def get_research_crew(self, user_query: str, region: str = "India"):
        """Three-step sequential research crew."""
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
        """Single-agent sequential crew for SQL queries."""
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
        Phase 1 onboarding: single-agent sequential crew.
        kyc_doc1/kyc_doc2 are pre-fetched by app.py to avoid a search on every turn.
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
    def get_credit_risk_crew(self, borrower_json: str = "{}"):
        """
        Two-agent sequential crew for US credit-risk scoring.
        Only invoked when user region is US.
        """
        tasks = create_credit_risk_tasks(self.agents, borrower_json)
        return Crew(
            agents=[
                self.agents["credit_risk_collector_agent"],
                self.agents["credit_risk_analyst_agent"],
            ],
            tasks=tasks,
            process=Process.sequential,
            verbose=True,
        )

    def get_loan_creation_crew(self, risk_assessment_result: str, borrower_data: dict,
                                borrower_email: str = ""):
        """
        Two-agent sequential crew for 3-category loan decision and notification.
        Classifies into: LOAN_APPROVED, NEEDS_VERIFY, or REJECTED.
        Sends email notification to the borrower.
        """
        tasks = create_loan_creation_tasks(
            self.agents, risk_assessment_result, borrower_data, borrower_email
        )
        return Crew(
            agents=[
                self.agents["loan_creation_agent"],
                self.agents["loan_notification_agent"],
            ],
            tasks=tasks,
            process=Process.sequential,
            verbose=True,
        )

# ---------------------------------------------------------------------------
# HELPER FUNCTION (imported by app.py)
# ---------------------------------------------------------------------------

def run_crew(user_query: str, region: str = "India"):
    """Routes the query to the appropriate crew."""
    crews = FixedDepositCrews()
    _CR_KW = ["credit risk", "credit score", "default probability", "loan risk",
              "borrower risk", "risk grade", "implied grade", "credit assessment",
              "will i default", "default chance", "credit check", "creditworthiness"]
    if region.upper() in ("US", "UNITED STATES", "USA") and any(k in user_query.lower() for k in _CR_KW):
        return crews.get_credit_risk_crew().kickoff()

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
        import warnings
        warnings.warn(
            f"run_crew: unrecognised routing decision '{decision}'. "
            "Falling back to research crew.",
            stacklevel=2,
        )
        return crews.get_research_crew(user_query, region=region).kickoff()