import streamlit as st
from streamlit_ref import (
    init_session_state,
    render_fd_advisor_tab,
    render_new_account_tab,
    render_credit_risk_tab,
    render_financial_news_tab,
    render_mortgage_analytics_tab,
    render_sidebar,
)
from streamlit_ref.config import apply_dark_luxury_theme

# =============================================================================
# PAGE CONFIG
# =============================================================================
st.set_page_config(
    page_title="Bank POC Agentic AI",
    page_icon="🏦",
    layout="wide",
    initial_sidebar_state="expanded",
)

# =============================================================================
# CUSTOM CSS - Dark Luxury Theme
# =============================================================================
apply_dark_luxury_theme()

# Additional custom styles
st.markdown(
    """
<style>
.main-header{font-size:2.2rem!important;color:#f8fafc;margin-bottom:.5rem;font-family:'Playfair Display',serif}
.sub-header{font-size:1.8rem!important;color:#f8fafc;margin-bottom:1rem;font-family:'Playfair Display',serif}
/* Override Streamlit default background */
.stApp {
    background: linear-gradient(135deg, #080d18 0%, #0e1525 100%);
}
/* Card styling */
.css-1r6slb0, .stMarkdown, .stDataFrame, .stPlotlyChart {
    background: #111827;
    border: 1px solid #1f2937;
    border-radius: 12px;
}
/* Button gradient */
.stButton > button {
    background: linear-gradient(135deg, #c9a84c 0%, #2dd4bf 100%)!important;
    color: #080d18!important;
    font-weight: 600!important;
    border: none!important;
    border-radius: 8px!important;
}
/* Metric cards */
.css-ffhzg2 .stMetric {
    background: #111827;
    border: 1px solid #1f2937;
    border-radius: 12px;
    padding: 16px;
}
</style>
""",
    unsafe_allow_html=True,
)

# =============================================================================
# INIT SESSION
# =============================================================================
init_session_state()

if "page" not in st.session_state:
    st.session_state.page = "home"

# =============================================================================
# HEADER
# =============================================================================
st.markdown(
    '<h1 class="main-header">Fixed Deposit Advisor</h1>', unsafe_allow_html=True
)

# =============================================================================
# TOP NAVIGATION (ONLY ON HOME PAGE)
# =============================================================================
if st.session_state.page == "home":

    st.markdown("### Quick Actions")

    col1, col2, col3 = st.columns(3)

    with col1:
        if st.button("TD Creation", use_container_width=True):
            st.session_state.page = "td"
            st.rerun()

    with col2:
        if st.button("FD Creation", use_container_width=True):
            st.session_state.page = "fd"
            st.rerun()

    with col3:
        if st.button("Credit Risk Analysis", use_container_width=True):
            st.session_state.page = "credit_risk"
            st.rerun()

    st.divider()

# =============================================================================
# PAGE ROUTING (FULL WIDTH RENDERING)
# =============================================================================
if st.session_state.page == "home":

    tab1, tab4, tab5 = st.tabs(
        [
            "FD Advisor",
            "Financial News",
            "Mortgage Analytics",
        ]
    )

    with tab1:
        render_fd_advisor_tab()

    with tab4:
        render_financial_news_tab()

    with tab5:
        render_mortgage_analytics_tab()

# -----------------------------
elif st.session_state.page in ["td", "fd"]:

    col_back, col_title = st.columns([1, 6])

    with col_back:
        if st.button("⬅ Back"):
            st.session_state.page = "home"
            st.rerun()

    with col_title:
        st.subheader("Open New Account")

    st.divider()

    render_new_account_tab()

# -----------------------------
elif st.session_state.page == "credit_risk":

    col_back, col_title = st.columns([1, 6])

    with col_back:
        if st.button("⬅ Back"):
            st.session_state.page = "home"
            st.rerun()

    with col_title:
        st.subheader("Credit Risk Analysis")

    st.divider()

    render_credit_risk_tab()

# =============================================================================
# SIDEBAR
# =============================================================================
render_sidebar()
