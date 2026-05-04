"""
Generate a sample AML Compliance PDF using the MarkdownPDFTool.
This script creates a sample AML report PDF to demonstrate the document_tool.py functionality.
"""

import sys
from pathlib import Path

# Add the Test directory to the path so we can import the tools
sys.path.insert(0, str(Path(__file__).parent))

from tools.document_tool import MarkdownPDFTool

# Sample AML compliance report markdown content
SAMPLE_MARKDOWN = """# AML Compliance Report — John Michael Smith

## Executive Summary

This report presents the findings of an automated Anti-Money Laundering (AML) compliance screening conducted on **John Michael Smith**. The screening process evaluates various risk factors including identity verification, sanctions lists, PEP (Politically Exposed Persons) databases, and adverse media mentions.

**Decision: PASS**

---

## Identity Verification

| Field | Value |
|---|---|
| Full Name | John Michael Smith |
| Date of Birth | 15 March 1978 |
| Nationality | British |
| Passport Number | GB123456789 |
| Address | 42 Westminster Avenue, London, SW1A 1AA, United Kingdom |

---

## Risk Assessment

| Risk Category | Score | Weight | Weighted Score |
|---|---|---|---|
| Geographic Risk | 25 | 30% | 7.5 |
| Product Risk | 30 | 25% | 7.5 |
| Customer Risk | 20 | 30% | 6.0 |
| Transaction Risk | 15 | 15% | 2.25 |

**Total Risk Score: 23.25 / 100**

**Risk Level: LOW**

---

## Screening Results

### Sanctions Lists
- OFAC (US): No Match
- UN Sanctions: No Match
- EU Sanctions: No Match
- UK HMT: No Match
- Interpol: No Match

### PEP Screening
- Current PEP Status: Not Found
- Historical PEP Status: Not Found
- Family/Associates: No Matches

### Adverse Media
- Negative News: None Found
- Financial Crime References: None
- Regulatory Actions: None

---

## Transaction Analysis

| Period | Total Volume | Transaction Count | Avg Transaction |
|---|---|---|---|
| Last 30 Days | $45,230 | 12 | $3,769 |
| Last 90 Days | $128,450 | 34 | $3,780 |
| Last 12 Months | $520,000 | 145 | $3,586 |

---

## Recommendations

1. **Account Status**: APPROVE - No adverse findings
2. **Enhanced Due Diligence**: Not Required
3. **Ongoing Monitoring**: Standard periodic review (annual)
4. **Next Review Date**: April 2027

---

## Compliance Notes

The subject has been screened against all required databases as of the report date. No adverse matches or elevated risk indicators were identified. The customer profile is consistent with expected activity for their stated business purpose.

Risk Score: 23 / 100
"""


def generate_sample_pdf():
    """Generate a sample AML compliance PDF."""
    print("Initializing MarkdownPDFTool...")
    tool = MarkdownPDFTool()

    print("Generating sample PDF...")
    result = tool._run(
        title="AML Compliance Report - John Smith",
        markdown_content=SAMPLE_MARKDOWN,
        filename="john_smith_sample",
    )

    print(f"\nResult: {result}")

    if result and not result.startswith("Error"):
        print(f"\n✓ Sample PDF successfully generated at: {result}")
        return result
    else:
        print(f"\n✗ Failed to generate PDF: {result}")
        return None


if __name__ == "__main__":
    generate_sample_pdf()
