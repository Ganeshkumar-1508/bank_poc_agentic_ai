# langfuse_instrumentation.py
"""
Langfuse instrumentation helpers for CrewAI agent observability.

Provides:
- get_langfuse_client(): Singleton Langfuse client for posting scores/traces
- get_langfuse_callback_handler(): LangChain callback for token tracking
- instrument_crewai(): Enable CrewAI OpenInference instrumentation
- get_trace_id_from_current(): Extract current trace ID for evaluation
- CrewAI integration helpers for automatic trace correlation
"""
import logging
import os
import threading
from typing import Optional
from langfuse import get_client
from openinference.instrumentation.crewai import CrewAIInstrumentor

# ---------------------------------------------------------------------------
# Silence noisy loggers — set to WARNING so only real problems surface
# ---------------------------------------------------------------------------
for noisy_logger in (
    "langfuse",
    "langfuse.client",
    "langfuse.callback",
    "langfuse.langchain",
    "langfuse.openai",
    "openinference.instrumentation.crewai",
    "opentelemetry",
    "opentelemetry.sdk",
    "opentelemetry.exporter",
    "httpx",
    "httpcore",
):
    logging.getLogger(noisy_logger).setLevel(logging.WARNING)

_langfuse_client = None
_instrumented = False
_callback_handler = None

# Thread-local storage for current trace ID (set during crew execution)
_trace_context = threading.local()


def get_langfuse_client():
    """Get singleton Langfuse client instance."""
    global _langfuse_client
    if _langfuse_client is None:
        _langfuse_client = get_client()
    return _langfuse_client


def get_langfuse_callback_handler():
    """
    Returns a singleton LangChain callback handler for Langfuse.
    Attach this to NVIDIA / LangChain LLM instances so every LLM call
    records token usage (prompt_tokens, completion_tokens, total_tokens)
    and cost in the Langfuse UI under the Generation span.

    Import path tries the v3 location first, then falls back to the
    legacy v2 location so the code works across SDK versions.
    """
    global _callback_handler
    if _callback_handler is not None:
        return _callback_handler

    _LFHandler = None

    # Try Langfuse SDK >= 3.x first
    try:
        from langfuse.langchain import CallbackHandler as _LFHandler  # type: ignore
    except ImportError:
        pass

    # Fall back to Langfuse SDK 2.x
    if _LFHandler is None:
        try:
            from langfuse.callback import CallbackHandler as _LFHandler  # type: ignore
        except ImportError:
            pass

    if _LFHandler is None:
        # No LangChain integration available — return None-safe stub
        print(
            "[Langfuse] WARNING: LangfuseCallbackHandler not available. "
            "Token usage will not be tracked per LLM call."
        )
        return None

    _callback_handler = _LFHandler()
    return _callback_handler


def instrument_crewai():
    """Enable CrewAI OpenInference instrumentation for Langfuse tracing."""
    global _instrumented
    if _instrumented:
        return

    # Initialize Langfuse client from env vars
    langfuse = get_langfuse_client()

    # Instrument CrewAI with OpenInference + Langfuse
    CrewAIInstrumentor().instrument(skip_dep_check=True)

    _instrumented = True
    print("[Langfuse] CrewAI instrumentation enabled")


def get_current_trace_id() -> Optional[str]:
    """
    Get the current trace ID from thread-local context.
    This is set automatically during CrewAI execution when instrumentation is enabled.

    Returns:
        Current trace ID string, or None if not in a traced context
    """
    return getattr(_trace_context, "trace_id", None)


def set_current_trace_id(trace_id: str) -> None:
    """
    Set the current trace ID in thread-local context.
    Called automatically by CrewAI instrumentation callbacks.

    Args:
        trace_id: The Langfuse trace ID to store
    """
    _trace_context.trace_id = trace_id


def clear_current_trace_id() -> None:
    """Clear the current trace ID from thread-local context."""
    if hasattr(_trace_context, "trace_id"):
        delattr(_trace_context, "trace_id")


def get_langfuse_trace_url(trace_id: str) -> str:
    """
    Generate a URL to view the trace in Langfuse UI.

    Args:
        trace_id: The Langfuse trace ID

    Returns:
        Full URL to the trace in Langfuse UI
    """
    langfuse_host = os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com")
    return f"{langfuse_host}/trace/{trace_id}"


# ---------------------------------------------------------------------------
# CrewAI-specific helpers for evaluation correlation
# ---------------------------------------------------------------------------


def extract_trace_id_from_crew_result(crew_result) -> Optional[str]:
    """
    Extract trace ID from a CrewAI execution result.
    The trace ID is typically stored in the result's metadata when instrumentation is enabled.

    Args:
        crew_result: The CrewAI CrewExecutionResult object

    Returns:
        Trace ID string if available, None otherwise
    """
    try:
        # Try common attribute paths where trace_id might be stored
        if hasattr(crew_result, "metadata") and crew_result.metadata:
            return crew_result.metadata.get("langfuse_trace_id")

        if hasattr(crew_result, "trace_id"):
            return crew_result.trace_id

        # Fallback: check if trace_id is in raw output as a comment
        if hasattr(crew_result, "raw") and crew_result.raw:
            import re

            match = re.search(
                r"trace_id[:\s=]+([a-f0-9-]{36})", str(crew_result.raw), re.I
            )
            if match:
                return match.group(1)

    except Exception as e:
        print(f"[Langfuse] Warning: Could not extract trace_id from crew result: {e}")

    return None


def post_crew_evaluation(
    crew_name: str, user_input: str, output_text: str, trace_id: Optional[str] = None
) -> None:
    """
    Convenience function to post crew evaluation to Langfuse.
    Automatically detects trace ID if not provided.

    Args:
        crew_name: Name of the crew (e.g., 'mortgage-analytics-crew')
        user_input: Original user query
        output_text: Crew output to evaluate
        trace_id: Optional trace ID (auto-detected if not provided)
    """
    from langfuse_evaluator import evaluate_crew_output_async

    # Auto-detect trace ID if not provided
    if not trace_id:
        trace_id = get_current_trace_id()

    if not trace_id:
        print(
            f"[Langfuse] Warning: No trace_id available for crew evaluation: {crew_name}"
        )
        return

    # Post evaluation asynchronously
    evaluate_crew_output_async(
        langfuse_client=get_langfuse_client(),
        trace_id=trace_id,
        crew_name=crew_name,
        user_input=user_input,
        output_text=output_text,
    )
