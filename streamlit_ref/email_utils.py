# email_utils.py  —  Email Utilities for Fixed Deposit Advisor
import os
import smtplib
import pandas as pd
import markdown
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart


# =============================================================================
# EMAIL DIGEST
# =============================================================================
def send_digest_email(recipient: str, maturing_df: pd.DataFrame) -> bool:
    smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER", "")
    smtp_pass = os.getenv("SMTP_PASSWORD", "")
    if not smtp_user or not smtp_pass:
        return False
    rows = ""
    for _, r in maturing_df.iterrows():
        rows += (
            f"<tr><td>{r.get('bank_name','')}</td>"
            f"<td>{r.get('product_type','')}</td>"
            f"<td>{r.get('initial_amount', 0):,.0f}</td>"
            f"<td>{r.get('maturity_date','')}</td></tr>"
        )
    html = f"""<html><body>
    <h2>📅 FD Maturity Digest — Next 30 Days</h2>
    <table border='1' cellpadding='6' style='border-collapse:collapse'>
    <tr><th>Bank</th><th>Type</th><th>Amount</th><th>Maturity Date</th></tr>
    {rows}
    </table>
    <p>Sent by Fixed Deposit Advisor</p></body></html>"""
    try:
        import time
        import uuid
        msg = MIMEMultipart("alternative")
        msg["Subject"] = "Your FD Maturity Digest — Next 30 Days"
        msg["From"] = smtp_user
        msg["To"] = recipient
        # Add essential headers for better deliverability
        msg["MIME-Version"] = "1.0"
        msg["Date"] = time.strftime("%a, %d %b %Y %H:%M:%S %z")
        message_id = f"<{uuid.uuid4().hex}@{smtp_host}>"
        msg["Message-ID"] = message_id
        msg["Reply-To"] = smtp_user
        msg["X-Mailer"] = "BankPOC-FDAdvisor/1.0"
        msg.attach(MIMEText(html, "html"))
        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.sendmail(smtp_user, recipient, msg.as_string())
        return True
    except Exception:
        return False


# =============================================================================
# MARKDOWN TO HTML CONVERTER
# =============================================================================
def _md_to_html(md_text: str) -> str:
    """Convert Markdown to clean HTML with inline styles for email compatibility."""
    if not md_text:
        return ""
    # Strip markdown code fences if present
    text = md_text.strip()
    for fence in ("```markdown", "```html", "```"):
        if fence in text:
            text = text.split(fence)[-1].split("```")[0].strip()
            break
    # Use markdown library for proper conversion
    html = markdown.markdown(text, extensions=["tables", "fenced_code", "nl2br"])
    # Wrap in styled container for email
    html = f"""<div style="font-family:Arial,Helvetica,sans-serif;line-height:1.7;color:#333;font-size:14px;">
{html}
</div>"""
    return html


# =============================================================================
# BUILD EMAIL HTML
# =============================================================================
def _build_email_html(
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
    llm_summary_html="",
):
    """Build a complete, professional HTML email for loan decisions."""
    summary_section = ""
    if llm_summary_html:
        summary_section = f"""
        <hr style="margin:24px 0;border:none;border-top:2px solid #E2E8F0;">
        <h2 style="color:#1E3A8A;font-size:18px;margin:0 0 12px 0;">
            📋 Detailed Borrower Summary
        </h2>
        {llm_summary_html}
        """
    conditions_html = "".join(
        f'<li style="margin-bottom:6px;">{c}</li>' for c in conditions
    )
    next_steps_html = "".join(
        f'<li style="margin-bottom:6px;">{s}</li>' for s in next_steps
    )
    return f"""
<html><head><meta charset="utf-8"></head>
<body style="font-family:Arial,Helvetica,sans-serif;color:#333;background:#F8FAFC;margin:0;padding:20px;">
<div style="max-width:680px;margin:0 auto;background:#FFFFFF;border-radius:12px;box-shadow:0 1px 3px rgba(0,0,0,0.1);overflow:hidden;">

    <!-- Header -->
    <div style="background:{rec_color};padding:24px 28px;">
        <h1 style="margin:0;color:#FFFFFF;font-size:22px;font-weight:700;">
            {rec_icon} Loan Application — {rec_decision}
        </h1>
        <p style="margin:6px 0 0 0;color:rgba(255,255,255,0.85);font-size:13px;">
            Generated on {datetime.now().strftime('%B %d, %Y at %H:%M')}
        </p>
    </div>

    <!-- Decision Summary -->
    <div style="padding:24px 28px;">
        <table style="width:100%;border-collapse:collapse;font-size:14px;">
            <tr style="background:#F1F5F9;">
                <td style="padding:10px 12px;border-bottom:1px solid #E2E8F0;font-weight:600;width:40%;">Decision</td>
                <td style="padding:10px 12px;border-bottom:1px solid #E2E8F0;font-size:16px;font-weight:700;color:{rec_color};">{rec_decision}</td>
            </tr>
            <tr>
                <td style="padding:10px 12px;border-bottom:1px solid #E2E8F0;font-weight:600;">Grade</td>
                <td style="padding:10px 12px;border-bottom:1px solid #E2E8F0;"><strong>{grade}</strong></td>
            </tr>
            <tr style="background:#F1F5F9;">
                <td style="padding:10px 12px;border-bottom:1px solid #E2E8F0;font-weight:600;">Default Probability</td>
                <td style="padding:10px 12px;border-bottom:1px solid #E2E8F0;">{prob_pct}</td>
            </tr>
            <tr>
                <td style="padding:10px 12px;border-bottom:1px solid #E2E8F0;font-weight:600;">Risk Level</td>
                <td style="padding:10px 12px;border-bottom:1px solid #E2E8F0;">{risk_level}</td>
            </tr>
            <tr style="background:#F1F5F9;">
                <td style="padding:10px 12px;border-bottom:1px solid #E2E8F0;font-weight:600;">Loan Amount</td>
                <td style="padding:10px 12px;border-bottom:1px solid #E2E8F0;">${borrower.get('loan_amnt', 0):,}</td>
            </tr>
            <tr>
                <td style="padding:10px 12px;border-bottom:1px solid #E2E8F0;font-weight:600;">Term</td>
                <td style="padding:10px 12px;border-bottom:1px solid #E2E8F0;">{borrower.get('term', 0)} months</td>
            </tr>
            <tr style="background:#F1F5F9;">
                <td style="padding:10px 12px;border-bottom:1px solid #E2E8F0;font-weight:600;">Interest Rate</td>
                <td style="padding:10px 12px;border-bottom:1px solid #E2E8F0;">{borrower.get('int_rate', 0):.2f}%</td>
            </tr>
            <tr>
                <td style="padding:10px 12px;border-bottom:1px solid #E2E8F0;font-weight:600;">FICO Score</td>
                <td style="padding:10px 12px;border-bottom:1px solid #E2E8F0;">{borrower.get('fico_score', 0)}</td>
            </tr>
            <tr style="background:#F1F5F9;">
                <td style="padding:10px 12px;border-bottom:1px solid #E2E8F0;font-weight:600;">DTI Ratio</td>
                <td style="padding:10px 12px;border-bottom:1px solid #E2E8F0;">{borrower.get('dti', 0):.1f}%</td>
            </tr>
            <tr>
                <td style="padding:10px 12px;border-bottom:1px solid #E2E8F0;font-weight:600;">Annual Income</td>
                <td style="padding:10px 12px;border-bottom:1px solid #E2E8F0;">${borrower.get('annual_inc', 0):,}</td>
            </tr>
        </table>

        <!-- Rationale -->
        <h3 style="color:#1E3A8A;font-size:16px;margin:24px 0 8px 0;border-bottom:2px solid #E2E8F0;padding-bottom:6px;">Rationale</h3>
        <p style="margin:0;color:#475569;line-height:1.6;">{rec_text}</p>

        <!-- Conditions -->
        <h3 style="color:#1E3A8A;font-size:16px;margin:24px 0 8px 0;border-bottom:2px solid #E2E8F0;padding-bottom:6px;">Conditions</h3>
        <ul style="margin:0;padding-left:20px;color:#475569;line-height:1.6;">{conditions_html}</ul>

        <!-- Next Steps -->
        <h3 style="color:#1E3A8A;font-size:16px;margin:24px 0 8px 0;border-bottom:2px solid #E2E8F0;padding-bottom:6px;">Next Steps</h3>
        <ul style="margin:0;padding-left:20px;color:#475569;line-height:1.6;">{next_steps_html}</ul>

        {summary_section}
    </div>

    <!-- Footer -->
    <div style="background:#F1F5F9;padding:16px 28px;font-size:12px;color:#94A3B8;text-align:center;">
        This decision was generated by our AI-powered credit risk assessment system using an XGBoost model trained on US Lending Club data (2007-2018).<br>
        For questions, please contact your loan officer or reply to this email.
    </div>
</div>
</body></html>"""
