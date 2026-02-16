import os
import re
import pandas as pd
import streamlit as st
import matplotlib.pyplot as plt
from dotenv import load_dotenv
from fd_crew import run_crew

load_dotenv()

def parse_projection_table(projection_text: str) -> pd.DataFrame:
    """Parse the projection output into a structured DataFrame."""
    data = []
    try:
        clean_text = projection_text.replace("```csv", "").replace("```", "").strip()
        lines = clean_text.split('\n')

        for line in lines:
            if line.strip() and not line.lower().startswith('provider,'):
                parts = [part.strip() for part in line.split(',')]
                if len(parts) >= 4:
                    provider = parts[0]

                    rate_str = parts[1].replace('%', '').strip()
                    try:
                        rate = float(rate_str)
                    except ValueError:
                        rate = 0.0

                    maturity_str = parts[2].replace('₹', '').replace(',', '').strip()
                    try:
                        maturity = float(maturity_str)
                    except ValueError:
                        maturity = 0.0

                    interest_str = parts[3].replace('₹', '').replace(',', '').strip()
                    try:
                        interest = float(interest_str)
                    except ValueError:
                        interest = 0.0

                    data.append({
                        'Provider': provider,
                        'Interest Rate (%)': rate,
                        'Maturity Amount': maturity,
                        'Interest Earned': interest
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
#st.markdown("Find the best fixed deposit options with highest interest rates and safety analysis.")

if not os.getenv("NVIDIA_API_KEY"):
    st.error("NVIDIA_API_KEY not found in environment variables!")
    st.stop()

st.markdown("### Enter your query")
#st.markdown("Example: *What will be maturity amount if I deposited 100k as a onetime payment for 5 years?*")

user_query = st.text_area("Your Question:", height=100, placeholder="your query..")

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
        #status_text.text("Analysis complete!")

        st.markdown("---")
        st.markdown('<h2 class="sub-header">Analysis Report</h2>', unsafe_allow_html=True)

        st.markdown(result.raw)

        st.markdown("---")
        st.markdown('<h2 class="sub-header">Financial Projections</h2>', unsafe_allow_html=True)

        if len(result.tasks_output) >= 5:
            projection_output = result.tasks_output[4].raw
            safety_output = result.tasks_output[3].raw

            projection_data = parse_projection_table(projection_output)
            safety_map = parse_safety_data(safety_output)

            if not projection_data.empty and safety_map:
                projection_data['Safety Category'] = projection_data['Provider'].apply(
                    lambda x: safety_map.get(x.strip(), safety_map.get(x.strip().lower(), "Unknown"))
                )
            else:
                projection_data['Safety Category'] = "Unknown"

            if not projection_data.empty:
                st.dataframe(projection_data, use_container_width=True)

                col_viz1, col_viz2 = st.columns(2)

                with col_viz1:
                    st.markdown("### Maturity Amount Comparison")
                    fig1, ax1 = plt.subplots(figsize=(10, 6))

                    color_map = {'Safe': '#3B82F6', 'Moderate': '#F59E0B', 'Risky': '#EF4444', 'Unknown': '#9CA3AF'}
                    colors = [color_map.get(cat, '#9CA3AF') for cat in projection_data['Safety Category']]

                    bars = ax1.barh(projection_data['Provider'], projection_data['Maturity Amount'], color=colors)
                    ax1.set_xlabel('Maturity Amount (INR)')
                    ax1.set_title('Projected Maturity Amounts by Provider')

                    for bar in bars:
                        width = bar.get_width()
                        ax1.text(width * 1.01, bar.get_y() + bar.get_height()/2, 
                                 f'Rs.{width:,.0f}', ha='left', va='center')

                    plt.tight_layout()
                    st.pyplot(fig1)

                with col_viz2:
                    st.markdown("### Interest Rate Distribution")
                    fig2, ax2 = plt.subplots(figsize=(10, 6))
                    ax2.bar(projection_data['Provider'], projection_data['Interest Rate (%)'], color=colors)
                    ax2.set_xlabel('Provider')
                    ax2.set_ylabel('Interest Rate (%)')
                    ax2.set_title('Interest Rates by Provider')
                    ax2.tick_params(axis='x', rotation=45)

                    for i, v in enumerate(projection_data['Interest Rate (%)']):
                        ax2.text(i, v + 0.05, f'{v}%', ha='center')

                    plt.tight_layout()
                    st.pyplot(fig2)

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

                st.markdown("---")
                st.markdown('<h2 class="sub-header">Top Recommendations</h2>', unsafe_allow_html=True)

                safe_options = projection_data[projection_data['Safety Category'] == 'Safe']
                if not safe_options.empty:
                    top_recommendation = safe_options.loc[safe_options['Interest Rate (%)'].idxmax()]
                    st.success(f"**Best Safe Option**: {top_recommendation['Provider']} "
                              f"at {top_recommendation['Interest Rate (%)']}% "
                              f"(Maturity: Rs.{top_recommendation['Maturity Amount']:,.2f})")

                highest_return = projection_data.loc[projection_data['Interest Rate (%)'].idxmax()]
                st.info(f"**Highest Return**: {highest_return['Provider']} "
                       f"at {highest_return['Interest Rate (%)']}% "
                       f"(Maturity: Rs.{highest_return['Maturity Amount']:,.2f}) - "
                       f"Safety: {highest_return['Safety Category']}")
            else:
                st.warning("Could not generate projection data visualization.")
        else:
            st.warning("Crew output structure was not as expected. Unable to visualize details.")

    except Exception as e:
        st.error(f"An error occurred during analysis: {str(e)}")
        st.exception(e)

elif analyze_button and not user_query:
    st.warning("Please enter a question to analyze.")