# rag_policy_tool.py
# ---------------------------------------------------------------------------
# CrewAI tool that allows agents to query the RAG system for policy documents.
# Agents call this tool during loan evaluation to check relevant banking policies
# (loan policies, credit score requirements, compliance rules, etc.).
# ---------------------------------------------------------------------------

from crewai.tools import BaseTool
from pydantic import BaseModel, Field
from typing import List, Optional, Type

from rag_engine import retrieve_as_text, get_stats


class RAGPolicySearchInput(BaseModel):
    """Input schema for the RAG Policy Search tool."""
    query: str = Field(
        description=(
            "The search query to find relevant policy documents. "
            "Be specific: e.g., 'minimum FICO score for personal loan approval', "
            "'maximum DTI ratio for mortgage', 'credit score impact of late payments', "
            "'loan approval policy for borrowers with bankruptcy'."
        )
    )
    category: Optional[str] = Field(
        default=None,
        description=(
            "Optional category filter. Use one of: 'loan_policy', 'credit_score', "
            "'compliance', 'risk_assessment', 'general'. "
            "If unsure, omit this field."
        )
    )
    max_results: Optional[int] = Field(
        default=5,
        description=(
            "Maximum number of relevant document chunks to retrieve. "
            "Default is 5. Use 3 for quick checks, up to 10 for comprehensive review."
        )
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

    def _run(self, query: str, category: Optional[str] = None,
             max_results: int = 5) -> str:
        """
        Execute the RAG policy search.

        Args:
            query: Search query for relevant policy documents
            category: Optional category filter
            max_results: Maximum number of results

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

        # Perform retrieval
        results = retrieve_as_text(
            query=query,
            n_results=max_results,
            category=category,
        )

        return results


class RAGPolicyStatsInput(BaseModel):
    """Input schema for the RAG Policy Stats tool."""
    pass


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
    args_schema: Type[BaseModel] = RAGPolicyStatsInput

    def _run(self) -> str:
        stats = get_stats()

        lines = [
            "RAG POLICY DATABASE STATUS",
            f"Total Documents: {stats['total_documents']}",
            f"Total Chunks: {stats['total_chunks']}",
            f"Categories: {', '.join(stats['categories']) if stats['categories'] else 'None'}",
        ]

        if stats['total_documents'] == 0:
            lines.append("\nWARNING: No documents uploaded. Decisions will be based on credit data only.")

        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Convenience singletons for import in agents.py
# ---------------------------------------------------------------------------
rag_policy_search_tool = RAGPolicySearchTool()
rag_policy_stats_tool = RAGPolicyStatsTool()
