# tab_new_account.py — New Account Tab for Fixed Deposit Advisor
import re
import json
import streamlit as st

# Import from UI first - this sets up sys.path for project-level imports via config
from .helpers import get_dynamic_kyc_docs, run_crew_with_langfuse
from .database import get_linked_user, save_aml_case, log_audit

# Now we can safely import from project-level modules
from tools import fetch_country_data
from crews import create_aml_crew


def render_new_account_tab():
    """Render the New Account (Onboarding) tab."""
    st.markdown("##  Open a New Account")
    country_info = st.session_state.user_region
    selected_country_name = country_info["country_name"]
    selected_country_code = country_info["country_code"]
    all_countries = fetch_country_data()
    country_lookup = {v["name"]: cc for cc, v in all_countries.items() if v["name"]}
    country_names_sorted = sorted(country_lookup.keys())
    detected_idx = (
        country_names_sorted.index(selected_country_name)
        if selected_country_name in country_names_sorted
        else 0
    )

    col_country, _ = st.columns([1, 2])
    with col_country:
        selected_country_name = st.selectbox(
            "Country",
            options=country_names_sorted,
            index=detected_idx,
            key="onboard_country",
        )
    selected_country_code = country_lookup.get(selected_country_name, "WW")

    with st.spinner("Loading KYC requirements..."):
        doc1, doc2 = get_dynamic_kyc_docs(selected_country_name)
    if (
        "kyc_document_names" not in st.session_state
        or st.session_state.get("_last_kyc_country") != selected_country_name
    ):
        st.session_state.kyc_document_names = [doc1, doc2]
        st.session_state["_last_kyc_country"] = selected_country_name

    badge_bg, badge_color = "#DBEAFE", "#1E40AF"
    st.markdown(
        f"""<div style="background:#F0FDF4;border:1px solid #BBF7D0;border-radius:8px;padding:12px 16px;margin-bottom:1rem">
          <b style="color:#166534">📋 KYC Requirements for {selected_country_name}</b><br>
          <span class="badge" style="background:{badge_bg};color:{badge_color}">1. {doc1}</span>
          <span class="badge" style="background:{badge_bg};color:{badge_color}">2. {doc2}</span>
        </div>""",
        unsafe_allow_html=True,
    )

    with st.form("onboarding_form"):
        st.markdown("#### Applicant Information")
        col1, col2 = st.columns(2)
        with col1:
            first_name = st.text_input("First Name")
            last_name = st.text_input("Last Name")
            email = st.text_input("Email Address")
            mobile = st.text_input("Mobile Number")
        with col2:
            address = st.text_area("Residential Address")
            pin_code = st.text_input("PIN / Postal Code")
            st.text_input("Country", value=selected_country_name, disabled=True)

        st.markdown("#### Deposit Details")
        col3, col4 = st.columns(2)
        with col3:
            product_type = st.radio("Product Type", ["FD", "RD"])
            amount = st.number_input(
                f"Amount ({'Principal' if product_type == 'FD' else 'Monthly Installment'})",
                min_value=1000,
            )
            tenure = st.slider("Tenure (Months)", 6, 120, 12)
        with col4:
            bank_name = st.text_input("Preferred Bank Name", value="SBI")
            compounding = st.selectbox(
                "Compounding Frequency", ["quarterly", "monthly", "yearly"]
            )

        st.markdown("#### KYC Documentation")
        col5, col6 = st.columns(2)
        with col5:
            kyc_val_1 = st.text_input(f"{doc1} Number")
        with col6:
            kyc_val_2 = st.text_input(f"{doc2} Number")

        submitted = st.form_submit_button("Submit Application")

        if submitted:
            if not all(
                [
                    first_name,
                    last_name,
                    email,
                    mobile,
                    address,
                    pin_code,
                    kyc_val_1,
                    kyc_val_2,
                ]
            ):
                st.error("Please fill all mandatory fields.")
            else:
                client_data = {
                    "first_name": first_name,
                    "last_name": last_name,
                    "email": email,
                    "user_address": address,
                    "pin_number": pin_code,
                    "mobile_number": mobile,
                    "bank_name": bank_name,
                    "product_type": product_type,
                    "initial_amount": float(amount),
                    "tenure_months": int(tenure),
                    "compounding_freq": compounding,
                    "kyc_details_1": f"{doc1}-{kyc_val_1}",
                    "kyc_details_2": f"{doc2}-{kyc_val_2}",
                    "country_code": selected_country_code,
                }
                json_str = json.dumps(client_data)
                st.session_state.langfuse_user_id = email
                st.info("Application submitted. Running compliance and risk checks...")
                try:
                    aml_response = run_crew_with_langfuse(
                        crew_callable=lambda: create_aml_crew(json_str).kickoff(),
                        crew_name="aml-execution-crew",
                        user_input=f"New account application for {first_name} {last_name}",
                        region=selected_country_name,
                        extra_metadata={
                            "product_type": product_type,
                            "bank_name": bank_name,
                            "applicant_email": email,
                        },
                    )
                    report_text = (
                        aml_response.raw
                        if hasattr(aml_response, "raw")
                        else str(aml_response)
                    )

                    # Persist AML result to DB
                    linked_user = get_linked_user(email)
                    if linked_user:
                        score_match = re.search(r"SCORE:\s*(\d+)", report_text)
                        risk_score = int(score_match.group(1)) if score_match else 50
                        dec_match = re.search(
                            r"DECISION:\s*(PASS|FAIL|APPROVE|REJECT)",
                            report_text,
                            re.IGNORECASE,
                        )
                        decision = dec_match.group(1).upper() if dec_match else "REVIEW"
                        band = (
                            "LOW"
                            if risk_score <= 20
                            else (
                                "MEDIUM"
                                if risk_score <= 40
                                else "HIGH" if risk_score <= 60 else "CRITICAL"
                            )
                        )
                        sanctions = (
                            1
                            if "sanctions" in report_text.lower()
                            and "hit" in report_text.lower()
                            else 0
                        )
                        pep = (
                            1
                            if "politically exposed" in report_text.lower()
                            or "pep" in report_text.lower()
                            else 0
                        )
                        adverse = 1 if "adverse" in report_text.lower() else 0
                        case_id = save_aml_case(
                            linked_user["user_id"],
                            risk_score,
                            band,
                            decision,
                            report_markdown=report_text,
                            sanctions_hit=sanctions,
                            pep_flag=pep,
                            adverse_media=adverse,
                        )
                        log_audit(
                            linked_user["user_id"],
                            case_id,
                            "DEPOSIT_APPLICATION",
                            f"Application submitted for {product_type} at {bank_name}",
                            "Onboarding Form",
                        )

                        st.markdown("### Compliance Report")
                        st.markdown(report_text)
                except Exception as e:
                    st.error(f"An error occurred during processing: {e}")
