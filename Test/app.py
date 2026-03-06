# app.py
import os
import re
import sqlite3
import json
import random
import pandas as pd
import streamlit as st
import plotly.express as px  
import altair as alt
from pathlib import Path
from dotenv import load_dotenv
from streamlit_echarts import st_echarts
from datetime import datetime, timedelta
from crews import run_crew, FixedDepositCrews
from tools import extract_json_balanced

load_dotenv()
DB_PATH = Path(__file__).resolve().parent / "bank_poc.db"

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

def reset_session():
    st.session_state.messages = []
    if "ONBOARDING_FLOW" in st.session_state:
        del st.session_state["ONBOARDING_FLOW"]
    if "last_analysis_data" in st.session_state:
        del st.session_state["last_analysis_data"]
    st.rerun()

# --- TABS ---
tab1, tab2 = st.tabs(["FD Advisor", "Peer Analysis"])

# =========================================================================
# TAB 1: Original FD Advisor Chat Interface
# =========================================================================
with tab1:
    for idx, message in enumerate(st.session_state.messages):
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
            if "chart_option" in message:
                st_echarts(options=message["chart_option"], height="400px", key=f"hist_viz_{idx}")

    user_input = st.chat_input("Ask about FDs, check your data, or say 'Open an account'")

    if user_input:
        st.session_state.messages.append({"role": "user", "content": user_input})
        with st.chat_message("user"):
            st.markdown(user_input)

        has_api_key = bool(os.getenv("NVIDIA_API_KEY"))
        if not has_api_key:
            with st.chat_message("assistant"):
                st.warning("NVIDIA_API_KEY not found. Please configure it to use AI features.")
        else:
            with st.chat_message("assistant"):
                with st.spinner("Processing..."):
                    try:
                        viz_keywords = ["plot", "chart", "graph", "visualize", "show me", "donut", "pie", "line", "bar", "break down"]
                        is_viz_request = any(keyword in user_input.lower() for keyword in viz_keywords)

                        if is_viz_request:
                            crews = FixedDepositCrews()
                            if st.session_state.last_analysis_data is not None:
                                data_json = st.session_state.last_analysis_data.to_json(orient="records")
                            else:
                                data_json = "None"
                            
                            viz_crew = crews.get_visualization_crew(user_input, data_json)
                            viz_result = viz_crew.kickoff()
                            
                            try:
                                chart_option = extract_json_balanced(viz_result.raw)
                                st.markdown("I've generated the chart for you below.")
                                st_echarts(options=chart_option, height="400px", key=f"viz_chat_{len(st.session_state.messages)}")
                                st.session_state.messages.append({
                                    "role": "assistant", 
                                    "content": f"Generated chart based on: {user_input}",
                                    "chart_option": chart_option
                                })
                            except Exception as e:
                                st.error(f"Failed to parse chart configuration: {str(e)}")
                                st.session_state.messages.append({"role": "assistant", "content": "Sorry, I couldn't generate that chart."})

                        elif "ONBOARDING_FLOW" in st.session_state:
                            conversation_history = "\n".join([f"{m['role']}: {m['content']}" for m in st.session_state.messages])
                            crews = FixedDepositCrews()
                            data_response = crews.get_data_collection_crew(conversation_history).kickoff()
                            
                            st.markdown(data_response.raw)
                            st.session_state.messages.append({"role": "assistant", "content": data_response.raw})

                            if "DATA_READY" in data_response.raw:
                                try:
                                    json_str = data_response.raw.split("DATA_READY:")[1].strip()
                                    with st.spinner("Performing AML Checks (This may take a moment)..."):
                                        aml_response = crews.get_aml_execution_crew(json_str).kickoff()
                                        st.markdown(aml_response.raw)
                                        st.session_state.messages.append({"role": "assistant", "content": aml_response.raw})
                                    del st.session_state["ONBOARDING_FLOW"]
                                except Exception as e:
                                    st.error(f"Error processing client data: {str(e)}")
                                    del st.session_state["ONBOARDING_FLOW"]
                        
                        else:
                            result = run_crew(user_input)
                            
                            if result.raw == "ONBOARDING":
                                st.session_state["ONBOARDING_FLOW"] = True
                                st.markdown("I can help with that. Let's start by collecting some details.")
                                st.session_state.messages.append({"role": "assistant", "content": "I can help with that. Let's start by collecting some details."})
                                
                                crews = FixedDepositCrews()
                                history = "\n".join([f"{m['role']}: {m['content']}" for m in st.session_state.messages])
                                data_resp = crews.get_data_collection_crew(history).kickoff()
                                st.markdown(data_resp.raw)
                                st.session_state.messages.append({"role": "assistant", "content": data_resp.raw})
                            
                            elif hasattr(result, 'tasks_output') and len(result.tasks_output) >= 5:
                                st.markdown(result.raw)
                                
                                if len(result.tasks_output) >= 5:
                                    projection_output = result.tasks_output[4].raw
                                    
                                    def parse_projection_table(projection_text: str) -> pd.DataFrame:
                                        try:
                                            clean_text = projection_output.replace("```csv", "").replace("```", "").strip()
                                            import io
                                            df = pd.read_csv(io.StringIO(clean_text))
                                            required = {"Provider", "General Rate (%)", "Senior Rate (%)",
                                                        "General Maturity", "Senior Maturity"}
                                            if not required.issubset(df.columns):
                                                return pd.DataFrame()
                                            return df
                                        except Exception as e:
                                            return pd.DataFrame()

                                    df = parse_projection_table(projection_output)
                                    if not df.empty:
                                        st.session_state.last_analysis_data = df
                                        st.info("Analysis complete. Switch to the 'Peer Analysis' tab to compare these banks visually.")

                                        def fmt(x):
                                            if isinstance(x, (int, float)):
                                                return f"{x:,.2f}"
                                            return str(x)

                                        styled_df = df.copy()
                                        for col in ["General Rate (%)", "Senior Rate (%)",
                                                    "General Maturity", "Senior Maturity",
                                                    "General Interest", "Senior Interest"]:
                                            if col in styled_df.columns:
                                                styled_df[col] = styled_df[col].apply(fmt)
                                        
                                        st.dataframe(styled_df, use_container_width=True, key="analysis_df")

                                        col1, col2 = st.columns(2)
                                        with col1:
                                            st.markdown("### Interest Rates by Provider")
                                            df_rate_long = df.melt(id_vars="Provider", value_vars=["General Rate (%)", "Senior Rate (%)"], var_name="Category", value_name="Rate")
                                            fig_rate = px.bar(df_rate_long, x="Provider", y="Rate", color="Category", barmode="group", title="General vs Senior Interest Rates", color_discrete_map={"General Rate (%)": "#7197D4", "Senior Rate (%)": "#1E3A8A"}, hover_data={"Rate": ":.2f"})
                                            fig_rate.update_layout(yaxis_title="Interest Rate (%)", legend_title="Category", xaxis_title="Provider")
                                            st.plotly_chart(fig_rate, use_container_width=True, key="plotly_rate")

                                        with col2:
                                            st.markdown("### Maturity Amounts by Provider")
                                            df_mat_long = df.melt(id_vars="Provider", value_vars=["General Maturity", "Senior Maturity"], var_name="Category", value_name="Amount")
                                            fig_mat = px.bar(df_mat_long, x="Provider", y="Amount", color="Category", barmode="group", title="General vs Senior Maturity Amounts", color_discrete_map={"General Maturity": "#7FACF5", "Senior Maturity": "#1E3A8A"}, hover_data={"Amount": ":.2f"})
                                            fig_mat.update_layout(yaxis_title="Maturity Amount", legend_title="Category", xaxis_title="Provider")
                                            st.plotly_chart(fig_mat, use_container_width=True, key="plotly_maturity")
                                
                                st.session_state.messages.append({"role": "assistant", "content": result.raw})
                            else:
                                st.markdown(result.raw)
                                st.session_state.messages.append({"role": "assistant", "content": result.raw})

                    except Exception as e:
                        st.error(f"An error occurred: {str(e)}")
                        st.exception(e)


# =========================================================================
# TAB 2: Peer Analysis (Updated Layout & Timeline)
# =========================================================================
with tab2:
    if st.session_state.last_analysis_data is None:
        st.info("No analysis data available yet. Please perform an FD search in the 'FD Advisor' tab first.")
    else:
        df = st.session_state.last_analysis_data
        available_banks = df["Provider"].unique().tolist()
        default_selection = available_banks[:3] if len(available_banks) > 3 else available_banks

        # --- CONTROLS SECTION ---
        tickers = st.multiselect(
            "Banks to Compare",
            options=available_banks,
            default=default_selection,
            placeholder="Select banks to analyze"
        )

        if not tickers:
            st.info("Select at least one bank.")
            st.stop()

        # --- SIMULATION HORIZON SECTION ---
        st.markdown("---")
        st.markdown("### Simulation Horizon")
        
        horizon_map = {
            "1 Year": 12,
            "2 Years": 24,
            "3 Years": 36,
            "5 Years": 60
        }
        
        # Default to 1 Year, or try to infer from the data if possible
        # Since the analysis is specific to a query, we offer projections for standard tenures
        horizon = st.pills(
            "Time Horizon",
            options=list(horizon_map.keys()),
            default="2 Years" # Default to 2 years for better visualization
        )
        
        selected_tenure_months = horizon_map[horizon]

        # --- VISUALIZATION SECTION (Full Width) ---
        if True:
            # --- DATA PREPARATION: Simulate Growth Curves with Timeline ---
            
            # Determine Principal from the first valid row (Maturity - Interest)
            if "General Maturity" in df.columns and "General Interest" in df.columns:
                # Use the first row's data to estimate principal
                principal = df.iloc[0]["General Maturity"] - df.iloc[0]["General Interest"]
            else:
                principal = 100000 # Fallback

            # Generate Date Timeline
            start_date = datetime.now()
            months = list(range(0, selected_tenure_months + 1))
            
            growth_records = []

            for _, row in df.iterrows():
                bank_name = row["Provider"]
                rate = row["General Rate (%)"] / 100.0 # Using General Rate for visualization
                
                for m in months:
                    # Calculate Date for timeline
                    # Approximate month addition using timedelta(days=30) for visualization purposes
                    current_date = start_date + timedelta(days=30*m)
                    
                    # Compound Interest Formula: A = P(1 + r/n)^(nt)
                    # Assuming Quarterly Compounding (n=4)
                    n = 4
                    t = m / 12
                    balance = principal * (1 + rate/n) ** (n*t)
                    interest_earned = balance - principal
                    
                    growth_records.append({
                        "Date": current_date,
                        "Month": m,
                        "Bank": bank_name,
                        "Balance": balance,
                        "Interest": interest_earned
                    })

            growth_df = pd.DataFrame(growth_records)
            selected_growth_df = growth_df[growth_df["Bank"].isin(tickers)]

            # --- 1. BEST / WORST METRICS (Based on Final Month of Simulation) ---
            final_month_data = selected_growth_df[selected_growth_df["Month"] == selected_tenure_months]
            
            if not final_month_data.empty:
                best_bank = final_month_data.loc[final_month_data["Balance"].idxmax()]
                worst_bank = final_month_data.loc[final_month_data["Balance"].idxmin()]

                best_pct = ((best_bank["Balance"] - principal) / principal) * 100
                worst_pct = ((worst_bank["Balance"] - principal) / principal) * 100

                col_metrics = st.columns(2)
                with col_metrics[0]:
                    st.metric(
                        "Best Performer",
                        best_bank["Bank"],
                        delta=f"↑ {best_pct:.1f}%",
                        delta_color="normal"
                    )
                with col_metrics[1]:
                    st.metric(
                        "Lowest Performer",
                        worst_bank["Bank"],
                        delta=f"↑ {worst_pct:.1f}%",
                        delta_color="normal"
                    )
            else:
                st.warning("Could not calculate metrics for selected horizon.")

            # --- 2. MAIN GROWTH TRAJECTORY CHART (Timeline, Quarterly Segments) ---
            st.markdown(f"### Growth Trajectory (Principal: ₹{principal:,.0f})")
            
            # Ensure we sort by Date for the line chart
            selected_growth_df = selected_growth_df.sort_values("Date")

            base_chart = alt.Chart(selected_growth_df).mark_line().encode(
                x=alt.X("Date:T", title="Timeline", axis=alt.Axis(format="%Y Q%q")), # Format as Year Q#
                y=alt.Y("Balance:Q", title="Maturity Amount", axis=alt.Axis(format=",.0f"), scale=alt.Scale(zero=False)),
                color=alt.Color("Bank:N", legend=alt.Legend(orient="bottom")),
                tooltip=[alt.Tooltip("Date:T", format="%Y-%m-%d"), "Bank", alt.Tooltip("Balance", format=",.2f")]
            ).properties(height=400)
            
            st.altair_chart(base_chart, use_container_width=True)

            st.markdown("---")
            st.markdown("### Individual Banks vs Peer Average")

            # --- 3. DETAILED COMPARISON (Fixed Alignment) ---
            
            # Check if we have enough banks for Peer Average
            if len(tickers) <= 1:
                st.info("Select at least 2 banks to see the Peer Comparison analysis.")
            else:
                # Pivot table to easily calculate peer average per month
                pivot_df = selected_growth_df.pivot(index="Date", columns="Bank", values="Balance")
                
                # Process all banks and store chart pairs
                chart_pairs = []
                
                for bank in tickers:
                    # Prepare Peer Average Data
                    # Select all columns EXCEPT current bank
                    other_banks = [b for b in tickers if b != bank]
                    
                    peer_avg = pivot_df[other_banks].mean(axis=1)
                    current_bank_vals = pivot_df[bank]
                    
                    comparison_df = pd.DataFrame({
                        "Date": pivot_df.index,
                        "Bank": current_bank_vals,
                        "Peer Average": peer_avg
                    }).reset_index(drop=True)

                    # CHART 1: Bank vs Peer (Line Chart: Red vs Gray)
                    chart1_data = comparison_df.melt(id_vars=["Date"], var_name="Series", value_name="Balance")
                    
                    chart1 = (
                        alt.Chart(chart1_data)
                        .mark_line()
                        .encode(
                            x=alt.X("Date:T", title="Timeline", axis=alt.Axis(format="%Y Q%q")),
                            y=alt.Y("Balance:Q", title="Maturity Amount", axis=alt.Axis(format=",.0f")),
                            color=alt.Color(
                                "Series:N",
                                scale=alt.Scale(domain=["Bank", "Peer Average"], range=["#EF4444", "#94A3B8"]), # Red vs Gray
                                legend=alt.Legend(orient="bottom"),
                            ),
                            tooltip=[alt.Tooltip("Date:T", format="%Y-%m-%d"), "Series", alt.Tooltip("Balance", format=",.2f")]
                        )
                        .properties(title=f"{bank} vs Peer Average", height=300)
                    )

                    # CHART 2: Delta (Area Chart: Bank minus Average)
                    delta_df = comparison_df.copy()
                    delta_df["Delta"] = delta_df["Bank"] - delta_df["Peer Average"]

                    chart2 = (
                        alt.Chart(delta_df)
                        .mark_area(opacity=0.6)
                        .encode(
                            x=alt.X("Date:T", title="Timeline", axis=alt.Axis(format="%Y Q%q")),
                            y=alt.Y("Delta:Q", title="Difference (Bank - Average)"),
                            color=alt.condition(
                                alt.datum.Delta > 0,
                                alt.value("#2563EB"), # Blue for positive
                                alt.value("#EF4444")  # Red for negative
                            ),
                            tooltip=[alt.Tooltip("Date:T", format="%Y-%m-%d"), alt.Tooltip("Delta", format=",.2f")]
                        )
                        .properties(title=f"{bank} minus Peer Average", height=300)
                    )
                    
                    chart_pairs.append((chart1, chart2))
                
                # Display chart pairs in rows of 2
                for i in range(0, len(chart_pairs), 2):
                    col1, col2 = st.columns(2, gap="medium")
                    
                    # First chart pair
                    with col1:
                        with st.container(border=True):
                            st.altair_chart(chart_pairs[i][0], use_container_width=True)
                            st.altair_chart(chart_pairs[i][1], use_container_width=True)
                    
                    # Second chart pair (if exists)
                    if i + 1 < len(chart_pairs):
                        with col2:
                            with st.container(border=True):
                                st.altair_chart(chart_pairs[i + 1][0], use_container_width=True)
                                st.altair_chart(chart_pairs[i + 1][1], use_container_width=True)

        st.markdown("---")
        st.markdown("### Raw Data Comparison")
        
        display_cols = ["Provider", "General Rate (%)", "General Maturity", "General Interest"]
        valid_cols = [col for col in display_cols if col in df.columns]
        
        st.dataframe(
            df[df["Provider"].isin(tickers)][valid_cols], 
            use_container_width=True
        )


# Sidebar Database Logic (Preserved from original)
st.sidebar.markdown("---")
st.sidebar.markdown("### Database Records")

def load_fd_table() -> pd.DataFrame:
    if not DB_PATH.exists(): return pd.DataFrame()
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