# helpers.py — General Helper Functions for Fixed Deposit Advisor
import os
import re
import json
import requests
import streamlit as st
import numpy as np
from datetime import datetime

from tools.config import fetch_country_data
from tools.search_tool import set_search_region
from langchain_nvidia_ai_endpoints import ChatNVIDIA

from .config import MODEL_DIR


# =============================================================================
# GEOLOCATION & REGION
# =============================================================================
def detect_user_region() -> dict:
    countries = fetch_country_data()
    try:
        resp = requests.get("https://ipinfo.io/json", timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            cc = data.get("country", "WW").upper()
            info = countries.get(cc, {})
            ddg = set_search_region(cc)
            return {
                "country_code": cc,
                "country_name": info.get("name", cc),
                "ddg_region": ddg,
                "currency_symbol": info.get("currency_symbol", ""),
                "currency_code": info.get("currency_code", ""),
            }
    except Exception:
        pass
    return {
        "country_code": "WW",
        "country_name": "Worldwide",
        "ddg_region": "wt-wt",
        "currency_symbol": "",
        "currency_code": "",
    }


# =============================================================================
# SESSION STATE INIT
# =============================================================================
def init_session_state():
    """Initialize all required session state variables."""
    if "user_region" not in st.session_state:
        st.session_state.user_region = detect_user_region()
    else:
        set_search_region(st.session_state.user_region["country_code"])

    if "langfuse_session_id" not in st.session_state:
        st.session_state.langfuse_session_id = f"fd-session-{st.session_state.user_region.get('country_code','WW')}-{os.urandom(4).hex()}"
    if "langfuse_user_id" not in st.session_state:
        st.session_state.langfuse_user_id = st.session_state.langfuse_session_id

    # logged_in_user: {session_id, display_name, email, country_code} or None
    if "logged_in_user" not in st.session_state:
        st.session_state.logged_in_user = None

    for key, val in [
        ("messages", []),
        ("last_analysis_data", None),
        ("last_report_markdown", ""),
        ("last_tenure_months", 12),
    ]:
        if key not in st.session_state:
            st.session_state[key] = val


def get_currency_symbol() -> str:
    return st.session_state.get("user_region", {}).get("currency_symbol", "")


def reset_session():
    for k in [
        "messages",
        "last_analysis_data",
        "last_report_markdown",
        "last_tenure_months",
        "PENDING_AML_JSON",
        "langfuse_session_id",
        "langfuse_user_id",
    ]:
        if k in st.session_state:
            del st.session_state[k]
        st.rerun()


# =============================================================================
# LANGFUSE WRAPPER
# =============================================================================
def run_crew_with_langfuse(
    crew_callable, crew_name, user_input="", region="Worldwide", extra_metadata=None
):
    # Lazy import to avoid circular dependency
    from .config import langfuse

    session_id = st.session_state.get("langfuse_session_id")
    user_id = st.session_state.get("langfuse_user_id")
    metadata = {"region": region, "crew_name": crew_name, "streamlit_session": "active"}
    if extra_metadata:
        metadata.update(extra_metadata)
    output_text = None
    trace_id = None
    with langfuse.start_as_current_observation(
        as_type="trace",
        name=crew_name,
        input={"user_input": user_input},
        metadata=metadata,
    ) as trace:
        trace.update(session_id=session_id, user_id=user_id)
        trace_id = getattr(trace, "trace_id", None) or getattr(trace, "id", None)
        from langfuse import propagate_attributes

        with propagate_attributes(session_id=session_id, user_id=user_id):
            result = crew_callable()
            if hasattr(result, "raw"):
                output_text = result.raw
            elif isinstance(result, str):
                output_text = result
            if output_text:
                trace.update(output={"output": output_text[:2000]})
    langfuse.flush()
    from langfuse_evaluator import evaluate_crew_output_async

    evaluate_crew_output_async(
        langfuse_client=langfuse,
        trace_id=trace_id,
        crew_name=crew_name,
        user_input=user_input,
        output_text=output_text or "",
    )
    return result


# =============================================================================
# CACHED HELPERS
# =============================================================================
@st.cache_data(ttl=3600)
def get_dynamic_kyc_docs(country_name: str) -> tuple:
    if not os.getenv("NVIDIA_API_KEY"):
        return ("Government-issued Photo ID", "Proof of Address")
    llm = ChatNVIDIA(model="meta/llama-3.1-8b-instruct")

    def _parse_docs(text):
        text = text.strip()
        for fence in ("```json", "```"):
            if fence in text:
                text = text.split(fence)[1].split("```")[0].strip()
                break
        match = re.search(r"\[.*?\]", text, re.DOTALL)
        if match:
            text = match.group(0)
        try:
            docs = json.loads(text)
            if isinstance(docs, list) and len(docs) >= 2:
                d1, d2 = str(docs[0]).strip(), str(docs[1]).strip()
                generic = {
                    "national id card",
                    "proof of address",
                    "government-issued photo id",
                    "passport",
                }
                if d1.lower() not in generic or d2.lower() not in generic:
                    return (d1, d2)
        except (json.JSONDecodeError, ValueError):
            pass
        return None

    try:
        prompt = (
            f"What are the TWO primary mandatory government-issued identity documents that banks "
            f"in '{country_name}' require for KYC?\n"
            f'Return ONLY a raw JSON array with exactly two strings. Example: ["Aadhaar Card", "PAN Card"]'
        )
        response = llm.invoke(prompt)
        result = _parse_docs(response.content)
        if result:
            return result
    except Exception:
        pass
    return ("Government-issued Photo ID", "Proof of Address")


# No longer needed - crews are now standalone functions
# get_crews() function removed as FixedDepositCrews class is eliminated


def clean_response(raw: str) -> str:
    text = raw.strip()
    for prefix in ("QUESTION:", "DATA_READY:"):
        if text.startswith(prefix):
            text = text[len(prefix) :].strip()
            break
    return text


def append_assistant(text: str, chart_options=None):
    msg = {"role": "assistant", "content": text}
    if chart_options:
        msg["chart_options"] = chart_options
    st.session_state.messages.append(msg)


# =============================================================================
# MODEL FUNCTIONS
# =============================================================================
def _cr_model_available():
    return (MODEL_DIR / "xgb_model.pkl").exists()


def _cr_predict(data):
    try:
        model, fi_df, mf = _load_model()
        feats = _engineer_features(data)
        if mf:
            for f in mf:
                if f not in feats:
                    feats[f] = np.nan
            ordered = [feats[f] for f in mf]
        else:
            ordered = list(feats.values())
        X = np.array(ordered).reshape(1, -1)
        try:
            prob = float(model.predict_proba(X)[0][1])
        except Exception:
            prob = float(model.predict(X)[0])
        grade, risk = _probability_to_grade(prob)
        top = []
        try:
            imp = model.get_booster().get_score(importance_type="gain")
            if not imp:
                imp = model.get_booster().get_score(importance_type="weight")

            tot = sum(imp.values()) or 1.0

            # Build f0→real-name map.
            # Priority 1: mf (booster.feature_names when available)
            # Priority 2: sklearn feature_names_in_
            # Priority 3: ordered keys from _engineer_features() — same order passed to model
            resolved_names = (
                mf
                or (
                    list(model.feature_names_in_)
                    if hasattr(model, "feature_names_in_")
                    else None
                )
                or list(feats.keys())
            )
            feature_name_map = {
                f"f{idx}": fname for idx, fname in enumerate(resolved_names)
            }

            for fn, g in sorted(imp.items(), key=lambda x: x[1], reverse=True)[:8]:
                actual_name = feature_name_map.get(fn, fn)
                rat = ""
                if fi_df is not None and not fi_df.empty:
                    m = fi_df[
                        fi_df.iloc[:, 0].astype(str).str.lower() == actual_name.lower()
                    ]
                    if not m.empty and m.shape[1] > 1:
                        rat = str(m.iloc[0, -1])
                value = data.get(
                    actual_name,
                    data.get(fn, feats.get(actual_name, feats.get(fn, "N/A"))),
                )
                top.append(
                    {
                        "feature": actual_name,
                        "importance_pct": round(g / tot * 100, 1),
                        "rationale": rat,
                        "value": value,
                    }
                )
        except Exception as e:
            import traceback

            traceback.print_exc()

        return {
            "default_probability": round(prob, 6),
            "default_probability_pct": f"{prob*100:.2f}%",
            "implied_grade": grade,
            "risk_level": risk,
            "top_features": top,
        }
    except Exception as e:
        return {"error": str(e)}


def _load_model():
    """Load XGBoost model from disk."""
    import pickle

    model_path = MODEL_DIR / "xgb_model.pkl"
    fi_path = MODEL_DIR / "feature_importance.csv"

    with open(model_path, "rb") as f:
        model = pickle.load(f)

    fi_df = None
    if fi_path.exists():
        import pandas as pd

        fi_df = pd.read_csv(fi_path)

    mf = None
    if hasattr(model, "get_booster"):
        try:
            mf = model.get_booster().feature_names
        except Exception:
            pass

    return model, fi_df, mf


def _engineer_features(data: dict) -> dict:
    """Engineer features for the credit risk model."""
    feats = {}

    # Direct mappings
    direct_keys = [
        "loan_amnt",
        "term",
        "int_rate",
        "annual_inc",
        "dti",
        "fico_score",
        "delinq_2yrs",
        "inq_last_6mths",
        "pub_rec",
        "revol_bal",
        "revol_util",
        "total_acc",
        "open_acc",
        "mths_since_last_delinq",
        "total_rev_hi_lim",
    ]
    for k in direct_keys:
        feats[k] = data.get(k, 0)

    # Derived features
    loan_amnt = data.get("loan_amnt", 0)
    annual_inc = data.get("annual_inc", 1)
    feats["loan_to_income"] = loan_amnt / max(annual_inc, 1) * 100

    # Credit history length (from earliest_cr_line)
    earliest_cr_line = data.get("earliest_cr_line", "")
    if earliest_cr_line:
        try:
            from datetime import datetime

            cr_date = datetime.strptime(earliest_cr_line, "%b-%Y")
            now = datetime.now()
            feats["cr_history_length"] = (now.year - cr_date.year) * 12 + (
                now.month - cr_date.month
            )
        except Exception:
            feats["cr_history_length"] = 0
    else:
        feats["cr_history_length"] = 0

    # Home ownership encoding
    home_ownership = data.get("home_ownership", "RENT")
    feats["home_ownership_MORTGAGE"] = 1 if home_ownership == "MORTGAGE" else 0
    feats["home_ownership_OWN"] = 1 if home_ownership == "OWN" else 0
    feats["home_ownership_RENT"] = 1 if home_ownership == "RENT" else 0

    # Verification status encoding
    verification_status = data.get("verification_status", "Not Verified")
    feats["verification_status_Source Verified"] = (
        1 if verification_status == "Source Verified" else 0
    )
    feats["verification_status_Verified"] = (
        1 if verification_status == "Verified" else 0
    )

    # Purpose encoding (simplified)
    purpose = data.get("purpose", "debt_consolidation")
    purpose_dummies = [
        "purpose_credit_card",
        "purpose_debt_consolidation",
        "purpose_home_improvement",
        "purpose_house",
        "purpose_major_purchase",
        "purpose_medical",
        "purpose_moving",
        "purpose_other",
        "purpose_renewable_energy",
        "purpose_small_business",
        "purpose_vacation",
        "purpose_wedding",
    ]
    for p in purpose_dummies:
        feats[p] = 1 if purpose == p.replace("purpose_", "") else 0

    return feats


def _probability_to_grade(prob: float) -> tuple:
    """Convert default probability to risk grade and level."""
    if prob < 0.05:
        return "A", "LOW"
    elif prob < 0.10:
        return "B", "LOW"
    elif prob < 0.15:
        return "C", "MEDIUM"
    elif prob < 0.20:
        return "D", "MEDIUM"
    elif prob < 0.30:
        return "E", "HIGH"
    elif prob < 0.40:
        return "F", "HIGH"
    else:
        return "G", "CRITICAL"
