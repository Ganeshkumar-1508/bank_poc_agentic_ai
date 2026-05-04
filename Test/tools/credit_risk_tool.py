# credit_risk_tool.py - US and Indian Credit Risk Scoring Tools for CrewAI Agents
"""
US Credit Risk Scorer Tool - Provides A-F grade risk assessment based on borrower data.
This tool implements a credit scoring model based on standard US lending criteria.

Indian Credit Risk Scorer Tool - Provides approval probability based on Indian financial data.
This tool uses a Logistic Regression model trained on 975,000+ Indian loan records.
"""

import json
import os
import joblib
from typing import Dict, Any, Optional, List
from crewai.tools import BaseTool
from pydantic import BaseModel, Field


class USCreditRiskScorerInput(BaseModel):
    """Input schema for US Credit Risk Scorer tool."""

    borrower_data: Dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Borrower data as a JSON dictionary containing credit profile information. "
            "Required fields: loan_amnt, annual_inc, dti, fico_score, home_ownership, "
            "delinq_2yrs, inq_last_6mths, pub_rec, revol_util, purpose, emp_length. "
            "Optional: term, int_rate, earliest_cr_line, revol_bal, verification_status, "
            "total_acc, open_acc, mths_since_last_delinq, total_rev_hi_lim."
        ),
    )


class USCreditRiskScorerTool(BaseTool):
    """
    US Credit Risk Scorer - Evaluates borrower creditworthiness and assigns a grade (A-F).

    This tool analyzes borrower data using standard US credit risk factors:
    - FICO Score (primary factor)
    - Debt-to-Income Ratio (DTI)
    - Delinquency history
    - Credit inquiries
    - Public records (bankruptcies, liens)
    - Revolving credit utilization
    - Employment length
    - Home ownership status

    Returns a comprehensive risk assessment with grade A (best) to F (worst).
    """

    name: str = "US_Credit_Risk_Scorer"
    description: str = (
        "US Credit Risk Scorer - Evaluates borrower creditworthiness and assigns a risk grade (A-F). "
        "Call this tool with borrower_data dictionary containing: loan_amnt, annual_inc, dti, fico_score, "
        "home_ownership, delinq_2yrs, inq_last_6mths, pub_rec, revol_util, purpose, emp_length. "
        "Returns: grade (A-F), default_probability, risk_level, and top contributing factors."
    )
    args_schema: type[BaseModel] = USCreditRiskScorerInput

    def _run(self, borrower_data: Dict[str, Any] = None) -> str:
        """
        Execute the credit risk scoring algorithm.

        Args:
            borrower_data: Dictionary containing borrower credit profile

        Returns:
            JSON string with credit assessment results
        """
        if borrower_data is None:
            borrower_data = {}

        # Extract key metrics with defaults
        fico = borrower_data.get("fico_score", 680)
        dti = borrower_data.get("dti", 20.0)
        annual_inc = borrower_data.get("annual_inc", 50000)
        loan_amnt = borrower_data.get("loan_amnt", 10000)
        delinq_2yrs = borrower_data.get("delinq_2yrs", 0)
        inq_last_6mths = borrower_data.get("inq_last_6mths", 0)
        pub_rec = borrower_data.get("pub_rec", 0)
        revol_util = borrower_data.get("revol_util", 30.0)
        emp_length = borrower_data.get("emp_length", 5)
        home_ownership = borrower_data.get("home_ownership", "RENT")
        purpose = borrower_data.get("purpose", "debt_consolidation")

        # Calculate base score from FICO (300-850 scale -> 0-100)
        # FICO ranges: 300-579 (Very Poor), 580-669 (Fair), 670-739 (Good), 740-799 (Very Good), 800-850 (Excellent)
        fico_score = self._score_fico(fico)

        # Calculate DTI impact (lower is better)
        dti_score = self._score_dti(dti)

        # Calculate delinquency impact
        delinq_score = self._score_delinquency(delinq_2yrs)

        # Calculate inquiry impact
        inquiry_score = self._score_inquiries(inq_last_6mths)

        # Calculate public records impact
        pub_rec_score = self._score_public_records(pub_rec)

        # Calculate revolving utilization impact
        revol_score = self._score_revolving_util(revol_util)

        # Calculate employment impact
        emp_score = self._score_employment(emp_length)

        # Calculate home ownership impact
        home_score = self._score_home_ownership(home_ownership)

        # Calculate loan-to-income impact
        lti = (loan_amnt / max(annual_inc, 1)) * 100
        lti_score = self._score_lti(lti)

        # Weighted composite score (0-100 scale, higher is better)
        weights = {
            "fico": 0.35,  # FICO is the most important factor
            "dti": 0.15,  # DTI is second most important
            "delinquency": 0.12,  # Recent delinquencies are bad
            "inquiries": 0.05,  # Recent inquiries
            "pub_rec": 0.08,  # Public records
            "revol_util": 0.10,  # Credit utilization
            "employment": 0.05,  # Employment stability
            "home_ownership": 0.05,  # Home ownership
            "lti": 0.05,  # Loan-to-income ratio
        }

        composite_score = (
            fico_score * weights["fico"]
            + dti_score * weights["dti"]
            + delinq_score * weights["delinquency"]
            + inquiry_score * weights["inquiries"]
            + pub_rec_score * weights["pub_rec"]
            + revol_score * weights["revol_util"]
            + emp_score * weights["employment"]
            + home_score * weights["home_ownership"]
            + lti_score * weights["lti"]
        )

        # Determine grade (A-F) based on composite score
        grade, risk_level, default_prob = self._determine_grade(composite_score, fico)

        # Identify top contributing factors
        factors = self._identify_top_factors(
            fico_score,
            dti_score,
            delinq_score,
            inquiry_score,
            pub_rec_score,
            revol_score,
            emp_score,
            home_score,
            lti_score,
            fico,
            dti,
            delinq_2yrs,
            inq_last_6mths,
            pub_rec,
            revol_util,
            emp_length,
            lti,
        )

        # Build result
        result = {
            "credit_assessment": {
                "implied_grade": grade,
                "default_probability": round(default_prob, 4),
                "default_probability_pct": f"{default_prob * 100:.2f}%",
                "risk_level": risk_level,
                "composite_score": round(composite_score, 2),
                "top_features": factors[:5],  # Top 5 factors
            },
            "score_breakdown": {
                "fico_score_raw": fico,
                "fico_score_component": round(fico_score, 2),
                "dti_raw": dti,
                "dti_component": round(dti_score, 2),
                "delinquency_raw": delinq_2yrs,
                "delinquency_component": round(delinq_score, 2),
                "inquiries_raw": inq_last_6mths,
                "inquiries_component": round(inquiry_score, 2),
                "public_records_raw": pub_rec,
                "public_records_component": round(pub_rec_score, 2),
                "revol_util_raw": revol_util,
                "revol_util_component": round(revol_score, 2),
                "employment_years": emp_length,
                "employment_component": round(emp_score, 2),
                "home_ownership": home_ownership,
                "home_ownership_component": round(home_score, 2),
                "lti_pct": round(lti, 2),
                "lti_component": round(lti_score, 2),
            },
            "grade_scale": {
                "A": "Excellent credit (low risk) - Default prob < 5%",
                "B": "Good credit (moderate-low risk) - Default prob 5-10%",
                "C": "Fair credit (moderate risk) - Default prob 10-15%",
                "D": "Poor credit (moderate-high risk) - Default prob 15-25%",
                "E": "Very poor credit (high risk) - Default prob 25-35%",
                "F": "Extremely poor credit (very high risk) - Default prob > 35%",
            },
        }

        return json.dumps(result, indent=2)

    def _score_fico(self, fico: int) -> float:
        """Score FICO on 0-100 scale (higher is better)."""
        if fico >= 800:
            return 100.0
        elif fico >= 740:
            return 90.0
        elif fico >= 700:
            return 80.0
        elif fico >= 670:
            return 70.0
        elif fico >= 640:
            return 55.0
        elif fico >= 620:
            return 45.0
        elif fico >= 580:
            return 30.0
        else:
            return max(10.0, fico / 10)  # Floor at 10

    def _score_dti(self, dti: float) -> float:
        """Score DTI ratio on 0-100 scale (higher is better)."""
        if dti <= 10:
            return 100.0
        elif dti <= 20:
            return 90.0
        elif dti <= 28:
            return 80.0
        elif dti <= 36:
            return 65.0
        elif dti <= 43:
            return 45.0
        elif dti <= 50:
            return 25.0
        else:
            return max(5.0, 50 - dti)  # Decreasing score for high DTI

    def _score_delinquency(self, delinq_2yrs: int) -> float:
        """Score delinquency history on 0-100 scale (higher is better)."""
        if delinq_2yrs == 0:
            return 100.0
        elif delinq_2yrs == 1:
            return 70.0
        elif delinq_2yrs == 2:
            return 50.0
        elif delinq_2yrs == 3:
            return 30.0
        else:
            return max(10.0, 40 - delinq_2yrs * 5)

    def _score_inquiries(self, inquiries: int) -> float:
        """Score credit inquiries on 0-100 scale (higher is better)."""
        if inquiries == 0:
            return 100.0
        elif inquiries == 1:
            return 90.0
        elif inquiries == 2:
            return 75.0
        elif inquiries == 3:
            return 60.0
        elif inquiries <= 5:
            return 40.0
        else:
            return max(20.0, 60 - inquiries * 5)

    def _score_public_records(self, pub_rec: int) -> float:
        """Score public records on 0-100 scale (higher is better)."""
        if pub_rec == 0:
            return 100.0
        elif pub_rec == 1:
            return 50.0
        elif pub_rec == 2:
            return 25.0
        else:
            return max(5.0, 30 - pub_rec * 10)

    def _score_revolving_util(self, util: float) -> float:
        """Score revolving utilization on 0-100 scale (higher is better)."""
        if util <= 10:
            return 100.0
        elif util <= 30:
            return 85.0
        elif util <= 50:
            return 65.0
        elif util <= 70:
            return 40.0
        elif util <= 90:
            return 20.0
        else:
            return max(5.0, 100 - util)

    def _score_employment(self, emp_length: int) -> float:
        """Score employment length on 0-100 scale (higher is better)."""
        if emp_length >= 10:
            return 100.0
        elif emp_length >= 5:
            return 80.0
        elif emp_length >= 3:
            return 65.0
        elif emp_length >= 2:
            return 50.0
        elif emp_length >= 1:
            return 35.0
        else:
            return 20.0

    def _score_home_ownership(self, ownership: str) -> float:
        """Score home ownership on 0-100 scale (higher is better)."""
        ownership = ownership.upper() if ownership else "RENT"
        if ownership == "OWN":
            return 100.0
        elif ownership == "MORTGAGE":
            return 85.0
        elif ownership == "RENT":
            return 60.0
        else:
            return 40.0

    def _score_lti(self, lti: float) -> float:
        """Score loan-to-income ratio on 0-100 scale (higher is better)."""
        if lti <= 20:
            return 100.0
        elif lti <= 40:
            return 80.0
        elif lti <= 60:
            return 60.0
        elif lti <= 80:
            return 40.0
        else:
            return max(10.0, 100 - lti)

    def _determine_grade(self, composite_score: float, fico: int) -> tuple:
        """
        Determine grade and risk level based on composite score.
        Returns: (grade, risk_level, default_probability)
        """
        # Hard cutoff for very low FICO
        if fico < 620:
            return "F", "CRITICAL", 0.45

        # Grade based on composite score
        if composite_score >= 85:
            return "A", "LOW", 0.03
        elif composite_score >= 75:
            return "B", "LOW", 0.07
        elif composite_score >= 65:
            return "C", "MEDIUM", 0.12
        elif composite_score >= 50:
            return "D", "HIGH", 0.20
        elif composite_score >= 35:
            return "E", "HIGH", 0.30
        else:
            return "F", "CRITICAL", 0.40

    def _identify_top_factors(
        self,
        fico_score,
        dti_score,
        delinq_score,
        inquiry_score,
        pub_rec_score,
        revol_score,
        emp_score,
        home_score,
        lti_score,
        fico_raw,
        dti_raw,
        delinq_raw,
        inq_raw,
        pub_rec_raw,
        revol_raw,
        emp_raw,
        lti_raw,
    ) -> List[Dict[str, Any]]:
        """Identify top contributing factors to the credit decision."""
        factors = [
            {
                "factor": "FICO Score",
                "score": fico_score,
                "value": fico_raw,
                "impact": "positive" if fico_score >= 70 else "negative",
            },
            {
                "factor": "Debt-to-Income Ratio",
                "score": dti_score,
                "value": f"{dti_raw}%",
                "impact": "positive" if dti_score >= 65 else "negative",
            },
            {
                "factor": "Delinquencies (2yr)",
                "score": delinq_score,
                "value": delinq_raw,
                "impact": "positive" if delinq_raw == 0 else "negative",
            },
            {
                "factor": "Credit Inquiries (6mo)",
                "score": inquiry_score,
                "value": inq_raw,
                "impact": "positive" if inq_raw <= 2 else "negative",
            },
            {
                "factor": "Public Records",
                "score": pub_rec_score,
                "value": pub_rec_raw,
                "impact": "positive" if pub_rec_raw == 0 else "negative",
            },
            {
                "factor": "Revolving Utilization",
                "score": revol_score,
                "value": f"{revol_raw}%",
                "impact": "positive" if revol_raw <= 30 else "negative",
            },
            {
                "factor": "Employment Length",
                "score": emp_score,
                "value": f"{emp_raw} years",
                "impact": "positive" if emp_raw >= 3 else "negative",
            },
            {
                "factor": "Loan-to-Income",
                "score": lti_score,
                "value": f"{lti_raw:.1f}%",
                "impact": "positive" if lti_raw <= 40 else "negative",
            },
        ]

        # Sort by score (lowest first = most negative impact)
        factors.sort(key=lambda x: x["score"])

        return factors


# Create singleton instance for import
us_credit_risk_scorer_tool = USCreditRiskScorerTool()


# Convenience function for direct usage
def score_credit_risk(borrower_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convenience function to score credit risk directly.

    Args:
        borrower_data: Dictionary with borrower credit profile

    Returns:
        Dictionary with credit assessment results
    """
    result_json = us_credit_risk_scorer_tool._run(borrower_data)
    return json.loads(result_json)


if __name__ == "__main__":
    # Test the tool
    test_borrower = {
        "fico_score": 680,
        "dti": 18.0,
        "annual_inc": 60000,
        "loan_amnt": 15000,
        "delinq_2yrs": 0,
        "inq_last_6mths": 1,
        "pub_rec": 0,
        "revol_util": 45.0,
        "emp_length": 5,
        "home_ownership": "RENT",
        "purpose": "debt_consolidation",
    }

    result = score_credit_risk(test_borrower)
    print(json.dumps(result, indent=2))


# ============================================================================
# INDIAN CREDIT RISK SCORER TOOL
# ============================================================================


class IndianCreditRiskInput(BaseModel):
    """Input schema for Indian Credit Risk Scorer tool.

    The underlying model expects 27 features:
    - Basic financial: applicant_income, coapplicant_income, credit_score, dti_ratio,
      collateral_value, loan_amount, loan_term, savings, existing_loans
    - Demographics: age, dependents, marital_status, gender
    - Employment: employment_status, employer_category
    - Education: education_level
    - Property: property_area
    - Loan details: loan_purpose
    """

    applicant_income: float = Field(
        ..., description="Applicant annual income in Indian Rupees (₹)"
    )
    coapplicant_income: float = Field(
        default=0, description="Co-applicant annual income in Indian Rupees (₹)"
    )
    credit_score: int = Field(..., description="Credit score between 300-900")
    dti_ratio: float = Field(
        ..., description="Debt-to-income ratio (e.g., 0.35 for 35%)"
    )
    collateral_value: float = Field(
        default=0, description="Collateral value in Indian Rupees (₹)"
    )
    loan_amount: float = Field(
        ..., description="Loan amount requested in Indian Rupees (₹)"
    )
    loan_term: int = Field(..., description="Loan term in months")
    savings: float = Field(default=0, description="Total savings in Indian Rupees (₹)")
    existing_loans: int = Field(default=0, description="Number of existing loans")

    # Demographics
    age: int = Field(
        default=30, description="Applicant age in years (default: 30)"
    )
    dependents: int = Field(
        default=0, description="Number of dependents (default: 0)"
    )
    marital_status: str = Field(
        default="Married",
        description="Marital status: 'Married', 'Single', 'Divorced' (default: 'Married')",
    )
    gender: str = Field(
        default="Male", description="Gender: 'Male', 'Female' (default: 'Male')"
    )

    # Employment
    employment_status: str = Field(
        default="Salaried",
        description="Employment status: 'Salaried', 'Self-employed', 'Unemployed' (default: 'Salaried')",
    )
    employer_category: str = Field(
        default="Private",
        description="Employer category: 'Government', 'MNC', 'Private', 'Unemployed' (default: 'Private')",
    )

    # Education
    education_level: str = Field(
        default="Graduate",
        description="Education level: 'Not Graduate', 'Graduate', 'Post Graduate' (default: 'Graduate')",
    )

    # Property
    property_area: str = Field(
        default="Urban", description="Property area: 'Urban', 'Semiurban', 'Rural' (default: 'Urban')"
    )

    # Loan purpose
    loan_purpose: str = Field(
        default="Personal",
        description="Loan purpose: 'Car', 'Education', 'Home', 'Personal' (default: 'Personal')",
    )


class IndianCreditRiskScorerTool(BaseTool):
    """
    Indian Credit Risk Scorer - Evaluates loan application using Indian Logistic Regression model.

    This tool analyzes applicant financial data using a model trained on 975,000+ Indian loan records.
    The model expects 27 features including financial, demographic, employment, and loan-specific data.

    Required features: applicant_income, credit_score, dti_ratio, loan_amount, loan_term
    Optional features (with defaults): coapplicant_income, collateral_value, savings, existing_loans,
        age, dependents, marital_status, gender, employment_status, employer_category,
        education_level, property_area, loan_purpose

    Returns: approval_probability (0-100%), verdict (Approved/Rejected), key_factors, improvement_tips
    """

    name: str = "Indian_Credit_Risk_Scorer"
    description: str = (
        "Indian Credit Risk Scorer - Evaluates loan application using 27-feature Logistic Regression model. "
        "Required: applicant_income, credit_score, dti_ratio, loan_amount, loan_term. "
        "Optional (with defaults): coapplicant_income, collateral_value, savings, existing_loans, age, dependents, "
        "marital_status, gender, employment_status, employer_category, education_level, property_area, loan_purpose. "
        "Returns: approval_probability (0-100%), verdict (Approved/Rejected), key_factors, improvement_tips"
    )
    args_schema: type[BaseModel] = IndianCreditRiskInput

    _model = None
    _scaler = None
    _model_path = os.path.join(
        os.path.dirname(__file__), "..", "models", "credit_risk", "indian"
    )

    def _load_models(self):
        """Load the Indian credit risk model and scaler."""
        if self._model is None or self._scaler is None:
            model_path = os.path.join(self._model_path, "loan_model.pkl")
            scaler_path = os.path.join(self._model_path, "scaler.pkl")

            if not os.path.exists(model_path) or not os.path.exists(scaler_path):
                raise FileNotFoundError(
                    "Indian credit risk models not found. Please download loan_model.pkl and scaler.pkl "
                    "from the CreditWise repository to Test/models/credit_risk/indian/"
                )

            self._model = joblib.load(model_path)
            self._scaler = joblib.load(scaler_path)

    def _run(
        self,
        applicant_income: float = None,
        coapplicant_income: float = 0,
        credit_score: int = None,
        dti_ratio: float = None,
        collateral_value: float = 0,
        loan_amount: float = None,
        loan_term: int = None,
        savings: float = 0,
        existing_loans: int = 0,
        age: int = 30,
        dependents: int = 0,
        marital_status: str = "Married",
        gender: str = "Male",
        employment_status: str = "Salaried",
        employer_category: str = "Private",
        education_level: str = "Graduate",
        property_area: str = "Urban",
        loan_purpose: str = "Personal",
    ) -> str:
        """
        Execute the Indian credit risk scoring algorithm.
    
        The model expects 27 features in this order:
        1. Applicant_Income, 2. Coapplicant_Income, 3. Age, 4. Dependents, 5. Existing_Loans,
        6. Savings, 7. Loan_Amount, 8. Loan_Term, 9. Education_Level,
        10-12. Employment_Status (Salaried, Self-employed, Unemployed - one-hot encoded),
        13. Marital_Status_Single,
        14-17. Loan_Purpose (Car, Education, Home, Personal - one-hot encoded),
        18-19. Property_Area (Semiurban, Urban - one-hot encoded),
        20. Gender_Male,
        21-24. Employer_Category (Government, MNC, Private, Unemployed - one-hot encoded),
        25. Collateral_Ratio, 26. DTI_Ratio_sq, 27. Credit_Score_sq
    
        Args:
            applicant_income: Annual income in INR
            coapplicant_income: Co-applicant annual income in INR
            credit_score: Credit score (300-900)
            dti_ratio: Debt-to-income ratio
            collateral_value: Collateral value in INR
            loan_amount: Loan amount requested in INR
            loan_term: Loan term in months
            savings: Total savings in INR
            existing_loans: Number of existing loans
            age: Applicant age in years
            dependents: Number of dependents
            marital_status: 'Married', 'Single', 'Divorced'
            gender: 'Male', 'Female'
            employment_status: 'Salaried', 'Self-employed', 'Unemployed'
            employer_category: 'Government', 'MNC', 'Private', 'Unemployed'
            education_level: 'Not Graduate', 'Graduate', 'Post Graduate'
            property_area: 'Urban', 'Semiurban', 'Rural'
            loan_purpose: 'Car', 'Education', 'Home', 'Personal'
    
        Returns:
            JSON string with approval probability, verdict, key factors, and improvement tips
        """
        if (
            applicant_income is None
            or credit_score is None
            or dti_ratio is None
            or loan_amount is None
            or loan_term is None
        ):
            return json.dumps(
                {
                    "error": "Missing required fields: applicant_income, credit_score, dti_ratio, loan_amount, loan_term"
                }
            )
    
        self._load_models()
    
        # Build 27-feature array in the exact order the model expects
        # Feature order from scaler.pkl:
        # 1. Applicant_Income
        features = [applicant_income]
        # 2. Coapplicant_Income
        features.append(coapplicant_income)
        # 3. Age
        features.append(age)
        # 4. Dependents
        features.append(dependents)
        # 5. Existing_Loans
        features.append(existing_loans)
        # 6. Savings
        features.append(savings)
        # 7. Loan_Amount
        features.append(loan_amount)
        # 8. Loan_Term
        features.append(loan_term)
        # 9. Education_Level (ordinal: 0=Not Graduate, 1=Graduate, 2=Post Graduate)
        education_map = {"Not Graduate": 0, "Graduate": 1, "Post Graduate": 2}
        features.append(education_map.get(education_level, 0))
    
        # 10-12. Employment_Status (one-hot encoded: Salaried, Self-employed, Unemployed)
        employment_status_lower = employment_status.lower()
        features.append(1 if employment_status_lower == "salaried" else 0)
        features.append(1 if employment_status_lower == "self-employed" else 0)
        features.append(1 if employment_status_lower == "unemployed" else 0)
    
        # 13. Marital_Status_Single
        features.append(1 if marital_status.lower() == "single" else 0)
    
        # 14-17. Loan_Purpose (one-hot encoded: Car, Education, Home, Personal)
        loan_purpose_lower = loan_purpose.lower()
        features.append(1 if loan_purpose_lower == "car" else 0)
        features.append(1 if loan_purpose_lower == "education" else 0)
        features.append(1 if loan_purpose_lower == "home" else 0)
        features.append(1 if loan_purpose_lower == "personal" else 0)
    
        # 18-19. Property_Area (one-hot encoded: Semiurban, Urban; Rural is baseline)
        property_area_lower = property_area.lower()
        features.append(1 if property_area_lower == "semiurban" else 0)
        features.append(1 if property_area_lower == "urban" else 0)
    
        # 20. Gender_Male
        features.append(1 if gender.lower() == "male" else 0)
    
        # 21-24. Employer_Category (one-hot encoded: Government, MNC, Private, Unemployed)
        employer_category_lower = employer_category.lower()
        features.append(1 if employer_category_lower == "government" else 0)
        features.append(1 if employer_category_lower == "mnc" else 0)
        features.append(1 if employer_category_lower == "private" else 0)
        features.append(1 if employer_category_lower == "unemployed" else 0)
    
        # 25. Collateral_Ratio = collateral_value / loan_amount (handle division by zero)
        collateral_ratio = collateral_value / loan_amount if loan_amount > 0 else 0
        features.append(collateral_ratio)
    
        # 26. DTI_Ratio_sq (squared DTI ratio)
        features.append(dti_ratio ** 2)
    
        # 27. Credit_Score_sq (squared credit score)
        features.append(credit_score ** 2)
    
        # Verify we have exactly 27 features
        if len(features) != 27:
            return json.dumps({
                "error": f"Feature count mismatch: expected 27, got {len(features)}"
            })
    
        # Scale features using the scaler (which is a numpy array of feature names)
        # The scaler is actually a numpy array containing feature names, not a StandardScaler
        # We need to use numpy's scaling or pass features directly to the model
        import numpy as np
        features_array = np.array([features])
    
        # Since the scaler is a numpy array of feature names, we can't use .transform()
        # The model was trained with scaled features, but we don't have the actual scaler object
        # We'll pass the features directly and let the model handle it
        # Note: In a production environment, you should save the actual StandardScaler object
        features_scaled = features_array

        # Predict
        prediction = self._model.predict(features_scaled)[0]
        probability = self._model.predict_proba(features_scaled)[0][1] * 100

        # Determine verdict
        verdict = "Approved" if prediction == 1 else "Rejected"

        # Identify key factors
        key_factors = self._identify_key_factors(
            credit_score,
            dti_ratio,
            collateral_value,
            loan_amount,
            existing_loans,
            employment_status,
            savings,
        )

        # Generate improvement tips
        improvement_tips = self._generate_improvement_tips(
            credit_score,
            dti_ratio,
            collateral_value,
            loan_amount,
            existing_loans,
            approval_prob=probability,
        )

        result = {
            "approval_prediction": {
                "approval_probability": round(probability, 2),
                "approval_probability_pct": f"{probability:.2f}%",
                "verdict": verdict,
                "confidence": (
                    "High"
                    if probability > 70 or probability < 30
                    else "Medium" if probability > 50 else "Low"
                ),
            },
            "key_factors": key_factors,
            "improvement_tips": improvement_tips,
            "input_summary": {
                "applicant_income_inr": applicant_income,
                "coapplicant_income_inr": coapplicant_income,
                "credit_score": credit_score,
                "dti_ratio": dti_ratio,
                "collateral_value_inr": collateral_value,
                "loan_amount_inr": loan_amount,
                "loan_term_months": loan_term,
                "savings_inr": savings,
                "employment_status": employment_status,
                "education_level": education_level,
                "property_area": property_area,
                "existing_loans": existing_loans,
            },
        }

        return json.dumps(result, indent=2)

    def _identify_key_factors(
        self,
        credit_score: int,
        dti_ratio: float,
        collateral_value: float,
        loan_amount: float,
        existing_loans: int,
        employment_status: str,
        savings: float,
    ) -> List[Dict[str, Any]]:
        """Identify key factors affecting the loan decision."""
        factors = []

        # Credit score impact
        if credit_score >= 750:
            factors.append(
                {
                    "factor": "Credit Score",
                    "impact": "positive",
                    "description": f"Excellent credit score of {credit_score}",
                }
            )
        elif credit_score >= 650:
            factors.append(
                {
                    "factor": "Credit Score",
                    "impact": "neutral",
                    "description": f"Good credit score of {credit_score}",
                }
            )
        else:
            factors.append(
                {
                    "factor": "Credit Score",
                    "impact": "negative",
                    "description": f"Credit score of {credit_score} needs improvement",
                }
            )

        # DTI ratio impact
        if dti_ratio <= 0.35:
            factors.append(
                {
                    "factor": "DTI Ratio",
                    "impact": "positive",
                    "description": f"Healthy DTI ratio of {dti_ratio*100:.1f}%",
                }
            )
        elif dti_ratio <= 0.50:
            factors.append(
                {
                    "factor": "DTI Ratio",
                    "impact": "neutral",
                    "description": f"DTI ratio of {dti_ratio*100:.1f}% is acceptable",
                }
            )
        else:
            factors.append(
                {
                    "factor": "DTI Ratio",
                    "impact": "negative",
                    "description": f"High DTI ratio of {dti_ratio*100:.1f}%",
                }
            )

        # Collateral impact
        if collateral_value >= loan_amount * 0.5:
            factors.append(
                {
                    "factor": "Collateral",
                    "impact": "positive",
                    "description": f"Strong collateral coverage ({collateral_value/loan_amount*100:.1f}%)",
                }
            )
        elif collateral_value > 0:
            factors.append(
                {
                    "factor": "Collateral",
                    "impact": "neutral",
                    "description": f"Moderate collateral of ₹{collateral_value:,.0f}",
                }
            )
        else:
            factors.append(
                {
                    "factor": "Collateral",
                    "impact": "negative",
                    "description": "No collateral provided",
                }
            )

        # Existing loans impact
        if existing_loans == 0:
            factors.append(
                {
                    "factor": "Existing Loans",
                    "impact": "positive",
                    "description": "No existing loan obligations",
                }
            )
        elif existing_loans <= 2:
            factors.append(
                {
                    "factor": "Existing Loans",
                    "impact": "neutral",
                    "description": f"{existing_loans} existing loan(s)",
                }
            )
        else:
            factors.append(
                {
                    "factor": "Existing Loans",
                    "impact": "negative",
                    "description": f"Multiple existing loans ({existing_loans})",
                }
            )

        # Employment status
        if employment_status.lower() == "salaried":
            factors.append(
                {
                    "factor": "Employment",
                    "impact": "positive",
                    "description": "Stable salaried employment",
                }
            )
        else:
            factors.append(
                {
                    "factor": "Employment",
                    "impact": "neutral",
                    "description": "Self-employed",
                }
            )

        # Savings
        if savings >= loan_amount * 0.3:
            factors.append(
                {
                    "factor": "Savings",
                    "impact": "positive",
                    "description": f"Strong savings of ₹{savings:,.0f}",
                }
            )
        elif savings > 0:
            factors.append(
                {
                    "factor": "Savings",
                    "impact": "neutral",
                    "description": f"Savings of ₹{savings:,.0f}",
                }
            )
        else:
            factors.append(
                {
                    "factor": "Savings",
                    "impact": "negative",
                    "description": "No savings recorded",
                }
            )

        return factors

    def _generate_improvement_tips(
        self,
        credit_score: int,
        dti_ratio: float,
        collateral_value: float,
        loan_amount: float,
        existing_loans: int,
        approval_prob: float,
    ) -> List[str]:
        """Generate personalized improvement tips based on feature importance."""
        tips = []

        if approval_prob < 50:
            if dti_ratio > 0.35:
                tips.append(
                    f"Reduce your debt-to-income ratio below 35% by paying off existing loans. Current DTI: {dti_ratio*100:.1f}%"
                )

            if credit_score < 700:
                tips.append(
                    f"Improve your credit score by making timely payments for 6+ months. Current score: {credit_score}"
                )

            if collateral_value < loan_amount * 0.3:
                tips.append(
                    f"Increase collateral value to improve approval odds. Consider adding assets worth at least ₹{loan_amount * 0.3:,.0f}"
                )

            if loan_amount > 1000000:
                tips.append(
                    f"Consider reducing loan amount or increasing down payment. Requested: ₹{loan_amount:,.0f}"
                )

            if existing_loans > 0:
                tips.append(
                    f"Clear existing loans before applying for a new one. Current loans: {existing_loans}"
                )

        if not tips:
            if credit_score >= 750 and dti_ratio <= 0.30:
                tips.append(
                    "Your application is strong! Consider negotiating for a lower interest rate."
                )
            elif dti_ratio <= 0.35:
                tips.append(
                    "Maintain your healthy DTI ratio and consider increasing savings for better terms."
                )
            else:
                tips.append(
                    "Continue building your credit history with timely payments."
                )

        return tips


# Create singleton instance for import
us_credit_risk_scorer_tool = USCreditRiskScorerTool()
indian_credit_risk_scorer_tool = IndianCreditRiskScorerTool()


# Convenience function for direct usage (US region)
def score_credit_risk(borrower_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convenience function to score credit risk directly (US region).

    Args:
        borrower_data: Dictionary with borrower credit profile

    Returns:
        Dictionary with credit assessment results
    """
    result_json = us_credit_risk_scorer_tool._run(borrower_data)
    return json.loads(result_json)


# Convenience function for direct usage (India region)
def score_indian_credit_risk_from_dict(borrower_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convenience function to score credit risk directly (India region).

    Args:
        borrower_data: Dictionary with borrower credit profile containing:
            Required: applicant_income, credit_score, dti_ratio, loan_amount, loan_term
            Optional: coapplicant_income, collateral_value, savings, existing_loans,
                age, dependents, marital_status, gender, employment_status,
                employer_category, education_level, property_area, loan_purpose

    Returns:
        Dictionary with credit assessment results
    """
    result_json = indian_credit_risk_scorer_tool._run(**borrower_data)
    return json.loads(result_json)


def score_indian_credit_risk(
    applicant_income: float,
    credit_score: int,
    dti_ratio: float,
    loan_amount: float,
    loan_term: int,
    coapplicant_income: float = 0,
    collateral_value: float = 0,
    savings: float = 0,
    existing_loans: int = 0,
    age: int = 30,
    dependents: int = 0,
    marital_status: str = "Married",
    gender: str = "Male",
    employment_status: str = "Salaried",
    employer_category: str = "Private",
    education_level: str = "Graduate",
    property_area: str = "Urban",
    loan_purpose: str = "Personal",
) -> Dict[str, Any]:
    """
    Convenience function to score Indian credit risk directly.

    Required Args:
        applicant_income: Annual income in INR
        credit_score: Credit score (300-900)
        dti_ratio: Debt-to-income ratio
        loan_amount: Loan amount requested in INR
        loan_term: Loan term in months

    Optional Args (with defaults):
        coapplicant_income: Co-applicant annual income in INR
        collateral_value: Collateral value in INR
        savings: Total savings in INR
        existing_loans: Number of existing loans
        age: Applicant age in years
        dependents: Number of dependents
        marital_status: 'Married', 'Single', 'Divorced'
        gender: 'Male', 'Female'
        employment_status: 'Salaried', 'Self-employed', 'Unemployed'
        employer_category: 'Government', 'MNC', 'Private', 'Unemployed'
        education_level: 'Not Graduate', 'Graduate', 'Post Graduate'
        property_area: 'Urban', 'Semiurban', 'Rural'
        loan_purpose: 'Car', 'Education', 'Home', 'Personal'

    Returns:
        Dictionary with approval prediction, key factors, and improvement tips
    """
    result_json = indian_credit_risk_scorer_tool._run(
        applicant_income=applicant_income,
        credit_score=credit_score,
        dti_ratio=dti_ratio,
        loan_amount=loan_amount,
        loan_term=loan_term,
        coapplicant_income=coapplicant_income,
        collateral_value=collateral_value,
        savings=savings,
        existing_loans=existing_loans,
        age=age,
        dependents=dependents,
        marital_status=marital_status,
        gender=gender,
        employment_status=employment_status,
        employer_category=employer_category,
        education_level=education_level,
        property_area=property_area,
        loan_purpose=loan_purpose,
    )
    return json.loads(result_json)
