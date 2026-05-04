# config.py  —  Configuration, Constants, and Imports for Fixed Deposit Advisor
import os
import sys
import re
import sqlite3
import json
import markdown
import plotly.graph_objects as go
import numpy as np
import math
import random
import smtplib
import requests
import pandas as pd
import matplotlib
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import io
import streamlit as st
from pathlib import Path
from dotenv import load_dotenv

# Lazy import of streamlit_echarts to avoid component registration issues at module load time
# Import is done inside functions that need it
from datetime import datetime, timedelta, date
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# =============================================================================
# ADD PARENT DIRECTORY TO PATH FOR PROJECT-LEVEL IMPORTS
# This ensures that modules like 'utils', 'crews', 'tools' can be imported
# =============================================================================
_PARENT_DIR = Path(__file__).resolve().parent.parent
if str(_PARENT_DIR) not in sys.path:
    sys.path.insert(0, str(_PARENT_DIR))

# =============================================================================
# EARLY DEFINITIONS - Must be defined before any imports to avoid circular deps
# =============================================================================
MODEL_DIR = _PARENT_DIR / "models" / "credit_risk"
DB_PATH = _PARENT_DIR / "bank_poc.db"

# ML model functions are now called by agents internally via CreditRiskScoringTool
from tools.config import fetch_country_data
from tools.search_tool import set_search_region

from crews import run_crew
from langchain_nvidia_ai_endpoints import ChatNVIDIA
from utils.report_parser import extract_structured_summary
from .json_utils import extract_json_balanced


# =============================================================================
# DARK LUXURY THEME (CreditWise CSS Theme)
# =============================================================================
DARK_LUXURY_CSS = """
/* CreditWise Dark Luxury Theme */
@import url('https://fonts.googleapis.com/css2?family=Playfair+Display:wght@400;500;600;700&family=DM+Sans:wght@400;500;600;700&family=DM+Mono:wght@400;500&display=swap');

:root {
    --bg-primary: #080d18;
    --bg-secondary: #0e1525;
    --bg-card: #111827;
    --bg-card-hover: #1f2937;
    --border-color: #1f2937;
    --border-highlight: #2d3748;
    --text-primary: #f8fafc;
    --text-secondary: #94a3b8;
    --text-muted: #64748b;
    --accent-gold: #c9a84c;
    --accent-gold-hover: #b8963e;
    --accent-teal: #2dd4bf;
    --accent-teal-hover: #26b8a3;
    --accent-blue: #3b82f6;
    --accent-red: #ef4444;
    --accent-green: #10b981;
    --accent-purple: #8b5cf6;
    --shadow-sm: 0 1px 2px 0 rgba(0, 0, 0, 0.05);
    --shadow-md: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
    --shadow-lg: 0 10px 15px -3px rgba(0, 0, 0, 0.3);
    --shadow-xl: 0 20px 25px -5px rgba(0, 0, 0, 0.4);
}

/* Base Streamlit Overrides */
.stApp {
    background: linear-gradient(135deg, var(--bg-primary) 0%, var(--bg-secondary) 100%);
    color: var(--text-primary);
    font-family: 'DM Sans', sans-serif;
}

/* Headers */
h1, h2, h3, h4, h5, h6 {
    font-family: 'Playfair Display', serif;
    color: var(--text-primary);
    font-weight: 600;
}

/* Cards */
.css-1r6slb0, .stMarkdown, .stDataFrame, .stPlotlyChart {
    background: var(--bg-card);
    border: 1px solid var(--border-color);
    border-radius: 12px;
    box-shadow: var(--shadow-md);
}

/* Buttons */
.stButton > button {
    background: linear-gradient(135deg, var(--accent-gold) 0%, var(--accent-teal) 100%);
    color: var(--bg-primary);
    font-family: 'DM Sans', sans-serif;
    font-weight: 600;
    border: none;
    border-radius: 8px;
    padding: 12px 24px;
    transition: all 0.3s ease;
    box-shadow: var(--shadow-md);
}

.stButton > button:hover {
    background: linear-gradient(135deg, var(--accent-gold-hover) 0%, var(--accent-teal-hover) 100%);
    box-shadow: var(--shadow-lg);
    transform: translateY(-2px);
}

/* Input Fields */
.stTextInput > div > div > input, .stNumberInput > div > div > input {
    background: var(--bg-secondary);
    border: 1px solid var(--border-color);
    color: var(--text-primary);
    border-radius: 8px;
    padding: 10px 14px;
}

.stTextInput > div > div > input:focus, .stNumberInput > div > div > input:focus {
    border-color: var(--accent-gold);
    box-shadow: 0 0 0 2px rgba(201, 168, 76, 0.2);
}

/* Select Boxes */
.stSelectbox > div > div {
    background: var(--bg-secondary);
    border: 1px solid var(--border-color);
    color: var(--text-primary);
    border-radius: 8px;
}

/* Slider */
.stSlider > div > div > div > div {
    background: var(--accent-gold);
}

/* Metrics */
.css-ffhzg2 .stMetric {
    background: var(--bg-card);
    border: 1px solid var(--border-color);
    border-radius: 12px;
    padding: 16px;
    box-shadow: var(--shadow-sm);
}

/* Expander */
.stExpander {
    background: var(--bg-card);
    border: 1px solid var(--border-color);
    border-radius: 8px;
    margin: 8px 0;
}

.stExpander > div {
    padding: 16px;
}

/* Alert Boxes */
.stAlert, .stInfo, .stWarning, .stError {
    border-radius: 8px;
    padding: 12px 16px;
}

/* Tables */
.stDataFrame {
    border-radius: 12px;
    overflow: hidden;
}

.stDataFrame > div {
    background: var(--bg-card);
    border: 1px solid var(--border-color);
}

/* Sidebar */
.css-1d391kg {
    background: var(--bg-secondary);
    border-right: 1px solid var(--border-color);
}

/* Divider */
.stMarkdown hr {
    border-color: var(--border-color);
}

/* Custom Card Component Class */
.creditwise-card {
    background: var(--bg-card);
    border: 1px solid var(--border-color);
    border-radius: 16px;
    padding: 24px;
    box-shadow: var(--shadow-md);
    transition: all 0.3s ease;
}

.creditwise-card:hover {
    border-color: var(--accent-gold);
    box-shadow: var(--shadow-lg);
    transform: translateY(-4px);
}

/* Result Ring Animation */
@keyframes pulse-ring {
    0% { box-shadow: 0 0 0 0 rgba(201, 168, 76, 0.4); }
    70% { box-shadow: 0 0 0 10px rgba(201, 168, 76, 0); }
    100% { box-shadow: 0 0 0 0 rgba(201, 168, 76, 0); }
}

.result-ring {
    animation: pulse-ring 2s infinite;
}

/* Gradient Text */
.gradient-text-gold {
    background: linear-gradient(135deg, var(--accent-gold) 0%, var(--accent-teal) 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
}

.gradient-text-blue {
    background: linear-gradient(135deg, var(--accent-blue) 0%, var(--accent-purple) 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
}
"""


def apply_dark_luxury_theme():
    """Apply the CreditWise dark luxury theme to Streamlit app."""
    st.markdown(f"<style>{DARK_LUXURY_CSS}</style>", unsafe_allow_html=True)


matplotlib.use("Agg")

# =============================================================================
# PAGE CONFIG — must be the very first Streamlit call
# =============================================================================
st.set_page_config(
    page_title="Fixed Deposit Advisor",
    layout="wide",
    initial_sidebar_state="expanded",
)

# =============================================================================
# LANGFUSE INTEGRATION
# =============================================================================
try:
    from langfuse_instrumentation import instrument_crewai, get_langfuse_client
    from langfuse import propagate_attributes
    from langfuse_evaluator import evaluate_crew_output_async
except ImportError as _import_err:
    st.error(
        f"Missing dependency: {_import_err}. "
        "Ensure langfuse_instrumentation.py, langfuse_evaluator.py, and the "
        "'langfuse' / 'langchain' packages are installed."
    )
    st.stop()

load_dotenv()
instrument_crewai()
langfuse = get_langfuse_client()

# =============================================================================
# DATABASE & CONFIG (DB_PATH already defined above)
# =============================================================================

RISK_COLORS = {
    "LOW": ("#D1FAE5", "#065F46"),
    "MEDIUM": ("#FEF3C7", "#92400E"),
    "HIGH": ("#FEE2E2", "#991B1B"),
    "CRITICAL": ("#7F1D1D", "#FECACA"),
}
DECISION_COLORS = {
    "PASS": ("#D1FAE5", "#065F46"),
    "FAIL": ("#FEE2E2", "#991B1B"),
    "REVIEW": ("#FEF3C7", "#92400E"),
    "APPROVE": ("#D1FAE5", "#065F46"),
    "REJECT": ("#FEE2E2", "#991B1B"),
}
