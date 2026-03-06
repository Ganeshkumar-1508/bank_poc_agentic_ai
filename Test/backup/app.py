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
from crews import run_crew, get_onboarding_crew

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

def reset_session():
    st.session_state.messages = []
    if "ONBOARDING_FLOW" in st.session_state:
        del st.session_state["ONBOARDING_FLOW"]
    st.rerun()

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

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
                    if st.session_state.messages and "ONBOARDING_FLOW" in st.session_state:
                        # HIERARCHICAL ONBOARDING FLOW
                        conversation_history = "\n".join([f"{m['role']}: {m['content']}" for m in st.session_state.messages])
                        
                        # Call the updated crew function
                        response = get_onboarding_crew(conversation_history).kickoff()
                        
                        st.markdown(response.raw)
                        st.session_state.messages.append({"role": "assistant", "content": response.raw})

                        if "Success" in response.raw or "Email sent" in response.raw or "Transaction Failed" in response.raw:
                            if "ONBOARDING_FLOW" in st.session_state:
                                del st.session_state["ONBOARDING_FLOW"]
                    
                    else:
                        # GENERAL FLOW (ROUTER -> EXECUTION)
                        result = run_crew(user_input)
                        
                        if result.raw == "ONBOARDING":
                            st.session_state["ONBOARDING_FLOW"] = True
                            conversation_history = f"user: {user_input}\nassistant: I can help with that. Let's start."
                            
                            # Start the hierarchical onboarding crew
                            response = get_onboarding_crew(conversation_history).kickoff()
                            st.markdown(response.raw)
                            st.session_state.messages.append({"role": "assistant", "content": response.raw})
                        
                        elif hasattr(result, 'tasks_output') and len(result.tasks_output) >= 5:
                            # ANALYSIS RESULT HANDLING
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
                                    st.dataframe(styled_df, use_container_width=True)

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
                                        st.plotly_chart(fig_rate, use_container_width=True)

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
                                        st.plotly_chart(fig_mat, use_container_width=True)
                            
                            st.session_state.messages.append({"role": "assistant", "content": result.raw})
                        else:
                            st.markdown(result.raw)
                            st.session_state.messages.append({"role": "assistant", "content": result.raw})

                except Exception as e:
                    st.error(f"An error occurred: {str(e)}")
                    st.exception(e)

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
    st.sidebar.dataframe(fd_df, use_container_width=True)
else:
    st.sidebar.info("No FD records found.")

if st.sidebar.button("Refresh Data"):
    st.rerun()

st.sidebar.markdown("---")
if st.sidebar.button("Reset Session / Clear Chat"):
    reset_session()