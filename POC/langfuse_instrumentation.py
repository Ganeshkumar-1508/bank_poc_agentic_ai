# langfuse_instrumentation.py
import logging
import os
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


def get_langfuse_client():
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

    try:
        # Langfuse SDK >= 3.x
        from langfuse.langchain import CallbackHandler as _LFHandler
    except ImportError:
        try:
            # Langfuse SDK 2.x fallback
            from langfuse.callback import CallbackHandler as _LFHandler
        except ImportError:
            # No LangChain integration available — return None-safe stub
            print("[Langfuse] WARNING: LangfuseCallbackHandler not available. "
                  "Token usage will not be tracked per LLM call.")
            return None

    _callback_handler = _LFHandler()
    return _callback_handler


def instrument_crewai():
    global _instrumented
    if _instrumented:
        return

    # Initialize Langfuse client from env vars
    langfuse = get_langfuse_client()

    # Instrument CrewAI with OpenInference + Langfuse
    CrewAIInstrumentor().instrument(skip_dep_check=True)

    _instrumented = True