# tools/credit_risk_tool.py
import os, json, math
import numpy as np
import pandas as pd
import joblib
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, List
from crewai.tools import BaseTool

MODEL_DIR = Path(os.getenv(
    "CREDIT_RISK_MODEL_DIR",
    str(Path(__file__).resolve().parent.parent / "models" / "credit_risk"),
))
_MODEL_PATH = MODEL_DIR / "xgb_model.pkl"
_FEATURE_INFO_PATH = MODEL_DIR / "feature_info.csv"

_GRADE_BANDS = [
    ("A", 0.00, 0.05), ("B", 0.05, 0.10), ("C", 0.10, 0.15),
    ("D", 0.15, 0.20), ("E", 0.20, 0.25), ("F", 0.25, 0.30), ("G", 0.30, 1.01),
]
_RISK_LABELS = {
    "A": "Low", "B": "Low-Medium", "C": "Medium",
    "D": "Medium-High", "E": "High", "F": "Very High", "G": "Critical",
}
_PURPOSES = [
    "debt_consolidation", "credit_card", "home_improvement", "major_purchase",
    "medical", "small_business", "car", "moving", "vacation", "house",
    "renewable_energy", "wedding", "educational", "other",
]
_HOME_OWNERSHIP = ["RENT", "OWN", "MORTGAGE", "OTHER", "NONE", "ANY"]

_model_cache = None
_feature_info_cache = None
_model_feature_names: Optional[List[str]] = None

def _load_model():
    global _model_cache, _feature_info_cache, _model_feature_names
    if _model_cache is not None:
        return _model_cache, _feature_info_cache, _model_feature_names
    if not _MODEL_PATH.exists():
        raise FileNotFoundError(
            f"Model not found at {_MODEL_PATH}. "
            "Download xgb_model.pkl from "
            "https://github.com/johndmcmillin/credit-risk-model/tree/main/app "
            f"and place it in {MODEL_DIR}/"
        )
    _model_cache = joblib.load(_MODEL_PATH)
    _model_feature_names = list(_model_cache.get_booster().feature_names) if hasattr(_model_cache, "get_booster") else None
    if _FEATURE_INFO_PATH.exists():
        _feature_info_cache = pd.read_csv(_FEATURE_INFO_PATH)
    else:
        _feature_info_cache = pd.DataFrame()
    return _model_cache, _feature_info_cache, _model_feature_names

def _compute_installment(loan_amnt, term, int_rate):
    r = int_rate / 100.0 / 12.0
    n = term
    if r <= 0:
        return loan_amnt / n
    return loan_amnt * r * (1 + r) ** n / ((1 + r) ** n - 1)

def _parse_earliest_cr_line(raw):
    if not raw or pd.isna(raw):
        return np.nan
    for fmt in ("%Y-%m", "%b-%Y", "%Y-%m-%d", "%m/%Y", "%m-%Y"):
        try:
            dt = datetime.strptime(str(raw).strip(), fmt)
            return max((datetime.now() - dt).days / 30.44, 0)
        except ValueError:
            continue
    return np.nan

def _engineer_features(data):
    loan_amnt = float(data.get("loan_amnt", np.nan))
    term = int(data.get("term", 36))
    int_rate = float(data.get("int_rate", np.nan))
    annual_inc = float(data.get("annual_inc", np.nan))
    dti = float(data.get("dti", np.nan))
    fico = float(data.get("fico_score", np.nan))
    home = str(data.get("home_ownership", "")).upper()
    delinq = int(data.get("delinq_2yrs", 0))
    inq = int(data.get("inq_last_6mths", 0))
    pub = int(data.get("pub_rec", 0))
    cr_line = str(data.get("earliest_cr_line", ""))
    revol_util = float(data.get("revol_util", np.nan))
    revol_bal = float(data.get("revol_bal", np.nan))
    purpose = str(data.get("purpose", "debt_consolidation")).lower().replace(" ", "_")
    emp_len = float(data.get("emp_length", np.nan))
    total_acc = float(data.get("total_acc", np.nan))
    open_acc = float(data.get("open_acc", np.nan))
    mths_since_delinq = float(data.get("mths_since_last_delinq", np.nan))
    total_rev_hi_lim = float(data.get("total_rev_hi_lim", np.nan))
    verification = str(data.get("verification_status", "")).upper()

    installment = _compute_installment(loan_amnt, term, int_rate) if not np.isnan(loan_amnt) and not np.isnan(int_rate) else np.nan
    monthly_inc = annual_inc / 12.0 if not np.isnan(annual_inc) else np.nan

    feats = {}
    for key, val in [
        ("int_rate", int_rate), ("term", float(term)), ("loan_amnt", loan_amnt),
        ("annual_inc", annual_inc), ("dti", dti), ("fico_score", fico),
        ("delinq_2yrs", float(delinq)), ("inq_last_6mths", float(inq)),
        ("pub_rec", float(pub)), ("revol_util", revol_util),
        ("revol_bal", revol_bal), ("emp_length", emp_len),
        ("installment", installment), ("total_acc", total_acc),
        ("open_acc", open_acc), ("mths_since_last_delinq", mths_since_delinq),
        ("total_rev_hi_lim", total_rev_hi_lim),
    ]:
        feats[key] = val

    feats["renter"] = 1.0 if home == "RENT" else 0.0
    feats["pro_forma_dti"] = dti + (installment * 12.0 / annual_inc * 100.0) if not np.isnan(dti) and not np.isnan(installment) and not np.isnan(annual_inc) and annual_inc > 0 else np.nan
    feats["payment_to_income"] = installment / monthly_inc * 100.0 if not np.isnan(installment) and not np.isnan(monthly_inc) and monthly_inc > 0 else np.nan
    feats["loan_to_income"] = loan_amnt / annual_inc * 100.0 if not np.isnan(loan_amnt) and not np.isnan(annual_inc) and annual_inc > 0 else np.nan
    feats["revol_bal_to_income"] = revol_bal / annual_inc * 100.0 if not np.isnan(revol_bal) and not np.isnan(annual_inc) and annual_inc > 0 else np.nan
    feats["revol_util_pct_of_limit"] = revol_util / total_rev_hi_lim * 100.0 if not np.isnan(revol_util) and not np.isnan(total_rev_hi_lim) and total_rev_hi_lim > 0 else np.nan
    feats["credit_history_months"] = _parse_earliest_cr_line(cr_line)
    for p in _PURPOSES:
        feats[f"purpose_{p}"] = 1.0 if purpose == p else 0.0
    for ho in _HOME_OWNERSHIP:
        feats[f"home_ownership_{ho}"] = 1.0 if home == ho else 0.0
    for vs in ["VERIFIED", "SOURCE_VERIFIED", "NOT_VERIFIED"]:
        feats[f"verification_{vs}"] = 1.0 if verification == vs else 0.0
    return feats

def _probability_to_grade(prob):
    for grade, lo, hi in _GRADE_BANDS:
        if lo <= prob < hi:
            return grade, _RISK_LABELS[grade]
    return "G", "Critical"

class CreditRiskScoringTool(BaseTool):
    name: str = "US Credit Risk Scorer"
    description: str = (
        "Predicts loan default probability using a US-trained XGBoost model. "
        "Input: JSON with loan_amnt, term, int_rate, annual_inc, dti, fico_score, "
        "home_ownership, delinq_2yrs, inq_last_6mths, pub_rec, earliest_cr_line, "
        "revol_util, revol_bal, purpose, emp_length. "
        "Returns JSON with default_probability, implied_grade, risk_level, top_features."
    )

    def _run(self, query: str) -> str:
        json_str = query.strip()
        if "```" in json_str:
            json_str = json_str.split("```")[1]
            if json_str.startswith("json"):
                json_str = json_str[4:]
        start = json_str.find("{")
        end = json_str.rfind("}") + 1
        if start == -1 or end == 0:
            return json.dumps({"error": "No JSON found in input."})
        try:
            borrower = json.loads(json_str[start:end])
        except json.JSONDecodeError as e:
            return json.dumps({"error": f"Invalid JSON: {e}"})
        try:
            model, feature_info_df, model_features = _load_model()
        except (FileNotFoundError, Exception) as e:
            return json.dumps({"error": str(e)})

        all_features = _engineer_features(borrower)
        if model_features:
            for f in model_features:
                if f not in all_features:
                    all_features[f] = np.nan
            ordered = [all_features[f] for f in model_features]
        else:
            ordered = list(all_features.values())

        X = np.array(ordered).reshape(1, -1)
        try:
            prob = float(model.predict_proba(X)[0][1])
        except Exception:
            prob = float(model.predict(X)[0])

        grade, risk_level = _probability_to_grade(prob)

        top_features = []
        try:
            booster = model.get_booster()
            importance = booster.get_score(importance_type="gain")
            if not importance:
                importance = booster.get_score(importance_type="weight")
            total_gain = sum(importance.values()) or 1.0

            # Build f0→real-name map with three fallback levels
            resolved_names = (
                model_features
                or (list(model.feature_names_in_) if hasattr(model, "feature_names_in_") else None)
                or list(all_features.keys())
            )
            feature_name_map = {f"f{idx}": fname for idx, fname in enumerate(resolved_names)}

            for fname, gain in sorted(importance.items(), key=lambda x: x[1], reverse=True)[:8]:
                actual_name = feature_name_map.get(fname, fname)
                rationale = ""
                if feature_info_df is not None and not feature_info_df.empty:
                    match = feature_info_df[feature_info_df.iloc[:, 0].astype(str).str.lower() == actual_name.lower()]
                    if not match.empty and match.shape[1] > 1:
                        rationale = str(match.iloc[0, -1])
                top_features.append({
                    "feature": actual_name, "importance_pct": round(gain / total_gain * 100, 1),
                    "rationale": rationale, "value": borrower.get(actual_name, all_features.get(actual_name, "N/A")),
                })
        except Exception:
            pass

        return json.dumps({
            "default_probability": round(prob, 6),
            "default_probability_pct": f"{prob * 100:.2f}%",
            "implied_grade": grade, "risk_level": risk_level,
            "top_features": top_features,
        }, default=str)