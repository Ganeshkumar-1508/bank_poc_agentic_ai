# tab_credit_risk.py — Credit Risk Tab for Fixed Deposit Advisor
import os
import re
import json
import smtplib
import streamlit as st
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import plotly.graph_objects as go
import pandas as pd

from .config import extract_json_balanced
from .helpers import _cr_model_available, run_crew_with_langfuse
from .validators import (
    _parse_llm_decision,
    _validate_decision_rationale,
    _sanitize_grade_in_text,
    _sanitize_thresholds_in_text,
)
from .email_utils import _md_to_html, _build_email_html
from .database import get_db_connection, save_loan_application
from .calculators import calculate_emi, generate_amortization_schedule


def render_credit_risk_tab():
    """Render the Credit Risk Assessment tab."""
    st.markdown(
        '<h2 class="sub-header">Credit Risk Assessment</h2>', unsafe_allow_html=True
    )

    # Region detection and routing
    user_region = st.session_state.get("user_region", {})
    user_country_code = user_region.get("country_code", "WW")
    user_country_name = user_region.get("country_name", "Worldwide")

    # Detect region type
    us_regions = ("US", "UNITED STATES", "USA")
    india_regions = ("IN", "INDIA", "BHARAT")

    is_us_region = user_country_code.upper() in us_regions
    is_india_region = user_country_code.upper() in india_regions

    # Region routing
    if not is_us_region and not is_india_region:
        detected_flag = (
            f": {user_country_name}" if user_country_name != "Worldwide" else ""
        )
        st.markdown(
            f"""
        <div style="text-align:center; padding:50px 20px; background:#FEF2F2; border-radius:12px; border:1px solid #FECACA; margin:20px 0;">
        <div style="width:48px; height:48px; background:#FEE2E2; border-radius:50%; display:flex; align-items:center; justify-content:center; margin:0 auto 16px auto; border:2px solid #FECACA;">
        <span style="color:#DC2626; font-size:24px; font-weight:bold;">!</span>
        </div>
        <h3 style="color:#991B1B; margin:0 0 8px 0;">Region Not Supported</h3>
        <p style="color:#7F1D1D; max-width:500px; margin:0 auto 16px auto; line-height:1.6;">
        Credit Risk Assessment is currently available only for <strong>United States</strong> and <strong>India (Bharat)</strong> region users.
        </p>
        <div style="background:#FEE2E2; display:inline-block; padding:8px 16px; border-radius:6px; font-size:14px; color:#991B1B;">
        Detected Region{detected_flag}
        </div>
        </div>
        """,
            unsafe_allow_html=True,
        )

        st.markdown("---")
        st.markdown("#### Why is this restricted?")
        st.markdown(
            """
        The credit risk models are trained on region-specific data and use local credit scoring conventions.
        - **US Model**: Uses FICO scores and US Lending Club data
        - **India Model**: Uses CIBIL-style scores and Indian loan data (975,000+ records)
        """
        )

        st.markdown("#### Available alternatives in your region")
        st.markdown(
            f"""
        - Use the **FD Advisor** tab to compare deposit rates in {user_country_name or "your region"}
        - Use the **FD Advisor** tab to compare deposit rates across banks
        - Open a new account via the **New Account** tab
        """
        )

        with st.expander("Region Detection Details", expanded=False):
            st.markdown(
                f"""
            | Field | Value |
            |-------|-------|
            | Country Code | `{user_country_code}` |
            | Country Name | {user_country_name} |
            | Currency | {user_region.get('currency_code', 'N/A')} |
            | Currency Symbol | {user_region.get('currency_symbol', 'N/A')} |
            | Search Region | `{user_region.get('ddg_region', 'wt-wt')}` |
            """
            )
        return

    # Display region badge
    if is_us_region:
        st.markdown(
            f"""
        <div style="display:flex; align-items:center; gap:8px; margin-bottom:16px; padding:8px 12px; background:#F0FDF4; border-radius:6px; border:1px solid #BBF7D0;">
        <span style="color:#16A34A; font-weight:600;">🇺🇸 US Region</span>
        <span style="color:#166534; font-size:13px;">Detected -- Using US XGBoost Credit Risk Model</span>
        </div>
        """,
            unsafe_allow_html=True,
        )
    elif is_india_region:
        st.markdown(
            f"""
        <div style="display:flex; align-items:center; gap:8px; margin-bottom:16px; padding:8px 12px; background:#ECFDF5; border-radius:6px; border:1px solid #A7F3D0;">
        <span style="color:#059669; font-weight:600;">🇮🇳 India (Bharat) Region</span>
        <span style="color:#047857; font-size:13px;">Detected -- Using Indian Logistic Regression Credit Risk Model</span>
        </div>
        """,
            unsafe_allow_html=True,
        )

    # Initialize session state for credit risk
    if "cr_form_data" not in st.session_state:
        st.session_state.cr_form_data = {}
    if "cr_results" not in st.session_state:
        st.session_state.cr_results = None
    if "emi_calculator_data" not in st.session_state:
        st.session_state.emi_calculator_data = None
    if "emi_results" not in st.session_state:
        st.session_state.emi_results = None

    # Route to appropriate form based on region
    if is_us_region:
        _render_us_credit_risk_form()
    else:
        _render_india_credit_risk_form()

    # Render results column
    cr_results_col = st.columns(1)[0]
    with cr_results_col:
        if is_us_region:
            _render_credit_risk_results()
        else:
            _render_india_credit_risk_results()

    # EMI Calculator section (available for India users)
    if is_india_region:
        st.markdown("---")
        _render_emi_calculator_section()

        if not _cr_model_available():
            st.warning(
                "Credit risk model not available. Please ensure the model files are in the expected directory."
            )
            st.stop()

        # Initialize session state for credit risk
        if "cr_form_data" not in st.session_state:
            st.session_state.cr_form_data = {}
        if "cr_results" not in st.session_state:
            st.session_state.cr_results = None

        cr_form_col, cr_results_col = st.columns([1, 2])

        with cr_form_col:
            st.markdown("### Borrower Information")
            st.caption("Enter borrower attributes for the US credit risk model")

            with st.form("credit_risk_form"):
                st.markdown("#### Loan Details")
                col_a, col_b = st.columns(2)
                with col_a:
                    loan_amnt = st.number_input(
                        "Loan Amount ($)",
                        min_value=1000,
                        max_value=500000,
                        value=15000,
                        step=1000,
                    )
                    term = st.selectbox(
                        "Term",
                        options=[36, 60],
                        format_func=lambda x: f"{x} months",
                        index=0,
                    )
                with col_b:
                    int_rate = st.number_input(
                        "Interest Rate (%)",
                        min_value=1.0,
                        max_value=30.0,
                        value=12.5,
                        step=0.25,
                    )
                    purpose = st.selectbox(
                        "Purpose",
                        options=[
                            "debt_consolidation",
                            "credit_card",
                            "home_improvement",
                            "major_purchase",
                            "medical",
                            "small_business",
                            "car",
                            "moving",
                            "vacation",
                            "house",
                            "renewable_energy",
                            "wedding",
                            "educational",
                            "other",
                        ],
                        index=0,
                    )

                st.markdown("#### Income & Employment")
                col_c, col_d = st.columns(2)
                with col_c:
                    annual_inc = st.number_input(
                        "Annual Income ($)",
                        min_value=5000,
                        max_value=5000000,
                        value=60000,
                        step=5000,
                    )
                    emp_length = st.selectbox(
                        "Employment Length",
                        options=[
                            "< 1 year",
                            "1 year",
                            "2 years",
                            "3 years",
                            "4 years",
                            "5 years",
                            "6 years",
                            "7 years",
                            "8 years",
                            "9 years",
                            "10+ years",
                        ],
                        index=5,
                    )
                with col_d:
                    home_ownership = st.selectbox(
                        "Home Ownership",
                        options=["RENT", "OWN", "MORTGAGE", "OTHER"],
                        index=0,
                    )
                    verification_status = st.selectbox(
                        "Verification Status",
                        options=["Not Verified", "Source Verified", "Verified"],
                        index=0,
                    )

                st.markdown("#### Credit Profile")
                col_e, col_f = st.columns(2)
                with col_e:
                    fico_score = st.number_input(
                        "FICO Score", min_value=300, max_value=850, value=680, step=5
                    )
                    dti = st.number_input(
                        "DTI Ratio (%)",
                        min_value=0.0,
                        max_value=100.0,
                        value=18.0,
                        step=0.5,
                    )
                with col_f:
                    delinq_2yrs = st.number_input(
                        "Delinquencies (2yr)",
                        min_value=0,
                        max_value=20,
                        value=0,
                        step=1,
                    )
                    inq_last_6mths = st.number_input(
                        "Inquiries (6mo)", min_value=0, max_value=20, value=1, step=1
                    )

                col_g, col_h = st.columns(2)
                with col_g:
                    pub_rec = st.number_input(
                        "Public Records", min_value=0, max_value=20, value=0, step=1
                    )
                    revol_util = st.number_input(
                        "Revolving Util (%)",
                        min_value=0.0,
                        max_value=150.0,
                        value=45.0,
                        step=1.0,
                    )
                with col_h:
                    revol_bal = st.number_input(
                        "Revolving Balance ($)",
                        min_value=0,
                        max_value=500000,
                        value=5000,
                        step=500,
                    )
                    earliest_cr_line = st.text_input(
                        "Earliest Credit Line",
                        value="Jan-2010",
                        help="Format: Mon-YYYY",
                    )

                st.markdown("#### Optional Fields")
                with st.expander("Advanced Options", expanded=False):
                    col_i, col_j = st.columns(2)
                    with col_i:
                        total_acc = st.number_input(
                            "Total Accounts",
                            min_value=1,
                            max_value=100,
                            value=15,
                            step=1,
                        )
                        open_acc = st.number_input(
                            "Open Accounts", min_value=0, max_value=50, value=8, step=1
                        )
                    with col_j:
                        mths_since_last_delinq = st.number_input(
                            "Months Since Last Delinq",
                            min_value=0,
                            max_value=180,
                            value=36,
                            step=1,
                        )
                        total_rev_hi_lim = st.number_input(
                            "Total Rev High Limit ($)",
                            min_value=0,
                            max_value=1000000,
                            value=20000,
                            step=1000,
                        )

                submitted = st.form_submit_button(
                    "Run Credit Risk Assessment",
                    type="primary",
                    use_container_width=True,
                )

            if submitted:
                emp_map = {
                    "< 1 year": 0,
                    "1 year": 1,
                    "2 years": 2,
                    "3 years": 3,
                    "4 years": 4,
                    "5 years": 5,
                    "6 years": 6,
                    "7 years": 7,
                    "8 years": 8,
                    "9 years": 9,
                    "10+ years": 10,
                }
                ver_map = {
                    "Not Verified": "Not Verified",
                    "Source Verified": "Source Verified",
                    "Verified": "Verified",
                }

                borrower_data = {
                    "loan_amnt": loan_amnt,
                    "term": term,
                    "int_rate": int_rate,
                    "annual_inc": annual_inc,
                    "dti": dti,
                    "fico_score": fico_score,
                    "home_ownership": home_ownership,
                    "delinq_2yrs": delinq_2yrs,
                    "inq_last_6mths": inq_last_6mths,
                    "pub_rec": pub_rec,
                    "earliest_cr_line": earliest_cr_line,
                    "revol_util": revol_util,
                    "revol_bal": revol_bal,
                    "purpose": purpose,
                    "emp_length": emp_map.get(emp_length, 5),
                    "emp_length_display": emp_length,
                    "verification_status": ver_map.get(
                        verification_status, "Not Verified"
                    ),
                    "total_acc": total_acc if total_acc > 1 else None,
                    "open_acc": open_acc if open_acc > 0 else None,
                    "mths_since_last_delinq": (
                        mths_since_last_delinq if mths_since_last_delinq > 0 else None
                    ),
                    "total_rev_hi_lim": (
                        total_rev_hi_lim if total_rev_hi_lim > 0 else None
                    ),
                }

                # Initialize result dict with borrower data
                result = {"_borrower_data": borrower_data}

                # --- Deterministic Hard-Decline Pre-Check (before LLM call) ---
                _precheck_auto_decline = False
                _precheck_hint = ""
                _fico_val = borrower_data.get("fico_score", 0)
                _dti_val = borrower_data.get("dti", 0)
                _purpose_val = borrower_data.get("purpose", "")
                _emp_display = borrower_data.get("emp_length_display", "")
                _annual_inc = borrower_data.get("annual_inc", 0)
                _delinq = borrower_data.get("delinq_2yrs", 0)

                # Deterministic AUTO-DECLINE criteria (no LLM needed)
                if _fico_val < 620:
                    _precheck_auto_decline = True
                    _precheck_hint = (
                        f"HARD DECLINE PRE-CHECK: FICO score {_fico_val} is below the minimum "
                        f"threshold of 620. Decision MUST be REJECTED. No need to search policy docs."
                    )
                elif _dti_val > 50 and _fico_val < 660:
                    _precheck_auto_decline = True
                    _precheck_hint = (
                        f"HARD DECLINE PRE-CHECK: DTI {_dti_val}% with FICO {_fico_val} "
                        f"exceeds acceptable risk limits. Decision MUST be REJECTED."
                    )

                # Deterministic CLEAR PASS hint (strong borrower — prevent false rejection)
                _precheck_clear_pass = False
                if (
                    not _precheck_auto_decline
                    and _fico_val >= 740
                    and _dti_val <= 30
                    and _delinq == 0
                ):
                    _precheck_clear_pass = True

                # --- Credit Risk Assessment via CrewAI (ML model called by agent internally) ---
                llm_decision_raw = None
                credit_assessment = {}
                nvidia_key = os.getenv("NVIDIA_NIM_API_KEY", "") or os.getenv(
                    "NVIDIA_API_KEY", ""
                )
                if nvidia_key:
                    try:
                        from crews import run_loan_creation_crew

                        # Inject precheck hints into prompt context
                        _hint_text = ""
                        if _precheck_auto_decline:
                            _hint_text = f"\n\n!!! {_precheck_hint} !!!\n"
                        elif _precheck_clear_pass:
                            _hint_text = (
                                f"\n\nPRE-CHECK NOTE: This borrower has a STRONG credit profile "
                                f"(FICO {_fico_val}>=740, DTI {_dti_val}%<=30%, no delinquencies). "
                                f"Do NOT fabricate violations or apply stricter thresholds than what "
                                f"the policy documents actually state. Only REJECT if an explicit "
                                f"hard-decline rule in the RAG output is violated VERBATIM.\n"
                            )

                        # Build prompt context - the crew agent will call the ML model internally
                        prompt_context = (
                            f"Borrower Application Data (JSON):\n"
                            f"{json.dumps({k: v for k, v in borrower_data.items() if v is not None}, default=str, indent=2)}\n\n"
                            f"{_hint_text}"
                            f"IMPORTANT: You MUST call the 'US_Credit_Risk_Scorer' tool to get the credit grade, "
                            f"default probability, and risk level. Include these results in your output under 'credit_assessment'."
                        )

                        llm_result = run_loan_creation_crew(prompt_context)

                        # Extract crew output for evaluation
                        crew_output = (
                            llm_result.raw
                            if hasattr(llm_result, "raw")
                            else str(llm_result)
                        )

                        # Task 0 = decision (JSON), Task 1 = summary (Markdown for email)
                        if (
                            hasattr(llm_result, "tasks_output")
                            and len(llm_result.tasks_output) >= 2
                        ):
                            result["_llm_decision_raw"] = llm_result.tasks_output[0].raw
                            result["_llm_summary_raw"] = llm_result.tasks_output[1].raw
                        else:
                            result["_llm_decision_raw"] = crew_output
                            result["_llm_summary_raw"] = None

                        # Parse credit assessment from crew output if available
                        decision_raw = result.get("_llm_decision_raw")
                        if decision_raw:
                            try:
                                decision_json = extract_json_balanced(decision_raw)
                                credit_assessment = decision_json.get(
                                    "credit_assessment", {}
                                )
                                if credit_assessment:
                                    result.update(credit_assessment)
                            except (
                                json.JSONDecodeError,
                                AttributeError,
                                ValueError,
                            ) as parse_error:
                                print(
                                    f"[Warning] Could not parse credit_assessment from crew output: {parse_error}"
                                )

                        # Post evaluation to Langfuse (async, non-blocking)
                        try:
                            from langfuse_instrumentation import (
                                get_current_trace_id,
                                post_crew_evaluation,
                            )

                            trace_id = get_current_trace_id()
                            post_crew_evaluation(
                                crew_name="loan-creation-crew",
                                user_input=prompt_context,
                                output_text=crew_output,
                                trace_id=trace_id,
                            )
                        except Exception as eval_error:
                            print(
                                f"[Langfuse] Evaluation failed for loan-creation-crew: {eval_error}"
                            )

                    except Exception as e:
                        st.warning(
                            f"WARNING: LLM Call Failed - using rule-based fallback. Error: {e}"
                        )
                        result["_llm_decision_raw"] = None
                        result["_llm_summary_raw"] = None
                        # Fallback: run ML scoring tool directly so results are never blank
                        try:
                            from tools.credit_risk_tool import score_credit_risk

                            _fb = score_credit_risk(borrower_data)
                            _ca = _fb.get("credit_assessment", {})
                            result.update(_ca)
                            result["credit_assessment"] = _ca
                        except Exception as _fe:
                            print(
                                f"[Warning] Direct fallback scoring also failed: {_fe}"
                            )
                else:
                    st.info(
                        "INFO: NVIDIA API key not set - using rule-based decision (no LLM)."
                    )
                    result["_llm_decision_raw"] = None
                    result["_llm_summary_raw"] = None
                    # Fallback: run ML scoring tool directly so results are never blank
                    try:
                        from tools.credit_risk_tool import score_credit_risk

                        _fb = score_credit_risk(borrower_data)
                        _ca = _fb.get("credit_assessment", {})
                        result.update(_ca)
                        result["credit_assessment"] = _ca
                    except Exception as _fe:
                        print(f"[Warning] Direct fallback scoring also failed: {_fe}")

                st.session_state.cr_results = result

        # Render results column
        with cr_results_col:
            _render_credit_risk_results()


def _render_credit_risk_results():
    """Render the credit risk results panel."""
    if st.session_state.cr_results is None:
        st.markdown(
            """
        <div style="text-align:center; padding:60px 20px; background:#F8FAFC; border-radius:12px; border:1px solid #E2E8F0;">
            <div style="width:64px; height:64px; background:#E2E8F0; border-radius:50%; display:flex; align-items:center; justify-content:center; margin:0 auto 16px auto;">
                <span style="color:#64748B; font-size:28px; font-weight:bold;">?</span>
            </div>
            <h3 style="color:#64748B; margin:0 0 8px 0;">No Assessment Yet</h3>
            <p style="color:#94A3B8; max-width:400px; margin:0 auto;">
                Complete the borrower information form and click "Run Credit Risk Assessment" 
                to generate a comprehensive credit risk report.
            </p>
        </div>
        """,
            unsafe_allow_html=True,
        )

        st.markdown("---")
        st.markdown(
            """
        <div style="background:#F1F5F9; border-radius:8px; padding:16px; border-left:4px solid #3B82F6;">
            <h4 style="margin:0 0 8px 0; color:#1E3A8A;">Model Information</h4>
            <table style="width:100%; font-size:13px; color:#475569;">
                <tr><td style="padding:4px 0;"><strong>Algorithm:</strong></td><td>XGBoost Classifier</td></tr>
                <tr><td style="padding:4px 0;"><strong>Training Data:</strong></td><td>US Lending Club (2007-2018)</td></tr>
                <tr><td style="padding:4px 0;"><strong>Output:</strong></td><td>Default Probability, Risk Grade, Feature Importance</td></tr>
                <tr><td style="padding:4px 0;"><strong>Grade Scale:</strong></td><td>AAA (safest) to D (highest risk)</td></tr>
            </table>
        </div>
        """,
            unsafe_allow_html=True,
        )
    else:
        result = st.session_state.cr_results
        borrower = result.get("_borrower_data", {})

        if "error" in result:
            st.error(f"Model Error: {result['error']}")
        else:
            # Render results
            _render_risk_summary(result, borrower)
            _render_loan_decision(result, borrower)


def _render_risk_summary(result: dict, borrower: dict):
    """Render the risk summary section."""
    credit_assessment = result.get("credit_assessment", {})

    # CRITICAL BUG FIX: The credit risk data may be stored in credit_assessment dict
    # but NOT at the top level of result. Always check credit_assessment first.
    # Priority order: result[key] -> credit_assessment[key] -> default

    # First, try to get values from top-level result (from crew output extraction)
    prob = result.get("default_probability", None)
    prob_pct = result.get("default_probability_pct", None)
    grade = result.get("implied_grade", None)
    risk_level = result.get("risk_level", None)

    # If not found at top level, check credit_assessment dict
    if prob is None:
        prob = credit_assessment.get("default_probability", 0)
    if prob_pct is None:
        prob_pct = credit_assessment.get("default_probability_pct", "0%")
    if grade is None:
        grade = credit_assessment.get("implied_grade", "N/A")
    if risk_level is None:
        risk_level = credit_assessment.get("risk_level", "UNKNOWN")

    # Last-resort fallback: if grade/risk are still defaults, run the scoring tool directly.
    # This covers cases where the LLM ran but JSON parsing failed, or crew output was malformed.
    if grade == "N/A" or grade is None or risk_level == "UNKNOWN" or risk_level is None:
        try:
            from tools.credit_risk_tool import score_credit_risk

            _fb = score_credit_risk(borrower)
            _ca = _fb.get("credit_assessment", {})
            # Update from fallback scoring
            if grade == "N/A" or grade is None:
                grade = _ca.get("implied_grade", "N/A")
            if risk_level == "UNKNOWN" or risk_level is None:
                risk_level = _ca.get("risk_level", "UNKNOWN")
            if prob == 0 or prob is None:
                prob = _ca.get("default_probability", 0)
            if prob_pct == "0%" or prob_pct is None:
                prob_pct = _ca.get("default_probability_pct", "0%")
            # Persist so _render_loan_decision sees the same values
            result.update(_ca)
            result["credit_assessment"] = _ca
        except Exception as _fe:
            print(f"[Warning] Last-resort scoring fallback failed: {_fe}")

    # Ensure we have valid values (not None)
    if grade is None:
        grade = "N/A"
    if risk_level is None:
        risk_level = "UNKNOWN"
    if prob is None:
        prob = 0
    if prob_pct is None:
        prob_pct = "0%"

    top_features = result.get("top_features", [])

    risk_config = {
        "LOW": {"bg": "#DCFCE7", "fg": "#166534", "border": "#22C55E"},
        "MEDIUM": {"bg": "#FEF9C3", "fg": "#854D0E", "border": "#EAB308"},
        "HIGH": {"bg": "#FEE2E2", "fg": "#991B1B", "border": "#EF4444"},
        "CRITICAL": {"bg": "#7F1D1D", "fg": "#FEE2E2", "border": "#DC2626"},
    }
    rc = risk_config.get(risk_level.upper(), risk_config["MEDIUM"])

    st.markdown(
        f"""
    <div style="background:{rc['bg']}; border:2px solid {rc['border']}; border-radius:12px; padding:20px; margin-bottom:20px;">
        <div style="display:flex; justify-content:space-between; align-items:center;">
            <div>
                <div style="font-size:12px; text-transform:uppercase; letter-spacing:1px; color:{rc['fg']}; opacity:0.8;">
                    Risk Assessment Result
                </div>
                <div style="font-size:28px; font-weight:700; color:{rc['fg']}; margin:4px 0;">
                    {risk_level.upper()} RISK
                </div>
            </div>
            <div style="text-align:right;">
                <div style="font-size:48px; font-weight:800; color:{rc['fg']};">{grade}</div>
                <div style="font-size:13px; color:{rc['fg']}; opacity:0.8;">Implied Grade</div>
            </div>
        </div>
    </div>
    """,
        unsafe_allow_html=True,
    )

    # Metrics row
    m1, m2, m3, m4 = st.columns(4)

    with m1:
        st.markdown(
            f"""
        <div class="metric-card">
            <div style="font-size:11px; text-transform:uppercase; letter-spacing:0.5px; color:#64748B;">
                Default Probability
            </div>
            <div style="font-size:24px; font-weight:700; color:{rc['fg']}; margin:4px 0;">
                {prob_pct}
            </div>
            <div style="font-size:11px; color:#94A3B8;">Likelihood of default</div>
        </div>
        """,
            unsafe_allow_html=True,
        )

    with m2:
        loan_to_income = (
            borrower.get("loan_amnt", 0) / max(borrower.get("annual_inc", 1), 1) * 100
        )
        lti_color = (
            "#16A34A"
            if loan_to_income < 30
            else "#EAB308" if loan_to_income < 50 else "#DC2626"
        )
        st.markdown(
            f"""
        <div class="metric-card">
            <div style="font-size:11px; text-transform:uppercase; letter-spacing:0.5px; color:#64748B;">
                Loan-to-Income
            </div>
            <div style="font-size:24px; font-weight:700; color:{lti_color}; margin:4px 0;">
                {loan_to_income:.1f}%
            </div>
            <div style="font-size:11px; color:#94A3B8;">Loan / Annual Income</div>
        </div>
        """,
            unsafe_allow_html=True,
        )

    with m3:
        fico = borrower.get("fico_score", 680)
        fico_color = (
            "#16A34A" if fico >= 740 else "#EAB308" if fico >= 670 else "#DC2626"
        )
        st.markdown(
            f"""
        <div class="metric-card">
            <div style="font-size:11px; text-transform:uppercase; letter-spacing:0.5px; color:#64748B;">
                FICO Score
            </div>
            <div style="font-size:24px; font-weight:700; color:{fico_color}; margin:4px 0;">
                {fico}
            </div>
            <div style="font-size:11px; color:#94A3B8;">Credit score range</div>
        </div>
        """,
            unsafe_allow_html=True,
        )

    with m4:
        dti_val = borrower.get("dti", 0)
        dti_color = (
            "#16A34A" if dti_val < 20 else "#EAB308" if dti_val < 36 else "#DC2626"
        )
        st.markdown(
            f"""
        <div class="metric-card">
            <div style="font-size:11px; text-transform:uppercase; letter-spacing:0.5px; color:#64748B;">
                DTI Ratio
            </div>
            <div style="font-size:24px; font-weight:700; color:{dti_color}; margin:4px 0;">
                {dti_val:.1f}%
            </div>
            <div style="font-size:11px; color:#94A3B8;">Debt-to-income</div>
        </div>
        """,
            unsafe_allow_html=True,
        )


def _render_loan_decision(result: dict, borrower: dict):
    """Render the loan decision section."""
    credit_assessment = result.get("credit_assessment", {})
    grade = result.get("implied_grade", credit_assessment.get("implied_grade", "N/A"))
    prob_pct = result.get(
        "default_probability_pct",
        credit_assessment.get("default_probability_pct", "0%"),
    )
    risk_level = result.get(
        "risk_level", credit_assessment.get("risk_level", "UNKNOWN")
    )
    llm_raw = result.get("_llm_decision_raw")

    # Parse LLM output if available
    llm_parsed = _parse_llm_decision(llm_raw) if llm_raw else {}

    # Validate LLM decision for hallucinations
    if llm_parsed:
        llm_parsed = _validate_decision_rationale(llm_parsed, borrower)

    # Rule-based fallback mapping: grade → category
    def _grade_to_decision(g):
        if g in ("A", "B"):
            return "LOAN_APPROVED"
        elif g in ("C", "D", "E"):
            return "NEEDS_VERIFY"
        else:
            return "REJECTED"

    # Determine final decision
    if llm_parsed.get("loan_decision"):
        loan_decision = llm_parsed["loan_decision"].upper()
    else:
        loan_decision = _grade_to_decision(grade)

    if loan_decision not in ("LOAN_APPROVED", "NEEDS_VERIFY", "REJECTED"):
        loan_decision = _grade_to_decision(grade)

    # Build decision details
    if loan_decision == "LOAN_APPROVED":
        rec_decision = "LOAN APPROVED"
        rec_color = "#166534"
        rec_bg = "#DCFCE7"
        rec_icon = "[APPROVED]"
        rec_text = (
            llm_parsed.get("rationale")
            or f"Borrower presents low default risk (Grade {grade}, {prob_pct} default probability)."
        )
        conditions = llm_parsed.get("conditions") or [
            "No additional conditions required"
        ]
        next_steps = llm_parsed.get("next_steps") or ["Loan amount will be disbursed"]
    elif loan_decision == "NEEDS_VERIFY":
        rec_decision = "NEED TO VERIFY & APPROVE"
        rec_color = "#854D0E"
        rec_bg = "#FEF9C3"
        rec_icon = "[VERIFY]"
        rec_text = (
            llm_parsed.get("rationale")
            or f"Borrower presents moderate risk (Grade {grade}, {prob_pct} default probability)."
        )
        conditions = llm_parsed.get("conditions") or [
            "Enhanced documentation verification required"
        ]
        next_steps = llm_parsed.get("next_steps") or ["Verification officer assigned"]
    else:
        rec_decision = "LOAN REJECTED"
        rec_color = "#991B1B"
        rec_bg = "#FEE2E2"
        rec_icon = "[REJECTED]"
        rec_text = (
            llm_parsed.get("rationale")
            or f"Borrower presents high default risk (Grade {grade}, {prob_pct} default probability)."
        )
        conditions = llm_parsed.get("conditions") or [
            "Application does not meet minimum credit policy"
        ]
        next_steps = llm_parsed.get("next_steps") or ["Adverse action notice sent"]

    # Sanitize text
    rec_text = _sanitize_grade_in_text(rec_text, grade)
    rec_text = _sanitize_thresholds_in_text(rec_text, borrower)

    # Store for DB save & notify
    st.session_state._loan_decision = loan_decision
    st.session_state._loan_rationale = rec_text
    st.session_state._loan_conditions = conditions
    st.session_state._loan_next_steps = next_steps

    st.markdown(
        f"""
    <div style="background:{rec_bg}; border-left:4px solid {rec_color}; border-radius:0 8px 8px 0; padding:16px; margin-bottom:16px;">
        <div style="font-size:20px; font-weight:700; color:{rec_color}; margin-bottom:8px;">
            {rec_icon} {rec_decision}
        </div>
        <p style="color:{rec_color}; margin:0; font-size:14px;">{rec_text}</p>
    </div>
    """,
        unsafe_allow_html=True,
    )

    # BUG FIX: Ensure conditions and next_steps are always lists, not strings
    # When LLM returns a string instead of list, wrap it in a list (DON'T use list() which splits chars)
    if isinstance(conditions, str):
        conditions = [conditions] if conditions.strip() else []
    if isinstance(next_steps, str):
        next_steps = [next_steps] if next_steps.strip() else []

    # Ensure they are lists (handle None or other types)
    # CRITICAL FIX: Use [value] to wrap, NOT list(value) which splits strings into characters
    if not isinstance(conditions, list):
        conditions = [conditions] if conditions else []
    if not isinstance(next_steps, list):
        next_steps = [next_steps] if next_steps else []

    if conditions:
        st.markdown("**Conditions:**")
        for cond in conditions:
            if cond and isinstance(cond, str):
                st.markdown(f"- {cond}")

    if next_steps:
        st.markdown("**Next Steps:**")
        for step in next_steps:
            if step and isinstance(step, str):
                st.markdown(f"- {step}")

    st.markdown("---")

    # Auto-save to DB
    llm_summary_md = result.get("_llm_summary_raw", "")
    llm_summary_md = (
        _sanitize_grade_in_text(llm_summary_md, grade) if llm_summary_md else ""
    )
    llm_summary_md = (
        _sanitize_thresholds_in_text(llm_summary_md, borrower) if llm_summary_md else ""
    )

    if llm_summary_md:
        st.markdown("---")
        st.markdown("#### AI Borrower Summary")
        st.markdown(llm_summary_md)

    _auto_save_done = st.session_state.get("_loan_auto_saved_id")
    if not _auto_save_done:
        logged = st.session_state.get("logged_in_user") or {}
        _uid = logged.get("user_id") if logged else None
        _email = logged.get("email", "") if logged else "guest@demo.com"
        _aid = save_loan_application(
            applicant_email=_email,
            borrower=borrower,
            result=result,
            loan_decision=loan_decision,
            rationale=rec_text,
            conditions=conditions,
            next_steps=next_steps,
            user_id=_uid,
        )
        if _aid:
            st.session_state._loan_auto_saved_id = _aid
            st.toast(f"Auto-saved as Application #{_aid}")

    # Export buttons
    btn_row1 = st.columns([1, 1, 1, 1])

    with btn_row1[0]:
        if st.button("Reset Assessment", use_container_width=True):
            st.session_state.cr_results = None
            st.session_state._loan_auto_saved_id = None
            st.rerun()

    with btn_row1[1]:
        export_data = {
            "assessment_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "loan_decision": loan_decision,
            "borrower_data": {k: v for k, v in borrower.items() if v is not None},
            "results": {
                "default_probability_pct": prob_pct,
                "implied_grade": grade,
                "risk_level": risk_level,
            },
        }
        st.download_button(
            "Export Report (JSON)",
            data=json.dumps(export_data, indent=2, default=str).encode("utf-8"),
            file_name=f"credit_risk_assessment_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
            mime="application/json",
            use_container_width=True,
        )

    with btn_row1[2]:
        report_text = f"""LOAN APPLICATION REPORT
{'='*50}
Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}
Decision: {rec_decision}
Grade: {grade}
Default Probability: {prob_pct}
Risk Level: {risk_level}
"""
        st.download_button(
            "Export Report (TXT)",
            data=report_text.encode("utf-8"),
            file_name=f"loan_decision_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
            mime="text/plain",
            use_container_width=True,
        )

    with btn_row1[3]:
        if st.button(
            "Notify Borrower via Email",
            use_container_width=True,
            key="notify_borrower_btn",
        ):
            _send_notification_email(
                rec_icon,
                rec_decision,
                rec_color,
                grade,
                prob_pct,
                risk_level,
                borrower,
                rec_text,
                conditions,
                next_steps,
                llm_summary_md,
            )


def _send_notification_email(
    rec_icon,
    rec_decision,
    rec_color,
    grade,
    prob_pct,
    risk_level,
    borrower,
    rec_text,
    conditions,
    next_steps,
    llm_summary_md,
):
    """Send notification email to borrower."""
    smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER", "")
    smtp_pass = os.getenv("SMTP_PASSWORD", "")
    _logged = st.session_state.get("logged_in_user") or {}
    recipient = _logged.get("email", "")
    if not recipient:
        st.warning("Please log in first to send notifications.")
    elif not smtp_user or not smtp_pass:
        st.warning("Email not configured. Set SMTP credentials in .env")
    else:
        _summary_html = _md_to_html(llm_summary_md) if llm_summary_md else ""
        html_body = _build_email_html(
            rec_icon,
            rec_decision,
            rec_color,
            grade,
            prob_pct,
            risk_level,
            borrower,
            rec_text,
            conditions,
            next_steps,
            llm_summary_html=_summary_html,
        )
        subject_map = {
            "LOAN APPROVED": "Your Loan Application Has Been Approved",
            "NEED TO VERIFY & APPROVE": "Action Required - Additional Verification Needed",
            "LOAN REJECTED": "Your Loan Application Status",
        }
        email_subject = subject_map.get(
            rec_decision, f"Loan Application Status: {rec_decision}"
        )
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = email_subject
            msg["From"] = smtp_user
            msg["To"] = recipient
            msg.attach(MIMEText(html_body, "html"))
            with smtplib.SMTP(smtp_host, smtp_port) as server:
                server.starttls()
                server.login(smtp_user, smtp_pass)
                server.sendmail(smtp_user, recipient, msg.as_string())
            # Update notification_sent flag in DB
            _saved_id = st.session_state.get("_loan_auto_saved_id")
            if _saved_id:
                _conn = get_db_connection()
                if _conn:
                    _conn.execute(
                        "UPDATE loan_applications SET notification_sent=1 WHERE application_id=?",
                        (_saved_id,),
                    )
                    _conn.commit()
                    _conn.close()
            st.success(f"Notification email sent to {recipient}")
        except Exception as e:
            st.error(f"Failed to send email: {e}")

    # ============================================================================
    # INDIA CREDIT RISK FORM AND RESULTS
    # ============================================================================

    def _render_india_credit_risk_form():
        """Render the India-specific credit risk form."""
        st.markdown("### Borrower Information (India)")
        st.caption(
            "Enter borrower attributes for the Indian Logistic Regression credit risk model"
        )

        with st.form("india_credit_risk_form"):
            st.markdown("#### Loan Details")
            col_a, col_b = st.columns(2)
            with col_a:
                loan_amount = st.number_input(
                    "Loan Amount (₹)",
                    min_value=10000,
                    max_value=50000000,
                    value=500000,
                    step=10000,
                    help="Loan amount in Indian Rupees",
                )
                loan_term = st.selectbox(
                    "Loan Term",
                    options=[12, 24, 36, 48, 60, 72, 84],
                    format_func=lambda x: f"{x} months",
                    index=2,
                )
            with col_b:
                collateral_value = st.number_input(
                    "Collateral Value (₹)",
                    min_value=0,
                    max_value=100000000,
                    value=0,
                    step=10000,
                    help="Collateral value in Indian Rupees (optional)",
                )

            st.markdown("#### Income & Employment")
            col_c, col_d = st.columns(2)
            with col_c:
                applicant_income = st.number_input(
                    "Applicant Annual Income (₹)",
                    min_value=10000,
                    max_value=100000000,
                    value=600000,
                    step=10000,
                )
                employment_status = st.selectbox(
                    "Employment Status", options=["Salaried", "Self-employed"], index=0
                )
            with col_d:
                coapplicant_income = st.number_input(
                    "Co-applicant Annual Income (₹)",
                    min_value=0,
                    max_value=100000000,
                    value=0,
                    step=10000,
                )
                education_level = st.selectbox(
                    "Education Level",
                    options=["Not Graduate", "Graduate", "Post Graduate"],
                    index=1,
                )

            st.markdown("#### Credit Profile")
            col_e, col_f = st.columns(2)
            with col_e:
                credit_score = st.number_input(
                    "Credit Score (300-900)",
                    min_value=300,
                    max_value=900,
                    value=720,
                    step=5,
                )
                property_area = st.selectbox(
                    "Property Area", options=["Urban", "Semi-Urban", "Rural"], index=0
                )
            with col_f:
                dti_ratio = st.number_input(
                    "DTI Ratio (%)",
                    min_value=0.0,
                    max_value=90.0,
                    value=35.0,
                    step=0.5,
                    help="Debt-to-Income ratio as percentage",
                )
                existing_loans = st.number_input(
                    "Existing Loans", min_value=0, max_value=20, value=0, step=1
                )

            st.markdown("#### Additional Financial Information")
            col_g, col_h = st.columns(2)
            with col_g:
                savings = st.number_input(
                    "Total Savings (₹)",
                    min_value=0,
                    max_value=100000000,
                    value=50000,
                    step=5000,
                )

            submitted = st.form_submit_button(
                "Run Credit Risk Assessment", type="primary", use_container_width=True
            )

            if submitted:
                try:
                    from tools.credit_risk_tool import score_indian_credit_risk

                    borrower_data = {
                        "applicant_income": applicant_income,
                        "coapplicant_income": coapplicant_income,
                        "credit_score": credit_score,
                        "dti_ratio": dti_ratio / 100,  # Convert percentage to decimal
                        "collateral_value": collateral_value,
                        "loan_amount": loan_amount,
                        "loan_term": loan_term,
                        "savings": savings,
                        "employment_status": employment_status,
                        "education_level": education_level,
                        "property_area": property_area,
                        "existing_loans": existing_loans,
                    }

                    result = score_indian_credit_risk(**borrower_data)
                    result["_borrower_data"] = borrower_data
                    st.session_state.cr_results = result

                except Exception as e:
                    st.error(f"Error: {str(e)}")
                    st.session_state.cr_results = {"error": str(e)}

    def _render_india_credit_risk_results():
        """Render the India credit risk results panel."""
        if st.session_state.cr_results is None:
            st.markdown(
                """
            <div style="text-align:center; padding:60px 20px; background:#F8FAFC; border-radius:12px; border:1px solid #E2E8F0;">
            <div style="width:64px; height:64px; background:#E2E8F0; border-radius:50%; display:flex; align-items:center; justify-content:center; margin:0 auto 16px auto;">
            <span style="color:#64748B; font-size:28px; font-weight:bold;">?</span>
            </div>
            <h3 style="color:#64748B; margin:0 0 8px 0;">No Assessment Yet</h3>
            <p style="color:#94A3B8; max-width:400px; margin:0 auto;">
            Complete the borrower information form and click "Run Credit Risk Assessment"
            to generate a comprehensive credit risk report.
            </p>
            </div>
            """,
                unsafe_allow_html=True,
            )

            st.markdown("---")
            st.markdown(
                """
            <div style="background:#F1F5F9; border-radius:8px; padding:16px; border-left:4px solid #3B82F6;">
            <h4 style="margin:0 0 8px 0; color:#1E3A8A;">Model Information</h4>
            <table style="width:100%; font-size:13px; color:#475569;">
            <tr><td style="padding:4px 0;"><strong>Algorithm:</strong></td><td>Logistic Regression</td></tr>
            <tr><td style="padding:4px 0;"><strong>Training Data:</strong></td><td>Indian Loan Approval Dataset (975,800 records)</td></tr>
            <tr><td style="padding:4px 0;"><strong>Output:</strong></td><td>Approval Probability, Verdict, Key Factors, Improvement Tips</td></tr>
            <tr><td style="padding:4px 0;"><strong>Accuracy:</strong></td><td>83.1% (Precision: 74.8%, Recall: 64.6%)</td></tr>
            </table>
            </div>
            """,
                unsafe_allow_html=True,
            )
            return

        result = st.session_state.cr_results
        borrower = result.get("_borrower_data", {})

        if "error" in result:
            st.error(f"Model Error: {result['error']}")
            return

        # Extract results
        approval_pred = result.get("approval_prediction", {})
        approval_prob = approval_pred.get("approval_probability", 0)
        approval_prob_pct = approval_pred.get("approval_probability_pct", "0%")
        verdict = approval_pred.get("verdict", "Unknown")
        confidence = approval_pred.get("confidence", "Medium")

        key_factors = result.get("key_factors", [])
        improvement_tips = result.get("improvement_tips", [])

        # Render approval probability gauge
        st.markdown("### Approval Prediction")

        # Color based on verdict
        if verdict == "Approved":
            color = "#10B981"
            verdict_icon = "✅"
        else:
            color = "#EF4444"
            verdict_icon = "❌"

        # Gauge chart
        fig = go.Figure(
            go.Indicator(
                mode="gauge+number+delta",
                value=approval_prob,
                domain={"x": [0, 1], "y": [0, 1]},
                title={"text": "Approval Probability", "font": {"size": 20}},
                delta={"reference": 50, "increasing": {"color": color}},
                gauge={
                    "axis": {"range": [0, 100]},
                    "bar": {"color": color},
                    "bgcolor": "white",
                    "borderwidth": 2,
                    "bordercolor": "gray",
                    "steps": [
                        {"range": [0, 30], "color": "#FEE2E2"},
                        {"range": [30, 70], "color": "#FEF3C7"},
                        {"range": [70, 100], "color": "#D1FAE5"},
                    ],
                    "threshold": {
                        "line": {"color": color, "width": 4},
                        "thickness": 0.75,
                        "value": approval_prob,
                    },
                },
            )
        )
        fig.update_layout(height=300, margin={"t": 50, "b": 20, "l": 20, "r": 20})
        st.plotly_chart(fig, use_container_width=True)

        # Verdict card
        verdict_color = "#10B981" if verdict == "Approved" else "#EF4444"
        st.markdown(
            f"""
        <div style="display:flex; align-items:center; gap:16px; padding:16px; background:{verdict_color}15; border-radius:8px; border:1px solid {verdict_color}40;">
        <span style="font-size:32px;">{verdict_icon}</span>
        <div>
        <h3 style="margin:0; color:{verdict_color};">{verdict}</h3>
        <p style="margin:4px 0 0 0; color:#6B7280; font-size:14px;">Confidence: {confidence}</p>
        </div>
        </div>
        """,
            unsafe_allow_html=True,
        )

        # Key factors
        if key_factors:
            st.markdown("### Key Factors")
            for factor in key_factors:
                icon = (
                    "✅"
                    if factor.get("impact") == "positive"
                    else "⚠️" if factor.get("impact") == "negative" else "ℹ️"
                )
                color = (
                    "#10B981"
                    if factor.get("impact") == "positive"
                    else "#EF4444" if factor.get("impact") == "negative" else "#6B7280"
                )
                st.markdown(
                    f"""
                <div style="display:flex; align-items:center; gap:8px; padding:8px 12px; background:{color}10; border-radius:6px; margin:4px 0;">
                <span>{icon}</span>
                <span style="color:{color}; font-weight:500;">{factor.get('factor', 'N/A')}:</span>
                <span>{factor.get('description', '')}</span>
                </div>
                """,
                    unsafe_allow_html=True,
                )

        # Improvement tips
        if improvement_tips:
            st.markdown("### Improvement Tips")
            for i, tip in enumerate(improvement_tips, 1):
                st.markdown(
                    f"""
                <div style="padding:12px; background:#FEF3C7; border-radius:6px; margin:4px 0; border-left:4px solid #F59E0B;">
                <span style="color:#92400E; font-weight:600;">Tip {i}:</span> {tip}
                </div>
                """,
                    unsafe_allow_html=True,
                )

        # Input summary
        with st.expander("Input Summary", expanded=False):
            st.json(borrower)

        # Export buttons
        st.markdown("### Export")
        export_data = {
            "approval_prediction": approval_pred,
            "key_factors": key_factors,
            "improvement_tips": improvement_tips,
            "input_summary": borrower,
        }
        st.download_button(
            "Export Report (JSON)",
            data=json.dumps(export_data, indent=2, default=str).encode("utf-8"),
            file_name=f"india_credit_risk_assessment_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
            mime="application/json",
            use_container_width=True,
        )

    # ============================================================================
    # EMI CALCULATOR SECTION
    # ============================================================================

    def _render_emi_calculator_section():
        """Render the EMI calculator section."""
        st.markdown("### EMI Calculator")
        st.caption(
            "Calculate your monthly EMI with three different interest calculation methods"
        )

        # Calculator inputs
        col1, col2, col3 = st.columns(3)
        with col1:
            loan_amount_emi = st.number_input(
                "Loan Amount (₹)",
                min_value=10000,
                max_value=50000000,
                value=500000,
                step=10000,
                key="emi_loan_amount",
            )
        with col2:
            interest_rate = st.number_input(
                "Interest Rate (%)",
                min_value=1.0,
                max_value=36.0,
                value=12.0,
                step=0.25,
                key="emi_interest_rate",
            )
        with col3:
            tenure = st.number_input(
                "Tenure (months)",
                min_value=6,
                max_value=360,
                value=36,
                step=6,
                key="emi_tenure",
            )

        # Calculation method
        method = st.selectbox(
            "Calculation Method",
            options=["Reducing Balance", "Flat Rate", "Compound Interest"],
            index=0,
            key="emi_method",
        )

        # Processing fee
        processing_fee = st.number_input(
            "Processing Fee (₹)",
            min_value=0,
            max_value=50000,
            value=5000,
            step=500,
            key="emi_processing_fee",
        )

        if st.button(
            "Calculate EMI",
            type="primary",
            use_container_width=True,
            key="calculate_emi_btn",
        ):
            try:
                emi_result = calculate_emi(
                    loan_amount_emi, interest_rate, tenure, method, processing_fee
                )

                if "error" in emi_result:
                    st.error(f"Calculation Error: {emi_result['error']}")
                else:
                    st.session_state.emi_results = emi_result
                    _render_emi_results(emi_result)
            except Exception as e:
                st.error(f"Error: {str(e)}")

        elif st.session_state.emi_results:
            _render_emi_results(st.session_state.emi_results)

    def _render_emi_results(emi_result: dict):
        """Render EMI calculation results."""
        st.markdown("---")

        # Summary cards
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Monthly EMI", f"₹{emi_result['monthly_emi']:,.2f}")
        with col2:
            st.metric("Total Interest", f"₹{emi_result['total_interest']:,.2f}")
        with col3:
            st.metric("Total Cost", f"₹{emi_result['total_cost']:,.2f}")
        with col4:
            st.metric("Processing Fee", f"₹{emi_result['processing_fee']:,.2f}")

        # Donut chart
        fig = go.Figure(
            data=[
                go.Pie(
                    labels=["Principal", "Interest"],
                    values=[emi_result["loan_amount"], emi_result["total_interest"]],
                    hole=0.4,
                    marker_colors=["#3B82F6", "#10B981"],
                    textinfo="label+percent",
                    textposition="inside",
                    font=dict(family="DM Sans", size=14),
                )
            ]
        )
        fig.update_layout(
            title="Loan Breakdown",
            showlegend=False,
            height=300,
            margin={"t": 50, "b": 20, "l": 20, "r": 20},
        )
        st.plotly_chart(fig, use_container_width=True)

        # Amortization schedule
        if (
            "amortization_schedule" in emi_result
            and emi_result["amortization_schedule"]
        ):
            with st.expander("View Amortization Schedule", expanded=False):
                schedule_df = pd.DataFrame(emi_result["amortization_schedule"])
                st.dataframe(schedule_df, use_container_width=True)

                # Download button
                csv_data = schedule_df.to_csv(index=False).encode("utf-8")
                st.download_button(
                    "Download Schedule (CSV)",
                    data=csv_data,
                    file_name=f"amortization_schedule_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                    mime="text/csv",
                    use_container_width=True,
                )
