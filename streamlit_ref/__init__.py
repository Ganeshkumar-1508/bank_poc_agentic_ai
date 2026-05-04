# UI Package for Fixed Deposit Advisor
"""
This package contains all the UI components and modules for the Fixed Deposit Advisor application.

Modules:
- config: Configuration, constants, and imports
- database: Database helper functions
- calculators: Financial calculators
- helpers: General helper functions
- email_utils: Email utilities
- validators: LLM decision parser and validators
- renderers: Parse and render helpers
- tab_fd_advisor: FD Advisor tab
- tab_new_account: New Account tab
- tab_credit_risk: Credit Risk tab
- tab_financial_news: Financial News tab
- tab_mortgage_analytics: Mortgage Analytics tab
- sidebar: Sidebar components
"""

from .json_utils import extract_json_balanced
from .config import (
    DB_PATH,
    RISK_COLORS,
    DECISION_COLORS,
)

from .database import (
    get_db_connection,
    db_query,
    db_execute,
    save_loan_application,
    get_loan_applications,
    update_loan_status,
    upsert_user_session,
    get_linked_user,
    get_all_deposits,
    get_portfolio_summary,
    get_all_aml_cases,
    get_aml_case,
    save_aml_case,
    log_audit,
    get_transactions,
    save_rate_alert,
    get_rate_alerts,
    toggle_alert,
    get_catalog_rates,
    get_session_artifacts,
    save_laddering_plan,
    get_laddering_plans,
    load_fd_table,
)

from .calculators import (
    calc_compound,
    calc_premature_withdrawal,
    calc_fd_ladder,
    inflation_adjusted_return,
)

from .helpers import (
    detect_user_region,
    init_session_state,
    get_currency_symbol,
    reset_session,
    run_crew_with_langfuse,
    get_dynamic_kyc_docs,
    clean_response,
    append_assistant,
    _cr_model_available,
    _cr_predict,
)

from .email_utils import (
    send_digest_email,
    _md_to_html,
    _build_email_html,
)

from .validators import (
    _parse_llm_decision,
    _sanitize_grade_in_text,
    _sanitize_thresholds_in_text,
    _validate_decision_rationale,
)

from .renderers import (
    format_news_for_display,
    clean_news_for_table,
    parse_projection_table,
    render_bar_charts,
    export_analysis_data,
    export_report_content,
    risk_badge,
    decision_badge,
)

from .tab_fd_advisor import render_fd_advisor_tab
from .tab_new_account import render_new_account_tab
from .tab_credit_risk import render_credit_risk_tab
from .tab_financial_news import render_financial_news_tab
from .tab_mortgage_analytics import render_mortgage_analytics_tab
from .sidebar import render_sidebar

__all__ = [
    # Config
    "DB_PATH",
    "RISK_COLORS",
    "DECISION_COLORS",
    "extract_json_balanced",
    # Database
    "get_db_connection",
    "db_query",
    "db_execute",
    "save_loan_application",
    "get_loan_applications",
    "update_loan_status",
    "upsert_user_session",
    "get_linked_user",
    "get_all_deposits",
    "get_portfolio_summary",
    "get_all_aml_cases",
    "get_aml_case",
    "save_aml_case",
    "log_audit",
    "get_transactions",
    "save_rate_alert",
    "get_rate_alerts",
    "toggle_alert",
    "get_catalog_rates",
    "get_session_artifacts",
    "save_laddering_plan",
    "get_laddering_plans",
    "load_fd_table",
    # Calculators
    "calc_compound",
    "calc_premature_withdrawal",
    "calc_fd_ladder",
    "inflation_adjusted_return",
    # Helpers
    "detect_user_region",
    "init_session_state",
    "get_currency_symbol",
    "reset_session",
    "run_crew_with_langfuse",
    "get_dynamic_kyc_docs",
    "get_crews",
    "clean_response",
    "append_assistant",
    "_cr_model_available",
    "_cr_predict",
    # Email utils
    "send_digest_email",
    "_md_to_html",
    "_build_email_html",
    # Validators
    "_parse_llm_decision",
    "_sanitize_grade_in_text",
    "_sanitize_thresholds_in_text",
    "_validate_decision_rationale",
    # Renderers
    "format_news_for_display",
    "clean_news_for_table",
    "parse_projection_table",
    "render_bar_charts",
    "export_analysis_data",
    "export_report_content",
    "risk_badge",
    "decision_badge",
    # Tab renderers
    "render_fd_advisor_tab",
    "render_new_account_tab",
    "render_credit_risk_tab",
    "render_financial_news_tab",
    "render_mortgage_analytics_tab",
    "render_sidebar",
]
