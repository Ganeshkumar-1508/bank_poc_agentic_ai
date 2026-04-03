# tools/kyc_tool.py
# ---------------------------------------------------------------------------
# KYC document vision extraction via NVIDIA ministral-14b-instruct-2512.
# ---------------------------------------------------------------------------

import os
import re
import json
import base64
import requests
from pathlib import Path
from typing import Type, Dict

from crewai.tools import BaseTool
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

NVIDIA_VISION_URL   = "https://integrate.api.nvidia.com/v1/chat/completions"
NVIDIA_VISION_MODEL = "mistralai/ministral-14b-instruct-2512"

_MIME_MAP: Dict[str, str] = {
    ".jpg":  "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png":  "image/png",
    ".webp": "image/webp",
    ".gif":  "image/gif",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_mime(filename: str) -> str:
    """Return MIME type string for a given filename/path."""
    return _MIME_MAP.get(Path(filename).suffix.lower(), "image/jpeg")


def _resize_image_for_vision(image_bytes: bytes, mime_type: str, max_px: int = 1024) -> tuple:
    """
    Resize image so its longest edge is at most max_px pixels, then re-encode
    as JPEG at quality=85 to keep the base64 payload small.
    Falls back to original bytes if Pillow is unavailable or image is already small.
    """
    try:
        from PIL import Image
        import io as _io
        img = Image.open(_io.BytesIO(image_bytes))
        w, h = img.size
        if max(w, h) > max_px:
            scale = max_px / max(w, h)
            img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
        if img.mode in ("RGBA", "P", "LA"):
            img = img.convert("RGB")
        buf = _io.BytesIO()
        img.save(buf, format="JPEG", quality=85, optimize=True)
        return buf.getvalue(), "image/jpeg"
    except Exception:
        return image_bytes, mime_type


def extract_kyc_from_image(
    image_bytes: bytes,
    mime_type: str = "image/jpeg",
    doc_hint: str = "",
) -> dict:
    """
    Sends a KYC document image to the NVIDIA vision model and returns
    structured extraction results as a plain dict.

    Args:
        image_bytes : Raw bytes of the uploaded image.
        mime_type   : MIME type, e.g. "image/png".
        doc_hint    : Optional document-type hint (e.g. "Aadhaar Card").

    Returns a dict with keys:
        doc_type      – document type as printed / detected
        doc_number    – primary unique ID / number
        full_name     – name as it appears on the document
        date_of_birth – YYYY-MM-DD or null
        expiry_date   – YYYY-MM-DD or null
        confidence    – HIGH | MEDIUM | LOW
        error         – present only when the call fails
    """
    api_key = os.getenv("NVIDIA_API_KEY")
    if not api_key:
        return {"error": "NVIDIA_API_KEY environment variable not set."}

    image_bytes, mime_type = _resize_image_for_vision(image_bytes, mime_type)
    image_b64  = base64.b64encode(image_bytes).decode()
    hint_clause = f" This is expected to be a '{doc_hint}'." if doc_hint else ""

    prompt = (
        f"You are a KYC document verification specialist.{hint_clause} "
        "Carefully analyse the document image and extract the fields below. "
        "Return ONLY a valid JSON object with exactly these keys — "
        "no markdown, no explanation:\n"
        "{\n"
        '  "doc_type": "exact document name visible on the document",\n'
        '  "doc_number": "the primary unique ID / serial number",\n'
        '  "full_name": "full name as printed on the document",\n'
        '  "date_of_birth": "DOB in YYYY-MM-DD format or null if not visible",\n'
        '  "expiry_date": "expiry date in YYYY-MM-DD or null if not applicable",\n'
        '  "confidence": "HIGH if all fields clearly readable, '
        'MEDIUM if some fields unclear, LOW if image quality is poor"\n'
        "}"
    )

    payload = {
        "model": NVIDIA_VISION_MODEL,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{image_b64}"}},
                ],
            }
        ],
        "max_tokens":        512,
        "temperature":       0.10,
        "top_p":             1.00,
        "frequency_penalty": 0.00,
        "presence_penalty":  0.00,
        "stream":            False,
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type":  "application/json",
        "Accept":        "application/json",
    }

    try:
        resp = requests.post(NVIDIA_VISION_URL, headers=headers, json=payload, timeout=30)
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"].strip()

        if "```" in content:
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
            content = content.strip()

        m = re.search(r"\{.*\}", content, re.DOTALL)
        if m:
            return json.loads(m.group(0))

        return {"error": "Model returned non-JSON output.", "raw": content[:300]}

    except requests.exceptions.Timeout:
        return {"error": "Request timed out (30 s). Try a smaller or clearer image."}
    except requests.exceptions.HTTPError as exc:
        return {"error": f"NVIDIA API HTTP {exc.response.status_code}: {exc.response.text[:200]}"}
    except json.JSONDecodeError as exc:
        return {"error": f"JSON parse error: {exc}"}
    except Exception as exc:
        return {"error": f"Unexpected error: {str(exc)}"}


# ---------------------------------------------------------------------------
# Input schema + CrewAI tool
# ---------------------------------------------------------------------------

class KYCVisionInput(BaseModel):
    image_path: str = Field(..., description="Absolute path to the KYC document image file.")
    doc_hint: str = Field(
        default="",
        description="Optional document type hint shown to the model, e.g. 'Aadhaar Card' or 'Passport'.",
    )


class KYCVisionTool(BaseTool):
    """
    CrewAI tool wrapper around extract_kyc_from_image().
    Accepts an image file path so agents in the AML / onboarding pipeline
    can trigger vision-based document verification mid-workflow.
    """
    name: str = "KYC Document Vision Extractor"
    description: str = (
        "Extracts structured identity information from a KYC document image "
        "using NVIDIA ministral-14b-instruct-2512 vision model. "
        "Input: image_path (absolute path to the image file) and an optional "
        "doc_hint (e.g. 'Aadhaar Card', 'Passport'). "
        "Returns JSON with doc_type, doc_number, full_name, date_of_birth, "
        "expiry_date, and confidence (HIGH / MEDIUM / LOW)."
    )
    args_schema: Type[BaseModel] = KYCVisionInput

    def _run(self, image_path: str, doc_hint: str = "") -> str:
        try:
            path = Path(image_path)
            if not path.exists():
                return json.dumps({"error": f"File not found: {image_path}"})
            mime_type   = _get_mime(path.name)
            image_bytes = path.read_bytes()
            result      = extract_kyc_from_image(image_bytes, mime_type, doc_hint)
            return json.dumps(result, indent=2)
        except Exception as exc:
            return json.dumps({"error": f"KYCVisionTool failed: {str(exc)}"})
