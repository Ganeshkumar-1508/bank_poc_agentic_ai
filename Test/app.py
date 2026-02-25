import os
import re
import pandas as pd
import streamlit as st
import json
import matplotlib.pyplot as plt
from dotenv import load_dotenv
from fd_crew import run_crew
from database_manager import save_user_data

load_dotenv()

# --- Helper Functions ---
def parse_projection_table(projection_text: str) -> pd.DataFrame:
    data = []
    try:
        clean_text = projection_text.replace("```csv", "").replace("```", "").strip()
        lines = clean_text.split('\n')

        for line in lines:
            if line.strip() and not line.lower().startswith('provider'):
                parts = [part.strip() for part in line.split(',')]
                if len(parts) >= 7:
                    def parse_val(val_str):
                        val_str = val_str.replace('%', '').replace('₹', '').replace(',', '').strip()
                        try:
                            return float(val_str)
                        except ValueError:
                            return 0.0

                    data.append({
                        'Provider': parts[0],
                        'General Rate (%)': parse_val(parts[1]),
                        'Senior Rate (%)': parse_val(parts[2]),
                        'General Maturity': parse_val(parts[3]),
                        'Senior Maturity': parse_val(parts[4]),
                        'General Interest': parse_val(parts[5]),
                        'Senior Interest': parse_val(parts[6])
                    })
        return pd.DataFrame(data)
    except Exception as e:
        st.warning(f"Could not parse projection table: {str(e)}")
        return pd.DataFrame()


def parse_safety_data(safety_text: str) -> dict:
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
    providers_data = {}
    blocks = [b for b in research_text.split("Provider:") if b.strip()]
    for block in blocks:
        lines = block.split('\n')
        provider_name = lines[0].strip()
        news_items = []
        for line in lines[1:]:
            if "News:" in line and "URL:" in line:
                try:
                    parts = line.split("URL:")
                    headline_part = parts[0].replace("News:", "").strip()
                    url_part = parts[1].strip()
                    news_items.append({"headline": headline_part, "url": url_part})
                except Exception:
                    continue
        if provider_name and news_items:
            providers_data[provider_name] = news_items
    return providers_data


# --- Page Configuration ---
st.set_page_config(
    page_title="FD Advisor with AML",
    page_icon="🛡️",
    layout="wide",
)

st.markdown("""
<style>
    .main-header { font-size: 2.5rem !important; color: #1E3A8A; margin-bottom: 1rem; }
    .chat-message { padding: 1rem; border-radius: 0.5rem; margin-bottom: 1rem; }
</style>
""", unsafe_allow_html=True)

st.markdown('<h1 class="main-header">FD Advisor & AML Check</h1>', unsafe_allow_html=True)

if not os.getenv("NVIDIA_API_KEY"):
    st.error("NVIDIA_API_KEY not found in environment variables!")
    st.stop()

# --- Session State Initialization ---
if "messages" not in st.session_state:
    st.session_state.messages = []
    st.session_state.messages.append({
        "role": "assistant",
        "content": (
            "Hello! I can help you find the best Fixed Deposit options. "
            "Before we proceed, I need to collect some details for KYC/AML verification."
        )
    })

if "user_data" not in st.session_state:
    st.session_state.user_data = {
        "name": None, "dob": None, "address": None,
        "pan": None, "phone": None, "email": None, "account_number": None
    }

if "kyc_complete" not in st.session_state:
    st.session_state.kyc_complete = False

if "aml_checked" not in st.session_state:
    st.session_state.aml_checked = False

if "last_analysis_result" not in st.session_state:
    st.session_state.last_analysis_result = None

# --- Chat History ---
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# --- Visualization Panel ---
# FIX 5: `last_analysis_result` is now actually populated (see below), so this
#         block will execute correctly instead of always being skipped.
if st.session_state.last_analysis_result:
    st.markdown("---")
    st.markdown("### 📊 Financial Visualizations")
    viz_df = st.session_state.last_analysis_result['df']
    news_map = st.session_state.last_analysis_result['news']

    if not viz_df.empty:
        col_viz1, col_viz2 = st.columns(2)

        with col_viz1:
            st.markdown("### Maturity Amount Comparison")
            fig1, ax1 = plt.subplots(figsize=(10, 6))
            providers = viz_df['Provider']
            gen_maturity = viz_df['General Maturity']
            sen_maturity = viz_df['Senior Maturity']
            x = range(len(providers))
            width = 0.35
            rects1 = ax1.barh([i - width/2 for i in x], gen_maturity, width, label='General', color='#60A5FA')
            rects2 = ax1.barh([i + width/2 for i in x], sen_maturity, width, label='Senior', color='#1E40AF')
            ax1.set_xlabel('Maturity Amount (INR)')
            ax1.set_yticks(x)
            ax1.set_yticklabels(providers)
            ax1.legend()
            ax1.bar_label(rects1, padding=3, fmt='Rs.%0.0f')
            ax1.bar_label(rects2, padding=3, fmt='Rs.%0.0f')
            plt.tight_layout()
            st.pyplot(fig1)

        with col_viz2:
            st.markdown("### Interest Rate Distribution")
            fig2, ax2 = plt.subplots(figsize=(10, 6))
            gen_rate = viz_df['General Rate (%)']
            sen_rate = viz_df['Senior Rate (%)']
            rects1 = ax2.bar([i - width/2 for i in x], gen_rate, width, label='General Rate', color='#60A5FA')
            rects2 = ax2.bar([i + width/2 for i in x], sen_rate, width, label='Senior Rate', color='#1E40AF')
            ax2.set_ylabel('Interest Rate (%)')
            ax2.set_xticks(x)
            ax2.set_xticklabels(providers, rotation=45, ha='right')
            ax2.legend()
            ax2.bar_label(rects1, padding=3, fmt='%0.1f%%')
            ax2.bar_label(rects2, padding=3, fmt='%0.1f%%')
            plt.tight_layout()
            st.pyplot(fig2)

    if news_map:
        st.markdown("### 📰 Latest News")
        for provider, items in news_map.items():
            with st.expander(f"News for {provider}"):
                for item in items:
                    st.markdown(f"- [{item['headline']}]({item['url']})")


# --- Chat Input & Logic ---
if prompt := st.chat_input("Type your message here..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Processing..."):
            current_context = {
                "kyc_complete": st.session_state.kyc_complete,
                "aml_checked": st.session_state.aml_checked,
                "user_data": st.session_state.user_data
            }

            # FIX 6: run_crew now returns (CrewOutput, tasks_output | None).
            #         Unpack both values so we can access tasks_output for visualizations.
            result, tasks_output = run_crew(prompt, current_context)
            response_text = result.raw

            # --- KYC: Incremental data saving on every KYC turn ---
            # The agent emits PARTIAL_DATA: {...} after every response so we can
            # persist each field as it is collected, keeping current_data accurate
            # for the next turn and preventing the agent from re-asking old questions.
            if not st.session_state.kyc_complete:
                # Prefer COLLECTION_COMPLETE; fall back to PARTIAL_DATA
                if "COLLECTION_COMPLETE" in response_text:
                    marker = "COLLECTION_COMPLETE"
                elif "PARTIAL_DATA" in response_text:
                    marker = "PARTIAL_DATA"
                else:
                    marker = None

                if marker:
                    try:
                        raw_json = response_text.split(marker)[-1].strip()
                        # Strip optional colon that the agent may include
                        raw_json = raw_json.lstrip(":").strip()
                        raw_json = re.sub(r'```json|```', '', raw_json).strip()
                        # Extract only the first JSON object found
                        json_match = re.search(r'\{.*?\}', raw_json, re.DOTALL)
                        if json_match:
                            partial = json.loads(json_match.group())
                            # Merge: only overwrite fields that are now non-null
                            for key, val in partial.items():
                                if val is not None and str(val).lower() not in ("null", "none", ""):
                                    st.session_state.user_data[key] = val
                        
                        if marker == "COLLECTION_COMPLETE":
                            st.session_state.kyc_complete = True
                            save_user_data("session_" + str(hash(prompt)), st.session_state.user_data)
                            response_text += "\n\nKYC Complete. Checking Sanctions..."
                    except Exception as e:
                        st.warning(f"KYC data parsing failed: {e}")

            # --- AML Completion Check ---
            if st.session_state.kyc_complete and not st.session_state.aml_checked:
                aml_keywords = ["OpenSanctions", "Sanctions", "Clear", "Risk", "Flagged", "No match"]
                if any(kw in response_text for kw in aml_keywords):
                    aml_status = "Flagged" if ("Suspicious" in response_text or "High Risk" in response_text) else "Checked"
                    save_user_data(
                        "session_" + str(hash(prompt)),
                        st.session_state.user_data,
                        {"status": aml_status, "details": response_text}
                    )
                    st.session_state.aml_checked = True
                    response_text += "\n\nAML Verification Complete. You can now ask for FD recommendations."

            # FIX 7: Replaced the bare `pass` block with actual visualization parsing.
            #         When the analysis crew runs, tasks_output is not None and contains
            #         the individual task results we need for charts and news.
            if st.session_state.kyc_complete and st.session_state.aml_checked and tasks_output:
                try:
                    # tasks_output order: parse, search, research, safety, projection, summary
                    # Index 4 = projection_task, Index 2 = research_task
                    projection_output = tasks_output[4].raw if len(tasks_output) > 4 else ""
                    research_output = tasks_output[2].raw if len(tasks_output) > 2 else ""

                    viz_df = parse_projection_table(projection_output)
                    news_map = parse_all_news_sources(research_output)

                    if not viz_df.empty or news_map:
                        st.session_state.last_analysis_result = {
                            "df": viz_df,
                            "news": news_map
                        }
                except Exception as e:
                    st.warning(f"Could not build visualizations: {e}")

            # Strip the internal marker lines before displaying to the user
            for marker in ("COLLECTION_COMPLETE", "PARTIAL_DATA"):
                if marker in response_text:
                    response_text = response_text.split(marker)[0].strip()

            st.markdown(response_text)
            st.session_state.messages.append({"role": "assistant", "content": response_text})