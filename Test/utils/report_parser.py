# utils/report_parser.py — Report parsing utilities
"""
Parser for extracting structured data from AI agent reports.

The extract_structured_summary function parses raw AI output to:
1. Extract STRUCTURED_SUMMARY sections (JSON data embedded in reports)
2. Return clean markdown for UI display
3. Return structured data as a dictionary for backend operations
"""

import re
import json
from typing import Tuple, Optional, Dict, Any


def extract_structured_summary(raw_output: str) -> Tuple[str, Optional[Dict[str, Any]]]:
    """
    Extract structured summary from raw AI agent output.

    Parses the raw output to find and extract STRUCTURED_SUMMARY sections,
    returning both a clean report for display and structured data for processing.

    Args:
        raw_output: The raw output string from an AI agent/crew

    Returns:
        Tuple containing:
        - clean_report (str): The report with structured sections removed,
          suitable for UI display
        - structured_data (dict or None): Parsed JSON data from STRUCTURED_SUMMARY
          sections, or None if no structured data found
    """
    if not raw_output:
        return "", None

    structured_data = None
    clean_report = raw_output

    # Pattern 1: Look for STRUCTURED_SUMMARY with JSON in code blocks
    # Example:
    # ## STRUCTURED_SUMMARY
    # ```json
    # {"key": "value"}
    # ```
    # Use a more robust pattern that handles nested braces and leading whitespace
    # Pattern matches: optional whitespace, ##, STRUCTURED_SUMMARY, newline, optional whitespace, ```json, newline, content, newline, ```
    structured_pattern = r"\s*##\s*STRUCTURED_SUMMARY\s*\n\s*```(?:json)?\s*\n([\s\S]*?)\n\s*```"
    match = re.search(structured_pattern, raw_output, re.DOTALL | re.IGNORECASE)

    if match:
        try:
            json_str = match.group(1).strip()
            structured_data = _safe_json_loads(json_str)
            if structured_data is not None:
                # Remove the entire STRUCTURED_SUMMARY section from the report
                clean_report = re.sub(
                    structured_pattern, "", raw_output, flags=re.DOTALL | re.IGNORECASE
                )
        except Exception:
            pass # Keep original output if JSON parsing fails

    # Pattern 2: Look for STRUCTURED_SUMMARY with inline JSON
    # Example:
    # ## STRUCTURED_SUMMARY
    # {"key": "value"}
    if structured_data is None:
        structured_pattern_inline = r"##\s*STRUCTURED_SUMMARY\s*\n(\{(?:[^{}]|\{[^{}]*\})*\})"
        match = re.search(
            structured_pattern_inline, raw_output, re.DOTALL | re.IGNORECASE
        )

        if match:
            try:
                json_str = match.group(1).strip()
                structured_data = _safe_json_loads(json_str)
                if structured_data is not None:
                    # Remove the entire STRUCTURED_SUMMARY section from the report
                    clean_report = re.sub(
                        structured_pattern_inline,
                        "",
                        raw_output,
                        flags=re.DOTALL | re.IGNORECASE,
                    )
            except Exception:
                pass

    # Pattern 3: Look for any JSON block at the end of the report
    # Some agents output JSON without explicit STRUCTURED_SUMMARY header
    if structured_data is None:
        json_block_pattern = r"```(?:json)?\s*\n(\{(?:[^{}]|\{[^{}]*\})*\})\s*\n```\s*$"
        match = re.search(json_block_pattern, raw_output, re.DOTALL)

        if match:
            try:
                json_str = match.group(1).strip()
                structured_data = _safe_json_loads(json_str)
                if structured_data is not None:
                    # Remove the JSON block from the report
                    clean_report = re.sub(
                        json_block_pattern, "", raw_output, flags=re.DOTALL
                    )
            except Exception:
                pass

    # Clean up excessive whitespace in the report
    clean_report = re.sub(r"\n{3,}", "\n\n", clean_report).strip()

    return clean_report, structured_data


def _safe_json_loads(json_str: str) -> Optional[Dict[str, Any]]:
    """
    Safely parse JSON string with validation.
    
    Args:
        json_str: JSON string to parse
        
    Returns:
        Parsed dict or None if parsing fails or JSON is malformed
        
    Raises:
        json.JSONDecodeError: If JSON is completely invalid
    """
    if not json_str or not isinstance(json_str, str):
        return None
        
    json_str = json_str.strip()
    
    # Check for malformed JSON patterns (like [ {...}, [...] ])
    # This catches the specific issue where LLM outputs array with mixed types
    if json_str.startswith('[') and ']' in json_str:
        try:
            parsed = json.loads(json_str)
            if isinstance(parsed, list):
                # If it's a list, try to extract valid dict objects
                for item in parsed:
                    if isinstance(item, dict):
                        return item  # Return first valid dict
                return None  # No valid dict found in list
        except json.JSONDecodeError:
            pass  # Continue to try other parsing methods
    
    # Standard JSON parsing
    parsed = json.loads(json_str)
    
    # Validate that result is a dict
    if isinstance(parsed, dict):
        return parsed
    elif isinstance(parsed, list) and parsed:
        # Try to extract first dict from list
        for item in parsed:
            if isinstance(item, dict):
                return item
    
    return None


def extract_json_from_text(text: str) -> Optional[Dict[str, Any]]:
    """
    Extract the first valid JSON object from text.

    Useful for parsing JSON that may be embedded in markdown or mixed text.

    Args:
        text: Text potentially containing JSON

    Returns:
        Parsed JSON as dictionary, or None if no valid JSON found
    """
    if not text:
        return None

    # Try to find JSON in code blocks first
    code_block_pattern = r"```(?:json)?\s*\n(.*?)\n```"
    for match in re.finditer(code_block_pattern, text, re.DOTALL):
        try:
            return json.loads(match.group(1).strip())
        except json.JSONDecodeError:
            continue

    # Try to find bare JSON objects
    brace_pattern = r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}"
    for match in re.finditer(brace_pattern, text, re.DOTALL):
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            continue

    return None


def format_structured_summary(data: Dict[str, Any]) -> str:
    """
    Format structured data as a markdown STRUCTURED_SUMMARY section.

    Args:
        data: Dictionary to format

    Returns:
        Markdown formatted string with STRUCTURED_SUMMARY header
    """
    if not data:
        return ""

    json_str = json.dumps(data, indent=2)
    return f"## STRUCTURED_SUMMARY\n```json\n{json_str}\n```"
