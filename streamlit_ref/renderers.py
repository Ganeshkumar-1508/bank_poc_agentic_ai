# renderers.py — Parse and Render Helpers for Fixed Deposit Advisor
import io
import re
import json
import pandas as pd
import streamlit as st

from .config import RISK_COLORS, DECISION_COLORS
from .helpers import get_currency_symbol


# Lazy import of streamlit_echarts to avoid component registration issues
def _get_echarts():
    from streamlit_echarts import st_echarts, JsCode

    return st_echarts, JsCode


# =============================================================================
# PARSE & RENDER HELPERS
# =============================================================================


def format_news_for_display(news_content: str) -> str:
    """
    Format news content for proper display in Streamlit markdown.
    Ensures headline, URL, and snippet are contained within a single entry.

    Converts multi-line news items into a compact format that doesn't break table alignment.

    Args:
        news_content: Raw news content with headlines, URLs, and snippets

    Returns:
        Formatted news content suitable for table cells
    """
    if not news_content:
        return ""

    # If already in proper format, return as-is
    # Format: - **[Headline]**(URL)\n  > _Snippet: ..._

    lines = news_content.split("\n")
    formatted_items = []
    current_item = []

    for line in lines:
        stripped = line.strip()

        # Start of a new news item (starts with "- **")
        if stripped.startswith("- **") and "(" in stripped:
            if current_item:
                # Join previous item into a single line with <br> for line breaks
                formatted_items.append(" ".join(current_item))
            current_item = [stripped]
        elif stripped.startswith(">") or stripped.startswith("_Snippet:"):
            # Continuation of snippet - add to current item
            current_item.append(stripped)
        elif stripped and current_item:
            # Additional content for current item
            current_item.append(stripped)

    # Don't forget the last item
    if current_item:
        formatted_items.append(" ".join(current_item))

    # Join items with HTML line breaks for proper rendering
    if formatted_items:
        return "<br><br>".join(formatted_items)

    return news_content


def clean_news_for_table(news_content: str) -> str:
    """
    Clean news content to ensure it displays properly in table cells.
    Replaces newlines with <br> and escapes problematic characters.

    Args:
        news_content: Raw news content

    Returns:
        Cleaned HTML-safe news content
    """
    if not news_content:
        return ""

    # Replace markdown blockquotes with plain text
    news_content = news_content.replace("> _Snippet:", "Snippet:").replace("_", "")

    # Replace newlines within news items with <br>
    # But keep separation between different news items
    lines = news_content.split("\n")
    cleaned_lines = []

    for line in lines:
        stripped = line.strip()
        if stripped:
            # Replace multiple spaces with single space
            stripped = " ".join(stripped.split())
            cleaned_lines.append(stripped)

    return "<br>".join(cleaned_lines)


def parse_projection_table(text: str) -> pd.DataFrame:
    try:
        clean = text.replace("```csv", " ").replace("```", " ").strip()
        lines = clean.splitlines()
        header_idx = next(
            (i for i, l in enumerate(lines) if "Provider" in l and "Rate" in l), 0
        )
        clean = "\n".join(lines[header_idx:])
        df = pd.read_csv(io.StringIO(clean))
        df.columns = [c.strip() for c in df.columns]
        required = {
            "Provider",
            "General Rate (%)",
            "Senior Rate (%)",
            "General Maturity",
            "Senior Maturity",
            "General Interest",
            "Senior Interest",
        }
        if not required.issubset(df.columns):
            return pd.DataFrame()
        numeric_cols = list(required - {"Provider"})
        for col in numeric_cols:
            df[col] = pd.to_numeric(
                df[col]
                .astype(str)
                .str.replace(",", "")
                .str.replace("N/A", "")
                .str.strip(),
                errors="coerce",
            )
        df = df.dropna(subset=numeric_cols, how="all").reset_index(drop=True)
        return df
    except Exception:
        return pd.DataFrame()


def render_bar_charts(df: pd.DataFrame):
    numeric_cols = [
        "General Maturity",
        "Senior Maturity",
        "General Interest",
        "Senior Interest",
    ]
    df = df.dropna(subset=numeric_cols).head(10).copy()
    if df.empty:
        st.warning("No projection data available to chart.")
        return
    sym = get_currency_symbol()
    providers_list = df["Provider"].tolist()
    st_echarts, JsCode = _get_echarts()
    axis_fmt = JsCode(f"function(v){{return '{sym}'+(v/1000).toFixed(0)+'K';}}")
    tooltip_fn = JsCode(
        f"function(params){{var s=params[0].axisValue+'<br/>';"
        f"params.forEach(function(p){{s+=p.marker+p.seriesName+': {sym}'"
        f"+p.value.toLocaleString(undefined,{{maximumFractionDigits:0}})+'<br/>';}});"
        f"return s;}}"
    )
    st.markdown("### Maturity & Interest Breakdown")
    col1, col2 = st.columns(2)
    for col, label, mat_col, int_col, mat_color, int_color, key in [
        (
            col1,
            "General",
            "General Maturity",
            "General Interest",
            "#3B82F6",
            "#93C5FD",
            "ec_general",
        ),
        (
            col2,
            "Senior Citizen",
            "Senior Maturity",
            "Senior Interest",
            "#EF4444",
            "#FCA5A5",
            "ec_senior",
        ),
    ]:
        with col:
            st.markdown(f"#### {label}")
            st_echarts(
                options={
                    "tooltip": {
                        "trigger": "axis",
                        "axisPointer": {"type": "shadow"},
                        "formatter": tooltip_fn,
                    },
                    "legend": {
                        "data": ["Maturity Amount", "Interest Earned"],
                        "bottom": 0,
                    },
                    "grid": {
                        "left": "3%",
                        "right": "4%",
                        "bottom": "15%",
                        "containLabel": True,
                    },
                    "xAxis": {
                        "type": "category",
                        "data": providers_list,
                        "axisLabel": {"rotate": 35, "interval": 0, "fontSize": 10},
                    },
                    "yAxis": {
                        "type": "value",
                        "name": f"Amount ({sym})" if sym else "Amount",
                        "axisLabel": {"formatter": axis_fmt},
                    },
                    "series": [
                        {
                            "name": "Maturity Amount",
                            "type": "bar",
                            "data": df[mat_col].round(0).tolist(),
                            "itemStyle": {"color": mat_color},
                        },
                        {
                            "name": "Interest Earned",
                            "type": "bar",
                            "data": df[int_col].round(0).tolist(),
                            "itemStyle": {"color": int_color},
                        },
                    ],
                },
                height="380px",
                key=key,
            )


def export_analysis_data():
    if st.session_state.get("last_analysis_data") is not None:
        return st.session_state.last_analysis_data.to_csv(index=False).encode("utf-8")
    return b""


def export_report_content():
    if st.session_state.messages:
        for msg in reversed(st.session_state.messages):
            if msg["role"] == "assistant" and len(msg["content"]) > 50:
                return msg["content"].encode("utf-8")
    return b"No report available."


def risk_badge(band: str) -> str:
    bg, fg = RISK_COLORS.get(band.upper(), ("#E5E7EB", "#374151"))
    return f'<span class="badge" style="background:{bg};color:{fg}">{band}</span>'


def decision_badge(decision: str) -> str:
    bg, fg = DECISION_COLORS.get(decision.upper(), ("#E5E7EB", "#374151"))
    return f'<span class="badge" style="background:{bg};color:{fg}">{decision}</span>'
