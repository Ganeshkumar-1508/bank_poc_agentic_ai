# app.py
import os
import re
import sqlite3
import json
import random
import pandas as pd
import streamlit as st
import plotly.express as px  
from pathlib import Path
from dotenv import load_dotenv
# Updated imports
from streamlit_echarts import st_echarts
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

# --- UPDATED: Chat Rendering Loop with Inline Charts ---
for idx, message in enumerate(st.session_state.messages):
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
        # Check if this message has a stored chart and render it here
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
                    # --- 1. ROUTING ---
                    # Check if this is a visualization request
                    viz_keywords = ["plot", "chart", "graph", "visualize", "show me", "donut", "pie", "line", "bar", "break down"]
                    is_viz_request = any(keyword in user_input.lower() for keyword in viz_keywords)

                    if is_viz_request:
                        # HANDLE VISUALIZATION (Web Search Enabled)
                        crews = FixedDepositCrews()
                        
                        # Prepare Data Context
                        if st.session_state.last_analysis_data is not None:
                            data_json = st.session_state.last_analysis_data.to_json(orient="records")
                        else:
                            data_json = "None" # Agent will see this and trigger Web Search per task instructions
                        
                        viz_crew = crews.get_visualization_crew(user_input, data_json)
                        viz_result = viz_crew.kickoff()
                        
                        try:
                            chart_option = extract_json_balanced(viz_result.raw)
                            
                            st.markdown("I've generated the chart for you below.")
                            # Render immediately with a unique key for this turn
                            st_echarts(options=chart_option, height="400px", key=f"viz_chat_{len(st.session_state.messages)}")
                            
                            # --- CRITICAL CHANGE: Save chart option into the message object ---
                            # This ensures it re-renders in the correct place on page reload
                            st.session_state.messages.append({
                                "role": "assistant", 
                                "content": f"Generated chart based on: {user_input}",
                                "chart_option": chart_option
                            })
                            
                        except Exception as e:
                            st.error(f"Failed to parse chart configuration: {str(e)}")
                            st.session_state.messages.append({"role": "assistant", "content": "Sorry, I couldn't generate that chart."})

                    # --- 2. STANDARD ONBOARDING FLOW ---
                    elif "ONBOARDING_FLOW" in st.session_state:
                        
                        # STEP 1: Run Lightweight Data Collection Crew
                        conversation_history = "\n".join([f"{m['role']}: {m['content']}" for m in st.session_state.messages])
                        crews = FixedDepositCrews()
                        data_response = crews.get_data_collection_crew(conversation_history).kickoff()
                        
                        st.markdown(data_response.raw)
                        st.session_state.messages.append({"role": "assistant", "content": data_response.raw})

                        # STEP 2: Check if data is ready to trigger Heavy AML Crew
                        if "DATA_READY" in data_response.raw:
                            try:
                                # Extract JSON
                                json_str = data_response.raw.split("DATA_READY:")[1].strip()
                                
                                with st.spinner("Performing AML Checks (This may take a moment)..."):
                                    # STEP 3: Run Heavy AML Crew
                                    aml_response = crews.get_aml_execution_crew(json_str).kickoff()
                                    st.markdown(aml_response.raw)
                                    st.session_state.messages.append({"role": "assistant", "content": aml_response.raw})
                                
                                # Clean up session after completion
                                del st.session_state["ONBOARDING_FLOW"]

                            except Exception as e:
                                st.error(f"Error processing client data: {str(e)}")
                                del st.session_state["ONBOARDING_FLOW"]
                    
                    # --- 3. GENERAL FLOW (ROUTER -> EXECUTION) ---
                    else:
                        result = run_crew(user_input)
                        
                        if result.raw == "ONBOARDING":
                            st.session_state["ONBOARDING_FLOW"] = True
                            # Initial greeting
                            st.markdown("I can help with that. Let's start by collecting some details.")
                            st.session_state.messages.append({"role": "assistant", "content": "I can help with that. Let's start by collecting some details."})
                            
                            # Trigger the first data question immediately using the data crew
                            crews = FixedDepositCrews()
                            history = "\n".join([f"{m['role']}: {m['content']}" for m in st.session_state.messages])
                            data_resp = crews.get_data_collection_crew(history).kickoff()
                            st.markdown(data_resp.raw)
                            st.session_state.messages.append({"role": "assistant", "content": data_resp.raw})
                        
                        elif hasattr(result, 'tasks_output') and len(result.tasks_output) >= 5:
                            # --- ORIGINAL ANALYSIS RESULT HANDLING ---
                            st.markdown(result.raw)
                            
                            if len(result.tasks_output) >= 5:
                                # Assuming projection is the 5th task (index 4) as per original code logic
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
                                    # --- PERSIST DATA FOR VISUALIZATION ---
                                    st.session_state.last_analysis_data = df
                                    st.info("Analysis complete. You can now ask me to 'plot this' or 'show a donut chart of maturity amounts'. I can also fetch new data from the web if you ask for specific charts.")

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
                                        df_rate_long = df.melt(
                                            id_vars="Provider", 
                                            value_vars=["General Rate (%)", "Senior Rate (%)"],
                                            var_name="Category", 
                                            value_name="Rate"
                                        )
                                        fig_rate = px.bar(
                                            df_rate_long, 
                                            x="Provider", 
                                            y="Rate", 
                                            color="Category",
                                            barmode="group",
                                            title="General vs Senior Interest Rates",
                                            color_discrete_map={
                                                "General Rate (%)": "#7197D4",  
                                                "Senior Rate (%)": "#1E3A8A"   
                                            },
                                            hover_data={"Rate": ":.2f"}
                                        )
                                        fig_rate.update_layout(yaxis_title="Interest Rate (%)", legend_title="Category", xaxis_title="Provider")
                                        st.plotly_chart(fig_rate, use_container_width=True, key="plotly_rate")

                                    with col2:
                                        st.markdown("### Maturity Amounts by Provider")
                                        df_mat_long = df.melt(
                                            id_vars="Provider", 
                                            value_vars=["General Maturity", "Senior Maturity"],
                                            var_name="Category", 
                                            value_name="Amount"
                                        )
                                        fig_mat = px.bar(
                                            df_mat_long, 
                                            x="Provider", 
                                            y="Amount", 
                                            color="Category",
                                            barmode="group",
                                            title="General vs Senior Maturity Amounts",
                                            color_discrete_map={
                                                "General Maturity": "#7FACF5",
                                                "Senior Maturity": "#1E3A8A"
                                            },
                                            hover_data={"Amount": ":.2f"}
                                        )
                                        fig_mat.update_layout(yaxis_title="Maturity Amount", legend_title="Category", xaxis_title="Provider")
                                        st.plotly_chart(fig_mat, use_container_width=True, key="plotly_maturity")
                            
                            st.session_state.messages.append({"role": "assistant", "content": result.raw})
                        else:
                            st.markdown(result.raw)
                            st.session_state.messages.append({"role": "assistant", "content": result.raw})

                except Exception as e:
                    st.error(f"An error occurred: {str(e)}")
                    st.exception(e)

# --- REMOVED: The bottom "Your Charts" section ---
# Charts are now rendered inline in the chat history above.

# Sidebar logic remains unchanged
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