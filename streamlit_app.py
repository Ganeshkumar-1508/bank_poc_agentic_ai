import json
import pandas as pd
import streamlit as st

from config import CSV_PATH, SOURCE_NAME, SOURCE_URL, TOP_PROVIDERS
from tools import parse_user_query, scrape_fd_rates, save_rates_to_csv, website_search_tool
from agents import run_consultant_summary

st.set_page_config(page_title="FD/TD POC", layout="wide")

st.title("FD/TD Agentic POC")


col1, col2, col3 = st.columns(3)
with col1:
    age = st.number_input("Age", min_value=10, max_value=120, value=30)
with col2:
    amount = st.number_input("Amount", min_value=1000.0, step=1000.0, value=100000.0)
with col3:
    query = st.text_input("Query", value="I want to invest in FD for 180 days with my savings")
#
if st.button("Run"):
    parsed = parse_user_query(query)
    senior = age >= 60
    selected_amount = amount if amount > 0 else parsed.amount

    rates = scrape_fd_rates(selected_amount, senior, tenure_days=parsed.tenure_days, top_n=TOP_PROVIDERS)
    csv_path = save_rates_to_csv(rates, CSV_PATH)

    if rates:
        df = pd.DataFrame([r.__dict__ for r in rates])
        selected_cols = [c for c in ["provider", "interest_rate", "tenure", "rate_max", "senior_citizen", "source_name"] if c in df.columns]
        df = df[selected_cols]
        st.subheader("Best Providers")
        st.dataframe(df, use_container_width=True)
    else:
        st.warning("No rows extracted. The source page structure may have changed.")

    if parsed.tenure_days is not None:
        st.caption(f"Parsed tenure from query: {parsed.tenure_days} days")
    st.caption(f"Primary source: {SOURCE_NAME}")
    st.caption(f"CSV saved to: {csv_path}")

    # st.subheader("RAG (WebsiteSearchTool)")
    # rag = website_search_tool(query, [SOURCE_URL])
    # st.write(rag)

    st.subheader("Consultant Summary")
    context = json.dumps({"query": query, "source": SOURCE_URL, "top_providers": [r.__dict__ for r in rates]}, indent=2)
    # summary = run_consultant_summary(context)
    # st.write(summary)
