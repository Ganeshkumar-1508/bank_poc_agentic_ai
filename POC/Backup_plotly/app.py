import os
import re
import io
import json
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
from dotenv import load_dotenv
from fd_crew import run_crew
from langchain_nvidia_ai_endpoints import NVIDIA

load_dotenv()

# --- 1. Helper Functions ---

def normalize_name(name):
    """Remove common suffixes and punctuation for better matching."""
    name = name.lower().strip()
    # Remove common words that cause mismatches
    for suffix in ["bank", "ltd", "limited", "co", "corp", "financial services", "finance", "."]:
        name = name.replace(suffix, "")
    return name.strip()

def parse_data(projection_text: str, safety_text: str) -> pd.DataFrame:
    """Parse projection CSV and safety text into a single DataFrame with robust matching."""
    try:
        # --- Parse Projection CSV ---
        clean_csv = projection_text.replace("```csv", "").replace("```", "").strip()
        df = pd.read_csv(io.StringIO(clean_csv))
        df.columns = ['Provider', 'Interest Rate (%)', 'Maturity Amount', 'Interest Earned']
        
        # Clean numeric columns
        df['Interest Rate (%)'] = df['Interest Rate (%)'].astype(str).str.replace('%', '').astype(float)
        df['Maturity Amount'] = df['Maturity Amount'].astype(str).str.replace(r'[₹,]', '', regex=True).astype(float)
        df['Interest Earned'] = df['Interest Earned'].astype(str).str.replace(r'[₹,]', '', regex=True).astype(float)

        # --- Parse Safety Data (Robust Regex) ---
        safety_map = {} # Map for exact matches
        safety_map_norm = {} # Map for normalized matches (fuzzy)
        
        # Regex looks for "Provider: [Name], Category: [Category]"
        # DOTALL allows newlines inside the text
        pattern = re.compile(r"Provider:\s*(.*?)\s*,\s*Category:\s*(Safe|Moderate|Risky)", re.IGNORECASE | re.DOTALL)
        matches = pattern.findall(safety_text)
        
        for match in matches:
            provider_raw = match[0].strip()
            category = match[1].strip().capitalize() # Ensure 'Safe' not 'safe'
            
            # Store exact match
            safety_map[provider_raw] = category
            # Store normalized match (e.g., "hdfc" -> "Safe")
            safety_map_norm[normalize_name(provider_raw)] = category

        # --- Map Safety to DataFrame ---
        def get_safety_category(provider_name):
            p = provider_name.strip()
            # 1. Try Exact Match
            if p in safety_map:
                return safety_map[p]
            # 2. Try Normalized Match
            p_norm = normalize_name(p)
            if p_norm in safety_map_norm:
                return safety_map_norm[p_norm]
            # 3. Fallback: Check if any safety key is a substring of the provider name
            for key, val in safety_map.items():
                if key.lower() in p.lower() or p.lower() in key.lower():
                    return val
            return "Unknown"

        df['Safety Category'] = df['Provider'].apply(get_safety_category)
        return df

    except Exception as e:
        st.warning(f"Data parsing issue: {e}")
        return pd.DataFrame()

def extract_entities(query: str):
    """Extract amount and tenure using improved Regex + LLM fallback."""
    
    # Pre-clean: Remove commas to handle "50,000" -> "50000"
    clean_query = query.replace(',', '').lower()
    
    # 1. Extract Tenure (Strict: requires time unit)
    tenure = 0.0
    t_match = re.search(r'(\d+(?:\.\d+)?)\s*(?:years?|yrs?|months?|mo)\b', clean_query)
    if t_match:
        val = float(t_match.group(1))
        unit = t_match.group(0) 
        if 'month' in unit or 'mo' in unit:
            tenure = val / 12.0
        else:
            tenure = val

    # 2. Extract Amount
    amount = 0.0
    amt_matches = re.findall(r'(\d+(?:\.\d+)?)\s*(k|thousand|lakh|lac)?', clean_query)
    
    possible_amounts = []
    for val_str, unit in amt_matches:
        val = float(val_str)
        if unit in ['k', 'thousand']: val *= 1000
        elif unit in ['lakh', 'lac']: val *= 100000
        if val != tenure: # Ignore tenure number
            possible_amounts.append(val)

    if possible_amounts:
        amount = max(possible_amounts)

    # 3. Fallback to LLM
    if amount == 0.0 or tenure == 0.0:
        try:
            llm = NVIDIA(model="meta/llama-3.1-405b-instruct")
            prompt = f'Extract amount and tenure in JSON from: "{query}". Format: {{"amount": 1000, "tenure": 1}}'
            resp = json.loads(llm.invoke(prompt).content.replace("```", ""))
            return float(resp.get("amount", 0)), float(resp.get("tenure", 0))
        except:
            return None, None
            
    return amount, tenure

# --- 2. Page Setup ---

st.set_page_config(page_title="FD Advisor Chat", layout="wide")
st.markdown('<h1 style="color:#1E3A8A">Fixed Deposit Advisor</h1>', unsafe_allow_html=True)

if not os.getenv("NVIDIA_API_KEY"):
    st.error("NVIDIA_API_KEY missing in .env"); st.stop()

# --- 3. Chat Logic ---

if "messages" not in st.session_state:
    st.session_state.messages = []

# Display History
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if "df" in msg:
            st.dataframe(msg["df"], use_container_width=True)

# Handle Input
if prompt := st.chat_input("Ask about FD rates..."):
    st.chat_message("user").markdown(prompt)
    st.session_state.messages.append({"role": "user", "content": prompt})

    with st.chat_message("assistant"):
        status = st.empty()
        status.markdown("Analyzing query...")
        
        amount, tenure = extract_entities(prompt)
        
        if not amount or not tenure:
            status.markdown(" Could not understand. Try: *'Invest 50,000 for 3 years'*")
        else:
            status.markdown(f" Found: **₹{amount:,.0f}** for **{tenure} years**. Running analysis...")
            
            try:
                result = run_crew(amount, tenure)
                status.markdown("✅ Analysis Complete!")
                st.markdown(result.raw)

                # Visualization
                if len(result.tasks_output) >= 4:
                    df = parse_data(result.tasks_output[3].raw, result.tasks_output[2].raw)
                    
                    if not df.empty:
                        st.markdown("### Visualizations")
                        st.dataframe(df, use_container_width=True)
                        
                        # Define Colors explicitly
                        color_map = {'Safe': '#3B82F6', 'Moderate': '#F59E0B', 'Risky': '#EF4444', 'Unknown': '#9CA3AF'}
                        colors = [color_map.get(cat, '#9CA3AF') for cat in df['Safety Category']]
                        
                        c1, c2 = st.columns(2)
                        with c1:
                            fig = go.Figure(go.Bar(
                                x=df['Maturity Amount'], y=df['Provider'], orientation='h',
                                marker_color=colors, 
                                text=df['Maturity Amount'].apply(lambda x: f'₹{x:,.0f}'),
                                textposition='auto'
                            ))
                            fig.update_layout(title="Maturity Amounts (Color = Safety)"); 
                            st.plotly_chart(fig, use_container_width=True)
                        
                        with c2:
                            fig = go.Figure(go.Bar(
                                x=df['Provider'], y=df['Interest Rate (%)'],
                                marker_color=colors,
                                text=df['Interest Rate (%)'].apply(lambda x: f'{x}%'),
                                textposition='auto'
                            ))
                            fig.update_layout(title="Interest Rates (Color = Safety)"); 
                            st.plotly_chart(fig, use_container_width=True)
                        
                        st.session_state.messages.append({"role": "assistant", "content": result.raw, "df": df})
                    else:
                        st.session_state.messages.append({"role": "assistant", "content": result.raw})
            except Exception as e:
                st.error(f"Error: {e}")