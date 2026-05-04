# tools/US_mortgage_tool.py
"""
US Mortgage Analytics Tool - Fannie Mae Model Wrapper

This tool wraps the FannieMaeModelHub from models/fannie_mae_models/inference_helper.py
and provides a CrewAI tool interface for mortgage analytics using 15-20 key features.

Key Features (selected from models/fannie_mae_models/app.py DEFAULTS and CATEGORICAL_OPTIONS):
1. Borrower_Credit_Score_at_Origination
2. Original_Loan_to_Value_Ratio_LTV
3. Debt_To_Income_DTI
4. Original_UPB
5. Loan_Purpose
6. Property_Type
7. Occupancy_Status
8. Property_State
9. Amortization_Type
10. Original_Interest_Rate
11. First_Time_Home_Buyer_Indicator
12. Modification_Flag
13. Channel
14. Number_of_Borrowers
15. Original_Loan_Term

Usage:
    from tools.US_mortgage_tool import US_Mortgage_Analytics_Tool
    tool = US_Mortgage_Analytics_Tool()
    result = tool.run_mortgage_analytics(borrower_data)
"""

import os
import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List
from crewai.tools import BaseTool
import pandas as pd
import numpy as np

# Set up logging
logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

# Model directory configuration
MODEL_DIR = Path(
    os.getenv(
        "FANNIE_MAE_MODEL_DIR",
        str(Path(__file__).resolve().parent.parent / "models" / "fannie_mae_models"),
    )
)

# Key features for mortgage analytics (15 features - most important based on app.py)
KEY_FEATURES = [
    "Borrower_Credit_Score_at_Origination",
    "Original_Loan_to_Value_Ratio_LTV",
    "Debt_To_Income_DTI",
    "Original_UPB",
    "Loan_Purpose",
    "Property_Type",
    "Occupancy_Status",
    "Property_State",
    "Amortization_Type",
    "Original_Interest_Rate",
    "First_Time_Home_Buyer_Indicator",
    "Modification_Flag",
    "Channel",
    "Number_of_Borrowers",
    "Original_Loan_Term",
]

# Default values for features (from app.py DEFAULTS)
DEFAULTS = {
    "Original_Interest_Rate": 6.5,
    "Original_UPB": 250000.0,
    "Original_Loan_Term": 360,
    "Original_Loan_to_Value_Ratio_LTV": 80.0,
    "Debt_To_Income_DTI": 35.0,
    "Borrower_Credit_Score_at_Origination": 740,
    "Number_of_Borrowers": 2,
    "First_Time_Home_Buyer_Indicator": "N",
    "Modification_Flag": "N",
    "Channel": "Branch",
    "Loan_Purpose": "Purchase",
    "Property_Type": "Single Family",
    "Occupancy_Status": "Owner Occupied",
    "Property_State": "CA",
    "Amortization_Type": "Fixed",
}

# Categorical options (from app.py CATEGORICAL_OPTIONS)
CATEGORICAL_OPTIONS = {
    "Channel": ["Branch", "Correspondent", "Direct"],
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
}

# Model descriptions for output interpretation
MODEL_DESCRIPTIONS = {
    "credit_risk": {
        "title": "Credit Risk Assessment",
        "description": "Predicts whether a borrower will become delinquent (miss payments) or stay current on their mortgage.",
        "interpretation": {
            0: "CURRENT - The borrower is predicted to stay current on payments. Low delinquency risk.",
            1: "DELINQUENT - The borrower is predicted to miss payments. High delinquency risk.",
        },
    },
    "customer_segmentation": {
        "title": "Customer Segmentation",
        "description": "Groups borrowers into 8 behavioral segments using K-Means clustering.",
        "cluster_descriptions": {
            0: "Conventional Stable - Established borrowers with strong credit, standard loan terms.",
            1: "First-Time Homebuyers - Newer borrowers, often with lower credit scores and higher LTV.",
            2: "Investment Property Owners - Multi-property investors with higher loan balances.",
            3: "Refinance Candidates - Borrowers with good equity positions and improved credit.",
            4: "ARM Borrowers - Adjustable-rate mortgage holders vulnerable to rate resets.",
            5: "Government-Backed Borrowers - FHA/VA/government-insured loans with specific eligibility.",
            6: "Distressed/Modified Loans - Previously delinquent or modified loans under assistance plans.",
            7: "Premium Low-LTV - High-credit, low-LTV borrowers with significant equity.",
        },
    },
    "portfolio_risk": {
        "title": "Portfolio Risk Analysis",
        "description": "Assesses overall portfolio risk based on loan characteristics and borrower profiles.",
    },
}


class US_Mortgage_Analytics_Tool(BaseTool):
    """
    CrewAI tool for US Mortgage Analytics using Fannie Mae ML models.

    This tool wraps the FannieMaeModelHub and provides mortgage analytics
    using 15 key borrower/loan features.
    """

    name: str = "US_Mortgage_Analytics_Scorer"
    description: str = (
        "Run Fannie Mae mortgage analytics on borrower data. "
        "Input: JSON with borrower attributes (credit score, LTV, DTI, loan purpose, property type, etc.). "
        "Output: Credit risk prediction, customer segmentation, and portfolio risk assessment."
    )

    _hub_cache = None

    def _load_model_hub(self):
        """Lazy load the FannieMaeModelHub."""
        if self._hub_cache is not None:
            return self._hub_cache

        try:
            # Add the models directory to sys.path for local import
            import sys

            models_dir = str(MODEL_DIR.parent)  # Get parent of fannie_mae_models
            if models_dir not in sys.path:
                sys.path.insert(0, models_dir)

            # Import using the local path
            import importlib.util

            spec = importlib.util.spec_from_file_location(
                "inference_helper", MODEL_DIR / "inference_helper.py"
            )
            if spec is None or spec.loader is None:
                raise ImportError(
                    f"Could not load spec for {MODEL_DIR / 'inference_helper.py'}"
                )

            inference_module = importlib.util.module_from_spec(spec)
            sys.modules["inference_helper"] = inference_module
            spec.loader.exec_module(inference_module)

            FannieMaeModelHub = inference_module.FannieMaeModelHub
            self._hub_cache = FannieMaeModelHub(str(MODEL_DIR))
            log.info(f"Loaded FannieMaeModelHub from {MODEL_DIR}")
            return self._hub_cache
        except Exception as e:
            log.error(f"Failed to import FannieMaeModelHub: {e}")
            raise ImportError(
                "Fannie Mae models not available. "
                "Ensure models/fannie_mae_models/ directory exists with model artifacts."
            ) from e

    def _prepare_features(self, borrower_data: Dict[str, Any]) -> pd.DataFrame:
        """
        Prepare feature DataFrame from borrower data, filling missing values with defaults.

        Args:
            borrower_data: Dictionary with borrower attributes

        Returns:
            DataFrame with all required features with proper dtypes (numeric for model compatibility)
        """
        features = {}

        for feature in KEY_FEATURES:
            if feature in borrower_data:
                features[feature] = borrower_data[feature]
            elif feature in DEFAULTS:
                features[feature] = DEFAULTS[feature]
            else:
                # Try to find a reasonable default
                if "Credit" in feature or "Score" in feature:
                    features[feature] = 700  # Average credit score
                elif "LTV" in feature or "Value" in feature:
                    features[feature] = 80.0  # 80% LTV
                elif "DTI" in feature or "Income" in feature:
                    features[feature] = 35.0  # 35% DTI
                elif "UPB" in feature or "Loan" in feature and "Term" not in feature:
                    features[feature] = 250000.0  # $250k loan
                elif "Rate" in feature:
                    features[feature] = 6.5  # 6.5% interest rate
                elif "Term" in feature:
                    features[feature] = 360  # 30-year loan
                elif "Number" in feature or "Count" in feature:
                    features[feature] = 2  # 2 borrowers
                elif "Indicator" in feature or "Flag" in feature:
                    features[feature] = "N"  # No by default
                else:
                    features[feature] = "Unknown"

        df = pd.DataFrame([features])

        # Ensure categorical columns are properly typed for model compatibility
        # The Fannie Mae models expect categorical columns to be encodable
        categorical_features = [
            "Channel",
            "First_Time_Home_Buyer_Indicator",
            "Loan_Purpose",
            "Property_Type",
            "Occupancy_Status",
            "Property_State",
            "Modification_Flag",
            "Amortization_Type",
        ]

        for col in df.columns:
            if col in categorical_features:
                # Convert to string type first to ensure consistency, then the model's
                # _preprocess_supervised will encode using cat.codes
                if df[col].dtype == "object" or str(df[col].dtype).startswith("string"):
                    df[col] = df[col].astype(str).fillna("MISSING")
            else:
                # Ensure numeric columns are numeric
                if col not in [
                    "Borrower_Credit_Score_at_Origination",
                    "Number_of_Borrowers",
                    "Original_Loan_Term",
                ]:
                    # Try to convert to float
                    try:
                        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)
                    except (ValueError, TypeError):
                        df[col] = df[col].fillna(0.0)
                else:
                    # Integer columns
                    try:
                        df[col] = (
                            pd.to_numeric(df[col], errors="coerce")
                            .fillna(0)
                            .astype(int)
                        )
                    except (ValueError, TypeError):
                        df[col] = df[col].fillna(0)

        return df

    def _interpret_credit_risk(
        self, prediction: int, probability: float
    ) -> Dict[str, Any]:
        """Interpret credit risk prediction."""
        model_info = MODEL_DESCRIPTIONS["credit_risk"]

        return {
            "model": model_info["title"],
            "description": model_info["description"],
            "prediction": int(prediction),
            "prediction_label": model_info["interpretation"].get(
                int(prediction), "Unknown"
            ),
            "probability": float(probability),
            "risk_level": "HIGH" if prediction == 1 else "LOW",
            "confidence": 1.0 - abs(probability - 0.5) * 2,  # Simple confidence metric
        }

    def _interpret_segmentation(self, cluster: int) -> Dict[str, Any]:
        """Interpret customer segmentation prediction."""
        model_info = MODEL_DESCRIPTIONS["customer_segmentation"]

        return {
            "model": model_info["title"],
            "description": model_info["description"],
            "cluster": int(cluster),
            "cluster_label": model_info["cluster_descriptions"].get(
                int(cluster), "Unknown segment"
            ),
        }

    def _run_analytics(self, borrower_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Run mortgage analytics on borrower data.

        Args:
            borrower_data: Dictionary with borrower attributes

        Returns:
            Dictionary with analytics results
        """
        hub = self._load_model_hub()

        # Prepare features
        X_df = self._prepare_features(borrower_data)

        results = {
            "input_features": borrower_data,
            "processed_features": X_df.to_dict(orient="records")[0],
            "analyses": {},
        }

        # Run credit risk model
        try:
            credit_risk_model = hub.get_model("credit_risk")
            credit_preds = credit_risk_model.predict(X_df)
            credit_probs = credit_risk_model.predict_proba(X_df)

            results["analyses"]["credit_risk"] = self._interpret_credit_risk(
                credit_preds[0], credit_probs[0][1] if len(credit_probs[0]) > 1 else 0.0
            )
        except Exception as e:
            log.warning(f"Credit risk model failed: {e}")
            results["analyses"]["credit_risk"] = {
                "error": str(e),
                "status": "unavailable",
            }

        # Run customer segmentation model
        try:
            segmentation_model = hub.get_model("customer_segmentation")
            seg_preds = segmentation_model.predict(X_df)

            results["analyses"]["customer_segmentation"] = self._interpret_segmentation(
                seg_preds[0]
            )
        except Exception as e:
            log.warning(f"Segmentation model failed: {e}")
            results["analyses"]["customer_segmentation"] = {
                "error": str(e),
                "status": "unavailable",
            }

        # Run portfolio risk model (if available)
        try:
            portfolio_model = hub.get_model("portfolio_risk")
            portfolio_preds = portfolio_model.predict(X_df)

            results["analyses"]["portfolio_risk"] = {
                "model": MODEL_DESCRIPTIONS["portfolio_risk"]["title"],
                "description": MODEL_DESCRIPTIONS["portfolio_risk"]["description"],
                "prediction": (
                    float(portfolio_preds[0])
                    if hasattr(portfolio_preds[0], "__float__")
                    else str(portfolio_preds[0])
                ),
            }
        except Exception as e:
            log.warning(f"Portfolio risk model failed: {e}")
            results["analyses"]["portfolio_risk"] = {
                "error": str(e),
                "status": "unavailable",
            }

        # Add summary
        results["summary"] = self._generate_summary(results)

        return results

    def _generate_summary(self, results: Dict[str, Any]) -> Dict[str, Any]:
        """Generate a summary of the analytics results."""
        summary = {
            "overall_risk": "UNKNOWN",
            "key_findings": [],
            "recommendations": [],
        }

        analyses = results.get("analyses", {})

        # Credit risk assessment
        if "credit_risk" in analyses and "error" not in analyses["credit_risk"]:
            cr = analyses["credit_risk"]
            if cr.get("risk_level") == "HIGH":
                summary["overall_risk"] = "HIGH"
                summary["key_findings"].append(
                    f"Borrower shows high delinquency risk ({cr.get('probability', 0):.1%} probability)"
                )
                summary["recommendations"].append(
                    "Consider additional verification or higher down payment requirements"
                )
            else:
                summary["overall_risk"] = "LOW"
                summary["key_findings"].append(
                    f"Borrower shows low delinquency risk ({cr.get('probability', 0):.1%} probability)"
                )
                summary["recommendations"].append("Standard loan terms are appropriate")

        # Customer segmentation
        if (
            "customer_segmentation" in analyses
            and "error" not in analyses["customer_segmentation"]
        ):
            seg = analyses["customer_segmentation"]
            summary["key_findings"].append(
                f"Borrower belongs to segment: {seg.get('cluster_label', 'Unknown')}"
            )

            # Segment-specific recommendations
            cluster = seg.get("cluster", -1)
            if cluster == 1:  # First-Time Homebuyers
                summary["recommendations"].append(
                    "Consider offering first-time homebuyer education resources"
                )
            elif cluster == 3:  # Refinance Candidates
                summary["recommendations"].append(
                    "This borrower may be a good candidate for refinance outreach"
                )
            elif cluster == 6:  # Distressed/Modified Loans
                summary["recommendations"].append(
                    "Proactive loss mitigation and monitoring recommended"
                )

        return summary

    def _run(self, borrower_data: Any) -> str:
        """Run mortgage analytics on borrower data (required by BaseTool)."""
        try:
            # Check for list input - common error when agent confuses RAG results with borrower data
            if isinstance(borrower_data, list):
                return json.dumps(
                    {
                        "error": "Invalid input: Received a list instead of borrower data dictionary. "
                        "The US_Mortgage_Analytics_Scorer expects borrower JSON with fields like "
                        "credit score, LTV, DTI, etc. Do NOT pass RAG search results or tool output lists.",
                        "status": "error",
                        "hint": "Ensure you're calling this tool with borrower data, not search/policy results.",
                    }
                )

            # Parse input - handle both string and dict
            if isinstance(borrower_data, str):
                data = json.loads(borrower_data)
            elif isinstance(borrower_data, dict):
                data = borrower_data
            else:
                return json.dumps(
                    {
                        "error": f"Invalid input type: {type(borrower_data)}. Expected JSON string or dictionary.",
                        "status": "error",
                    }
                )

            # Additional check: if parsed JSON is a list
            if isinstance(data, list):
                return json.dumps(
                    {
                        "error": "Invalid input: Parsed JSON is a list, not a dictionary. "
                        "Expected borrower data with fields like Borrower_Credit_Score_at_Origination, "
                        "Original_Loan_to_Value_Ratio_LTV, etc.",
                        "status": "error",
                    }
                )

            # Run analytics
            results = self._run_analytics(data)

            return json.dumps(results, indent=2, default=str)

        except json.JSONDecodeError as e:
            return json.dumps(
                {
                    "error": f"Invalid JSON input: {e}",
                    "status": "error",
                }
            )
        except Exception as e:
            log.exception("Mortgage analytics failed")
            return json.dumps(
                {
                    "error": str(e),
                    "status": "error",
                    "traceback": str(e),
                }
            )

    def run(self, borrower_data: Any) -> str:
        """
        Public method to run mortgage analytics on borrower data.

        Args:
            borrower_data: JSON string or dictionary with borrower attributes

        Returns:
            JSON string with analytics results
        """
        return self._run(borrower_data)


# Convenience function for direct usage
def run_mortgage_analytics(borrower_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convenience function to run mortgage analytics.

    Args:
        borrower_data: Dictionary with borrower attributes

    Returns:
        Dictionary with analytics results
    """
    tool = US_Mortgage_Analytics_Tool()
    result_str = tool.run(json.dumps(borrower_data))
    return json.loads(result_str)


# Export for easy importing
__all__ = [
    "US_Mortgage_Analytics_Tool",
    "run_mortgage_analytics",
    "KEY_FEATURES",
    "DEFAULTS",
    "CATEGORICAL_OPTIONS",
]
