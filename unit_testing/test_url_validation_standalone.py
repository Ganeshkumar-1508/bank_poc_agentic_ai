#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Standalone test for URL validation tool - no crewai dependency.
Tests the validate_urls_tool_func logic directly.
"""

import re


def validate_urls_tool_func(content: str) -> str:
    """
    Validates all URLs in the content and flags hallucinated URLs.
    Returns the content with invalid URLs replaced by **[Headline]** (no URL).
    Copied from url_validation_tool.py for standalone testing.
    """
    # Patterns for valid URLs
    valid_patterns = [
        r'/articleshow/\d+',
        r'/news/\d{4}/\d{2}/\d{2}',
        r'/article/\d+',
        r'\.cms$',
        r'\.html$',
        r'/releases/\d{4}/\d{2}/\d{2}',
    ]

    # Find all markdown links - match empty URLs too
    link_pattern = r'\[([^\]]+)\]\(([^)]*)\)'

    def check_url(match):
        headline, url = match.groups()
        if not url or url.startswith('**'):
            return f'**{headline}** (no URL available)'

        # Check if URL matches any valid pattern
        if any(re.search(p, url) for p in valid_patterns):
            return f'[{headline}]({url})'
        else:
            return f'**{headline}** (URL removed: invalid format)'

    validated = re.sub(link_pattern, check_url, content)

    if validated != content:
        return f"URLS VALIDATED: Invalid URLs removed.\n{validated}"
    return content


def test_url_validation():
    """Test the validate_urls_tool_func function"""
    print("=" * 70)
    print("Testing URL Validation Tool (Standalone)")
    print("=" * 70)

    test_cases = [
        # (input, expected_pattern, description)
        (
            "[SBI FD Rates 2026](https://www.sbi.co.in/articleshow/12345678)",
            r"\[SBI FD Rates 2026\]\(https://www\.sbi\.co\.in/articleshow/12345678\)",
            "Valid URL with articleshow pattern"
        ),
        (
            "[HDFC News](https://www.hdfc.com/news/2026/01/15/article)",
            r"\[HDFC News\]\(https://www\.hdfc\.com/news/2026/01/15/article\)",
            "Valid URL with news date pattern"
        ),
        (
            "[Fake Article](https://hallucinated-url.xyz/fake)",
            r"\*\*Fake Article\*\* \(URL removed: invalid format\)",
            "Invalid URL - should be removed"
        ),
        (
            "[Empty URL]()",
            r"\*\*Empty URL\*\* \(no URL available\)",
            "Empty URL - should show no URL available"
        ),
        (
            "[ICICI Article](https://www.icici.com/article/98765)",
            r"\[ICICI Article\]\(https://www\.icici\.com/article/98765\)",
            "Valid URL with article pattern"
        ),
        (
            "[Press Release](https://www.rbi.gov.in/releases/2026/02/01)",
            r"\[Press Release\]\(https://www\.rbi\.gov\.in/releases/2026/02/01\)",
            "Valid URL with releases date pattern"
        ),
        (
            "[Blog Post](https://example.com/blog/post)",
            r"\*\*Blog Post\*\* \(URL removed: invalid format\)",
            "Invalid URL - no matching pattern"
        ),
        (
            "[News Page](https://example.com/page.html)",
            r"\[News Page\]\(https://example\.com/page\.html\)",
            "Valid URL with .html extension"
        ),
        (
            "[CMS Content](https://example.com/article.cms)",
            r"\[CMS Content\]\(https://example\.com/article\.cms\)",
            "Valid URL with .cms extension"
        ),
    ]

    passed = 0
    failed = 0

    for i, (input_content, expected_pattern, description) in enumerate(test_cases, 1):
        try:
            result = validate_urls_tool_func(input_content)
            if re.search(expected_pattern, result):
                print(f"[PASS] Test {i}: {description}")
                print(f"  Input: {input_content}")
                print(f"  Output: {result}")
                passed += 1
            else:
                print(f"[FAIL] Test {i}: {description}")
                print(f"  Input: {input_content}")
                print(f"  Expected pattern: {expected_pattern}")
                print(f"  Got: {result}")
                failed += 1
        except Exception as e:
            print(f"[FAIL] Test {i}: {description}")
            print(f"  Input: {input_content}")
            print(f"  Error: {e}")
            failed += 1
        print()

    # Test mixed valid/invalid URLs in same content
    print("-" * 70)
    print("Testing mixed valid/invalid URLs:")
    print("-" * 70)

    mixed_content = """
    Here are some search results:
    1. [SBI FD Rates](https://www.sbi.co.in/articleshow/12345678) - Valid
    2. [Fake News](https://hallucinated.com/fake) - Invalid
    3. [HDFC Article](https://www.hdfc.com/news/2026/01/15/story) - Valid
    4. [Empty Link]() - Empty
    5. [RBI Release](https://www.rbi.gov.in/releases/2026/02/01/notice) - Valid
    """

    result = validate_urls_tool_func(mixed_content)
    print(f"Input:\n{mixed_content}")
    print(f"Output:\n{result}")

    # Check that valid URLs are preserved and invalid ones are removed
    checks = [
        (r"\[SBI FD Rates\]\(https://www\.sbi\.co\.in/articleshow/12345678\)", "Valid SBI URL preserved"),
        (r"\*\*Fake News\*\* \(URL removed: invalid format\)", "Invalid Fake News URL removed"),
        (r"\[HDFC Article\]\(https://www\.hdfc\.com/news/2026/01/15/story\)", "Valid HDFC URL preserved"),
        (r"\*\*Empty Link\*\* \(no URL available\)", "Empty URL handled"),
        (r"\[RBI Release\]\(https://www\.rbi\.gov\.in/releases/2026/02/01/notice\)", "Valid RBI URL preserved"),
    ]

    for pattern, description in checks:
        if re.search(pattern, result):
            print(f"[PASS] {description}")
            passed += 1
        else:
            print(f"[FAIL] {description}")
            print(f"  Expected pattern: {pattern}")
            failed += 1

    print()
    print("=" * 70)
    print(f"RESULTS: {passed} passed, {failed} failed")
    print("=" * 70)

    return failed == 0


if __name__ == "__main__":
    success = test_url_validation()
    exit(0 if success else 1)
