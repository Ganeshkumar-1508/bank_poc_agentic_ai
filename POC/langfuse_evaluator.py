# langfuse_evaluator.py
"""
LLM-as-a-Judge evaluation layer for Langfuse.

Uses direct NVIDIA API calls with two models:
  - Fast model  (llama-3.1-8b)  for binary 0/1 criteria — low latency, sufficient for scoring.
  - Strong model (qwen3.5-122b)  for holistic overall_quality — deeper reasoning needed.

After each crew run, evaluate_crew_output_async() fires in a daemon thread so it
never blocks the Streamlit UI.

Scores posted to Langfuse per crew:
  • Binary criteria scores  0.0 or 1.0   →  e.g. judge/relevance
  • Holistic quality score  0.0 – 1.0    →  judge/overall_quality  (1-10 normalised)
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
from typing import Optional

import requests

NVIDIA_INVOKE_URL = "https://integrate.api.nvidia.com/v1/chat/completions"  # https://integrate.api.nvidia.com/v1 , https://integrate.api.nvidia.com/v1/chat/completions
JUDGE_MODEL_FAST = "mistralai/mistral-small-4-119b-2603"
JUDGE_MODEL_STRONG = "mistralai/mistral-small-4-119b-2603"


def call_judge(
    system_prompt: str, user_prompt: str, model: str, timeout: int = 90
) -> str:
    """
    Call the NVIDIA judge model and return the full assistant text response.
    Retries once on timeout before giving up.
    """
    api_key = os.environ.get("NVIDIA_API_KEY", "")
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "max_tokens": 256,
        "temperature": 0.1,
        "stream": False,
    }

    for attempt in range(2):
        try:
            response = requests.post(
                NVIDIA_INVOKE_URL,
                headers=headers,
                json=payload,
                timeout=timeout,
            )
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"].strip()
        except requests.exceptions.Timeout:
            if attempt == 0:
                print(
                    f"[Evaluator] Timeout on attempt 1 for model {model} — retrying..."
                )
                time.sleep(2)
                continue
            raise
    return ""


CUSTOM_CRITERIA: dict[str, str] = {
    # Financial domain-specific criteria
    "financial_accuracy": (
        "Does the response contain accurate, specific financial data such as interest "
        "rates, maturity amounts, or tenure details that are internally consistent?"
    ),
    "risk_completeness": (
        "Does the AML/compliance response cover all required risk dimensions: "
        "sanctions screening, PEP checks, adverse media, UBO identification, "
        "and a final numeric risk score?"
    ),
    "data_specificity": (
        "Does the response reference specific named institutions, rates, or figures "
        "rather than generic or vague statements?"
    ),
    "chart_validity": (
        "Does the response represent a valid Apache ECharts JSON configuration with "
        "required keys (series, xAxis/yAxis or an appropriate chart type)?"
    ),
    "actionability": (
        "Does the response provide clear, actionable next steps or recommendations "
        "the user can act on immediately?"
    ),
    "regulatory_compliance": (
        "Does the compliance report clearly state a PASS or FAIL decision with "
        "supporting evidence and comply with standard AML reporting norms?"
    ),
    "credit_risk_validity": (
        "Does the credit risk assessment correctly interpret ML model outputs (FICO, DTI, "
        "default probability, risk grade) and provide sound lending recommendations?"
    ),
    "mortgage_analysis_completeness": (
        "Does the mortgage analysis cover all three model outputs: credit risk prediction, "
        "customer segmentation, and portfolio risk assessment with actionable recommendations?"
    ),
    "loan_decision_rationale": (
        "Does the loan decision provide clear, policy-backed rationale with specific "
        "references to credit scores, DTI thresholds, and risk factors?"
    ),
    "research_depth": (
        "Does the research response include comprehensive provider comparisons with "
        "current rates, credit ratings, news sentiment, and risk assessments?"
    ),
    "query_understanding": (
        "Does the response correctly identify the user's intent and extract all relevant "
        "parameters from the query?"
    ),
    # General quality criteria
    "relevance": "Is the response relevant and directly addressing what the user asked for?",
    "helpfulness": "Is the response genuinely helpful and useful to the user?",
    "correctness": "Is the information factually correct and free of errors?",
    "conciseness": "Is the response appropriately concise without unnecessary repetition?",
    "depth": "Does the response provide sufficient depth and detail to fully answer the query?",
    "harmlessness": "Is the response free of harmful, misleading, or dangerous content?",
    "clarity": "Is the response well-structured and easy to understand?",
    "completeness": "Does the response address all aspects of the user's query?",
}

# ---------------------------------------------------------------------------
# Per-crew evaluation plans
# ---------------------------------------------------------------------------

CREW_EVAL_PLAN: dict[str, list[str]] = {
    # Fixed Deposit / Investment Analysis Crews
    "fd-analysis-crew": [
        "relevance",
        "helpfulness",
        "financial_accuracy",
        "data_specificity",
        "actionability",
        "query_understanding",
        "overall_quality",
    ],
    "fd-research-crew": [
        "relevance",
        "depth",
        "data_specificity",
        "financial_accuracy",
        "research_depth",
        "overall_quality",
    ],
    "fd-visualization-crew": [
        "relevance",
        "chart_validity",
        "conciseness",
        "clarity",
        "overall_quality",
    ],
    "fd-database-crew": [
        "correctness",
        "relevance",
        "conciseness",
        "clarity",
        "overall_quality",
    ],
    # AML / Compliance Crews
    "aml-execution-crew": [
        "correctness",
        "risk_completeness",
        "regulatory_compliance",
        "harmlessness",
        "data_specificity",
        "overall_quality",
    ],
    # US Credit Risk Crews
    "credit-risk-crew": [
        "correctness",
        "credit_risk_validity",
        "actionability",
        "data_specificity",
        "clarity",
        "overall_quality",
    ],
    # Loan Underwriting Crews
    "loan-creation-crew": [
        "correctness",
        "loan_decision_rationale",
        "regulatory_compliance",
        "actionability",
        "depth",
        "overall_quality",
    ],
    # Mortgage Analytics Crews
    "mortgage-analytics-crew": [
        "correctness",
        "mortgage_analysis_completeness",
        "credit_risk_validity",
        "actionability",
        "data_specificity",
        "overall_quality",
    ],
    # Routing / Manager Crew
    "router-crew": [
        "query_understanding",
        "correctness",
        "clarity",
        "relevance",
        "overall_quality",
    ],
    # Default fallback for unrecognized crews
    "default": [
        "relevance",
        "helpfulness",
        "correctness",
        "overall_quality",
    ],
}


CRITERIA_SYSTEM = """\
You are a strict evaluator of AI-generated financial assistant responses.

Criterion — {criterion}:
{criterion_description}

Output ONLY a JSON object:
{{"score": 1, "reasoning": "one-sentence explanation"}}

score must be exactly 1 (criterion met) or 0 (criterion not met). No markdown.\
"""

CRITERIA_USER = """\
User query:
{user_input}

AI response:
{prediction}\
"""

HOLISTIC_SYSTEM = """\
You are a senior quality reviewer for a financial AI assistant.
Score the response 1 (very poor) to 10 (excellent) considering accuracy, \
relevance, completeness, and usefulness.

Output ONLY a JSON object:
{"score": 7, "reasoning": "one-sentence explanation"}

No markdown. score must be an integer 1-10.\
"""

HOLISTIC_USER = """\
User query:
{user_input}

AI response:
{prediction}\
"""

# ---------------------------------------------------------------------------
# JSON extraction
# ---------------------------------------------------------------------------


def extract_json(text: str) -> dict:
    """
    Extract the last valid JSON object from the text.
    
    Handles:
    - JSON in code blocks (```json ... ```)
    - Bare JSON objects
    - Malformed JSON with validation
    - Mixed content (text + JSON)
    
    Raises:
        ValueError: If no valid JSON object is found or if JSON is malformed
    """
    if not text or not isinstance(text, str):
        raise ValueError(f"Invalid input type: {type(text).__name__}")
    
    # Strip markdown code blocks
    text = re.sub(r"```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    text = text.strip(" `\n")
    
    if not text.strip():
        raise ValueError("Empty text after stripping markdown")
    
    # Try to find JSON in code blocks first (more reliable for nested structures)
    code_block_pattern = r"\{(?:[^{}]|\{[^{}]*\})*\}"
    matches = list(re.finditer(code_block_pattern, text, re.DOTALL))
    
    if not matches:
        raise ValueError(f"No JSON object found in: {text[:200]!r}")
    
    # Try each match from last to first (prefer last JSON object)
    for match in reversed(matches):
        json_str = match.group(0)
        try:
            parsed = json.loads(json_str)
            # Validate that it's a dict (not a list or other type)
            if isinstance(parsed, dict):
                return parsed
            elif isinstance(parsed, list):
                # If it's a list, check if it contains valid objects
                if parsed and all(isinstance(item, dict) for item in parsed):
                    # Return the last dict in the list if it's a list of dicts
                    return parsed[-1]
                elif parsed:
                    # Return first valid dict in list
                    for item in parsed:
                        if isinstance(item, dict):
                            return item
        except json.JSONDecodeError:
            continue  # Try next match
    
    # If we get here, no valid JSON object was found
    raise ValueError(f"No valid JSON object found in: {text[:200]!r}")


# ---------------------------------------------------------------------------
# Individual evaluators
# ---------------------------------------------------------------------------


def eval_criterion(
    criterion: str, user_input: str, prediction: str
) -> tuple[float, str]:
    """Binary 0/1 score for a named criterion. Uses fast model."""
    system = CRITERIA_SYSTEM.format(
        criterion=criterion,
        criterion_description=CUSTOM_CRITERIA.get(criterion, criterion),
    )
    user = CRITERIA_USER.format(user_input=user_input, prediction=prediction)
    raw = call_judge(system, user, model=JUDGE_MODEL_FAST, timeout=45)
    parsed = extract_json(raw)
    score = float(int(bool(parsed.get("score", 0))))
    reasoning = str(parsed.get("reasoning", ""))
    return score, reasoning


def eval_holistic(user_input: str, prediction: str) -> tuple[float, str]:
    """Holistic 1-10 score, normalised to 0.0–1.0. Uses stronger model."""
    user = HOLISTIC_USER.format(user_input=user_input, prediction=prediction)
    raw = call_judge(HOLISTIC_SYSTEM, user, model=JUDGE_MODEL_STRONG, timeout=90)
    parsed = extract_json(raw)
    raw_score = float(parsed.get("score", 5))
    normalised = round(max(0.0, min(10.0, raw_score)) / 10.0, 2)
    reasoning = str(parsed.get("reasoning", ""))
    return normalised, reasoning


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def evaluate_crew_output(
    langfuse_client,
    trace_id: str,
    crew_name: str,
    user_input: str,
    output_text: str,
) -> None:
    """
    Run all evaluators for the given crew and post scores to Langfuse.
    Scores appear in the Scores panel of the trace under names like:
      judge/relevance, judge/financial_accuracy, judge/overall_quality
    All exceptions are caught — must never surface errors to the UI.
    """
    if not output_text or len(output_text.strip()) < 30:
        return

    plan = CREW_EVAL_PLAN.get(crew_name, CREW_EVAL_PLAN["default"])
    prediction = output_text[:3000]  # stay within context limits

    for criterion in plan:
        try:
            if criterion == "overall_quality":
                score_value, reasoning = eval_holistic(user_input, prediction)
            else:
                score_value, reasoning = eval_criterion(
                    criterion, user_input, prediction
                )

            # Langfuse v3: create_score() posts to the Scores panel of the trace
            langfuse_client.create_score(
                trace_id=trace_id,
                name=f"judge/{criterion}",
                value=score_value,
                comment=reasoning[:600] if reasoning else None,
            )

            print(
                f"[Evaluator] {crew_name} | {criterion} "
                f"= {score_value:.2f} | trace={trace_id[:8]}…"
            )

            # Small pause between judge calls to avoid rate-limiting
            time.sleep(0.3)

        except Exception as exc:
            print(f"[Evaluator] WARN: '{criterion}' failed — {exc}")


def evaluate_crew_output_async(
    langfuse_client,
    trace_id: Optional[str],
    crew_name: str,
    user_input: str,
    output_text: str,
) -> None:
    """
    Fire-and-forget wrapper — spawns a daemon thread so evaluation never
    blocks the Streamlit response loop.
    """
    if not trace_id:
        print("[Evaluator] WARN: No trace_id — skipping evaluation.")
        return

    thread = threading.Thread(
        target=evaluate_crew_output,
        args=(langfuse_client, trace_id, crew_name, user_input, output_text),
        daemon=True,
        name=f"eval-{crew_name}-{trace_id[:6]}",
    )
    thread.start()
