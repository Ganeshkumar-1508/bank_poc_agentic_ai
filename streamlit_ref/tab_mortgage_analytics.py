# tab_mortgage_analytics.py  —  Mortgage Analytics Tab for Fixed Deposit Advisor
import json
import streamlit as st


def render_mortgage_analytics_tab():
    """Render the Mortgage Analytics tab."""
    st.markdown(
        '<h2 class="sub-header">Mortgage Analytics</h2>', unsafe_allow_html=True
    )

    # Region gating - Mortgage Analytics is US-only
    user_region = st.session_state.get("user_region", {})
    user_country_code = user_region.get("country_code", "WW")
    user_country_name = user_region.get("country_name", "Worldwide")

    is_us_region = user_country_code.upper() in ("US", "UNITED STATES", "USA")

    if not is_us_region:
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
                Mortgage Analytics is currently available only for <strong>United States</strong> region users.
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
        The Fannie Mae mortgage analytics models are trained on **US mortgage data** and use US-specific
        lending conventions (FICO scores, US-style LTV/DTI calculations, US property types, state codes).
        Applying these models to borrowers from other regions would produce unreliable results.
        """
        )

        st.markdown("#### Available alternatives in your region")
        st.markdown(
            f"""
        - Use the **FD Advisor** tab to compare deposit rates in {user_country_name or "your region"}
        - Use the **Credit Risk** tab for US consumer lending risk assessment
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
    else:
        # US users get full access
        st.markdown(
            f"""
        <div style="display:flex; align-items:center; gap:8px; margin-bottom:16px; padding:8px 12px; background:#F0FDF4; border-radius:6px; border:1px solid #BBF7D0;">
            <span style="color:#16A34A; font-weight:600;">US Region</span>
            <span style="color:#166534; font-size:13px;">Detected -- Fannie Mae mortgage models are applicable for your region</span>
        </div>
        """,
            unsafe_allow_html=True,
        )

        # Initialize session state for mortgage analytics
        if "ma_form_data" not in st.session_state:
            st.session_state.ma_form_data = {}
        if "ma_results" not in st.session_state:
            st.session_state.ma_results = None

        ma_form_col, ma_results_col = st.columns([1, 2])

        with ma_form_col:
            st.markdown("### Borrower Information")
            st.caption(
                "Enter borrower attributes for Fannie Mae mortgage analytics (15 key features)"
            )

            with st.form("mortgage_analytics_form"):
                st.markdown("#### Loan Details")
                col_a, col_b = st.columns(2)
                with col_a:
                    original_upb = st.number_input(
                        "Original UPB ($)",
                        min_value=10000,
                        max_value=2000000,
                        value=250000,
                        step=10000,
                        key="ma_upb",
                    )
                    original_ltv = st.number_input(
                        "Original LTV (%)",
                        min_value=10.0,
                        max_value=125.0,
                        value=80.0,
                        step=0.5,
                        key="ma_ltv",
                    )
                    original_interest_rate = st.number_input(
                        "Original Interest Rate (%)",
                        min_value=1.0,
                        max_value=15.0,
                        value=6.5,
                        step=0.125,
                        key="ma_rate",
                    )
                    original_loan_term = st.selectbox(
                        "Original Loan Term",
                        options=[180, 360],
                        format_func=lambda x: f"{x//12} years",
                        index=1,
                        key="ma_term",
                    )
                with col_b:
                    borrower_credit_score = st.number_input(
                        "Borrower Credit Score",
                        min_value=300,
                        max_value=850,
                        value=740,
                        step=10,
                        key="ma_credit",
                    )
                    debt_to_income = st.number_input(
                        "Debt-to-Income Ratio (%)",
                        min_value=0.0,
                        max_value=100.0,
                        value=35.0,
                        step=0.5,
                        key="ma_dti",
                    )
                    number_of_borrowers = st.number_input(
                        "Number of Borrowers",
                        min_value=1,
                        max_value=5,
                        value=2,
                        step=1,
                        key="ma_borrowers",
                    )

                st.markdown("#### Loan Characteristics")
                col_c, col_d = st.columns(2)
                with col_c:
                    loan_purpose = st.selectbox(
                        "Loan Purpose",
                        options=["Purchase", "Refinance", "Cash-Out Refinance"],
                        index=0,
                        key="ma_purpose",
                    )
                    property_type = st.selectbox(
                        "Property Type",
                        options=[
                            "Single Family",
                            "Condo",
                            "Townhouse",
                            "PUD",
                            "Manufactured Housing",
                        ],
                        index=0,
                        key="ma_property",
                    )
                    occupancy_status = st.selectbox(
                        "Occupancy Status",
                        options=["Owner Occupied", "Investor", "Second Home"],
                        index=0,
                        key="ma_occupancy",
                    )
                    amortization_type = st.selectbox(
                        "Amortization Type",
                        options=["Fixed", "ARM"],
                        index=0,
                        key="ma_amortization",
                    )
                with col_d:
                    channel = st.selectbox(
                        "Channel",
                        options=["Branch", "Correspondent", "Direct"],
                        index=0,
                        key="ma_channel",
                    )
                    property_state = st.selectbox(
                        "Property State",
                        options=[
                            "CA",
                            "TX",
                            "FL",
                            "NY",
                            "IL",
                            "PA",
                            "OH",
                            "GA",
                            "NC",
                            "MI",
                            "NJ",
                            "VA",
                            "WA",
                            "AZ",
                            "MA",
                            "MD",
                            "CO",
                            "MN",
                            "OR",
                            "IN",
                        ],
                        index=0,
                        key="ma_state",
                    )
                    first_time_home_buyer = st.selectbox(
                        "First Time Home Buyer",
                        options=["Y", "N"],
                        index=1,
                        key="ma_first_time",
                    )
                    modification_flag = st.selectbox(
                        "Modification Flag",
                        options=["Y", "N"],
                        index=1,
                        key="ma_modification",
                    )

                submitted_ma = st.form_submit_button(
                    "Analyze Mortgage", type="primary", use_container_width=True
                )

                if submitted_ma:
                    borrower_data = {
                        "Borrower_Credit_Score_at_Origination": borrower_credit_score,
                        "Original_Loan_to_Value_Ratio_LTV": original_ltv,
                        "Debt_To_Income_DTI": debt_to_income,
                        "Original_UPB": original_upb,
                        "Loan_Purpose": loan_purpose,
                        "Property_Type": property_type,
                        "Occupancy_Status": occupancy_status,
                        "Property_State": property_state,
                        "Amortization_Type": amortization_type,
                        "Original_Interest_Rate": original_interest_rate,
                        "First_Time_Home_Buyer_Indicator": first_time_home_buyer,
                        "Modification_Flag": modification_flag,
                        "Channel": channel,
                        "Number_of_Borrowers": number_of_borrowers,
                        "Original_Loan_Term": original_loan_term,
                    }
                    st.session_state.ma_form_data = borrower_data

                    # Run mortgage analytics via CrewAI
                    try:
                        from crews import run_mortgage_analytics_crew
                        from tools.US_mortgage_tool import run_mortgage_analytics

                        with st.spinner(
                            "Running Fannie Mae mortgage analytics with AI agents..."
                        ):
                            # First, run the ML model directly to get structured results
                            borrower_json = json.dumps(borrower_data, indent=2)
                            ml_results = run_mortgage_analytics(borrower_data)

                            # Then, have the crew interpret the results and provide analysis
                            prompt_context = (
                                f"Borrower Data:\n{borrower_json}\n\n"
                                f"ML Model Results:\n{json.dumps(ml_results, indent=2)}\n\n"
                                "Provide a comprehensive mortgage analytics report interpreting these results, "
                                "including key findings, risk assessment, and actionable recommendations."
                            )
                            crew_result = run_mortgage_analytics_crew(borrower_json)

                            # Extract crew output for evaluation
                            crew_output = (
                                crew_result.raw
                                if hasattr(crew_result, "raw")
                                else str(crew_result)
                            )

                            # Combine ML results with crew interpretation
                            st.session_state.ma_results = {
                                **ml_results,  # Include structured ML results
                                "crew_analysis": crew_output,
                            }

                            # Post evaluation to Langfuse (async, non-blocking)
                            try:
                                from langfuse_instrumentation import (
                                    get_current_trace_id,
                                    post_crew_evaluation,
                                )

                                trace_id = get_current_trace_id()
                                post_crew_evaluation(
                                    crew_name="mortgage-analytics-crew",
                                    user_input=borrower_json,
                                    output_text=crew_output,
                                    trace_id=trace_id,
                                )
                            except Exception as eval_error:
                                print(
                                    f"[Langfuse] Evaluation failed for mortgage-analytics-crew: {eval_error}"
                                )

                            st.success("Analysis complete!")
                            st.rerun()
                    except ImportError as e:
                        st.error(f"CrewAI or dependencies not available: {e}")
                        st.session_state.ma_results = {"error": str(e), "analyses": {}}
                    except Exception as e:
                        st.error(f"Analysis failed: {e}")
                        import traceback

                        st.session_state.ma_results = {
                            "error": str(e),
                            "traceback": traceback.format_exc(),
                            "analyses": {},
                        }

        with ma_results_col:
            if st.session_state.ma_results:
                # Display results
                results = st.session_state.ma_results

                st.markdown("## Analytics Results")

                # Summary card
                summary = results.get("summary", {})
                overall_risk = summary.get("overall_risk", "UNKNOWN")
                risk_color = (
                    "#16A34A"
                    if overall_risk == "LOW"
                    else "#EAB308" if overall_risk == "MEDIUM" else "#DC2626"
                )

                st.markdown(
                    f"""
                <div style="background:{'#DCFCE7' if overall_risk == 'LOW' else '#FEF9C3' if overall_risk == 'MEDIUM' else '#FEE2E2'};
                    border:1px solid {risk_color}; border-radius:8px; padding:16px; margin-bottom:16px;">
                    <div style="display:flex; align-items:center; gap:12px;">
                        <div style="width:40px; height:40px; background:{risk_color}; border-radius:50%; display:flex;
                            align-items:center; justify-content:center;">
                            <span style="color:white; font-weight:bold; font-size:18px;">
                                {'✓' if overall_risk == 'LOW' else '⚠' if overall_risk == 'MEDIUM' else '✗'}
                            </span>
                        </div>
                        <div>
                            <div style="font-size:14px; color:#64748B;">Overall Risk Assessment</div>
                            <div style="font-size:24px; font-weight:700; color:{risk_color};">{overall_risk}</div>
                        </div>
                    </div>
                </div>
                """,
                    unsafe_allow_html=True,
                )

                # Key findings
                if summary.get("key_findings"):
                    st.markdown("#### Key Findings")
                    for finding in summary["key_findings"]:
                        st.markdown(f"- {finding}")

                # Recommendations
                if summary.get("recommendations"):
                    st.markdown("#### Recommendations")
                    for rec in summary["recommendations"]:
                        st.markdown(f"- {rec}")

                st.markdown("---")

                # Credit Risk Analysis
                if "credit_risk" in results.get("analyses", {}):
                    cr = results["analyses"]["credit_risk"]
                    if "error" not in cr:
                        st.markdown("#### Credit Risk Assessment")
                        col_cr1, col_cr2 = st.columns(2)
                        with col_cr1:
                            st.markdown(
                                f"**Prediction:** {cr.get('prediction_label', 'N/A')}"
                            )
                            st.markdown(
                                f"**Risk Level:** {cr.get('risk_level', 'N/A')}"
                            )
                        with col_cr2:
                            prob = cr.get("probability", 0)
                            st.markdown(f"**Delinquency Probability:** {prob:.1%}")
                            st.markdown(
                                f"**Confidence:** {(cr.get('confidence', 0)):.1%}"
                            )

                # Customer Segmentation
                if "customer_segmentation" in results.get("analyses", {}):
                    seg = results["analyses"]["customer_segmentation"]
                    if "error" not in seg:
                        st.markdown("#### Customer Segmentation")
                        st.markdown(f"**Segment:** {seg.get('cluster_label', 'N/A')}")
                        st.markdown(f"**Cluster ID:** {seg.get('cluster', 'N/A')}")

                # Portfolio Risk
                if "portfolio_risk" in results.get("analyses", {}):
                    pr = results["analyses"]["portfolio_risk"]
                    if "error" not in pr:
                        st.markdown("#### Portfolio Risk")
                        st.markdown(f"**Prediction:** {pr.get('prediction', 'N/A')}")

                # Crew Analysis Report (detailed interpretation)
                if "crew_analysis" in results and results["crew_analysis"]:
                    st.markdown("---")
                    st.markdown("## AI Agent Analysis Report")
                    st.caption("Comprehensive interpretation generated by AI agents")

                    crew_analysis = results["crew_analysis"]

                    # Check if it's a string and display as markdown
                    if isinstance(crew_analysis, str):
                        st.markdown(crew_analysis)
                    else:
                        st.markdown(str(crew_analysis))

                # Input features
                st.markdown("---")
                st.markdown("#### Input Features")
                features = results.get("processed_features", {})
                feat_cols = st.columns(3)
                for i, (key, value) in enumerate(features.items()):
                    col_idx = i % 3
                    with feat_cols[col_idx]:
                        st.markdown(f"**{key.replace('_', ' ').title()}:** {value}")

            else:
                # No results yet - show placeholder
                st.markdown(
                    """
                <div style="text-align:center; padding:40px 20px; background:#F8FAFC; border-radius:8px; border:1px solid #E2E8F0;">
                    <div style="font-size:48px; margin-bottom:16px;">📊</div>
                    <h3 style="color:#64748B; margin:0 0 8px 0;">Mortgage Analytics</h3>
                    <p style="color:#94A3B8; margin:0;">
                        Enter borrower information on the left and click "Analyze Mortgage" to see predictions.
                    </p>
                </div>
                """,
                    unsafe_allow_html=True,
                )
