# tab_fd_advisor.py — FD Advisor Tab for Fixed Deposit Advisor
import os
import re
import json
import streamlit as st

from crews import run_crew, run_visualization_crew
from utils.report_parser import extract_structured_summary
from .config import extract_json_balanced
from .helpers import append_assistant, run_crew_with_langfuse
from .renderers import (
    parse_projection_table,
    render_bar_charts,
    export_analysis_data,
    export_report_content,
)
from tools.echarts_tool import echarts_builder_tool


# Lazy import of streamlit_echarts to avoid component registration issues
def _get_st_echarts():
    from streamlit_echarts import st_echarts

    return st_echarts


def _resolve_echarts_config(config: dict) -> dict | None:
    """
    If *config* looks like an EChartsBuilderTool INPUT (has ``"chart_type"``),
    run it through the tool and return the resulting ECharts OUTPUT dict.
    If it is already a valid ECharts output, return it as-is.
    Returns ``None`` when conversion fails or the dict is not usable.
    """
    if not isinstance(config, dict):
        return None

    # ── Tool-input signature: has "chart_type" ────────────────────────────
    if "chart_type" in config:
        try:
            raw_output = echarts_builder_tool._run(json.dumps(config))
            echarts_config = json.loads(raw_output)
            # Guard against tool errors
            if isinstance(echarts_config, dict) and not echarts_config.get("error"):
                return echarts_config
        except Exception:
            pass
        return None

    # ── Already an ECharts output? Accept if it has structural keys ────────
    if any(k in config for k in ("series", "xAxis", "yAxis", "tooltip")):
        return config

    return None


# Regex for JSON code blocks — used in multiple places below
_CODE_BLOCK_RE = re.compile(r"```(?:json)?\s*\n.*?\n\s*```", re.DOTALL)


def _strip_echarts_code_blocks(markdown_text: str) -> str:
    """Remove all ````json` code blocks from markdown text.

    These blocks typically contain raw ECharts configuration that should be
    rendered as interactive charts, not displayed as source code.
    Also collapses any resulting consecutive blank lines.
    """
    cleaned = _CODE_BLOCK_RE.sub("", markdown_text)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)  # collapse blank lines
    return cleaned.strip()


def render_fd_advisor_tab():
    """Render the FD Advisor tab."""
    # Display message history
    for idx, message in enumerate(st.session_state.messages):
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
            if "chart_options" in message and message["chart_options"]:
                chart_rendered = False
                for i, opt in enumerate(message["chart_options"]):
                    # Ensure opt is a dict (parse if it's a JSON string)
                    if isinstance(opt, str):
                        try:
                            opt = json.loads(opt)
                        except json.JSONDecodeError:
                            # Skip invalid JSON strings - these are likely data field names, not chart configs
                            continue
                            # Resolve to a proper ECharts config (handles tool-input JSON too)
                            resolved = (
                                _resolve_echarts_config(opt)
                                if isinstance(opt, dict)
                                else None
                            )
                            if resolved is not None:
                                st_echarts = _get_st_echarts()
                                st_echarts(
                                    options=resolved,
                                    height="400px",
                                    key=f"hist_viz_{idx}_{i}",
                                )
                        chart_rendered = True
                    elif isinstance(opt, dict):
                        # It's a dict but missing required ECharts keys - skip silently
                        continue
                # If no valid charts were rendered, show a helpful message
                if not chart_rendered and message.get("chart_options"):
                    st.info(
                        "💡 Tip: You can view the bar charts by scrolling up to the analysis table, or ask me to 'show bar chart comparison'"
                    )

    user_input = st.chat_input(
        "Ask about FDs, check your data, or say 'Open an account'"
    )

    if user_input:
        st.session_state.messages.append({"role": "user", "content": user_input})

        if not bool(os.getenv("NVIDIA_API_KEY")):
            append_assistant("⚠️ NVIDIA_API_KEY not found. Please configure it.")
            st.rerun()

        try:
            # ── All requests go through the manager agent for routing ──────────────────
            # The router classifies queries into: CREDIT_RISK, LOAN_CREATION, MORTGAGE_ANALYTICS,
            # ANALYSIS, RESEARCH, DATABASE, or ONBOARDING
            # Build data_context from any prior analysis stored in session
            # IMPORTANT: Use last_raw_analysis for visualization (contains full data tables)
            # Fall back to last_report_markdown if raw analysis not available
            # Use explicit checks to handle None vs empty string correctly
            _raw_analysis = st.session_state.get("last_raw_analysis")
            _report_md = st.session_state.get("last_report_markdown")
            _data_ctx = ""
            if (
                _raw_analysis
                and isinstance(_raw_analysis, str)
                and _raw_analysis.strip()
            ):
                _data_ctx = _raw_analysis
                print(
                    f"[FD Advisor] Using last_raw_analysis ({len(_raw_analysis)} chars)"
                )
            elif _report_md and isinstance(_report_md, str) and _report_md.strip():
                _data_ctx = _report_md
                print(
                    f"[FD Advisor] Using last_report_markdown ({len(_report_md)} chars)"
                )
            else:
                print("[FD Advisor] No prior analysis data found in session state")

            with st.spinner("Processing..."):
                result = run_crew_with_langfuse(
                    crew_callable=lambda: run_crew(
                        user_input,
                        region=st.session_state.get("user_region", {}).get(
                            "country_name", "Worldwide"
                        ),
                        data_context=_data_ctx,
                    ),
                    crew_name="fd-analysis-crew",
                    user_input=user_input,
                    region=st.session_state.get("user_region", {}).get(
                        "country_name", "Worldwide"
                    ),
                )

            if hasattr(result, "raw") and result.raw.strip() == "ONBOARDING":
                append_assistant(
                    "To open a new account, switch to the **New Account** tab."
                )
                st.rerun()

            elif hasattr(result, "tasks_output") and len(result.tasks_output) >= 4:
                raw_content = result.raw

                # ── Sanitize markdown for Streamlit rendering ─────────
                # 1. Fix legacy news format: combine headline + separate snippet/blockquote line
                def fix_news_format(match):
                    headline_url = match.group(1)
                    snippet = match.group(2) if match.group(2) else ""
                    if snippet:
                        return f"- {headline_url} — {snippet}"
                    return f"- {headline_url}"

                fixed_content = re.sub(
                    r"(-\s*\*\*.*?\*\*\(.*?\))\s*\n\s*(>?\s*_?Snippet:.*?)(?=\n\s*-|\n\s*##|\n\s*###|$)",
                    fix_news_format,
                    raw_content,
                    flags=re.DOTALL,
                )

                # 2. Collapse blockquote-based snippets into inline text
                fixed_content = re.sub(
                    r"\n\s*>\s*_?(.*?)_\s*\n",
                    lambda m: f" — {m.group(1)}\n" if m.group(1).strip() else "\n",
                    fixed_content,
                )

                # 3. Strip any raw HTML tags the LLM may have emitted
                fixed_content = re.sub(
                    r"<\s*/?\s*(?:br|b|i|div|span|p|em|strong)\s*/?\s*>",
                    "",
                    fixed_content,
                    flags=re.IGNORECASE,
                )

                # 4. Extract eCharts JSON from code blocks (delimiter-based, handles any nesting depth)
                code_block_pattern = r"```(?:json)?\s*\n(.*?)\n\s*```"
                all_code_blocks = re.findall(
                    code_block_pattern, fixed_content, re.DOTALL
                )

                echarts_matches = []
                for block in all_code_blocks:
                    try:
                        config = json.loads(block.strip())
                        # Use _resolve_echarts_config to handle both tool-input
                        # and already-valid ECharts output dicts
                        resolved = _resolve_echarts_config(config)
                        if resolved is not None:
                            echarts_matches.append(resolved)
                    except json.JSONDecodeError:
                        continue

                # 5. Remove eCharts code blocks from display markdown
                content_without_charts = re.sub(
                    code_block_pattern, "", fixed_content, flags=re.DOTALL
                )

                # 6. Strip raw tool-call reference lines
                content_without_charts = re.sub(
                    r"^\s*(?:apache_e_charts_configuration_builder|Apache ECharts Configuration Builder)\s*\(.*\)\s*$",
                    "",
                    content_without_charts,
                    flags=re.MULTILINE,
                )

                # 7. Collapse consecutive blank lines
                content_without_charts = re.sub(
                    r"\n{3,}", "\n\n", content_without_charts
                )

                # 8. Strip trailing whitespace per line
                content_without_charts = re.sub(
                    r"[ \t]+\n", "\n", content_without_charts
                )

                # ── Render ──────────────────────────────────────────────
                st.markdown(content_without_charts)

                # Render extracted eCharts configurations from analysis output
                chart_rendered = False
                for echarts_config in echarts_matches:
                    try:
                        st_echarts = _get_st_echarts()
                        st_echarts(options=echarts_config, height="400px")
                        chart_rendered = True
                    except Exception as e:
                        st.warning(f"Could not render chart: {str(e)[:100]}")

                if not chart_rendered and echarts_matches:
                    st.info("Chart data was found but could not be rendered.")

                # Task indices after optimization (4 tasks instead of 6):
                # [0] = query_search_task (merged parse + search)
                # [1] = projection_task
                # [2] = research_safety_task
                # [3] = summary_task
                projection_output = result.tasks_output[1].raw
                try:
                    query_search_raw = result.tasks_output[0].raw
                    tenure_match = re.search(
                        r"Tenure:\s*(\d+)", query_search_raw, re.IGNORECASE
                    )
                    if tenure_match:
                        st.session_state.last_tenure_months = int(tenure_match.group(1))
                except Exception:
                    pass

                # Store RAW analysis output for visualization BEFORE checking df
                # This ensures visualization can use existing data without re-running analysis
                st.session_state.last_raw_analysis = raw_content

                df = parse_projection_table(projection_output)
                if not df.empty:
                    st.session_state.last_analysis_data = df
                    # Extract STRUCTURED_SUMMARY and store clean report for UI display
                    clean_report, structured_data = extract_structured_summary(
                        result.raw
                    )
                    st.session_state.last_report_markdown = clean_report
                    # Store structured data for backend operations if needed
                    if structured_data:
                        st.session_state.last_structured_data = structured_data

                    # ── Run visualization crew on the analysis results ──────
                    try:
                        viz_result = run_visualization_crew(
                            user_input, data_context=raw_content
                        )
                        if hasattr(viz_result, "raw") and viz_result.raw.strip():
                            viz_raw = viz_result.raw
                            # Extract ECharts JSON configs from viz output
                            viz_code_blocks = re.findall(
                                r"```(?:json)?\s*\n(.*?)\n\s*```", viz_raw, re.DOTALL
                            )
                            for block in viz_code_blocks:
                                try:
                                    config = json.loads(block.strip())
                                    resolved = _resolve_echarts_config(config)
                                    if resolved is not None:
                                        echarts_matches.append(resolved)
                                        # Mark that we have new charts to render
                                        chart_rendered = False
                                except json.JSONDecodeError:
                                    continue
                    except Exception as viz_err:
                        print(f"[Visualization Crew] Warning: {viz_err}")

                    st.success("Analysis complete!")

                    # ── Render any additional charts from the visualization crew ──
                    if len(echarts_matches) > 0:
                        for i, echarts_config in enumerate(echarts_matches):
                            try:
                                st_echarts = _get_st_echarts()
                                st_echarts(
                                    options=echarts_config,
                                    height="400px",
                                    key=f"viz_{i}",
                                )
                            except Exception:
                                pass

                    def fmt(x):
                        return f"{x:,.2f}" if isinstance(x, (int, float)) else str(x)

                    styled_df = df.copy()
                    for col in [
                        "General Rate (%)",
                        "Senior Rate (%)",
                        "General Maturity",
                        "Senior Maturity",
                        "General Interest",
                        "Senior Interest",
                    ]:
                        if col in styled_df.columns:
                            styled_df[col] = styled_df[col].apply(fmt)
                    st.dataframe(styled_df, use_container_width=True, key="analysis_df")
                    render_bar_charts(df)

                    st.markdown("---")
                    ec1, ec2 = st.columns(2)
                    with ec1:
                        st.download_button(
                            "Download Analysis (CSV)",
                            export_analysis_data(),
                            "fd_analysis.csv",
                            "text/csv",
                        )
                    with ec2:
                        st.download_button(
                            "Download Report (MD)",
                            export_report_content(),
                            "fd_report.md",
                            "text/markdown",
                        )

                # Extract STRUCTURED_SUMMARY and store clean report for UI display
                clean_report, structured_data = extract_structured_summary(result.raw)
                # Strip raw ECharts JSON code blocks from stored report
                clean_report = _strip_echarts_code_blocks(clean_report)
                st.session_state.last_report_markdown = clean_report
                # Store structured data for backend operations if needed
                if structured_data:
                    st.session_state.last_structured_data = structured_data
                append_assistant(clean_report)
                st.rerun()
            else:
                # Handle VISUALIZATION and other single-task results
                raw_output = result.raw if hasattr(result, "raw") else str(result)

                # Try to extract ECharts configurations from the output
                viz_echarts_configs = []
                code_block_pattern = r"```(?:json)?\s*\n(.*?)\n\s*```"
                viz_code_blocks = re.findall(code_block_pattern, raw_output, re.DOTALL)

                for block in viz_code_blocks:
                    try:
                        config = json.loads(block.strip())
                        resolved = _resolve_echarts_config(config)
                        if resolved is not None:
                            viz_echarts_configs.append(resolved)
                    except json.JSONDecodeError:
                        continue

                # Render charts immediately if found
                if viz_echarts_configs:
                    st.markdown("### 📊 Visualization")
                    for i, echarts_config in enumerate(viz_echarts_configs):
                        try:
                            st_echarts = _get_st_echarts()
                            st_echarts(
                                options=echarts_config,
                                height="400px",
                                key=f"viz_result_{i}",
                            )
                        except Exception as e:
                            st.warning(f"Could not render chart: {str(e)[:100]}")

                # Store for history with chart options
                clean_report, structured_data = extract_structured_summary(raw_output)
                clean_report = _strip_echarts_code_blocks(clean_report)
                st.session_state.last_report_markdown = clean_report
                if structured_data:
                    st.session_state.last_structured_data = structured_data

                # Pass chart_options so they render in history
                if viz_echarts_configs:
                    append_assistant(
                        clean_report or "Chart generated successfully.",
                        chart_options=viz_echarts_configs,
                    )
                else:
                    append_assistant(clean_report)
            st.rerun()

        except Exception as e:
            append_assistant(f"An error occurred: {e}")
            st.rerun()
