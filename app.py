import streamlit as st
import pandas as pd
import plotly.express as px
from io import StringIO
from chat_crew import ChatCrew

# Page Configuration
st.set_page_config(page_title="FD Rate Chatbot", layout="wide")
st.title("Bank FD Rate Assistant")

# Initialize session state
if 'messages' not in st.session_state:
    st.session_state.messages = []
if 'df_data' not in st.session_state:
    st.session_state.df_data = None

# --- Helper Functions ---
def clean_rate_column(series):
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

def parse_csv_from_response(response_text):
    """Attempts to find and parse CSV data from the LLM response."""
    if "Bank," in response_text:
        csv_data = response_text[response_text.find("Bank,"):]
        try:
            return pd.read_csv(StringIO(csv_data))
        except Exception as e:
            st.error(f"Failed to parse CSV from response: {e}")
            return None
    return None

def display_grouped_tables(df):
    """Displays the dataframe broken down by Tenure."""
    st.subheader("Extracted Data Tables")
    
    df.columns = [c.strip().lower() for c in df.columns]
    
    tenure_col = next((c for c in df.columns if 'tenure' in c), None)
    bank_col = next((c for c in df.columns if 'bank' in c), None)
    gen_col = next((c for c in df.columns if 'general' in c), None)
    sen_col = next((c for c in df.columns if 'senior' in c), None)

    if not tenure_col:
        st.warning("Could not find 'Tenure' column in data.")
        st.dataframe(df)
        return

    unique_tenures = df[tenure_col].unique()
    unique_tenures = sorted(unique_tenures, key=str)

    for i, tenure in enumerate(unique_tenures, 1):
        with st.expander(f"Extracted Table {i}: Rates for {tenure}", expanded=True):
            subset = df[df[tenure_col] == tenure]
            cols_to_show = [bank_col, tenure_col, gen_col, sen_col]
            cols_to_show = [c for c in cols_to_show if c in subset.columns]
            st.dataframe(subset[cols_to_show], use_container_width=True)

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# Chat Input
if prompt := st.chat_input("Ask about FD rates (e.g., 'What are the rates for 1 year?')"):
    # Add user message to history
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # Generate response
    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            try:
                chat_crew = ChatCrew()
                result = chat_crew.kickoff(prompt)
                response_text = result.raw
                
                # Display the text response
                st.markdown(response_text)
                
                # Add assistant response to history
                st.session_state.messages.append({"role": "assistant", "content": response_text})

                # Check if response contains CSV data to update UI
                new_df = parse_csv_from_response(response_text)
                if new_df is not None:
                    st.session_state.df_data = new_df
                    st.success("Data updated successfully!")

            except Exception as e:
                st.error(f"An error occurred: {e}")
                st.session_state.messages.append({"role": "assistant", "content": f"Error: {e}"})

if st.session_state.df_data is not None:
    st.markdown("---")
    st.subheader("Interest Rate Comparison")

    df = st.session_state.df_data
    df.columns = [c.strip().lower() for c in df.columns]
    
    gen_col = next((c for c in df.columns if 'general' in c), None)
    sen_col = next((c for c in df.columns if 'senior' in c), None)
    bank_col = next((c for c in df.columns if 'bank' in c), None)
    tenure_col = next((c for c in df.columns if 'tenure' in c), None)

    if all([gen_col, sen_col, bank_col, tenure_col]):
        df['Gen Display'], df['Gen Max'] = clean_rate_column(df[gen_col])
        df['Sen Display'], df['Sen Max'] = clean_rate_column(df[sen_col])
        
        unique_tenures = df[tenure_col].unique()
        unique_tenures = sorted(unique_tenures, key=str)
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

        # Plot
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
        
        fig.update_layout(yaxis_title="Max Interest Rate (%)", xaxis_title="Bank Name", legend_title="Category")
        st.plotly_chart(fig, use_container_width=True)
    
    # Display Grouped Tables
    display_grouped_tables(st.session_state.df_data)

st.markdown("---")