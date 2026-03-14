# app.py
import os
import re
import sqlite3
import json
import random
import requests
import pandas as pd
import streamlit as st
from pathlib import Path
from dotenv import load_dotenv
from streamlit_echarts import st_echarts, JsCode
from datetime import datetime, timedelta
from crews import run_crew, FixedDepositCrews
from tools import extract_json_balanced, set_search_region, fetch_country_data
from langchain_nvidia_ai_endpoints import ChatNVIDIA

# =============================================================================
# LANGFUSE INTEGRATION
# =============================================================================
# Assuming langfuse_instrumentation.py is in the same directory
try:
    from langfuse_instrumentation import instrument_crewai, get_langfuse_client
    from langfuse import propagate_attributes
    from langfuse_evaluator import evaluate_crew_output_async
except ImportError as _import_err:
    st.error(
        f"Missing dependency: {_import_err}. "
        "Ensure langfuse_instrumentation.py, langfuse_evaluator.py, and the "
        "'langfuse' / 'langchain' packages are installed."
    )
    st.stop()

load_dotenv()

# Initialize Langfuse once at startup
instrument_crewai()
langfuse = get_langfuse_client()

# =============================================================================
# DATABASE & CONFIG
# =============================================================================
DB_PATH = Path(__file__).resolve().parent / "bank_poc.db"

# =============================================================================
# GEOLOCATION & REGION DETECTION
# =============================================================================
def detect_user_region() -> dict:
    countries = fetch_country_data()
    try:
        resp = requests.get("https://ipinfo.io/json", timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            cc = data.get("country", "WW").upper()
            info = countries.get(cc, {})
            ddg = set_search_region(cc)
            return {
                "country_code": cc,
                "country_name": info.get("name", cc),
                "ddg_region": ddg,
                "currency_symbol": info.get("currency_symbol", ""),
                "currency_code": info.get("currency_code", ""),
            }
    except Exception:
        pass
    return {
        "country_code": "WW",
        "country_name": "Worldwide",
        "ddg_region": "wt-wt",
        "currency_symbol": "",
        "currency_code": "",
    }

if "user_region" not in st.session_state:
    st.session_state.user_region = detect_user_region()
else:
    set_search_region(st.session_state.user_region["country_code"])

# Initialize Langfuse Session/User IDs if not present
if "langfuse_session_id" not in st.session_state:
    st.session_state.langfuse_session_id = f"fd-session-{st.session_state.user_region.get('country_code', 'WW')}-{os.urandom(4).hex()}"

if "langfuse_user_id" not in st.session_state:
    # Default to session ID if no user login exists
    st.session_state.langfuse_user_id = st.session_state.langfuse_session_id

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

st.set_page_config(
    page_title="Fixed Deposit Advisor",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
    <style>
    .main-header { font-size: 2.5rem !important; color: #1E3A8A; margin-bottom: 1rem; }
    .sub-header { font-size: 1.5rem; color: #3B82F6; margin-top: 1rem; margin-bottom: 0.5rem; }
    </style>
""", unsafe_allow_html=True)

st.markdown('<h1 class="main-header">Fixed Deposit Advisor</h1>', unsafe_allow_html=True)

if "messages" not in st.session_state:
    st.session_state.messages = []

if "last_analysis_data" not in st.session_state:
    st.session_state.last_analysis_data = None

if "last_tenure_months" not in st.session_state:
    st.session_state.last_tenure_months = 12

def get_currency_symbol() -> str:
    return st.session_state.get("user_region", {}).get("currency_symbol", "")

def reset_session():
    st.session_state.messages = []
    if "ONBOARDING_FLOW" in st.session_state:
        del st.session_state["ONBOARDING_FLOW"]
    if "last_analysis_data" in st.session_state:
        del st.session_state["last_analysis_data"]
    if "last_tenure_months" in st.session_state:
        del st.session_state["last_tenure_months"]
    if "PENDING_AML_JSON" in st.session_state:
        del st.session_state["PENDING_AML_JSON"]
    # Reset Langfuse IDs on session reset
    if "langfuse_session_id" in st.session_state:
        del st.session_state["langfuse_session_id"]
    if "langfuse_user_id" in st.session_state:
        del st.session_state["langfuse_user_id"]
    st.rerun()

# =============================================================================
# LANGFUSE WRAPPER HELPER
# =============================================================================

def run_crew_with_langfuse(
    crew_callable,
    crew_name: str,
    user_input: str = "",
    region: str = "Worldwide",
    extra_metadata: dict = None,
):
    """
    Wraps a crew execution in a Langfuse Trace with Session/User context.
    """
    session_id = st.session_state.get("langfuse_session_id")
    user_id = st.session_state.get("langfuse_user_id")

    metadata = {
        "region": region,
        "crew_name": crew_name,
        "streamlit_session": "active",
    }
    if extra_metadata:
        metadata.update(extra_metadata)

    # Start a Trace
    # Note: session_id and user_id are not accepted as constructor kwargs in Langfuse v3.
    # They must be set via trace.update() after the span is opened.
    output_text = None
    trace_id = None

    with langfuse.start_as_current_observation(
        as_type="trace",
        name=crew_name,
        input={"user_input": user_input},
        metadata=metadata,
    ) as trace:
        # Attach session/user context at the trace level
        trace.update(session_id=session_id, user_id=user_id)

        # Capture trace ID now; the async evaluator posts scores after
        # the context manager exits (trace must be finalised first)
        trace_id = getattr(trace, "trace_id", None) or getattr(trace, "id", None)

        # Propagate attributes to nested spans (CrewAI tasks/agents)
        with propagate_attributes(
            session_id=session_id,
            user_id=user_id,
        ):
            # Execute the crew
            result = crew_callable()

            # Capture output for both trace logging and LLM-as-a-judge
            if hasattr(result, "raw"):
                output_text = result.raw
            elif isinstance(result, str):
                output_text = result

            if output_text:
                trace.update(output={"output": output_text[:2000]})

    # Flush trace to Langfuse before evaluation scores are posted against it
    langfuse.flush()

    # -----------------------------------------------------------------------
    # LLM-as-a-Judge evaluation (async — never blocks the Streamlit UI)
    # Criteria and holistic scores are posted to the "Scores" panel in
    # the Langfuse trace dashboard under names like judge/relevance,
    # judge/financial_accuracy, judge/overall_quality, etc.
    # -----------------------------------------------------------------------
    evaluate_crew_output_async(
        langfuse_client=langfuse,
        trace_id=trace_id,
        crew_name=crew_name,
        user_input=user_input,
        output_text=output_text or "",
    )

    return result

@st.cache_data(ttl=3600)
def get_dynamic_kyc_docs(country_name: str) -> tuple:
    """
    Returns the two mandatory KYC documents for a given country.

    Strategy (in order):
      1. LLM direct knowledge  — fast, no search needed, works for every country.
      2. LLM + web search      — fallback if step 1 returns unparseable output.
      3. Generic labels        — only if both LLM calls fail entirely.

    The cache key is `country_name`, so each country is fetched once per hour.
    """
    if not os.getenv("NVIDIA_API_KEY"):
        return ("Government-issued Photo ID", "Proof of Address")

    llm = ChatNVIDIA(model="meta/llama-3.1-8b-instruct")

    def _parse_docs(text: str) -> tuple | None:
        """Extract a (doc1, doc2) tuple from LLM output. Returns None on failure."""
        text = text.strip()
        # Strip markdown fences
        for fence in ("```json", "```"):
            if fence in text:
                text = text.split(fence)[1].split("```")[0].strip()
                break
        # Find the JSON array anywhere in the response
        import re as _re
        match = _re.search(r'\[.*?\]', text, _re.DOTALL)
        if match:
            text = match.group(0)
        try:
            docs = json.loads(text)
            if isinstance(docs, list) and len(docs) >= 2:
                d1, d2 = str(docs[0]).strip(), str(docs[1]).strip()
                # Reject obviously generic fallback values
                generic = {"national id card", "proof of address",
                           "government-issued photo id", "passport"}
                if d1.lower() not in generic or d2.lower() not in generic:
                    return (d1, d2)
        except (json.JSONDecodeError, ValueError):
            pass
        return None

    # ── Step 1: LLM direct knowledge ─────────────────────────────────────────
    try:
        direct_prompt = (
            f"You are a banking compliance expert with deep knowledge of global KYC regulations.\n\n"
            f"What are the TWO primary mandatory government-issued identity documents that banks in "
            f"'{country_name}' require from customers for KYC (Know Your Customer) verification "
            f"when opening a bank account?\n\n"
            f"Rules:\n"
            f"- Use the official local document name (e.g. 'Aadhaar Card', 'PAN Card', "
            f"'Emirates ID', 'SSN', 'CNIC', 'CPF', etc.).\n"
            f"- Do NOT return generic terms like 'National ID' or 'Proof of Address' — "
            f"use the specific, country-issued document name.\n"
            f"- Return ONLY a raw JSON array with exactly two strings. "
            f"No explanation, no markdown, no extra text.\n"
            f"Example for India: [\"Aadhaar Card\", \"PAN Card\"]\n"
            f"Example for UAE:   [\"Emirates ID\", \"Passport\"]\n"
            f"Now respond for: {country_name}"
        )
        response = llm.invoke(direct_prompt)
        result = _parse_docs(response.content)
        if result:
            return result
        print(f"[KYC] Step 1 unparseable for '{country_name}': {response.content[:120]}")
    except Exception as e:
        print(f"[KYC] Step 1 failed for '{country_name}': {e}")

    # ── Step 2: LLM + web search ──────────────────────────────────────────────
    try:
        from tools import search_news
        query = f"mandatory KYC documents bank account opening {country_name} official government ID"
        search_context = search_news(query)

        search_prompt = (
            f"You are a banking compliance expert. Based on the search results below, "
            f"identify the TWO primary government-issued identity documents that banks in "
            f"'{country_name}' require for KYC verification.\n\n"
            f"Search Results:\n{search_context}\n\n"
            f"Rules:\n"
            f"- Use the official local document name — not generic terms.\n"
            f"- Return ONLY a raw JSON array with exactly two strings. No markdown.\n"
            f"Example: [\"Aadhaar Card\", \"PAN Card\"]"
        )
        response = llm.invoke(search_prompt)
        result = _parse_docs(response.content)
        if result:
            return result
        print(f"[KYC] Step 2 unparseable for '{country_name}': {response.content[:120]}")
    except Exception as e:
        print(f"[KYC] Step 2 failed for '{country_name}': {e}")

    # ── Step 3: hard fallback ─────────────────────────────────────────────────
    print(f"[KYC] All steps failed for '{country_name}' — using generic fallback.")
    return ("Government-issued Photo ID", "Proof of Address")

# =============================================================================
# TABS
# =============================================================================
tab1, tab2, tab3 = st.tabs(["FD Advisor", "Peer Analysis", "New Account"])

@st.cache_resource
def get_crews():
    return FixedDepositCrews()

def clean_response(raw: str) -> str:
    text = raw.strip()
    for prefix in ("QUESTION:", "DATA_READY:"):
        if text.startswith(prefix):
            text = text[len(prefix):].strip()
            break
    return text

def append_assistant(text: str, chart_options=None):
    msg = {"role": "assistant", "content": text}
    if chart_options:
        msg["chart_options"] = chart_options # Expecting a list of options now
    st.session_state.messages.append(msg)

# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def parse_projection_table(text: str) -> pd.DataFrame:
    """Parses the projection CSV output into a DataFrame. Rows with all-NaN numerics are dropped."""
    try:
        import io
        clean = text.replace("```csv", " ").replace("```", " ").strip()
        # Strip any leading non-CSV lines (agent preamble text)
        lines = clean.splitlines()
        header_idx = next(
            (i for i, l in enumerate(lines) if "Provider" in l and "Rate" in l), 0
        )
        clean = "\n".join(lines[header_idx:])

        df = pd.read_csv(io.StringIO(clean))
        df.columns = [c.strip() for c in df.columns]

        required = {
            "Provider", "General Rate (%)", "Senior Rate (%)",
            "General Maturity", "Senior Maturity",
            "General Interest", "Senior Interest"
        }

        if not required.issubset(df.columns):
            st.warning(f"Missing columns in projection output. Found: {list(df.columns)}")
            return pd.DataFrame()

        numeric_cols = list(required - {"Provider"})
        for col in numeric_cols:
            df[col] = pd.to_numeric(
                df[col].astype(str).str.replace(",", "").str.replace("N/A", "").str.strip(),
                errors="coerce"
            )

        # Drop rows where ALL numeric columns are NaN (provider had no confirmed rates)
        df = df.dropna(subset=numeric_cols, how="all").reset_index(drop=True)
        return df
    except Exception as e:
        st.warning(f"Parse error: {e}")
        return pd.DataFrame()

def render_bar_charts(df: pd.DataFrame):
    """
    Renders 2 grouped bar charts side by side:
      - General: Maturity Amount + Interest Earned
      - Senior:  Maturity Amount + Interest Earned
    Rows with NaN in any numeric column are silently dropped.
    """
    numeric_cols = ["General Maturity", "Senior Maturity", "General Interest", "Senior Interest"]
    df = df.dropna(subset=numeric_cols).head(10).copy()

    if df.empty:
        st.warning(
            "⚠️ No projection data with confirmed rates available to chart. "
            "The providers found may not have publicly disclosed rates for this region. "
            "Try a different region or tenure in your query."
        )
        return

    sym = get_currency_symbol()
    providers_list = df["Provider"].tolist()

    fmt_js   = JsCode(f"function(v){{return '{sym}'+v.toLocaleString(undefined,{{maximumFractionDigits:0}});}}")
    axis_fmt = JsCode(f"function(v){{return '{sym}'+(v/1000).toFixed(0)+'K';}}")
    tooltip_fn = JsCode(
        f"function(params){{"
        f"var s=params[0].axisValue+'<br/>';"
        f"params.forEach(function(p){{s+=p.marker+p.seriesName+': {sym}'+p.value.toLocaleString(undefined,{{maximumFractionDigits:0}})+'<br/>';}});"
        f"return s;}}"
    )

    st.markdown("### Maturity & Interest Breakdown")
    col1, col2 = st.columns(2)

    with col1:
        st.markdown("#### General")
        st_echarts(options={
            "tooltip": {"trigger": "axis", "axisPointer": {"type": "shadow"}, "formatter": tooltip_fn},
            "legend": {"data": ["Maturity Amount", "Interest Earned"], "bottom": 0},
            "grid": {"left": "3%", "right": "4%", "bottom": "15%", "containLabel": True},
            "xAxis": {
                "type": "category", "data": providers_list,
                "axisLabel": {"rotate": 35, "interval": 0, "fontSize": 10}
            },
            "yAxis": {
                "type": "value",
                "name": f"Amount ({sym})" if sym else "Amount",
                "axisLabel": {"formatter": axis_fmt}
            },
            "series": [
                {"name": "Maturity Amount", "type": "bar",
                 "data": df["General Maturity"].round(0).tolist(),
                 "itemStyle": {"color": "#3B82F6"}},
                {"name": "Interest Earned", "type": "bar",
                 "data": df["General Interest"].round(0).tolist(),
                 "itemStyle": {"color": "#93C5FD"}},
            ]
        }, height="380px", key="ec_general")

    with col2:
        st.markdown("#### Senior Citizen")
        st_echarts(options={
            "tooltip": {"trigger": "axis", "axisPointer": {"type": "shadow"}, "formatter": tooltip_fn},
            "legend": {"data": ["Maturity Amount", "Interest Earned"], "bottom": 0},
            "grid": {"left": "3%", "right": "4%", "bottom": "15%", "containLabel": True},
            "xAxis": {
                "type": "category", "data": providers_list,
                "axisLabel": {"rotate": 35, "interval": 0, "fontSize": 10}
            },
            "yAxis": {
                "type": "value",
                "name": f"Amount ({sym})" if sym else "Amount",
                "axisLabel": {"formatter": axis_fmt}
            },
            "series": [
                {"name": "Maturity Amount", "type": "bar",
                 "data": df["Senior Maturity"].round(0).tolist(),
                 "itemStyle": {"color": "#EF4444"}},
                {"name": "Interest Earned", "type": "bar",
                 "data": df["Senior Interest"].round(0).tolist(),
                 "itemStyle": {"color": "#FCA5A5"}},
            ]
        }, height="380px", key="ec_senior")

def export_analysis_data():
    if st.session_state.get("last_analysis_data") is not None:
        return st.session_state.last_analysis_data.to_csv(index=False).encode('utf-8')
    return b""

def export_report_content():
    if st.session_state.messages:
        for msg in reversed(st.session_state.messages):
            if msg["role"] == "assistant" and len(msg["content"]) > 50:
                return msg["content"].encode('utf-8')
    return b"No report available."

# =============================================================================
# TAB 1: FD Advisor Chat Interface
# =============================================================================
with tab1:
    for idx, message in enumerate(st.session_state.messages):
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
            # Handle multiple charts
            if "chart_options" in message and message["chart_options"]:
                for i, opt in enumerate(message["chart_options"]):
                    st_echarts(options=opt, height="400px", key=f"hist_viz_{idx}_{i}")

    user_input = st.chat_input("Ask about FDs, check your data, or say 'Open an account'")

    if user_input:
        st.session_state.messages.append({"role": "user", "content": user_input})

        if not bool(os.getenv("NVIDIA_API_KEY")):
            append_assistant("WARNING: NVIDIA_API_KEY not found. Please configure it to use AI features.")
            st.rerun()

        crews = get_crews()

        try:
            viz_keywords = ["plot", "chart", "graph", "visualize", "show me",
                           "donut", "pie", "line", "bar", "break down"]
            if any(kw in user_input.lower() for kw in viz_keywords):
                with st.spinner("Generating chart..."):
                    data_json = (
                        st.session_state.last_analysis_data.to_json(orient="records") 
                        if st.session_state.last_analysis_data is not None else "None"
                    )
                    
                    # --- WRAPPED VISUALIZATION CALL ---
                    viz_result = run_crew_with_langfuse(
                        crew_callable=lambda: crews.get_visualization_crew(user_input, data_json).kickoff(),
                        crew_name="fd-visualization-crew",
                        user_input=user_input,
                        region=st.session_state.get("user_region", {}).get("country_name", "Worldwide"),
                        extra_metadata={"has_data_context": data_json != "None"}
                    )

                try:
                    # Expecting a list of JSONs now
                    chart_options_raw = extract_json_balanced(viz_result.raw)
                    
                    # Handle single object or list of objects
                    if isinstance(chart_options_raw, list):
                        chart_options = chart_options_raw
                    else:
                        chart_options = [chart_options_raw]
                        
                    append_assistant(f"Here are the visualizations for: {user_input}", chart_options)
                except Exception as e:
                    append_assistant(f"Sorry, I couldn't generate that chart. ({e}) ")
                st.rerun()

            else:
                with st.spinner("Processing..."):
                    # --- WRAPPED ANALYSIS CALL ---
                    result = run_crew_with_langfuse(
                        crew_callable=lambda: run_crew(
                            user_input,
                            region=st.session_state.get("user_region", {}).get("country_name", "Worldwide")
                        ),
                        crew_name="fd-analysis-crew",
                        user_input=user_input,
                        region=st.session_state.get("user_region", {}).get("country_name", "Worldwide")
                    )

                if hasattr(result, "raw") and result.raw.strip() == "ONBOARDING":
                    append_assistant("To open a new account, please switch to the 'New Account' tab and fill out the form.")
                    st.rerun()

                elif hasattr(result, "tasks_output") and len(result.tasks_output) >= 5:
                    st.markdown(result.raw)
                    projection_output = result.tasks_output[4].raw

                    # Extract tenure from the parse task output (task index 0)
                    # Format: "Type: FD, Amount: 100000, Tenure: 24, Compounding: quarterly"
                    try:
                        parse_raw = result.tasks_output[0].raw
                        tenure_match = re.search(r"Tenure:\s*(\d+)", parse_raw, re.IGNORECASE)
                        if tenure_match:
                            st.session_state.last_tenure_months = int(tenure_match.group(1))
                    except Exception:
                        pass  # keep previous value

                    df = parse_projection_table(projection_output)
                    
                    if not df.empty:
                        st.session_state.last_analysis_data = df
                        st.success("Analysis complete! Charts generated below.")
                        
                        def fmt(x):
                            return f"{x:,.2f}" if isinstance(x, (int, float)) else str(x)

                        styled_df = df.copy()
                        for col in ["General Rate (%)", "Senior Rate (%)",
                                    "General Maturity", "Senior Maturity",
                                    "General Interest", "Senior Interest"]:
                            if col in styled_df.columns:
                                styled_df[col] = styled_df[col].apply(fmt)
                        
                        st.dataframe(styled_df, use_container_width=True, key="analysis_df")
                        
                        render_bar_charts(df)
                        
                        st.markdown("---")
                        st.markdown("### Download Options")
                        export_col1, export_col2 = st.columns(2)
                        
                        with export_col1:
                            st.download_button(
                                label="Download Analysis (CSV)",
                                data=export_analysis_data(),
                                file_name="fd_analysis.csv",
                                mime="text/csv",
                            )
                        
                        with export_col2:
                            st.download_button(
                                label="Download Report (MD)",
                                data=export_report_content(),
                                file_name="fd_report.md",
                                mime="text/markdown",
                            )

                    append_assistant(result.raw)
                    st.rerun()

                else:
                    append_assistant(result.raw)
                    st.rerun()

        except Exception as e:
            append_assistant(f"An error occurred: {e}")
            st.rerun()

# =============================================================================
# TAB 2: Peer Analysis
# =============================================================================
with tab2:
    if st.session_state.last_analysis_data is None:
        st.info("No analysis data available yet. Please perform an FD search in the 'FD Advisor' tab first.")
    else:
        df = st.session_state.last_analysis_data
        available_banks = df["Provider"].unique().tolist()
        default_selection = available_banks[:3] if len(available_banks) > 3 else available_banks

        tickers = st.multiselect(
            "Banks to Compare",
            options=available_banks,
            default=default_selection,
            placeholder="Select banks to analyze"
        )

        if not tickers:
            st.info("Select at least one bank.")
            st.stop()

        st.markdown("---")

        # ── Tenure: default to what the user queried, allow override ────────
        actual_tenure = st.session_state.get("last_tenure_months", 12)

        # Build pill options that always include the actual tenure
        _base_options = {12: "1 Year", 24: "2 Years", 36: "3 Years", 60: "5 Years"}
        horizon_map: dict[str, int] = {}
        # Insert actual tenure first if it's not already a standard option
        if actual_tenure not in _base_options:
            label = f"{actual_tenure} Months (your query)"
            horizon_map[label] = actual_tenure
        for months_val, lbl in _base_options.items():
            horizon_map[lbl] = months_val

        actual_label = next(
            (lbl for lbl, m in horizon_map.items() if m == actual_tenure),
            list(horizon_map.keys())[0]
        )

        st.markdown("### Simulation Horizon")
        horizon = st.pills(
            "Time Horizon",
            options=list(horizon_map.keys()),
            default=actual_label,
        )
        selected_tenure_months = horizon_map[horizon]

        # ── Principal ────────────────────────────────────────────────────────
        if "General Maturity" in df.columns and "General Interest" in df.columns:
            principal = df.iloc[0]["General Maturity"] - df.iloc[0]["General Interest"]
        else:
            principal = 100_000

        # ── Build growth data ────────────────────────────────────────────────
        start_date = datetime.now()
        month_range = list(range(0, selected_tenure_months + 1))
        growth_records = []

        for _, row in df.iterrows():
            bank_name = row["Provider"]
            rate = row["General Rate (%)"] / 100.0
            for m in month_range:
                t = m / 12.0
                n = 4  # quarterly compounding
                balance = principal * (1 + rate / n) ** (n * t)
                growth_records.append({
                    "Month": m,
                    "Bank": bank_name,
                    "Balance": round(balance, 2),
                    "Interest": round(balance - principal, 2),
                })

        growth_df = pd.DataFrame(growth_records)
        selected_growth_df = growth_df[growth_df["Bank"].isin(tickers)].copy()

        # ── Summary metrics ──────────────────────────────────────────────────
        final_month_data = selected_growth_df[selected_growth_df["Month"] == selected_tenure_months]
        if not final_month_data.empty:
            best_bank  = final_month_data.loc[final_month_data["Balance"].idxmax()]
            worst_bank = final_month_data.loc[final_month_data["Balance"].idxmin()]
            best_pct   = ((best_bank["Balance"]  - principal) / principal) * 100
            worst_pct  = ((worst_bank["Balance"] - principal) / principal) * 100

            col_m1, col_m2 = st.columns(2)
            with col_m1:
                st.metric("Best Performer",   best_bank["Bank"],  delta=f"+{best_pct:.1f}%")
            with col_m2:
                st.metric("Lowest Performer", worst_bank["Bank"], delta=f"+{worst_pct:.1f}%")

        # ── Shared ECharts helpers ───────────────────────────────────────────
        sym      = get_currency_symbol()
        sym_label = f" ({sym})" if sym else ""

        fmt_js   = JsCode(f"function(v){{return '{sym}'+v.toLocaleString(undefined,{{maximumFractionDigits:0}});}}")
        axis_fmt = JsCode(f"function(v){{return '{sym}'+(v/1000).toFixed(0)+'K';}}")

        palette = ["#3B82F6", "#EF4444", "#10B981", "#F59E0B", "#8B5CF6",
                   "#EC4899", "#06B6D4", "#84CC16", "#F97316", "#6366F1"]

        # ── Month labels (shared x-axis) ─────────────────────────────────────
        # Use plain "Month N" strings — avoids any datetime conversion issues
        month_labels = [f"M{m}" for m in month_range]

        # ── Growth Trajectory chart ──────────────────────────────────────────
        st.markdown(f"### Growth Trajectory — Principal: {sym}{principal:,.0f}")

        trajectory_series = []
        for i, bank in enumerate(tickers):
            bank_rows = selected_growth_df[selected_growth_df["Bank"] == bank].sort_values("Month")
            trajectory_series.append({
                "name": bank,
                "type": "line",
                "smooth": True,
                "data": bank_rows["Balance"].tolist(),
                "itemStyle": {"color": palette[i % len(palette)]},
                "emphasis": {"focus": "series"},
                "symbol": "none",
            })

        st_echarts(
            options={
                "tooltip": {
                    "trigger": "axis",
                    "formatter": JsCode(
                        f"function(params){{"
                        f"  var s=params[0].axisValue+'<br/>';"
                        f"  params.forEach(function(p){{"
                        f"    s+=p.marker+p.seriesName+': {sym}'+p.value.toLocaleString(undefined,{{maximumFractionDigits:0}})+'<br/>';"
                        f"  }});"
                        f"  return s;"
                        f"}}"
                    ),
                },
                "legend": {"data": tickers, "bottom": 0, "type": "scroll"},
                "grid": {"left": "3%", "right": "4%", "bottom": "12%", "containLabel": True},
                "xAxis": {
                    "type": "category",
                    "data": month_labels,
                    "boundaryGap": False,
                    "axisLabel": {
                        "formatter": JsCode("function(v,i){return i%3===0?v:''}"),
                        "rotate": 0,
                    },
                },
                "yAxis": {
                    "type": "value",
                    "name": f"Balance{sym_label}",
                    "axisLabel": {"formatter": axis_fmt},
                    "scale": True,
                },
                "series": trajectory_series,
            },
            height="420px",
            key="ec_trajectory",
        )

        # ── Individual vs Peer Average ───────────────────────────────────────
        st.markdown("---")
        st.markdown("### Individual Banks vs Peer Average")

        if len(tickers) <= 1:
            st.info("Select at least 2 banks to see peer comparison.")
        else:
            # Build pivot: rows = months, columns = banks
            pivot_df = (
                selected_growth_df
                .pivot(index="Month", columns="Bank", values="Balance")
                .sort_index()
            )
            # Ensure all selected tickers are present
            pivot_df = pivot_df.reindex(columns=tickers)
            peer_month_labels = [f"M{m}" for m in pivot_df.index.tolist()]

            chart_pairs = []
            for i, bank in enumerate(tickers):
                other_banks = [b for b in tickers if b != bank]
                bank_vals = pivot_df[bank].round(2).tolist()
                peer_avg  = pivot_df[other_banks].mean(axis=1).round(2).tolist()
                delta_vals = [round(b - p, 2) for b, p in zip(bank_vals, peer_avg)]
                bank_color = palette[i % len(palette)]

                tooltip_fmt = JsCode(
                    f"function(params){{"
                    f"  var s=params[0].axisValue+'<br/>';"
                    f"  params.forEach(function(p){{"
                    f"    s+=p.marker+p.seriesName+': {sym}'+p.value.toLocaleString(undefined,{{maximumFractionDigits:0}})+'<br/>';"
                    f"  }});"
                    f"  return s;"
                    f"}}"
                )

                line_option = {
                    "title": {"text": f"{bank} vs Peer Avg", "textStyle": {"fontSize": 13}},
                    "tooltip": {"trigger": "axis", "formatter": tooltip_fmt},
                    "legend": {"data": [bank, "Peer Avg"], "bottom": 0},
                    "grid": {"left": "3%", "right": "4%", "bottom": "15%", "containLabel": True},
                    "xAxis": {
                        "type": "category",
                        "data": peer_month_labels,
                        "boundaryGap": False,
                        "axisLabel": {
                            "formatter": JsCode("function(v,i){return i%3===0?v:''}"),
                        },
                    },
                    "yAxis": {
                        "type": "value",
                        "scale": True,
                        "axisLabel": {"formatter": axis_fmt, "fontSize": 10},
                    },
                    "series": [
                        {"name": bank, "type": "line", "smooth": True, "data": bank_vals,
                         "itemStyle": {"color": bank_color}, "lineStyle": {"width": 2}, "symbol": "none"},
                        {"name": "Peer Avg", "type": "line", "smooth": True, "data": peer_avg,
                         "itemStyle": {"color": "#94A3B8"},
                         "lineStyle": {"width": 2, "type": "dashed"}, "symbol": "none"},
                    ],
                }

                delta_tooltip = JsCode(
                    f"function(params){{"
                    f"  var p=params[0];"
                    f"  return p.axisValue+'<br/>Delta: {sym}'+p.value.toLocaleString(undefined,{{maximumFractionDigits:0}});"
                    f"}}"
                )

                delta_option = {
                    "title": {"text": f"{bank} − Peer Avg", "textStyle": {"fontSize": 13}},
                    "tooltip": {"trigger": "axis", "formatter": delta_tooltip},
                    "grid": {"left": "3%", "right": "4%", "bottom": "15%", "containLabel": True},
                    "xAxis": {
                        "type": "category",
                        "data": peer_month_labels,
                        "boundaryGap": False,
                        "axisLabel": {
                            "formatter": JsCode("function(v,i){return i%3===0?v:''}"),
                        },
                    },
                    "yAxis": {
                        "type": "value",
                        "scale": True,
                        "axisLabel": {"formatter": axis_fmt, "fontSize": 10},
                    },
                    "visualMap": {
                        "show": False,
                        "type": "piecewise",
                        "seriesIndex": 0,
                        "pieces": [{"gte": 0, "color": "#2563EB"}, {"lt": 0, "color": "#EF4444"}],
                    },
                    "series": [{
                        "type": "line",
                        "smooth": True,
                        "data": delta_vals,
                        "areaStyle": {"opacity": 0.4},
                        "lineStyle": {"width": 1.5},
                        "symbol": "none",
                    }],
                }

                chart_pairs.append((line_option, delta_option, bank))

            for j in range(0, len(chart_pairs), 2):
                c1, c2 = st.columns(2, gap="medium")
                with c1:
                    with st.container(border=True):
                        st_echarts(options=chart_pairs[j][0], height="300px", key=f"ec_line_{chart_pairs[j][2]}")
                        st_echarts(options=chart_pairs[j][1], height="220px", key=f"ec_delta_{chart_pairs[j][2]}")
                if j + 1 < len(chart_pairs):
                    with c2:
                        with st.container(border=True):
                            st_echarts(options=chart_pairs[j+1][0], height="300px", key=f"ec_line_{chart_pairs[j+1][2]}")
                            st_echarts(options=chart_pairs[j+1][1], height="220px", key=f"ec_delta_{chart_pairs[j+1][2]}")

        # ── Raw data table ───────────────────────────────────────────────────
        st.markdown("---")
        st.markdown("### Raw Data Comparison")
        display_cols = ["Provider", "General Rate (%)", "Senior Rate (%)",
                        "General Maturity", "General Interest",
                        "Senior Maturity", "Senior Interest"]
        valid_cols = [c for c in display_cols if c in df.columns]
        st.dataframe(df[df["Provider"].isin(tickers)][valid_cols], use_container_width=True)

# =============================================================================
# TAB 3: NEW ACCOUNT (ONBOARDING FORM)
# =============================================================================
with tab3:
    st.markdown("### Open a New Fixed Deposit Account")
    
    # Retrieve detected country
    countries_data = fetch_country_data()
    country_names = sorted([v["name"] for v in countries_data.values()])
    detected_country_name = st.session_state.user_region.get("country_name", "Worldwide")
    
    try:
        default_country_idx = country_names.index(detected_country_name)
    except ValueError:
        default_country_idx = 0

    # Country Selector OUTSIDE the form to trigger dynamic updates
    selected_country_name = st.selectbox(
        "Select Country of Residence", 
        options=country_names, 
        index=default_country_idx
    )
    
    # Lookup code
    selected_country_code = "WW"
    for cc, data in countries_data.items():
        if data["name"] == selected_country_name:
            selected_country_code = cc
            break
    
    # Dynamic KYC Fetch
    _GENERIC = {"Government-issued Photo ID", "Proof of Address"}
    _kyc_cache_key = f"kyc_{selected_country_name}"

    # Bust the in-memory cache for this country if the user hits Refresh
    if st.button("🔄 Refresh KYC Documents", key="kyc_refresh"):
        get_dynamic_kyc_docs.clear()
        st.rerun()

    with st.spinner(f"Fetching KYC requirements for {selected_country_name}..."):
        doc1, doc2 = get_dynamic_kyc_docs(selected_country_name)

    _is_generic = doc1 in _GENERIC or doc2 in _GENERIC

    if _is_generic:
        st.warning(
            f"⚠️ Could not retrieve specific KYC documents for **{selected_country_name}**. "
            f"Showing generic placeholders — click **Refresh KYC Documents** to retry, "
            f"or enter the document type manually below.",
            icon=None,
        )
        badge_bg, badge_color, header_bg, header_border, header_color = (
            "#FEF3C7", "#92400E", "#FFFBEB", "#FDE68A", "#92400E"
        )
    else:
        badge_bg, badge_color, header_bg, header_border, header_color = (
            "#DBEAFE", "#1D4ED8", "#EFF6FF", "#BFDBFE", "#1E40AF"
        )

    st.markdown(
        f"""
        <div style="background:{header_bg};border:1px solid {header_border};
                    border-radius:8px;padding:12px 16px;margin-bottom:12px">
          <span style="font-size:0.85rem;color:{header_color};font-weight:600">
            🪪 Required KYC Documents — {selected_country_name}
          </span><br>
          <span style="display:inline-block;background:{badge_bg};color:{badge_color};
                       border-radius:4px;padding:4px 10px;margin:6px 4px 0 0;
                       font-size:0.92rem;font-weight:500">
            1. {doc1}
          </span>
          <span style="display:inline-block;background:{badge_bg};color:{badge_color};
                       border-radius:4px;padding:4px 10px;margin:6px 0 0;
                       font-size:0.92rem;font-weight:500">
            2. {doc2}
          </span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    with st.form("onboarding_form"):
        st.markdown("#### Applicant Information")
        col1, col2 = st.columns(2)
        
        with col1:
            first_name = st.text_input("First Name")
            last_name = st.text_input("Last Name")
            email = st.text_input("Email Address")
            mobile = st.text_input("Mobile Number")
        
        with col2:
            address = st.text_area("Residential Address")
            pin_code = st.text_input("PIN / Postal Code")
            # Hidden field essentially, shown above form but passed here for clarity
            st.text_input("Country", value=selected_country_name, disabled=True)

        st.markdown("#### Deposit Details")
        col3, col4 = st.columns(2)
        
        with col3:
            product_type = st.radio("Product Type", ["FD", "RD"])
            amount = st.number_input(
                f"Amount ({'Principal' if product_type == 'FD' else 'Monthly Installment'})", 
                min_value=1000
            )
            tenure = st.slider("Tenure (Months)", 6, 120, 12)
        
        with col4:
            bank_name = st.text_input("Preferred Bank Name", value="SBI")
            compounding = st.selectbox("Compounding Frequency", ["quarterly", "monthly", "yearly"])

        st.markdown("#### KYC Documentation")
        col5, col6 = st.columns(2)
        with col5:
            kyc_val_1 = st.text_input(f"{doc1} Number")
        with col6:
            kyc_val_2 = st.text_input(f"{doc2} Number")

        submitted = st.form_submit_button("Submit Application")

        if submitted:
            if not all([first_name, last_name, email, mobile, address, pin_code, kyc_val_1, kyc_val_2]):
                st.error("Please fill all mandatory fields.")
            else:
                client_data = {
                    "first_name": first_name,
                    "last_name": last_name,
                    "email": email,
                    "user_address": address,
                    "pin_number": pin_code,
                    "mobile_number": mobile,
                    "bank_name": bank_name,
                    "product_type": product_type,
                    "initial_amount": float(amount),
                    "tenure_months": int(tenure),
                    "compounding_freq": compounding,
                    "kyc_details_1": f"{doc1}-{kyc_val_1}",
                    "kyc_details_2": f"{doc2}-{kyc_val_2}",
                    "country_code": selected_country_code
                }
                
                json_str = json.dumps(client_data)
                crews = get_crews()
                
                # Update Langfuse User ID to the actual applicant
                st.session_state.langfuse_user_id = email
                
                st.info("Application submitted. Running compliance and risk checks...")
                
                try:
                    # --- WRAPPED AML CALL ---
                    aml_response = run_crew_with_langfuse(
                        crew_callable=lambda: crews.get_aml_execution_crew(json_str).kickoff(),
                        crew_name="aml-execution-crew",
                        user_input=f"New account application for {first_name} {last_name}",
                        region=selected_country_name,
                        extra_metadata={
                            "product_type": product_type,
                            "bank_name": bank_name,
                            "applicant_email": email
                        }
                    )
                    
                    st.markdown("### Compliance Report")
                    st.markdown(aml_response.raw)
                    
                except Exception as e:
                    st.error(f"An error occurred during processing: {e}")

# =============================================================================
# SIDEBAR
# =============================================================================
st.sidebar.markdown("---")
st.sidebar.markdown("### Search Region")

region_info = st.session_state.user_region
detected_name = region_info["country_name"]
all_countries = fetch_country_data()
country_lookup = {v["name"]: cc for cc, v in all_countries.items() if v["name"]}
country_names = sorted(country_lookup.keys())
detected_idx = country_names.index(detected_name) if detected_name in country_names else 0

st.sidebar.caption(f"Auto-detected: {detected_name}")
selected_country_name_sb = st.sidebar.selectbox(
    "Override region",
    options=country_names,
    index=detected_idx,
    key="region_selectbox",
)

selected_cc = country_lookup.get(selected_country_name_sb, "WW")
if selected_cc != st.session_state.user_region["country_code"]:
    info = all_countries.get(selected_cc, {})
    ddg = set_search_region(selected_cc)
    st.session_state.user_region = {
        "country_code": selected_cc,
        "country_name": selected_country_name_sb,
        "ddg_region": ddg,
        "currency_symbol": info.get("currency_symbol", ""),
        "currency_code": info.get("currency_code", ""),
    }
    st.rerun()

active_region = st.session_state.user_region["country_name"]
active_sym = st.session_state.user_region.get("currency_symbol", "")
active_ddg = st.session_state.user_region["ddg_region"]

st.sidebar.success(
    f"Active: {active_region} " +
    (f" - {active_sym} " if active_sym else "") +
    f"\nDDG: {active_ddg}"
)

st.sidebar.markdown("---")
st.sidebar.markdown("### System Status")

langsmith_active = os.getenv("LANGCHAIN_TRACING_V2") == "true" and os.getenv("LANGCHAIN_API_KEY")
if langsmith_active:
    st.sidebar.success("LangSmith Monitoring Active")
    st.sidebar.caption(f"Project: {os.getenv('LANGCHAIN_PROJECT', 'default')}")
else:
    st.sidebar.warning("LangSmith Monitoring Inactive")
    st.sidebar.caption("Set LANGCHAIN_TRACING_V2=true to enable.")

# Langfuse Status
if os.getenv("LANGFUSE_PUBLIC_KEY") and os.getenv("LANGFUSE_SECRET_KEY"):
    st.sidebar.success("Langfuse Observability Active")
else:
    st.sidebar.warning("Langfuse Observability Inactive")
    st.sidebar.caption("Set LANGFUSE_PUBLIC_KEY and SECRET_KEY.")

if os.getenv("NVIDIA_API_KEY"):
    st.sidebar.success("NVIDIA API Connected")
else:
    st.sidebar.error("NVIDIA API Missing")

st.sidebar.markdown("---")
st.sidebar.markdown("### Database Records")

def load_fd_table() -> pd.DataFrame:
    if not DB_PATH.exists():
        return pd.DataFrame()
    try:
        with sqlite3.connect(DB_PATH) as conn:
            return pd.read_sql_query("SELECT * FROM fixed_deposit ORDER BY fd_id", conn)
    except Exception as e:
        st.sidebar.warning(f"Error: {str(e)}")
        return pd.DataFrame()

fd_df = load_fd_table()
if not fd_df.empty:
    st.sidebar.dataframe(fd_df, use_container_width=True, key="sidebar_df")
else:
    st.sidebar.info("No FD records found.")

if st.sidebar.button("Refresh Data"):
    st.rerun()

st.sidebar.markdown("---")
if st.sidebar.button("Reset Session / Clear Chat"):
    reset_session()

st.sidebar.markdown("---")
st.sidebar.markdown("### Debug Info")
st.sidebar.json({
    "Country Code": st.session_state.user_region["country_code"],
    "DDG Region": st.session_state.user_region["ddg_region"],
    "Currency": st.session_state.user_region["currency_symbol"],
    "Langfuse Session": st.session_state.get("langfuse_session_id", "N/A"),
    "Langfuse User": st.session_state.get("langfuse_user_id", "N/A"),
})

if st.session_state.get("kyc_document_names"):
    st.sidebar.info(
        f" Required KYC for {st.session_state.user_region['country_name']}:\n"
        f"1. {st.session_state.kyc_document_names[0]}\n"
        f"2. {st.session_state.kyc_document_names[1]}"
    )