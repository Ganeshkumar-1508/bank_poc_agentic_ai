# crews.py - OPTIMIZED VERSION (matching merged agents)

import json
import logging

from crewai import Crew, Process
from agents import (
    create_router_agents,
    create_analysis_agents,
    create_research_agents,
    create_database_agents,
    create_aml_agents,
    create_visualization_agents,
    create_credit_risk_agents,
    create_loan_creation_agents,
    create_mortgage_agents,
    create_td_fd_agents,
    create_fd_template_agents,
)
from tasks import (
    create_analysis_tasks,
    create_research_tasks,
    create_database_tasks,
    create_aml_execution_tasks,
    create_visualization_task,
    create_routing_task,
    create_credit_risk_tasks,
    create_loan_creation_tasks,
    create_mortgage_analytics_tasks,
    create_td_fd_tasks,
    create_fd_template_tasks,
)
from typing import Dict, Any, Optional


# =============================================================================
# ROUTER CREW FUNCTION
# =============================================================================
def run_router_crew(user_query: str, region: str = "India"):
    """
    Single-task crew for routing - creates only router agents fresh each time.

    Args:
        user_query: The user's query to route
        region: The region for context (default: "India")

    Returns:
        CrewOutput object with routing decision
    """
    agents = create_router_agents()
    task = create_routing_task(agents, user_query, region=region)
    crew = Crew(
        agents=[agents["manager_agent"]],
        tasks=[task],
        process=Process.sequential,
        verbose=True,
        cache=False,
    )
    return crew.kickoff()


# =============================================================================
# AML EXECUTION CREW FUNCTIONS (OPTIMIZED: 9→6 agents)
# =============================================================================
def create_aml_crew(client_data_json: str):
    """
    Create AML execution crew - created FRESH per execution.
    Each AML case is unique and compliance requires fresh state.

    Args:
        client_data_json: JSON string containing client data

    Returns:
        Crew instance ready for kickoff
    """
    agents = create_aml_agents()
    tasks = create_aml_execution_tasks(agents, client_data_json)
    return Crew(
        agents=[
            agents["neo4j_agent"],
            agents["sanctions_agent"],
            agents[
                "entity_intelligence_agent"
            ],  
            agents["risk_scoring_agent"],
            agents["fd_processor_agent"],
            agents["report_delivery_agent"], 
        ],
        tasks=tasks,
        process=Process.sequential,
        verbose=True,
        cache=False,
    )


def run_aml_crew(client_data_json: str) -> dict:
    """
    Run the AML execution crew and return a structured result dict.

    This function handles the full AML pipeline execution and extracts
    the generated PDF path from the crew output.

    Args:
        client_data_json: JSON string containing client data

    Returns:
        dict with keys:
        - 'raw': full crew output text
        - 'pdf_path': path to the generated PDF report (or None)
        - 'decision': PASS or FAIL (or None)
        - 'tasks_output': list of individual task outputs
    """
    import re as _re

    crew = create_aml_crew(client_data_json)
    result = crew.kickoff()

    # Extract raw output
    crew_output = result.raw if hasattr(result, "raw") else str(result)

    # Extract PDF path from task outputs
    pdf_path = None
    tasks_output = []
    if hasattr(result, "tasks_output"):
        tasks_output = result.tasks_output
        for task_out in tasks_output:
            task_raw = task_out.raw if hasattr(task_out, "raw") else str(task_out)
            path_match = _re.search(
                r"(outputs/sessions/\S+\.pdf|outputs/pdfs/\S+\.pdf|/\S+\.pdf)", task_raw
            )
            if path_match:
                pdf_path = path_match.group(1)
                break

    # Also try to extract from the final raw output
    if not pdf_path:
        path_match = _re.search(
            r"(outputs/sessions/\S+\.pdf|outputs/pdfs/\S+\.pdf|/\S+\.pdf)", crew_output
        )
        if path_match:
            pdf_path = path_match.group(1)

    # Detect PASS/FAIL decision
    decision = None
    upper_output = crew_output.upper()
    if "DECISION: PASS" in upper_output or "APPLICATION APPROVED" in upper_output:
        decision = "PASS"
    elif (
        "DECISION: FAIL" in upper_output
        or "APPLICATION REJECTED" in upper_output
        or "TRANSACTION BLOCKED" in upper_output
    ):
        decision = "FAIL"

    return {
        "raw": crew_output,
        "pdf_path": pdf_path,
        "decision": decision,
        "tasks_output": tasks_output,
    }


# =============================================================================
# ANALYSIS CREW FUNCTION (OPTIMIZED: 6→4 agents)
# =============================================================================
def run_analysis_crew(user_query: str, region: str = "India", product_type: str = "FD"):
    """
    Analysis crew - creates only analysis agents fresh each time.
    OPTIMIZED: Reduced from 6 to 4 agents by merging:
    - query_parser + search → query_search_agent
    - research + safety → research_safety_agent

    Args:
    user_query: The user's query for analysis
    region: The region for context (default: "India")
    product_type: Financial product type (FD, RD, PPF, MF, NPS, SGB, BOND, TBILL, CD)

    Returns:
    CrewOutput object with analysis results
    """
    agents = create_analysis_agents(region=region, product_type=product_type)
    tasks = create_analysis_tasks(agents, user_query, region=region, product_type=product_type)
    crew = Crew(
    agents=[
    agents["query_search_agent"],
    agents["projection_agent"],
    agents["research_safety_agent"],
    agents["summary_agent"],
    ],
    tasks=tasks,
    process=Process.sequential,
    verbose=True,
    cache=False,
    )
    return crew.kickoff()


# =============================================================================
# RESEARCH CREW FUNCTION (OPTIMIZED: 3→2 agents)
# =============================================================================
def run_research_crew(user_query: str, region: str = "India"):
    """
    Research crew - creates only research agents fresh each time.
    OPTIMIZED: Reduced from 3 to 2 agents by merging:
    - provider_search + deep_research → provider_research_agent

    Args:
        user_query: The user's query for research
        region: The region for context (default: "India")

    Returns:
        CrewOutput object with research results
    """
    agents = create_research_agents(region=region)
    tasks = create_research_tasks(agents, user_query, region=region)
    crew = Crew(
        agents=[
            agents["provider_research_agent"],
            agents["research_compilation_agent"],
        ],
        tasks=tasks,
        process=Process.sequential,
        verbose=True,
        cache=False,
    )
    return crew.kickoff()


# =============================================================================
# DATABASE CREW FUNCTION
# =============================================================================
def run_database_crew(user_query: str):
    """
    Database crew - creates only database agent fresh each time.

    Args:
        user_query: The user's query for database operations

    Returns:
        CrewOutput object with database results
    """
    agents = create_database_agents()
    tasks = create_database_tasks(agents, user_query)
    crew = Crew(
        agents=[agents["db_agent"]],
        tasks=tasks,
        process=Process.sequential,
        verbose=True,
        cache=False,
    )
    return crew.kickoff()


# =============================================================================
# VISUALIZATION CREW FUNCTION
# =============================================================================
def run_visualization_crew(user_query: str, data_context: str):
    """
    Single-agent sequential crew for chart generation - creates fresh each time.

    Args:
        user_query: The user's query for visualization
        data_context: The data context for chart generation

    Returns:
        CrewOutput object with visualization results
    """
    agents = create_visualization_agents()
    task = create_visualization_task(agents, user_query, data_context)
    crew = Crew(
        agents=[agents["data_visualizer_agent"]],
        tasks=[task],
        process=Process.sequential,
        verbose=True,
        cache=False,
    )
    return crew.kickoff()


# =============================================================================
# CREDIT RISK CREW FUNCTION
# =============================================================================
def run_credit_risk_crew(borrower_json: str = "{}", region: str = "IN"):
    """
    Credit risk crew - creates only credit risk agents fresh each time.
    Routes to region-specific models based on the region parameter.

    Args:
        borrower_json: JSON string containing borrower data (default: "{}")
        region: Region code - "US" for US model, "IN" for India model (default: "IN")

    Returns:
        CrewOutput object with credit risk assessment
    """
    # Normalize region
    region_code = region.upper() if region else "IN"
    
    # Route to appropriate model based on region
    us_regions = ('US', 'UNITED STATES', 'USA')
    india_regions = ('IN', 'INDIA', 'BHARAT')
    
    is_us_region = region_code in us_regions
    is_india_region = region_code in india_regions
    
    logger = logging.getLogger(__name__)
    logger.info(f"run_credit_risk_crew: region={region_code}, is_us={is_us_region}, is_india={is_india_region}")
    
    agents = create_credit_risk_agents(region=region_code)
    tasks = create_credit_risk_tasks(agents, borrower_json, region=region_code)
    crew = Crew(
        agents=[
            agents["credit_risk_collector_agent"],
            agents["credit_risk_analyst_agent"],
        ],
        tasks=tasks,
        process=Process.sequential,
        verbose=True,
        cache=False,
    )
    return crew.kickoff()


# =============================================================================
# LOAN CREATION CREW FUNCTION
# =============================================================================
def run_loan_creation_crew(borrower_context: str = ""):
    """
    Loan creation crew - created fresh per underwriting decision.
    Each loan application is unique.

    Args:
        borrower_context: Context string about the borrower (default: "")

    Returns:
        CrewOutput object with loan creation results
    """
    agents = create_loan_creation_agents()
    tasks = create_loan_creation_tasks(agents, borrower_context)
    crew = Crew(
        agents=[
            agents["loan_creation_agent"],
            agents["loan_summary_agent"],
        ],
        tasks=tasks,
        process=Process.sequential,
        verbose=True,
        cache=False,
    )
    return crew.kickoff()


# =============================================================================
# MORTGAGE ANALYTICS CREW FUNCTION
# =============================================================================
def run_mortgage_analytics_crew(borrower_json: str = "{}"):
    """
    Mortgage analytics crew - created fresh per analysis.

    Args:
        borrower_json: JSON string containing borrower data (default: "{}")

    Returns:
        CrewOutput object with mortgage analytics results
    """
    agents = create_mortgage_agents()
    tasks = create_mortgage_analytics_tasks(agents, borrower_json)
    crew = Crew(
        agents=[
            agents["mortgage_data_collector_agent"],
            agents["mortgage_analyst_agent"],
        ],
        tasks=tasks,
        process=Process.sequential,
        verbose=True,
        cache=False,
    )
    return crew.kickoff()


# =============================================================================
# TD/FD CREATION FUNCTION
# =============================================================================
def run_td_fd_creation(
    user_query: str, user_email: str = "", user_id: Optional[int] = None
) -> Any:
    """
    Run TD/FD creation process.

    This function performs the full TD/FD creation workflow:
    1. Provider selection based on user intent
    2. Deposit creation in the database
    3. Email notification sending

    Args:
        user_query: User's deposit request with amount, tenure, and intent
        user_email: Customer email for notification
        user_id: Customer ID for account/deposit creation

    Returns:
        CrewOutput object with .raw, .tasks_output attributes containing
        the results of provider selection, creation, and notification tasks.

    Example:
        result = run_td_fd_creation(
            user_query="I want to create an FD of Rs. 5,00,000 for 12 months with best rate",
            user_email="user@example.com",
            user_id=1
        )
        print(result.raw)
    """
    agents = create_td_fd_agents()
    tasks = create_td_fd_tasks(agents, user_query, user_email, user_id)
    crew = Crew(
        agents=[
            agents["td_fd_provider_selection_agent"],
            agents["td_fd_creation_agent"],
            agents["td_fd_notification_agent"],
        ],
        tasks=tasks,
        process=Process.sequential,
        verbose=True,
        cache=False,
    )
    return crew.kickoff()


# =============================================================================
# FD TEMPLATE GENERATION FUNCTION
# =============================================================================
def generate_fd_template(
    fd_data: Dict[str, Any], template_type: str = "confirmation"
) -> Any:
    """
    Generate FD email template.

    This function generates dynamic HTML email templates for FD events:
    - confirmation: FD creation confirmation
    - maturity_reminder: FD maturity reminder
    - renewal_offer: FD renewal offer

    Args:
        fd_data: Dictionary containing FD details (customer_name, fd_number, bank_name,
            amount, rate, tenure, maturity_date, maturity_amount, etc.)
        template_type: Type of template - "confirmation", "maturity_reminder", "renewal_offer"

    Returns:
        CrewOutput object with .raw attribute containing the complete HTML email template.

    Example:
        fd_data = {
            "customer_name": "John Doe",
            "fd_number": "FD123456",
            "bank_name": "HDFC Bank",
            "amount": 500000,
            "rate": 7.5,
            "tenure": 12,
            "maturity_date": "2025-01-15",
            "maturity_amount": 537500
        }
        result = generate_fd_template(fd_data, template_type="confirmation")
        print(result.raw)
    """
    agents = create_fd_template_agents()
    tasks = create_fd_template_tasks(agents, fd_data, template_type)
    crew = Crew(
        agents=[
            agents["fd_template_generator_agent"],
        ],
        tasks=tasks,
        process=Process.sequential,
        verbose=True,
        cache=False,
    )
    return crew.kickoff()


# =============================================================================
# MAIN ROUTING FUNCTION
# =============================================================================
def run_crew(
    user_query: str,
    region: str = "India",
    borrower_context: str = "",
    data_context: str = "",
):
    """
    Routes the query to the appropriate crew via the LLM-based router agent.

    The router agent (manager_agent) classifies the user query into one of six
    intents: CREDIT_RISK, LOAN_CREATION, MORTGAGE_ANALYTICS, ANALYSIS, RESEARCH,
    or DATABASE. No keyword matching is used - the LLM decides.

    Args:
        user_query: The user's query to route
        region: The region for context (default: "India")
        borrower_context: Context string about the borrower (default: "")

    Returns:
        CrewOutput object from the routed crew
    """

    # Helper to run crew with evaluation
    def _run_with_eval(crew_func, crew_name):
        try:
            result = crew_func()
            crew_output = result.raw if hasattr(result, "raw") else str(result)

            # Post evaluation to Langfuse
            try:
                from langfuse_instrumentation import (
                    get_current_trace_id,
                    post_crew_evaluation,
                )

                trace_id = get_current_trace_id()
                post_crew_evaluation(
                    crew_name=crew_name,
                    user_input=user_query,
                    output_text=crew_output,
                    trace_id=trace_id,
                )
            except Exception as eval_error:
                print(f"[Langfuse] Evaluation failed for {crew_name}: {eval_error}")

            return result
        except Exception as e:
            print(f"[Crew] Error running {crew_name}: {e}")
            raise

    # ── LLM-based routing ──
    # The manager_agent classifies the query - no keyword matching needed.
    router_result = _run_with_eval(
        lambda: run_router_crew(user_query, region=region), "router-crew"
    )
    decision = router_result.raw.strip().upper()

    if "CREDIT_RISK" in decision:
        return _run_with_eval(
            lambda: run_credit_risk_crew(borrower_context), "credit-risk-crew"
        )
    elif "LOAN_CREATION" in decision:
        return _run_with_eval(
            lambda: run_loan_creation_crew(borrower_context), "loan-creation-crew"
        )
    elif "MORTGAGE_ANALYTICS" in decision:
        return _run_with_eval(
            lambda: run_mortgage_analytics_crew(borrower_context or "{}"),
            "mortgage-analytics-crew",
        )
    elif "ANALYSIS" in decision:
        return _run_with_eval(
            lambda: run_analysis_crew(user_query, region=region), "fd-analysis-crew"
        )
    elif "DATABASE" in decision:
        return _run_with_eval(lambda: run_database_crew(user_query), "fd-database-crew")
    elif "VISUALIZATION" in decision:

        def _viz_pipeline():
            # If no prior data context available, run analysis first
            ctx = data_context
            # Ensure ctx is a string before calling strip()
            if isinstance(ctx, dict):
                ctx = json.dumps(ctx)
            elif not isinstance(ctx, str):
                ctx = str(ctx) if ctx else ""

            # Debug logging to track data context
            print(
                f"[Visualization] Data context length: {len(ctx) if ctx else 0} chars"
            )
            print(
                f"[Visualization] Data context preview: {ctx[:200] if ctx and len(ctx) > 200 else ctx}..."
            )

            if not ctx.strip():
                print("[Visualization] No prior data context - running analysis first")
                analysis_result = run_analysis_crew(user_query, region=region)
                ctx = (
                    analysis_result.raw
                    if hasattr(analysis_result, "raw")
                    else str(analysis_result)
                )
            else:
                print(
                    "[Visualization] Using existing data context from previous analysis"
                )
            return run_visualization_crew(user_query, data_context=ctx)

        return _run_with_eval(_viz_pipeline, "visualization-crew")
    else:
        import warnings

        warnings.warn(
            f"run_crew: unrecognised routing decision '{decision}'. "
            "Falling back to research crew.",
            stacklevel=2,
        )
        return _run_with_eval(
            lambda: run_research_crew(user_query, region=region), "fd-research-crew"
        )
        