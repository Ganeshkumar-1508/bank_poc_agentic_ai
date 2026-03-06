import streamlit as st
import plotly.graph_objects as go
import json
import os
from typing import List, Dict, Any, Union

# Geolocation
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut, GeocoderUnavailable

# LangChain Components
from langchain_community.tools import DuckDuckGoSearchResults

# CrewAI & NVIDIA NIM
from crewai.tools import tool 
from crewai import Agent, Task, Crew, Process
from langchain_nvidia_ai_endpoints import ChatNVIDIA

# --- PAGE CONFIGURATION ---
st.set_page_config(layout="wide", page_title="Global Deposit Finder AI", page_icon="🌍")

# --- SIDEBAR CONFIGURATION ---
st.sidebar.title("⚙️ Configuration")
st.sidebar.markdown("Enter your **NVIDIA NIM API Key** to enable the AI agents.")
NVIDIA_API_KEY = st.sidebar.text_input("NVIDIA API Key", type="password")

# --- ROBUST TOOL DEFINITION ---
# We add logic to handle both dictionary and string inputs to prevent parsing errors.

@tool
def search_deposit_providers(query: Union[str, dict]) -> str:
    """
    Searches for Fixed Deposit or Term Deposit providers using DuckDuckGo.
    Input can be a search query string or a dictionary with a 'query' key.
    Returns a JSON list of results.
    """
    # 1. Robust Input Parsing
    # If the agent passes a dictionary (e.g., {"query": "banks"}), extract the value.
    if isinstance(query, dict):
        search_term = query.get("query", str(query))
    else:
        search_term = str(query)

    # 2. Execute Search
    search = DuckDuckGoSearchResults(output_format="list", num_results=5)
    
    try:
        results = search.invoke(search_term)
        return json.dumps(results, indent=2)
    except Exception as e:
        return f"Error during search: {str(e)}"

# --- HELPER FUNCTIONS ---

def get_location_from_coords(lat, lon):
    """Reverse geocode coordinates to get country/region."""
    geolocator = Nominatim(user_agent="global_deposit_app")
    try:
        location = geolocator.reverse(f"{lat}, {lon}", language='en', exactly_one=True)
        if location:
            address = location.raw.get('address', {})
            country = address.get('country', 'Unknown')
            city = address.get('city') or address.get('state') or address.get('region') or address.get('county')
            return country, city
    except (GeocoderTimedOut, GeocoderUnavailable):
        return "Unknown", "Unknown"
    except Exception:
        return "Unknown", "Unknown"
    return "Unknown", "Unknown"

# --- AI AGENT SETUP (CrewAI + NVIDIA NIM) ---

def run_financial_crew(location_name):
    """
    Initializes CrewAI agents to find Fixed Deposit providers using NVIDIA NIM.
    """
    if not NVIDIA_API_KEY:
        return "⚠️ Please enter your NVIDIA API Key in the sidebar."

    # CRITICAL: Set Environment Variable for LiteLLM (used by CrewAI)
    os.environ["NVIDIA_NIM_API_KEY"] = NVIDIA_API_KEY

    # 1. Initialize the LLM (NVIDIA NIM)
    try:
        llm = ChatNVIDIA(
            model="meta/llama-3.1-70b-instruct",
            nvidia_api_key=NVIDIA_API_KEY,
            temperature=0.2
        )
    except Exception as e:
        return f"Error initializing NVIDIA NIM: {str(e)}"

    # 2. Define Agents
    researcher = Agent(
        role='Senior Financial Researcher',
        goal=f'Find the top 5 Fixed Deposit or Term Deposit providers in {location_name}',
        backstory="""You are an expert financial analyst. You use search tools to find accurate, 
        up-to-date information about banking institutions. You focus on interest rates (APY) and terms.""",
        verbose=True,
        allow_delegation=False,
        tools=[search_deposit_providers], 
        llm=llm
    )

    analyst = Agent(
        role='Financial Summarizer',
        goal='Summarize findings into a concise list with key interest rates or benefits',
        backstory="""You take raw financial data and format it cleanly for users. 
        You highlight key interest rates and unique selling points.""",
        verbose=True,
        allow_delegation=False,
        llm=llm
    )

    # 3. Define Tasks
    search_task = Task(
        description=f"""Search for the top 5 Fixed Deposit providers in {location_name}. 
        1. Identify the bank name.
        2. Identify the approximate interest rate (APY).
        3. Identify a key feature (e.g., 'no minimum deposit', 'insured').
        Use the search tool to gather this data.
        """,
        expected_output="A structured list of banks with their financial details.",
        agent=researcher
    )

    summary_task = Task(
        description="""Format the search results into a clean Markdown list.
        For each provider, provide:
        1. **Name**
        2. *Interest Rate*
        3. A short 1-sentence summary.
        
        If specific rates are not found, provide the best available information.
        """,
        expected_output="A formatted markdown list of the top 5 providers.",
        agent=analyst
    )

    # 4. Form Crew and Execute
    crew = Crew(
        agents=[researcher, analyst],
        tasks=[search_task, summary_task],
        process=Process.sequential,
        verbose=True
    )

    try:
        result = crew.kickoff()
        return result
    except Exception as e:
        return f"An error occurred with the AI Agents: {str(e)}"

# --- VISUALIZATION ---

def create_globe():
    """Creates a 3D Globe using Plotly."""
    countries = ['USA', 'CAN', 'GBR', 'FRA', 'DEU', 'JPN', 'AUS', 'BRA', 'IND', 'CHN', 'RUS', 'ZAF']
    
    fig = go.Figure()
    
    fig.add_trace(go.Choropleth(
        locations = countries,
        z = [1] * len(countries),
        colorscale = [[0, 'rgb(230, 230, 230)'], [1, 'rgb(230, 230, 230)']],
        showscale = False,
        geo = 'geo',
        hoverinfo = 'location',
        marker_line_color='white',
        marker_line_width=0.5
    ))

    fig.update_geos(
        projection_type="orthographic",
        showland=True,
        landcolor="rgb(230, 230, 230)",
        coastlinecolor="white",
        showocean=True,
        oceancolor="rgb(210, 230, 250)",
        showcountries=True,
        countrycolor="darkgray",
        showframe=False
    )

    fig.update_layout(
        margin=dict(l=0, r=0, t=0, b=0),
        height=700,
        clickmode='event+select',
        dragmode='pan'
    )
    
    return fig

# --- MAIN APP ---

def main():
    st.title("🌍 Global Fixed Deposit Finder")
    st.markdown("""
        **Click anywhere on the globe** (or use the input below) to find the Top 5 Fixed/Term Deposit providers in that region.
        Data is fetched in real-time by **CrewAI Agents** powered by **NVIDIA NIM**.
    """)

    if not NVIDIA_API_KEY:
        st.warning("⚠️ Please enter your NVIDIA NIM API Key in the sidebar to proceed.")
        st.stop()

    if 'results' not in st.session_state:
        st.session_state.results = None
    if 'location' not in st.session_state:
        st.session_state.location = "United States"

    col1, col2 = st.columns([2, 1])

    with col1:
        st.subheader("Interactive Globe")
        fig = create_globe()
        st.plotly_chart(fig, on_select="rerun", use_container_width=True)

    with col2:
        st.subheader("Location Details")
        user_location = st.text_input("Refine Location", value=st.session_state.location)
        
        if st.button("Find Top 5 Providers", type="primary"):
            if not user_location:
                st.error("Please enter a location.")
            else:
                st.session_state.location = user_location
                with st.spinner("🤖 Agents are researching... (Powered by NVIDIA NIM)"):
                    st.session_state.results = run_financial_crew(user_location)

        if st.session_state.results:
            st.markdown(f"### Results for {st.session_state.location}")
            st.markdown("---")
            st.markdown(st.session_state.results)

if __name__ == "__main__":
    main()