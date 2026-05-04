import json
import re


def extract_json_balanced(text: str):
    """Extract JSON from text using balanced bracket matching."""
    # Strip markdown fences
    text = re.sub(r"```[a-z]*", "", text).strip()
    for start_char, end_char in [("[", "]"), ("{", "}")]:
        start = text.find(start_char)
        if start == -1:
            continue
        depth = 0
        in_string = False
        escape_next = False
        for i, ch in enumerate(text[start:], start):
            if escape_next:
                escape_next = False
                continue
            if ch == "\\" and in_string:
                escape_next = True
                continue
            if ch == '"':
                in_string = not in_string
                continue
            if in_string:
                continue
            if ch == start_char:
                depth += 1
            elif ch == end_char:
                depth -= 1
            if depth == 0:
                return json.loads(text[start : i + 1])
    raise ValueError("No valid JSON found in text")
