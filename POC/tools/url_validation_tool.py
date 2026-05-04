from crewai.tools import tool
import re

@tool("URL Validator")
def validate_urls(content: str) -> str:
    """
    Validates all URLs in the content and flags hallucinated URLs.
    Returns the content with invalid URLs replaced by **[Headline]** (no URL).
    Use this tool BEFORE submitting your output to catch hallucinated URLs.
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

    # Find all markdown links
    # Match markdown links: [headline](url) where url can be empty
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
