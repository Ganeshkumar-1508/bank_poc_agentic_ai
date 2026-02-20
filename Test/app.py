import os
import re
import pandas as pd
import streamlit as st
import matplotlib.pyplot as plt
from dotenv import load_dotenv
from fd_crew import run_crew

load_dotenv()

def parse_projection_table(projection_text: str) -> pd.DataFrame:
    """Parse the projection output into a structured DataFrame with General & Senior columns."""
    data = []
    try:
        clean_text = projection_text.replace("```csv", "").replace("```", "").strip()
        lines = clean_text.split('\n')

        for line in lines:
            if line.strip() and not line.lower().startswith('provider'):
                # Expecting: Provider, Gen Rate, Sen Rate, Gen Mat, Sen Mat, Gen Int, Sen Int
                parts = [part.strip() for part in line.split(',')]
                
                if len(parts) >= 7:
                    provider = parts[0]

                    # Helper to clean and convert
                    def parse_val(val_str):
                        val_str = val_str.replace('%', '').replace('₹', '').replace(',', '').strip()
                        try:
                            return float(val_str)
                        except ValueError:
                            return 0.0

                    gen_rate = parse_val(parts[1])
                    sen_rate = parse_val(parts[2])
                    gen_maturity = parse_val(parts[3])
                    sen_maturity = parse_val(parts[4])
                    gen_interest = parse_val(parts[5])
                    sen_interest = parse_val(parts[6])

                    data.append({
                        'Provider': provider,
                        'General Rate (%)': gen_rate,
                        'Senior Rate (%)': sen_rate,
                        'General Maturity': gen_maturity,
                        'Senior Maturity': sen_maturity,
                        'General Interest': gen_interest,
                        'Senior Interest': sen_interest
                    })

        df = pd.DataFrame(data)
        return df

    except Exception as e:
        st.warning(f"Could not parse projection table: {str(e)}")
        return pd.DataFrame()

def parse_safety_data(safety_text: str) -> dict:
    """Parse safety task output to extract categories."""
    safety_map = {}
    try:
        lines = safety_text.split('\n')
        for line in lines:
            if "Provider:" in line and "Category:" in line:
                provider_part = line.split("Provider:")[1].split(",")[0].strip()
                category_part = line.split("Category:")[1].split(",")[0].strip()
                safety_map[provider_part] = category_part
    except Exception as e:
        st.warning(f"Could not parse safety data: {str(e)}")
    return safety_map

def parse_all_news_sources(research_text: str) -> dict:
    """
    Parses the research output to extract all news headlines and URLs per provider.
    Expected Format:
        Provider: Name
        News: Headline | URL: Link
        News: Headline | URL: Link
    """
    providers_data = {}
    
    # Split the text by "Provider:" to get blocks for each bank
    blocks = [b for b in research_text.split("Provider:") if b.strip()]
    
    for block in blocks:
        lines = block.split('\n')
        
        # The first line of the block is the Provider Name
        provider_name = lines[0].strip()
        
        news_items = []
        
        # Iterate through the rest of the lines to find news
        for line in lines[1:]:
            if "News:" in line and "URL:" in line:
                try:
                    # Split by "URL:" to separate headline and link
                    parts = line.split("URL:")
                    headline_part = parts[0].replace("News:", "").strip()
                    url_part = parts[1].strip()
                    
                    news_items.append({
                        "headline": headline_part,
                        "url": url_part
                    })
                except Exception:
                    continue
        
        if provider_name and news_items:
            providers_data[provider_name] = news_items
            
    return providers_data

st.set_page_config(
    page_title="Fixed Deposit Advisor",
    page_icon="",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem !important;
        color: #1E3A8A;
        margin-bottom: 1rem;
    }
    .sub-header {
        font-size: 1.5rem;
        color: #3B82F6;
        margin-top: 1rem;
        margin-bottom: 0.5rem;
    }
    .stButton>button {
        background-color: #3B82F6;
        color: white;
        font-weight: bold;
        border-radius: 5px;
        padding: 0.5rem 1rem;
    }
    .stButton>button:hover {
        background-color: #2563EB;
    }
</style>
""", unsafe_allow_html=True)

st.markdown('<h1 class="main-header">Fixed Deposit Advisor</h1>', unsafe_allow_html=True)

if not os.getenv("NVIDIA_API_KEY"):
    st.error("NVIDIA_API_KEY not found in environment variables!")
    st.stop()

st.markdown("### Enter your query")

user_query = st.text_area("Your Question:", height=100, placeholder="e.g., What will be maturity amount for 5 lakhs for 5 years?")

col1, col2, col3 = st.columns([1, 2, 1])
with col2:
    analyze_button = st.button("Analyze Fixed Deposit Options", use_container_width=True)

if analyze_button and user_query:
    progress_bar = st.progress(0)
    status_text = st.empty()

    try:
        status_text.text("Analyzing your request to extract investment details...")
        progress_bar.progress(10)

        with st.spinner("Processing... This may take 2-3 minutes. Please wait."):
            result = run_crew(user_query)

        progress_bar.progress(80)
        status_text.text("Preparing visualizations...")

        progress_bar.progress(100)

        st.markdown("---")
        st.markdown('<h2 class="sub-header">Analysis Report</h2>', unsafe_allow_html=True)
        st.markdown(result.raw)

        # --- Process Data for Visualization ---
        st.markdown("---")
        st.markdown('<h2 class="sub-header">Financial Projections</h2>', unsafe_allow_html=True)

        if len(result.tasks_output) >= 5:
            projection_output = result.tasks_output[4].raw
            safety_output = result.tasks_output[3].raw

            projection_data = parse_projection_table(projection_output)
            safety_map = parse_safety_data(safety_output)

            # Map Safety
            if not projection_data.empty and safety_map:
                projection_data['Safety Category'] = projection_data['Provider'].apply(
                    lambda x: safety_map.get(x.strip(), safety_map.get(x.strip().lower(), "Unknown"))
                )
            else:
                projection_data['Safety Category'] = "Unknown"

            if not projection_data.empty:
                st.dataframe(projection_data, use_container_width=True)

                col_viz1, col_viz2 = st.columns(2)

                # --- Visualization 1: Maturity Amounts (Side by Side) ---
                with col_viz1:
                    st.markdown("### Maturity Amount Comparison")
                    fig1, ax1 = plt.subplots(figsize=(10, 6))

                    providers = projection_data['Provider']
                    gen_maturity = projection_data['General Maturity']
                    sen_maturity = projection_data['Senior Maturity']
                    
                    x = range(len(providers))
                    width = 0.35

                    # Create bars
                    rects1 = ax1.barh([i - width/2 for i in x], gen_maturity, width, label='General', color='#60A5FA') # Lighter Blue
                    rects2 = ax1.barh([i + width/2 for i in x], sen_maturity, width, label='Senior', color='#1E40AF')   # Darker Blue

                    ax1.set_xlabel('Maturity Amount (INR)')
                    ax1.set_title('Projected Maturity: General vs Senior')
                    ax1.set_yticks(x)
                    ax1.set_yticklabels(providers)
                    ax1.legend()

                    # Add labels
                    ax1.bar_label(rects1, padding=3, fmt='Rs.%0.0f')
                    ax1.bar_label(rects2, padding=3, fmt='Rs.%0.0f')

                    plt.tight_layout()
                    st.pyplot(fig1)

                # --- Visualization 2: Interest Rates (Side by Side) ---
                with col_viz2:
                    st.markdown("### Interest Rate Distribution")
                    fig2, ax2 = plt.subplots(figsize=(10, 6))
                    
                    gen_rate = projection_data['General Rate (%)']
                    sen_rate = projection_data['Senior Rate (%)']

                    rects1 = ax2.bar([i - width/2 for i in x], gen_rate, width, label='General Rate', color='#60A5FA')
                    rects2 = ax2.bar([i + width/2 for i in x], sen_rate, width, label='Senior Rate', color='#1E40AF')

                    ax2.set_xlabel('Provider')
                    ax2.set_ylabel('Interest Rate (%)')
                    ax2.set_title('Interest Rates: General vs Senior')
                    ax2.set_xticks(x)
                    ax2.set_xticklabels(providers, rotation=45, ha='right')
                    ax2.legend()

                    ax2.bar_label(rects1, padding=3, fmt='%0.1f%%')
                    ax2.bar_label(rects2, padding=3, fmt='%0.1f%%')

                    plt.tight_layout()
                    st.pyplot(fig2)

                # --- News & Sources Section ---
                st.markdown("---")
                st.markdown('<h2 class="sub-header">News & Sources</h2>', unsafe_allow_html=True)

                # Research task is at index 2
                if len(result.tasks_output) >= 3:
                    research_output = result.tasks_output[2].raw
                    all_news = parse_all_news_sources(research_output)

                    if all_news:
                        for provider, items in all_news.items():
                            with st.expander(f"📰 News for {provider} ({len(items)} articles)"):
                                for item in items:
                                    st.markdown(f"- [{item['headline']}]({item['url']})")
                    else:
                        st.info("No structured news links found. Check the Market Overview in the report above.")
                else:
                    st.warning("Research output not available.")

                # --- Safety Overview ---
                st.markdown("---")
                st.markdown('<h2 class="sub-header">Safety Overview</h2>', unsafe_allow_html=True)

                safety_counts = projection_data['Safety Category'].value_counts()
                col_safety1, col_safety2, col_safety3 = st.columns(3)

                with col_safety1:
                    st.metric("Safe Providers", safety_counts.get('Safe', 0), delta=None)
                with col_safety2:
                    st.metric("Moderate Risk", safety_counts.get('Moderate', 0), delta=None)
                with col_safety3:
                    st.metric("High Risk", safety_counts.get('Risky', 0), delta=None)

                # --- Top Recommendations ---
                st.markdown("---")
                st.markdown('<h2 class="sub-header">Top Recommendations</h2>', unsafe_allow_html=True)

                # Best Safe Options (General)
                safe_options = projection_data[projection_data['Safety Category'] == 'Safe']
                if not safe_options.empty:
                    best_safe_gen = safe_options.loc[safe_options['General Rate (%)'].idxmax()]
                    st.success(f"**Best Safe Option (General)**: {best_safe_gen['Provider']} "
                              f"at {best_safe_gen['General Rate (%)']}% "
                              f"(Maturity: Rs.{best_safe_gen['General Maturity']:,.2f})")
                    
                    # Best Safe Options (Senior)
                    best_safe_sen = safe_options.loc[safe_options['Senior Rate (%)'].idxmax()]
                    st.info(f"**Best Safe Option (Senior)**: {best_safe_sen['Provider']} "
                              f"at {best_safe_sen['Senior Rate (%)']}% "
                              f"(Maturity: Rs.{best_safe_sen['Senior Maturity']:,.2f})")

                # Highest Returns (General vs Senior)
                highest_gen = projection_data.loc[projection_data['General Rate (%)'].idxmax()]
                highest_sen = projection_data.loc[projection_data['Senior Rate (%)'].idxmax()]
                
                st.warning(f"**Highest Return (General)**: {highest_gen['Provider']} "
                       f"at {highest_gen['General Rate (%)']}% "
                       f"(Maturity: Rs.{highest_gen['General Maturity']:,.2f}) - "
                       f"Safety: {highest_gen['Safety Category']}")
                
                st.warning(f"**Highest Return (Senior)**: {highest_sen['Provider']} "
                       f"at {highest_sen['Senior Rate (%)']}% "
                       f"(Maturity: Rs.{highest_sen['Senior Maturity']:,.2f}) - "
                       f"Safety: {highest_sen['Safety Category']}")

            else:
                st.warning("Could not generate projection data visualization.")
        else:
            st.warning("Crew output structure was not as expected. Unable to visualize details.")

    except Exception as e:
        st.error(f"An error occurred during analysis: {str(e)}")
        st.exception(e)

elif analyze_button and not user_query:
    st.warning("Please enter a question to analyze.")