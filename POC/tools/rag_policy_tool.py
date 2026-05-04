# rag_policy_tool.py

from crewai.tools import BaseTool
from pydantic import BaseModel, Field
from typing import List, Optional, Type, Dict
import threading

from rag_engine import retrieve_as_text, get_stats

# Global state to track RAG tool usage (thread-safe)
_rag_call_tracker: Dict[str, bool] = {
    "stats_called": False,
    "search_called": False,
}
_tracker_lock = threading.Lock()


class RAGPolicySearchInput(BaseModel):
    """Input schema for the RAG Policy Search tool."""

    query: str = Field(
        description=(
            "The search query to find relevant policy documents. "
            "Be specific: e.g., 'minimum FICO score for personal loan approval', "
            "'maximum DTI ratio for mortgage', 'credit score impact of late payments', "
            "'loan approval policy for borrowers with bankruptcy'. "
            "For multiple queries, provide them as a single string with queries separated by semicolons. "
            "Example: 'mortgage LTV requirements; FICO score thresholds; DTI limits'"
        )
    )
    category: Optional[str] = Field(
        default=None,
        description=(
            "Optional category filter. Use one of: 'loan_policy', 'credit_score', "
            "'compliance', 'risk_assessment', 'general'. "
            "If unsure, omit this field."
        ),
    )
    max_results: Optional[int] = Field(
        default=5,
        description=(
            "Maximum number of relevant document chunks to retrieve per query. "
            "Default is 5. Use 3 for quick checks, up to 10 for comprehensive review."
        ),
    )


class RAGPolicySearchTool(BaseTool):
    """
    CRITICAL TOOL — You MUST use this tool before making any loan decision.
    Search the RAG knowledge base for the bank's current lending policies.
    Without calling this tool, you have NO access to the bank's actual policies
    and any decision you make would be based on assumptions, not real policy.
    """

    name: str = "RAG Policy Search"
    description: str = (
        "MUST USE BEFORE ANY LOAN DECISION. Searches the bank's policy document database. "
        "Returns real policy excerpts — not assumptions. Use it to find: loan approval criteria, "
        "FICO score thresholds, DTI limits, income requirements, risk assessment rules, "
        "borrower eligibility criteria, and compliance regulations. "
        "You CANNOT make a compliant decision without querying this tool first. "
        "Input: query (what policy you need to check), optional category filter, optional max_results."
    )
    args_schema: Type[BaseModel] = RAGPolicySearchInput

    def _run(
        self, query: str, category: Optional[str] = None, max_results: int = 5
    ) -> str:
        """
        Execute the RAG policy search.

        Args:
            query: Search query for relevant policy documents.
                   Can be a single query or multiple queries separated by semicolons.
                   Example: 'mortgage LTV requirements; FICO score thresholds; DTI limits'
            category: Optional category filter
            max_results: Maximum number of results per query

        Returns:
            Formatted text with relevant policy excerpts and sources
        """
        # Validate max_results
        if max_results is None or max_results < 1:
            max_results = 5
        max_results = min(max_results, 15)

        # Check if RAG has any documents
        stats = get_stats()
        if stats["total_chunks"] == 0:
            return (
                "WARNING: RAG POLICY DATABASE IS EMPTY\n\n"
                "No policy documents have been uploaded yet. "
                "Please upload policy documents using the RAG document upload interface "
                "(rag_upload_app.py) before using this tool.\n\n"
                "Suggested document types to upload:\n"
                "- Loan approval policies\n"
                "- Credit score guidelines\n"
                "- Risk assessment frameworks\n"
                "- Compliance and regulatory documents\n"
                "- Borrower eligibility criteria\n"
                "Without policy documents, decisions must rely solely on the "
                "borrower's credit profile data."
            )

        # Handle batch queries (semicolon-separated)
        queries = [q.strip() for q in query.split(";") if q.strip()]

        if len(queries) == 1:
            # Single query - return results directly
            results = retrieve_as_text(
                query=queries[0],
                n_results=max_results,
                category=category,
            )
            return results
        else:
            # Multiple queries - run each and combine results
            all_results = []
            for i, q in enumerate(queries, 1):
                all_results.append(f"### Query {i}: {q}\n")
                results = retrieve_as_text(
                    query=q,
                    n_results=max_results,
                    category=category,
                )
                all_results.append(results)
                all_results.append("\n")

            return "\n---\n".join(all_results)


class RAGPolicyStatsTool(BaseTool):
    """
    Check if the RAG policy database has documents loaded.
    Always call this first to verify the database is populated.
    """

    name: str = "RAG Policy Stats"
    description: str = (
        "Check whether the policy document database has documents loaded. "
        "Returns the count of documents, chunks, and available categories. "
        "Call this FIRST to verify the database has policy documents before searching."
    )

    def _run(self) -> str:
        stats = get_stats()

        lines = [
            "RAG POLICY DATABASE STATUS",
            f"Total Documents: {stats['total_documents']}",
            f"Total Chunks: {stats['total_chunks']}",
            f"Categories: {', '.join(stats['categories']) if stats['categories'] else 'None'}",
        ]

        if stats["total_documents"] == 0:
            lines.append(
                "\nWARNING: No documents uploaded. Decisions will be based on credit data only."
            )

        return "\n".join(lines)


# ---------------------------------------------------------------------------
# RAG Enforcement Tool - Validates RAG tools were called
# ---------------------------------------------------------------------------


class RAGEnforcementInput(BaseModel):
    """Empty input schema for RAG Enforcement Tool - no parameters required."""

    pass


class RAGEnforcementTool(BaseTool):
    """
    ENFORCEMENT TOOL - Validates that RAG policy tools were called before report generation.
    This tool should be called at the end of the workflow to verify compliance.
    """

    name: str = "RAG Enforcement Check"
    description: str = (
        "Call this tool BEFORE generating your final report to verify that you have "
        "called both RAG_Policy_Stats and RAG_Policy_Search. "
        "If either tool was not called, you MUST call them now. "
        "This is a COMPLIANCE REQUIREMENT - reports without RAG validation will be rejected."
    )
    args_schema: Type[BaseModel] = RAGEnforcementInput

    def _run(self) -> str:
        """Check if RAG tools were called and return validation status."""
        with _tracker_lock:
            stats_called = _rag_call_tracker["stats_called"]
            search_called = _rag_call_tracker["search_called"]

        missing = []
        if not stats_called:
            missing.append("RAG_Policy_Stats")
        if not search_called:
            missing.append("RAG_Policy_Search")

        if missing:
            return (
                f"⛔ COMPLIANCE VIOLATION: Missing required RAG tool calls.\n\n"
                f"Tools NOT called: {', '.join(missing)}\n\n"
                "YOU MUST call these tools before generating your report:\n"
                "1. Call 'RAG_Policy_Stats' to check policy database status\n"
                "2. Call 'RAG_Policy_Search' with mortgage policy queries\n\n"
                "Your report will be REJECTED without these tool calls."
            )
        else:
            return (
                "✅ COMPLIANCE VERIFIED: All required RAG tools have been called.\n\n"
                "You may now proceed to generate your final report with:\n"
                "- Policy Database Status (from RAG_Policy_Stats)\n"
                "- Policy Search Results (from RAG_Policy_Search)\n\n"
                "Include actual excerpts from the RAG results in your report."
            )


# ---------------------------------------------------------------------------
# Convenience singletons for import in agents.py
# ---------------------------------------------------------------------------
rag_policy_search_tool = RAGPolicySearchTool()
rag_policy_stats_tool = RAGPolicyStatsTool()

# Wrap the tools to track calls
_original_stats_run = rag_policy_stats_tool._run
_original_search_run = rag_policy_search_tool._run


def _tracked_stats_run() -> str:
    with _tracker_lock:
        _rag_call_tracker["stats_called"] = True
    return _original_stats_run()


def _tracked_search_run(
    query: str, category: Optional[str] = None, max_results: int = 5
) -> str:
    with _tracker_lock:
        _rag_call_tracker["search_called"] = True
    return _original_search_run(query, category, max_results)


# Replace the _run methods with tracked versions
rag_policy_stats_tool._run = _tracked_stats_run
rag_policy_search_tool._run = _tracked_search_run

# Add enforcement tool to exports
rag_enforcement_tool = RAGEnforcementTool()


# ---------------------------------------------------------------------------
# COMBINED RAG TOOL - Guarantees both stats AND search are called together
# This is the RECOMMENDED tool for mortgage analytics to ensure compliance
# ---------------------------------------------------------------------------


class RAGPolicyCompleteInput(BaseModel):
    """Input schema for the combined RAG Policy tool."""

    query: str = Field(
        default=(
            "minimum FICO score for mortgage approval; "
            "maximum LTV ratio for single family purchase; "
            "maximum DTI ratio for mortgage; "
            "underwriting guidelines for owner occupied single family"
        ),
        description=(
            "The search query to find relevant policy documents. "
            "For mortgage analytics, use the default query which covers: "
            "FICO requirements, LTV limits, DTI thresholds, and underwriting guidelines. "
            "For other use cases, provide custom queries separated by semicolons."
        ),
    )
    category: Optional[str] = Field(
        default="loan_policy",
        description="Category filter. Default: 'loan_policy' for mortgage analytics.",
    )
    max_results: Optional[int] = Field(
        default=5, description="Maximum results per query. Default: 5."
    )


class RAGPolicyCompleteTool(BaseTool):
    """
    COMBINED RAG TOOL - Call this ONCE to get both stats AND policy search results.

    This tool GUARANTEES compliance by always returning:
    1. Policy database status (document count, categories)
    2. Policy search results (actual policy excerpts)

    Use this INSTEAD of calling RAG_Policy_Stats and RAG_Policy_Search separately.
    This ensures you never miss any compliance step.
    """

    name: str = "RAG Policy Complete"
    description: str = (
        "MANDATORY FOR MORTGAGE ANALYTICS. Call this tool ONCE to get COMPLETE policy information. "
        "Returns BOTH database status AND policy search results in a single call. "
        "Default query covers: FICO requirements, LTV limits, DTI thresholds, underwriting guidelines. "
        "This tool GUARANTEES compliance - use it instead of calling Stats and Search separately. "
        "IMPORTANT: This is the ONLY RAG tool you need to call for mortgage analytics."
    )
    args_schema: Type[BaseModel] = RAGPolicyCompleteInput

    def _run(
        self,
        query: str = None,
        category: Optional[str] = "loan_policy",
        max_results: int = 5,
    ) -> str:
        """
        Execute combined RAG policy check: stats + search in one call.

        This guarantees both operations happen and returns combined results.
        """
        # Default query for mortgage analytics
        if query is None or query.strip() == "":
            query = (
                "minimum FICO score for mortgage approval; "
                "maximum LTV ratio for single family purchase; "
                "maximum DTI ratio for mortgage; "
                "underwriting guidelines for owner occupied single family"
            )

        # Track that tools were called
        with _tracker_lock:
            _rag_call_tracker["stats_called"] = True
            _rag_call_tracker["search_called"] = True

        # Get stats
        stats = get_stats()
        stats_output = [
            "=" * 60,
            "RAG POLICY DATABASE STATUS",
            "=" * 60,
            f"Total Documents: {stats['total_documents']}",
            f"Total Chunks: {stats['total_chunks']}",
            f"Categories: {', '.join(stats['categories']) if stats['categories'] else 'None'}",
        ]

        if stats["total_documents"] == 0:
            stats_output.append("\n⚠️ WARNING: No policy documents uploaded!")
            stats_output.append("Decisions will be based on ML model results only.")
            return "\n".join(stats_output)

        # Get search results
        queries = [q.strip() for q in query.split(";") if q.strip()]
        search_output = ["\n", "=" * 60, "POLICY SEARCH RESULTS", "=" * 60]

        for i, q in enumerate(queries, 1):
            search_output.append(f"\n### Query {i}: {q}")
            search_output.append("-" * 40)
            results = retrieve_as_text(
                query=q,
                n_results=max_results,
                category=category,
            )
            search_output.append(results)

        # Add compliance footer
        compliance_footer = [
            "\n" + "=" * 60,
            "✅ COMPLIANCE STATUS: VERIFIED",
            "=" * 60,
            "Both RAG_Policy_Stats and RAG_Policy_Search have been executed.",
            "You may now proceed to generate your mortgage analytics report.",
            "Include the policy excerpts above in your Policy Compliance section.",
        ]

        return "\n".join(stats_output + search_output + compliance_footer)


# Create singleton for the combined tool
rag_policy_complete_tool = RAGPolicyCompleteTool()


# ---------------------------------------------------------------------------
# Reset function for testing
# ---------------------------------------------------------------------------


def reset_rag_tracker():
    """Reset the RAG call tracker. Call this before each new workflow."""
    global _rag_call_tracker
    with _tracker_lock:
        _rag_call_tracker = {
            "stats_called": False,
            "search_called": False,
        }


def get_rag_tracker_status() -> Dict[str, bool]:
    """Get current RAG tracker status."""
    with _tracker_lock:
        return _rag_call_tracker.copy()
