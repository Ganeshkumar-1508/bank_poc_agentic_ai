import os
import streamlit as st
import pandas as pd
import plotly.express as px
from io import StringIO
from dotenv import load_dotenv
from crewai import Agent, Task, Crew, Process
from crewai_tools import ScrapeWebsiteTool
from langchain_nvidia_ai_endpoints import ChatNVIDIA

load_dotenv()

st.set_page_config(page_title="FD", layout="wide")
st.title("Bank FD")

scrape_tool = ScrapeWebsiteTool()

llm = ChatNVIDIA(
    model="nvidia_nim/meta/llama3-70b-instruct", 
    temperature=0,
    max_completion_tokens= 1300
)

data_scraper_agent = Agent(
    role="Financial Data Scraper",
    goal="Extract detailed FD rates for both General and Senior citizens.",
    backstory="You specialize in extracting financial comparison tables.",
    tools=[scrape_tool],
    verbose=True,
    llm=llm
)

scraping_task = Task(
    description=(
        "Scrape 'https://www.bankbazaar.com/fixed-deposit-rate.html'. "
        "Look for data covering both 'General Citizens' and 'Senior Citizens'. "
        "Extract the following columns: 'Bank', 'Tenure', 'General Interest Rate', 'Senior Interest Rate'. "
        "Ensure you capture the rates for the SAME tenure for both categories in the same row. "
        "Keep ranges (e.g., '6.50% - 7.25%') exactly as they appear. "
        "Return ONLY the CSV text with headers: Bank,Tenure,General Rate,Senior Rate. No markdown."
    ),
    expected_output="Strictly CSV string with Bank, Tenure, General Rate, Senior Rate.",
    agent=data_scraper_agent,
    tools=[scrape_tool]
)

my_crew = Crew(
    agents=[data_scraper_agent],
    tasks=[scraping_task],
    process=Process.sequential,
    verbose=True
)
def clean_rate_column(series):
    """Cleans rate strings and returns Max Value (for plotting) and Display String."""
    clean_display = []
    plot_values = []
    
    for val in series:
        val_str = str(val).replace('%', '').strip()
        if '-' in val_str:
            parts = val_str.split('-')
            try:
                max_val = max(float(p.strip()) for p in parts)
                plot_values.append(max_val)
                clean_display.append(val_str)
            except ValueError:
                plot_values.append(0.0)
                clean_display.append(val_str)
        else:
            try:
                val_float = float(val_str)
                plot_values.append(val_float)
                clean_display.append(val_str)
            except ValueError:
                plot_values.append(0.0)
                clean_display.append(val_str)
                
    return clean_display, plot_values

if st.button("Compare Rates"):
    with st.spinner("Scraping data..."):
        try:
            result = my_crew.kickoff()
            output_text = result.raw.strip()
            
            if "Bank," in output_text:
                csv_data = output_text[output_text.find("Bank,"):]
            else:
                csv_data = output_text

            df = pd.read_csv(StringIO(csv_data))
            
            df.columns = [c.strip().lower() for c in df.columns]
            
            gen_col = next((c for c in df.columns if 'general' in c), None)
            sen_col = next((c for c in df.columns if 'senior' in c), None)
            bank_col = next((c for c in df.columns if 'bank' in c), None)
            tenure_col = next((c for c in df.columns if 'tenure' in c), None)

            if not all([gen_col, sen_col, bank_col, tenure_col]):
                st.error("Missing required columns. Check raw output below.")
                st.text(result.raw)
                st.stop()

            df['Gen Display'], df['Gen Max'] = clean_rate_column(df[gen_col])
            df['Sen Display'], df['Sen Max'] = clean_rate_column(df[sen_col])
            
            csv_filename = "fd_rates_comparison.csv"
            df.to_csv(csv_filename, index=False)
            st.success(f"Data saved to `{csv_filename}`")

            st.subheader("Interest Rate Comparison")

            unique_tenures = df[tenure_col].unique()
            selected_tenure = st.selectbox("Select Tenure to Visualize", unique_tenures)

            df_filtered = df[df[tenure_col] == selected_tenure].copy()
            df_filtered = df_filtered.sort_values(by='Sen Max', ascending=False)

            df_long = pd.melt(
                df_filtered, 
                id_vars=[bank_col], 
                value_vars=['Gen Max', 'Sen Max'], 
                var_name='Citizen Type', 
                value_name='Interest Rate (%)'
            )

            df_long['Citizen Type'] = df_long['Citizen Type'].map({
                'Gen Max': 'General Citizen', 
                'Sen Max': 'Senior Citizen'
            })

            fig = px.bar(
                df_long, 
                x=bank_col, 
                y='Interest Rate (%)', 
                color='Citizen Type', 
                barmode='group', 
                title=f'FD Rates Comparison ({selected_tenure})',
                height=600,
                text_auto=True 
            )
            
            fig.update_layout(
                yaxis_title="Max Interest Rate (%)",
                xaxis_title="Bank Name",
                legend_title="Category"
            )
            
            st.plotly_chart(fig, use_container_width=True)

            st.subheader("Extracted Data")
            st.dataframe(df[[bank_col, tenure_col, gen_col, sen_col]])

        except Exception as e:
            st.error(f"An error occurred: {e}")
            st.exception(e)

st.markdown("---")