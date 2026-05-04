# sidebar.py  —  Sidebar Components for Fixed Deposit Advisor
import os
import streamlit as st
from datetime import datetime, timedelta
from tools import fetch_country_data, set_search_region
from .config import DB_PATH
from .helpers import reset_session
from .database import upsert_user_session, get_all_deposits, load_fd_table
from .email_utils import send_digest_email


def render_sidebar():
    """Render the sidebar components."""
    # =============================================================================
    # USER LOGIN
    # =============================================================================
    st.sidebar.markdown("##  Your Profile")
    logged_user = st.session_state.logged_in_user

    if logged_user:
        st.sidebar.success(f"Logged in as **{logged_user['display_name']}**")
        st.sidebar.caption(f"Email: {logged_user['email']}")
        if st.sidebar.button("Log Out"):
            st.session_state.logged_in_user = None
            st.rerun()
    else:
        with st.sidebar.form("login_form", clear_on_submit=False):
            login_name = st.text_input("Your Name")
            login_email = st.text_input("Email")
            login_submit = st.form_submit_button("Login / Register")
        if login_submit and login_name and login_email:
            session_row = upsert_user_session(
                login_name, login_email, st.session_state.user_region["country_code"]
            )
            st.session_state.logged_in_user = session_row
            st.session_state.langfuse_user_id = login_email
            st.sidebar.success(f"Welcome, {login_name}!")
            st.rerun()

    st.sidebar.markdown("---")

    # =============================================================================
    # SEARCH REGION
    # =============================================================================
    st.sidebar.markdown("###  Search Region")
    region_info = st.session_state.user_region
    detected_name = region_info["country_name"]
    all_countries = fetch_country_data()
    country_lookup_sb = {v["name"]: cc for cc, v in all_countries.items() if v["name"]}
    country_names_sb = sorted(country_lookup_sb.keys())
    detected_idx_sb = (
        country_names_sb.index(detected_name)
        if detected_name in country_names_sb
        else 0
    )
    st.sidebar.caption(f"Auto-detected: {detected_name}")
    selected_country_name_sb = st.sidebar.selectbox(
        "Override region",
        options=country_names_sb,
        index=detected_idx_sb,
        key="region_selectbox",
    )
    selected_cc = country_lookup_sb.get(selected_country_name_sb, "WW")
    if selected_cc != st.session_state.user_region["country_code"]:
        info = all_countries.get(selected_cc, {})
        ddg = set_search_region(selected_cc)
        st.session_state.user_region = {
            "country_code": selected_cc,
            "country_name": selected_country_name_sb,
            "ddg_region": ddg,
            "currency_symbol": info.get("currency_symbol", ""),
            "currency_code": info.get("currency_code", ""),
        }
        st.rerun()

    active_region = st.session_state.user_region["country_name"]
    active_sym = st.session_state.user_region.get("currency_symbol", "")
    st.sidebar.success(
        f"Active: {active_region}" + (f" ({active_sym})" if active_sym else "")
    )

    st.sidebar.markdown("---")

    # =============================================================================
    # MATURITY DIGEST EMAIL
    # =============================================================================
    st.sidebar.markdown("###  Maturity Digest")
    if st.sidebar.button("Send 30-Day Digest Email"):
        digest_email = (
            st.session_state.logged_in_user["email"]
            if st.session_state.logged_in_user
            else ""
        )
        if not digest_email:
            st.sidebar.warning("Log in to receive the digest.")
        else:
            all_dep = get_all_deposits()
            if not all_dep.empty and "maturity_date" in all_dep.columns:
                cutoff = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")
                today = datetime.now().strftime("%Y-%m-%d")
                maturing = all_dep[
                    (all_dep["fd_status"] == "ACTIVE")
                    & (all_dep["maturity_date"].fillna("9999-12-31").str[:10] <= cutoff)
                    & (all_dep["maturity_date"].fillna("0000-00-00").str[:10] >= today)
                ]
                if maturing.empty:
                    st.sidebar.info("No deposits maturing in the next 30 days.")
                elif send_digest_email(digest_email, maturing):
                    st.sidebar.success(f"Digest sent to {digest_email}!")
                else:
                    st.sidebar.warning(
                        "Email not configured (set SMTP_HOST, SMTP_USER, SMTP_PASSWORD)."
                    )

    st.sidebar.markdown("---")

    # =============================================================================
    # SYSTEM STATUS
    # =============================================================================
    st.sidebar.markdown("###  System Status")
    langfuse_active = os.getenv("LANGFUSE_PUBLIC_KEY") and os.getenv(
        "LANGFUSE_SECRET_KEY"
    )
    nvidia_active = bool(os.getenv("NVIDIA_API_KEY"))
    db_active = DB_PATH.exists()

    st.sidebar.markdown(
        f"{'✅' if nvidia_active else '❌'} NVIDIA API  \n"
        f"{'✅' if langfuse_active else '❌'} Langfuse Observability  \n"
        f"{'✅' if db_active else '❌'} Database"
    )

    # =============================================================================
    # QUICK DB STATS
    # =============================================================================
    st.sidebar.markdown("---")
    st.sidebar.markdown("###  Database Records")

    fd_df = load_fd_table()
    if not fd_df.empty:
        st.sidebar.dataframe(
            fd_df[
                ["fd_id", "bank_name", "product_type", "initial_amount", "fd_status"]
            ],
            use_container_width=True,
            key="sidebar_df",
        )
    else:
        st.sidebar.info("No FD records found.")

    if st.sidebar.button("Refresh Data"):
        st.rerun()

    st.sidebar.markdown("---")
    if st.sidebar.button("Reset Session / Clear Chat"):
        reset_session()

    st.sidebar.markdown("---")
    st.sidebar.markdown("###  Debug Info")
    st.sidebar.json(
        {
            "Country": st.session_state.user_region["country_code"],
            "DDG Region": st.session_state.user_region["ddg_region"],
            "Currency": st.session_state.user_region["currency_symbol"],
            "Langfuse Session": st.session_state.get("langfuse_session_id", "N/A"),
            "Logged In": (
                st.session_state.logged_in_user["email"]
                if st.session_state.logged_in_user
                else "None"
            ),
        }
    )
