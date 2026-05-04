"""
FD/TD Certificate Generation Utilities

This module provides functionality to generate FD certificates as PDF files
using ReportLab.
"""

import os
import logging
from datetime import datetime
from decimal import Decimal
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm, inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from django.conf import settings
from django.core.files.storage import default_storage

logger = logging.getLogger(__name__)


def generate_fd_certificate(fd_instance, output_dir=None):
    """
    Generate an FD certificate PDF for the given FixedDeposit instance.

    Args:
        fd_instance: FixedDeposit model instance
        output_dir: Optional directory path for output. Defaults to MEDIA_ROOT/fd_certificates

    Returns:
        str: Path to the generated PDF file (relative to MEDIA_ROOT)
    """
    try:
        # Create output directory
        if output_dir is None:
            output_dir = os.path.join(settings.MEDIA_ROOT, 'fd_certificates')
        
        os.makedirs(output_dir, exist_ok=True)
        
        # Generate filename
        filename = f"FD_Certificate_{fd_instance.fd_id}.pdf"
        filepath = os.path.join(output_dir, filename)
        
        # Create PDF document
        doc = SimpleDocTemplate(
            filepath,
            pagesize=landscape(A4),
            rightMargin=72,
            leftMargin=72,
            topMargin=72,
            bottomMargin=72
        )
        
        # Build certificate content
        elements = []
        styles = getSampleStyleSheet()
        
        # Custom styles
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=28,
            textColor=colors.HexColor('#1a1a2e'),
            spaceAfter=30,
            alignment=TA_CENTER,
            fontName='Helvetica-Bold'
        )
        
        subtitle_style = ParagraphStyle(
            'Subtitle',
            parent=styles['Heading2'],
            fontSize=16,
            textColor=colors.HexColor('#c9a84c'),
            spaceAfter=20,
            alignment=TA_CENTER,
            fontName='Helvetica'
        )
        
        label_style = ParagraphStyle(
            'Label',
            parent=styles['Normal'],
            fontSize=11,
            textColor=colors.HexColor('#4a4a6a'),
            fontName='Helvetica-Bold'
        )
        
        value_style = ParagraphStyle(
            'Value',
            parent=styles['Normal'],
            fontSize=11,
            textColor=colors.HexColor('#1a1a2e'),
            fontName='Helvetica'
        )
        
        # Header - Bank Logo/Name placeholder
        elements.append(Paragraph("BANK POC - FIXED DEPOSIT CERTIFICATE", title_style))
        elements.append(Paragraph("Certificate of Deposit", subtitle_style))
        elements.append(Spacer(1, 20))
        
        # Certificate border/table container
        data = []
        
        # Certificate number row
        data.append([
            Paragraph("<b>Certificate Number:</b>", label_style),
            Paragraph(fd_instance.fd_id, value_style)
        ])
        data.append([Spacer(inch, 0.2)])
        
        # Issue date row
        issue_date = fd_instance.created_at.strftime('%B %d, %Y')
        data.append([
            Paragraph("<b>Date of Issue:</b>", label_style),
            Paragraph(issue_date, value_style)
        ])
        data.append([Spacer(inch, 0.2)])
        
        # Main FD details table
        fd_details = [
            [Paragraph("<b>Depositor Name:</b>", label_style), 
             Paragraph(fd_instance.customer_name or "N/A", value_style)],
            [Paragraph("<b>Bank Name:</b>", label_style), 
             Paragraph(fd_instance.bank_name, value_style)],
            [Paragraph("<b>Deposit Amount:</b>", label_style), 
             Paragraph(f"₹{float(fd_instance.amount):,}", value_style)],
            [Paragraph("<b>Interest Rate:</b>", label_style), 
             Paragraph(f"{float(fd_instance.rate)}% per annum", value_style)],
            [Paragraph("<b>Tenure:</b>", label_style), 
             Paragraph(f"{fd_instance.tenure_months} months", value_style)],
            [Paragraph("<b>Start Date:</b>", label_style), 
             Paragraph(fd_instance.start_date.strftime('%B %d, %Y'), value_style)],
            [Paragraph("<b>Maturity Date:</b>", label_style), 
             Paragraph(fd_instance.maturity_date.strftime('%B %d, %Y'), value_style)],
            [Paragraph("<b>Maturity Amount:</b>", label_style), 
             Paragraph(f"₹{float(fd_instance.maturity_amount):,}", value_style)],
            [Paragraph("<b>Interest Earned:</b>", label_style), 
             Paragraph(f"₹{float(fd_instance.interest_earned):,}", value_style)],
        ]
        
        data.extend(fd_details)
        data.append([Spacer(inch, 0.2)])
        
        # Additional features row
        features = []
        if fd_instance.senior_citizen:
            features.append("Senior Citizen Benefits Applied")
        if fd_instance.loan_against_fd:
            features.append("Loan Against FD Available")
        if fd_instance.auto_renewal:
            features.append("Auto-Renewal Enabled")
        
        features_text = ", ".join(features) if features else "Standard Terms Apply"
        data.append([
            Paragraph("<b>Features:</b>", label_style),
            Paragraph(features_text, value_style)
        ])
        
        # Create table with styling
        table = Table(data, colWidths=[10*cm, 14*cm])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#f5f5f5')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.HexColor('#1a1a2e')),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 12),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#ffffff')),
            ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#e0e0e0')),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#fafafa')]),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('FONTSIZE', (0, 1), (-1, -1), 11),
            ('BOTTOMPADDING', (0, 1), (-1, -1), 10),
            ('TOPPADDING', (0, 1), (-1, -1), 10),
        ]))
        
        elements.append(table)
        elements.append(Spacer(1, 30))
        
        # Terms and conditions section
        elements.append(Paragraph("<b>Terms and Conditions:</b>", label_style))
        elements.append(Spacer(1, 10))
        
        terms = [
            "1. This certificate is issued as proof of the Fixed Deposit mentioned above.",
            "2. The deposit will mature on the maturity date specified. Early withdrawal may incur penalties.",
            "3. Interest is compounded monthly and payable at maturity.",
            "4. Loan against this FD is available up to 90% of the deposit amount.",
            "5. In case of premature closure, interest will be paid at the rate applicable for the period the deposit remained with us.",
            "6. This certificate is non-transferable and is issued in the name of the depositor.",
            "7. All disputes are subject to the jurisdiction of the bank's local courts.",
        ]
        
        for term in terms:
            elements.append(Paragraph(f"&bull; {term}", styles['Normal']))
            elements.append(Spacer(1, 5))
        
        elements.append(Spacer(1, 20))
        
        # Signature section
        sig_data = [
            [
                Paragraph("<br/><br/>_________________________<br/>Authorized Signatory", styles['Normal']),
                Spacer(1, 20),
                Paragraph("<br/><br/>_________________________<br/>Bank Manager", styles['Normal'])
            ]
        ]
        
        sig_table = Table(sig_data, colWidths=[12*cm, 12*cm])
        sig_table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('TOPPADDING', (0, 0), (-1, -1), 20),
        ]))
        
        elements.append(sig_table)
        
        # Footer
        elements.append(Spacer(1, 30))
        footer_style = ParagraphStyle(
            'Footer',
            parent=styles['Normal'],
            fontSize=9,
            textColor=colors.HexColor('#888888'),
            alignment=TA_CENTER,
            fontName='Helvetica-Oblique'
        )
        elements.append(Paragraph(
            f"Generated on: {datetime.now().strftime('%B %d, %Y at %I:%M %p')} | "
            "This is a computer-generated certificate and does not require a physical signature.",
            footer_style
        ))
        
        # Build PDF
        doc.build(elements)
        
        # Get relative path for storage
        if str(settings.MEDIA_ROOT) in filepath:
            relative_path = filepath.replace(str(settings.MEDIA_ROOT) + os.sep, '')
        else:
            relative_path = f"fd_certificates/{filename}"
        
        logger.info(f"FD certificate generated: {relative_path}")
        return relative_path
        
    except Exception as e:
        logger.error(f"Error generating FD certificate: {e}")
        import traceback
        traceback.print_exc()
        return None


def format_currency(amount, currency='INR'):
    """
    Format amount as currency string.
    
    Args:
        amount: Decimal or float amount
        currency: Currency code (INR or USD)
    
    Returns:
        str: Formatted currency string
    """
    if currency == 'USD':
        return f"${float(amount):,.2f}"
    else:
        return f"₹{float(amount):,.2f}"
