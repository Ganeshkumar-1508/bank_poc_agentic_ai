#!/usr/bin/env python3
"""
Fannie Mae Mortgage Analytics - Streamlit UI

A production-ready web application for running all 5 Fannie Mae ML models
on borrower data and displaying the results.

Usage:
    streamlit run app.py
"""

import sys
import logging
from pathlib import Path

import streamlit as st
import pandas as pd
import numpy as np

# Ensure project root is on sys.path so fannie_mae_models can be imported
PROJECT_ROOT = Path(__file__).parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fannie_mae_models.inference_helper import FannieMaeModelHub

logging.basicConfig(level=logging.WARNING)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Fannie Mae Mortgage Analytics",
    page_icon="F",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ---------------------------------------------------------------------------
# Load models (cached)
# ---------------------------------------------------------------------------
@st.cache_resource
def load_model_hub() -> FannieMaeModelHub:
    """Load all models once and cache for the session."""
    return FannieMaeModelHub(str(PROJECT_ROOT / "fannie_mae_models"))


# ---------------------------------------------------------------------------
# Default values for form fields
# ---------------------------------------------------------------------------
DEFAULTS = {
    "Original_Interest_Rate": 6.5,
    "Current_Interest_Rate": 6.5,
    "Original_UPB": 250000.0,
    "Current_Actual_UPB": 240000.0,
    "Original_Loan_Term": 360,
    "Loan_Age": 24,
    "Remaining_Months_to_Legal_Maturity": 336,
    "Original_Loan_to_Value_Ratio_LTV": 80.0,
    "Original_Combined_Loan_to_Value_Ratio_CLTV": 85.0,
    "Number_of_Borrowers": 2,
    "Debt_To_Income_DTI": 35.0,
    "Borrower_Credit_Score_at_Origination": 740,
    "Co_Borrower_Credit_Score_at_Origination": 720,
    "Current_Deferred_UPB": 0.0,
    "Modification_Flag": "N",
    "Channel": "Branch",
    "Seller_Name": "Other",
    "Servicer_Name": "Other",
    "First_Time_Home_Buyer_Indicator": "N",
    "Loan_Purpose": "Purchase",
    "Property_Type": "Single Family",
    "Occupancy_Status": "Owner Occupied",
    "Property_State": "CA",
    "MSA_or_MSDA": "0",
    "Zip_Code_Short": "0",
    "Zero_Balance_Code": "0",
    "Mortgage_Insurance_Type": "0",
    "Servicing_Activity_Indicator": "N",
    "Special_Eligibility_Program": "0",
    "Relocation_Mortgage_Indicator": "N",
    "Property_Valuation_Method": "1",
    "High_Balance_Loan_Indicator": "N",
    "Borrower_Assistance_Plan": "0",
    "Repurchase_Make_Whole_Proceeds_Flag": "N",
    "Alternative_Delinquency_Resolution": "0",
    "Amortization_Type": "Fixed",
    "Report_Year": 2025,
    "Report_Month": 1,
    "Report_Quarter": 1,
    "Loan_Identifier": "0000000001",
}

CATEGORICAL_OPTIONS = {
    "Channel": ["Branch", "Correspondent", "Direct"],
    "Seller_Name": [
        "Other",
        "Wells Fargo",
        "JPMorgan",
        "Bank of America",
        "Quicken Loans",
    ],
    "Servicer_Name": [
        "Other",
        "Wells Fargo",
        "JPMorgan",
        "Bank of America",
        "Nationstar",
    ],
    "First_Time_Home_Buyer_Indicator": ["Y", "N"],
    "Loan_Purpose": ["Purchase", "Refinance", "Cash-Out Refinance"],
    "Property_Type": [
        "Single Family",
        "Condo",
        "Townhouse",
        "PUD",
        "Manufactured Housing",
    ],
    "Occupancy_Status": ["Owner Occupied", "Investor", "Second Home"],
    "Property_State": [
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
    "Modification_Flag": ["Y", "N"],
    "Amortization_Type": ["Fixed", "ARM"],
    "High_Balance_Loan_Indicator": ["Y", "N"],
    "Relocation_Mortgage_Indicator": ["Y", "N"],
    "Mortgage_Insurance_Type": ["0", "1", "2"],
    "Servicing_Activity_Indicator": ["Y", "N"],
    "Borrower_Assistance_Plan": ["0", "1", "2", "3", "4"],
    "Zero_Balance_Code": ["0", "1", "2", "3", "6", "9"],
    "Property_Valuation_Method": ["1", "2", "3", "4"],
    "Special_Eligibility_Program": ["0", "1", "2", "3"],
    "Alternative_Delinquency_Resolution": ["0", "1", "2", "3"],
    "Repurchase_Make_Whole_Proceeds_Flag": ["Y", "N"],
}

# ---------------------------------------------------------------------------
# Model descriptions and interpretive info
# ---------------------------------------------------------------------------
MODEL_DESCRIPTIONS = {
    "credit_risk": {
        "title": "Credit Risk Assessment",
        "what": "Predicts whether a borrower will become **delinquent** (miss payments) or stay **current** on their mortgage.",
        "why": "Helps lenders identify high-risk loans early for proactive loss mitigation -- the #1 use case in mortgage analytics.",
        "metrics_note": "Test AUC: 99.99% | Test Accuracy: 99.9% | Test F1: 91.8%",
        "result_meaning": {
            0: "**Current** -- The borrower is predicted to stay current on payments. Low delinquency risk.",
            1: "**Delinquent** -- The borrower is predicted to miss payments. High delinquency risk -- consider early intervention, loss mitigation, or additional monitoring.",
        },
    },
    "customer_segmentation": {
        "title": "Customer Segmentation",
        "what": "Groups borrowers into **8 behavioral segments** using K-Means clustering based on loan characteristics, credit profiles, and payment patterns.",
        "why": "Enables targeted servicing strategies, personalized outreach, and portfolio-level risk diversification analysis.",
        "metrics_note": "8 clusters | Silhouette score: 0.055 (clusters overlap -- typical for mortgage data)",
        "cluster_descriptions": {
            0: (
                "**Conventional Stable**",
                "Established borrowers with strong credit, standard loan terms, and consistent payment history. Low-risk, core portfolio.",
            ),
            1: (
                "**First-Time Homebuyers**",
                "Newer borrowers, often with lower credit scores and higher LTV. May benefit from education and counseling programs.",
            ),
            2: (
                "**Investment Property Owners**",
                "Multi-property investors with higher loan balances. Revenue opportunity but sensitive to market downturns.",
            ),
            3: (
                "**Refinance Candidates**",
                "Borrowers with good equity positions and improved credit. Prime candidates for refinance outreach and retention campaigns.",
            ),
            4: (
                "**ARM Borrowers**",
                "Adjustable-rate mortgage holders vulnerable to rate resets. Monitor for payment shock as rates adjust.",
            ),
            5: (
                "**Government-Backed Borrowers**",
                "FHA/VA/government-insured loans with specific eligibility. Require specialized servicing compliance.",
            ),
            6: (
                "**Distressed/Modified Loans**",
                "Previously delinquent or modified loans under assistance plans. Active loss mitigation needed.",
            ),
            7: (
                "**Premium Low-LTV**",
                "High-credit, low-LTV borrowers with significant equity. Lowest risk -- ideal for cross-sell and upsell.",
            ),
        },
    },
    "operational_efficiency": {
        "title": "Operational Efficiency Score",
        "what": "Predicts a **processing efficiency score** (0-1) that measures how efficiently a loan is being serviced relative to its characteristics.",
        "why": "Identifies loans that require disproportionate servicing effort, enabling resource optimization and process improvement.",
        "metrics_note": "Note: Model R-squared is approximately 0 -- efficiency scores are near-uniform, suggesting servicing is already well-standardized across the portfolio.",
        "score_ranges": [
            (
                0.0,
                0.2,
                "**Low Efficiency**",
                "Significantly above-average servicing effort. Investigate for process bottlenecks, documentation issues, or exception handling.",
            ),
            (
                0.2,
                0.4,
                "**Below Average**",
                "Moderately higher servicing cost than typical. May benefit from process review.",
            ),
            (
                0.4,
                0.6,
                "**Average**",
                "Standard servicing efficiency. No immediate action needed.",
            ),
            (
                0.6,
                0.8,
                "**Above Average**",
                "Well-serviced loan with lower-than-typical effort. Good servicing practices in place.",
            ),
            (
                0.8,
                1.0,
                "**Highly Efficient**",
                "Minimal servicing friction. Best-in-class processing.",
            ),
        ],
    },
    "portfolio_risk": {
        "title": "Portfolio Risk Score",
        "what": "Predicts a **risk score** (0-1) that quantifies the expected loss exposure of this loan within the broader portfolio context.",
        "why": "Critical for capital allocation, hedging strategies, and regulatory reporting (e.g., CECL calculations).",
        "metrics_note": "Test R-squared: 99.95% | Test MAE: 0.0013 -- excellent predictive accuracy",
        "score_ranges": [
            (
                0.0,
                0.1,
                "**Minimal Risk**",
                "Very low expected loss. Prime-quality loan with strong borrower profile and collateral.",
            ),
            (
                0.1,
                0.3,
                "**Low Risk**",
                "Below-average risk. Well-secured with reliable payment history.",
            ),
            (
                0.3,
                0.5,
                "**Moderate Risk**",
                "Average portfolio risk. Monitor for adverse changes in borrower or market conditions.",
            ),
            (
                0.5,
                0.7,
                "**Elevated Risk**",
                "Above-average risk exposure. Consider enhanced monitoring, higher loss reserves, or risk transfer.",
            ),
            (
                0.7,
                1.0,
                "**High Risk**",
                "Significant expected loss potential. Prioritize for loss mitigation, workout options, or portfolio de-risking.",
            ),
        ],
    },
    "regional_performance": {
        "title": "Regional Performance Classification",
        "what": "Classifies the loan's **regional market performance** based on property state and local economic indicators.",
        "why": "Guides geographic concentration limits, regional servicing strategies, and market timing for originations.",
        "metrics_note": "Test Accuracy: 84.2% | Test F1: 82.6%",
        "result_meaning": {
            0: (
                "**Underperforming**",
                "The property's regional market is underperforming -- declining home values, higher delinquency rates, or weak economic conditions. Exercise caution for new originations; increase monitoring for existing loans.",
            ),
            1: (
                "**Average**",
                "The regional market is performing in line with national averages. Standard lending and servicing practices apply.",
            ),
            2: (
                "**Outperforming**",
                "The regional market is strong -- rising home values, low delinquency rates, robust employment. Favorable for originations and likely lower loss severity.",
            ),
        },
    },
}


def _get_score_interpretation(score: float, ranges: list) -> tuple:
    """Find the matching interpretation band for a numeric score."""
    for low, high, label, desc in ranges:
        if low <= score < high:
            return label, desc
    # Fallback: return last range
    return ranges[-1][2], ranges[-1][3]


def render_result_card(use_case: str, result: dict):
    """Render a model result as a styled card with interpretive descriptions."""

    info = MODEL_DESCRIPTIONS.get(use_case, {})

    if "error" in result:
        st.error(f"**{info.get('title', use_case)}** -- Error: {result['error']}")
        return

    task_type = result.get("task_type", "")

    # -- Binary Classification (Credit Risk) --------------------------------
    if task_type == "binary_classification":
        pred = result.get("predictions", [None])[0]
        probas = result.get("probabilities", [[0.5, 0.5]])
        if isinstance(probas[0], list):
            prob = probas[0][1] if len(probas[0]) > 1 else probas[0][0]
        else:
            prob = probas[0]
        confidence = result.get("confidence", [0.5])[0]

        # Result badge
        if pred == 1:
            st.error(f"### Delinquent -- {float(prob):.1%} probability")
        else:
            st.success(f"### Current -- {1 - float(prob):.1%} confidence")

        # Probability bar
        st.progress(min(float(prob), 1.0))
        st.caption(
            f"Delinquency probability: {float(prob):.1%} | Model confidence: {float(confidence):.1%}"
        )

        # Interpretation
        meaning = info.get("result_meaning", {}).get(pred, "")
        if meaning:
            st.info(meaning)

        # Metrics
        st.caption(info.get("metrics_note", ""))

    # -- Multiclass Classification (Regional Performance) --------------------
    elif task_type == "multiclass_classification":
        pred = result.get("predictions", [None])[0]
        confidence = result.get("confidence", [0.5])[0]

        meaning_info = info.get("result_meaning", {}).get(pred, (str(pred), ""))
        if isinstance(meaning_info, tuple):
            badge, desc = meaning_info
        else:
            badge, desc = str(pred), meaning_info

        if pred == 2:
            st.success(f"### {badge}")
        elif pred == 1:
            st.info(f"### {badge}")
        else:
            st.warning(f"### {badge}")

        st.progress(min(float(confidence), 1.0))
        st.caption(f"Model confidence: {float(confidence):.1%}")

        # Class probabilities
        top_k = result.get("top_k_classes", [[]])
        if top_k and top_k[0]:
            st.markdown("**Class Probabilities:**")
            cls_names = {"0": "Underperforming", "1": "Average", "2": "Outperforming"}
            for item in top_k[0]:
                name = cls_names.get(str(item["class"]), str(item["class"]))
                pct = item["probability"]
                bar_val = min(pct, 1.0)
                st.progress(bar_val)
                st.caption(f"{name}: {pct:.1%}")

        # Interpretation
        st.info(desc)
        st.caption(info.get("metrics_note", ""))

    # -- Regression (Efficiency / Risk scores) ------------------------------
    elif task_type == "regression":
        pred = result.get("predictions", [0])[0]
        score = float(pred)

        st.metric(label="Predicted Score", value=f"{score:.4f}")
        st.progress(min(score, 1.0))

        # Score interpretation
        ranges = info.get("score_ranges", [])
        if ranges:
            label, desc = _get_score_interpretation(score, ranges)
            st.markdown(f"**{label}** (score: {score:.4f})")
            st.info(desc)

        st.caption(info.get("metrics_note", ""))

    # -- Clustering (Customer Segmentation) ----------------------------------
    elif task_type == "clustering":
        label = result.get("cluster_labels", [0])[0]
        distance = result.get("cluster_distance", [0])[0]
        confidence = result.get("cluster_confidence", [0.5])[0]

        cluster_descs = info.get("cluster_descriptions", {})
        if label in cluster_descs:
            cluster_name, cluster_desc = cluster_descs[label]
            st.metric(label="Segment", value=f"Cluster {label}")
            st.success(f"### {cluster_name}")
            st.info(cluster_desc)
        else:
            st.metric(label="Segment", value=f"Cluster {label}")

        st.progress(min(float(confidence), 1.0))
        st.caption(
            f"Distance from centroid: {float(distance):.3f} | Assignment confidence: {float(confidence):.1%}"
        )

        # Show all segments for reference
        with st.expander("All Customer Segments"):
            for cid, (cname, cdesc) in sorted(cluster_descs.items()):
                highlight = ">> " if cid == label else "   "
                st.markdown(f"{highlight}**Cluster {cid} -- {cname}**: {cdesc}")

        st.caption(info.get("metrics_note", ""))


# ---------------------------------------------------------------------------
# Main app
# ---------------------------------------------------------------------------
def main():
    st.title("Fannie Mae Mortgage Analytics")
    st.markdown("Enter borrower details to get predictions across all 5 ML models.")

    # Load models
    with st.spinner("Loading models..."):
        hub = load_model_hub()

    # -- Sidebar: Borrower Input Form ----------------------------------------
    with st.sidebar:
        st.header("Borrower Details")

        st.subheader("Loan Information")
        Original_Interest_Rate = st.number_input(
            "Original Interest Rate (%)",
            min_value=0.0,
            max_value=15.0,
            value=DEFAULTS["Original_Interest_Rate"],
            step=0.125,
        )
        Current_Interest_Rate = st.number_input(
            "Current Interest Rate (%)",
            min_value=0.0,
            max_value=15.0,
            value=DEFAULTS["Current_Interest_Rate"],
            step=0.125,
        )
        Original_UPB = st.number_input(
            "Original Loan Amount ($)",
            min_value=10000,
            max_value=2000000,
            value=int(DEFAULTS["Original_UPB"]),
            step=5000,
        )
        Current_Actual_UPB = st.number_input(
            "Current UPB ($)",
            min_value=0,
            max_value=2000000,
            value=int(DEFAULTS["Current_Actual_UPB"]),
            step=5000,
        )
        Original_Loan_Term = st.selectbox(
            "Loan Term (months)", [180, 240, 360], index=2
        )
        Loan_Age = st.number_input(
            "Loan Age (months)", min_value=0, max_value=360, value=DEFAULTS["Loan_Age"]
        )
        Amortization_Type = st.selectbox(
            "Amortization Type", CATEGORICAL_OPTIONS["Amortization_Type"], index=0
        )

        st.subheader("Borrower Profile")
        Borrower_Credit_Score_at_Origination = st.slider(
            "Borrower Credit Score",
            min_value=300,
            max_value=850,
            value=DEFAULTS["Borrower_Credit_Score_at_Origination"],
        )
        Co_Borrower_Credit_Score_at_Origination = st.slider(
            "Co-Borrower Credit Score",
            min_value=300,
            max_value=850,
            value=DEFAULTS["Co_Borrower_Credit_Score_at_Origination"],
        )
        Debt_To_Income_DTI = st.slider(
            "Debt-to-Income Ratio (%)",
            min_value=0.0,
            max_value=65.0,
            value=DEFAULTS["Debt_To_Income_DTI"],
            step=0.5,
        )
        Number_of_Borrowers = st.selectbox("Number of Borrowers", [1, 2], index=1)
        First_Time_Home_Buyer_Indicator = st.selectbox(
            "First Time Home Buyer?",
            CATEGORICAL_OPTIONS["First_Time_Home_Buyer_Indicator"],
            index=1,
        )

        st.subheader("Property Details")
        Property_State = st.selectbox(
            "Property State", CATEGORICAL_OPTIONS["Property_State"], index=0
        )
        Property_Type = st.selectbox(
            "Property Type", CATEGORICAL_OPTIONS["Property_Type"], index=0
        )
        Occupancy_Status = st.selectbox(
            "Occupancy Status", CATEGORICAL_OPTIONS["Occupancy_Status"], index=0
        )
        Original_Loan_to_Value_Ratio_LTV = st.slider(
            "LTV Ratio (%)",
            min_value=0.0,
            max_value=100.0,
            value=DEFAULTS["Original_Loan_to_Value_Ratio_LTV"],
            step=1.0,
        )
        Original_Combined_Loan_to_Value_Ratio_CLTV = st.slider(
            "CLTV Ratio (%)",
            min_value=0.0,
            max_value=120.0,
            value=DEFAULTS["Original_Combined_Loan_to_Value_Ratio_CLTV"],
            step=1.0,
        )

        st.subheader("Loan Details")
        Loan_Purpose = st.selectbox(
            "Loan Purpose", CATEGORICAL_OPTIONS["Loan_Purpose"], index=0
        )
        Channel = st.selectbox("Channel", CATEGORICAL_OPTIONS["Channel"], index=0)
        Modification_Flag = st.selectbox(
            "Modified Loan?", CATEGORICAL_OPTIONS["Modification_Flag"], index=1
        )
        High_Balance_Loan_Indicator = st.selectbox(
            "High Balance Loan?",
            CATEGORICAL_OPTIONS["High_Balance_Loan_Indicator"],
            index=1,
        )

        analyze_button = st.button(
            "Analyze Borrower", type="primary", use_container_width=True
        )

    # -- Build input DataFrame from form -------------------------------------
    input_data = {
        "Original_Interest_Rate": Original_Interest_Rate,
        "Current_Interest_Rate": Current_Interest_Rate,
        "Original_UPB": Original_UPB,
        "Current_Actual_UPB": Current_Actual_UPB,
        "Original_Loan_Term": Original_Loan_Term,
        "Loan_Age": Loan_Age,
        "Amortization_Type": Amortization_Type,
        "Borrower_Credit_Score_at_Origination": Borrower_Credit_Score_at_Origination,
        "Co_Borrower_Credit_Score_at_Origination": Co_Borrower_Credit_Score_at_Origination,
        "Debt_To_Income_DTI": Debt_To_Income_DTI,
        "Number_of_Borrowers": Number_of_Borrowers,
        "First_Time_Home_Buyer_Indicator": First_Time_Home_Buyer_Indicator,
        "Property_State": Property_State,
        "Property_Type": Property_Type,
        "Occupancy_Status": Occupancy_Status,
        "Original_Loan_to_Value_Ratio_LTV": Original_Loan_to_Value_Ratio_LTV,
        "Original_Combined_Loan_to_Value_Ratio_CLTV": Original_Combined_Loan_to_Value_Ratio_CLTV,
        "Loan_Purpose": Loan_Purpose,
        "Channel": Channel,
        "Modification_Flag": Modification_Flag,
        "High_Balance_Loan_Indicator": High_Balance_Loan_Indicator,
        # Auto-filled with defaults
        "Remaining_Months_to_Legal_Maturity": DEFAULTS[
            "Remaining_Months_to_Legal_Maturity"
        ],
        "Current_Deferred_UPB": DEFAULTS["Current_Deferred_UPB"],
        "Seller_Name": DEFAULTS["Seller_Name"],
        "Servicer_Name": DEFAULTS["Servicer_Name"],
        "MSA_or_MSDA": DEFAULTS["MSA_or_MSDA"],
        "Zip_Code_Short": DEFAULTS["Zip_Code_Short"],
        "Zero_Balance_Code": DEFAULTS["Zero_Balance_Code"],
        "Mortgage_Insurance_Type": DEFAULTS["Mortgage_Insurance_Type"],
        "Servicing_Activity_Indicator": DEFAULTS["Servicing_Activity_Indicator"],
        "Special_Eligibility_Program": DEFAULTS["Special_Eligibility_Program"],
        "Relocation_Mortgage_Indicator": DEFAULTS["Relocation_Mortgage_Indicator"],
        "Property_Valuation_Method": DEFAULTS["Property_Valuation_Method"],
        "Borrower_Assistance_Plan": DEFAULTS["Borrower_Assistance_Plan"],
        "Repurchase_Make_Whole_Proceeds_Flag": DEFAULTS[
            "Repurchase_Make_Whole_Proceeds_Flag"
        ],
        "Alternative_Delinquency_Resolution": DEFAULTS[
            "Alternative_Delinquency_Resolution"
        ],
        "Report_Year": DEFAULTS["Report_Year"],
        "Report_Month": DEFAULTS["Report_Month"],
        "Report_Quarter": DEFAULTS["Report_Quarter"],
        "Loan_Identifier": DEFAULTS["Loan_Identifier"],
    }

    X = pd.DataFrame([input_data])

    # -- Results -------------------------------------------------------------
    if analyze_button:
        with st.spinner("Running all 5 models..."):
            results = hub.predict_all(X)

        st.markdown("---")
        st.header("Analysis Results")

        # Row 1: 3 cards
        col1, col2, col3 = st.columns(3)
        with col1:
            st.subheader("Credit Risk")
            render_result_card("credit_risk", results.get("credit_risk", {}))
        with col2:
            st.subheader("Customer Segment")
            render_result_card(
                "customer_segmentation", results.get("customer_segmentation", {})
            )
        with col3:
            st.subheader("Operational Efficiency")
            render_result_card(
                "operational_efficiency", results.get("operational_efficiency", {})
            )

        # Row 2: 2 cards
        col1, col2 = st.columns(2)
        with col1:
            st.subheader("Portfolio Risk")
            render_result_card("portfolio_risk", results.get("portfolio_risk", {}))
        with col2:
            st.subheader("Regional Performance")
            render_result_card(
                "regional_performance", results.get("regional_performance", {})
            )

        # Raw JSON expander
        with st.expander("Raw Model Outputs (JSON)"):
            import json

            def make_serializable(obj):
                if isinstance(obj, (np.integer,)):
                    return int(obj)
                if isinstance(obj, (np.floating,)):
                    return float(obj)
                if isinstance(obj, np.ndarray):
                    return obj.tolist()
                return obj

            clean = {}
            for k, v in results.items():
                clean[k] = {k2: make_serializable(v2) for k2, v2 in v.items()}
            st.json(clean)

    else:
        # Show placeholder
        st.info(
            "Fill in borrower details on the sidebar and click **Analyze Borrower** to get predictions."
        )

        # Show model info with rich descriptions
        with st.expander("About the Models"):
            for name in hub.available_models:
                desc = MODEL_DESCRIPTIONS.get(name, {})
                st.markdown(f"### {desc.get('title', name.replace('_', ' ').title())}")
                st.markdown(f"**What it does:** {desc.get('what', 'N/A')}")
                st.markdown(f"**Why it matters:** {desc.get('why', 'N/A')}")
                st.caption(desc.get("metrics_note", ""))
                st.markdown("")


if __name__ == "__main__":
    main()
