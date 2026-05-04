"""
Mortgage Report Generation Utilities

This module provides functionality to generate mortgage analytics reports as PDF files
using ReportLab, following the CreditWise Dark Luxury Theme.
"""

import os
import logging
import re
from datetime import datetime
from decimal import Decimal
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm, inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.pdfgen import canvas
from reportlab.lib.fonts import addMapping

from django.conf import settings

logger = logging.getLogger(__name__)


def generate_mortgage_report_pdf(borrower_data, analysis_data=None):
    """
    Generate a mortgage analytics report PDF.
    
    Args:
        borrower_data: Dictionary with borrower and loan details
        analysis_data: Optional dictionary with analysis results (markdown, structured data)
        
    Returns:
        BytesIO buffer containing the PDF content
    """
    try:
        # Create in-memory buffer
        buffer = BytesIO()
        
        # Create PDF document
        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            rightMargin=72,
            leftMargin=72,
            topMargin=72,
            bottomMargin=72
        )
        
        # Build report content
        elements = []
        styles = getSampleStyleSheet()
        
        # Custom styles matching CreditWise Dark Luxury Theme
        # Note: Using standard fonts that are available in ReportLab
        title_style = ParagraphStyle(
            'MortgageTitle',
            parent=styles['Heading1'],
            fontSize=24,
            textColor=colors.HexColor('#1a1a2e'),
            spaceAfter=20,
            alignment=TA_CENTER,
            fontName='Helvetica-Bold'
        )
        
        subtitle_style = ParagraphStyle(
            'MortgageSubtitle',
            parent=styles['Heading2'],
            fontSize=14,
            textColor=colors.HexColor('#c9a84c'),
            spaceAfter=15,
            alignment=TA_CENTER,
            fontName='Helvetica'
        )
        
        section_header_style = ParagraphStyle(
            'SectionHeader',
            parent=styles['Heading3'],
            fontSize=14,
            textColor=colors.HexColor('#1a1a2e'),
            spaceAfter=10,
            spaceBefore=15,
            fontName='Helvetica-Bold'
        )
        
        label_style = ParagraphStyle(
            'Label',
            parent=styles['Normal'],
            fontSize=10,
            textColor=colors.HexColor('#4a4a6a'),
            fontName='Helvetica-Bold'
        )
        
        value_style = ParagraphStyle(
            'Value',
            parent=styles['Normal'],
            fontSize=10,
            textColor=colors.HexColor('#1a1a2e'),
            fontName='Helvetica'
        )
        
        # Header
        elements.append(Paragraph("CREDITWISE - MORTGAGE ANALYTICS REPORT", title_style))
        elements.append(Paragraph("Comprehensive Mortgage Analysis", subtitle_style))
        elements.append(Spacer(1, 10))
        
        # Report date
        report_date = datetime.now().strftime('%B %d, %Y at %I:%M %p')
        elements.append(Paragraph(
            f"<i>Generated on: {report_date}</i>",
            ParagraphStyle('Date', parent=styles['Normal'], fontSize=9, alignment=TA_CENTER)
        ))
        elements.append(Spacer(1, 20))
        
        # Loan Details Section
        elements.append(Paragraph("Loan Details", section_header_style))
        
        loan_details = [
            [Paragraph("<b>Home Price:</b>", label_style), 
             Paragraph(f"${float(borrower_data.get('home_price', 0)):,.0f}", value_style)],
            [Paragraph("<b>Down Payment:</b>", label_style), 
             Paragraph(f"${float(borrower_data.get('down_payment', 0)):,.0f}", value_style)],
            [Paragraph("<b>Loan Amount:</b>", label_style), 
             Paragraph(f"${float(borrower_data.get('loan_amount', 0)):,.0f}", value_style)],
            [Paragraph("<b>Interest Rate:</b>", label_style), 
             Paragraph(f"{float(borrower_data.get('interest_rate', 0))}%", value_style)],
            [Paragraph("<b>Loan Term:</b>", label_style), 
             Paragraph(f"{int(borrower_data.get('term_years', 30))} years", value_style)],
        ]
        
        table = Table(loan_details, colWidths=[10*cm, 10*cm])
        table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ]))
        elements.append(table)
        elements.append(Spacer(1, 15))
        
        # Payment Summary Section
        elements.append(Paragraph("Payment Summary", section_header_style))
        
        monthly_payment = borrower_data.get('monthly_payment', 0)
        total_interest = borrower_data.get('total_interest', 0)
        total_payment = borrower_data.get('total_payment', 0)
        
        payment_details = [
            [Paragraph("<b>Monthly Payment:</b>", label_style), 
             Paragraph(f"${float(monthly_payment):,.2f}", value_style)],
            [Paragraph("<b>Total Interest:</b>", label_style), 
             Paragraph(f"${float(total_interest):,.0f}", value_style)],
            [Paragraph("<b>Total Payment:</b>", label_style), 
             Paragraph(f"${float(total_payment):,.0f}", value_style)],
        ]
        
        table = Table(payment_details, colWidths=[10*cm, 10*cm])
        table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ]))
        elements.append(table)
        elements.append(Spacer(1, 15))
        
        # Borrower Profile Section
        elements.append(Paragraph("Borrower Profile", section_header_style))
        
        borrower_profile = [
            [Paragraph("<b>Credit Score:</b>", label_style), 
             Paragraph(str(borrower_data.get('credit_score', 'N/A')), value_style)],
            [Paragraph("<b>Debt-to-Income Ratio:</b>", label_style), 
             Paragraph(f"{float(borrower_data.get('dti_ratio', 0))}%", value_style)],
            [Paragraph("<b>Loan Purpose:</b>", label_style), 
             Paragraph(str(borrower_data.get('loan_purpose', 'N/A')), value_style)],
            [Paragraph("<b>Property Type:</b>", label_style), 
             Paragraph(str(borrower_data.get('property_type', 'N/A')), value_style)],
        ]
        
        table = Table(borrower_profile, colWidths=[10*cm, 10*cm])
        table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ]))
        elements.append(table)
        elements.append(Spacer(1, 15))
        
        # Analysis Section (if available)
        if analysis_data and analysis_data.get('summary_markdown'):
            elements.append(Paragraph("AI Analysis", section_header_style))
            
            # Convert markdown to plain text for PDF
            markdown_text = analysis_data.get('summary_markdown', '')
            plain_text = markdown_to_plain_text(markdown_text)
            
            # Split into paragraphs
            paragraphs = plain_text.split('\n\n')
            for para in paragraphs:
                if para.strip():
                    elements.append(Paragraph(para.replace('\n', '<br/>'), styles['Normal']))
                    elements.append(Spacer(1, 8))
        
        # Footer
        elements.append(PageBreak())
        elements.append(Spacer(1, 50))
        
        footer_style = ParagraphStyle(
            'Footer',
            parent=styles['Normal'],
            fontSize=8,
            textColor=colors.HexColor('#888888'),
            alignment=TA_CENTER
        )
        
        elements.append(Paragraph(
            "This report is generated for informational purposes only. "
            "Please consult with a mortgage professional for specific advice.",
            footer_style
        ))
        elements.append(Spacer(1, 5))
        elements.append(Paragraph(
            f"© {datetime.now().year} CreditWise Bank POC. All rights reserved.",
            footer_style
        ))
        
        # Build PDF
        doc.build(elements)
        
        # Reset buffer position
        buffer.seek(0)
        
        logger.info("Mortgage report PDF generated successfully")
        return buffer
        
    except Exception as e:
        logger.error(f"Error generating mortgage report PDF: {e}")
        import traceback
        traceback.print_exc()
        raise


def markdown_to_plain_text(markdown_text):
    """
    Convert markdown text to plain text for PDF display.
    Removes markdown formatting while preserving content structure.
    
    Args:
        markdown_text: Markdown formatted text
        
    Returns:
        Plain text string
    """
    if not markdown_text:
        return ''
    
    text = markdown_text
    
    # Remove code blocks
    text = re.sub(r'```[\s\S]*?```', '', text)
    
    # Remove inline code
    text = re.sub(r'`([^`]+)`', r'\1', text)
    
    # Remove headers markers
    text = re.sub(r'^#+\s*', '', text, flags=re.MULTILINE)
    
    # Remove bold/italic markers
    text = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)
    text = re.sub(r'\*([^*]+)\*', r'\1', text)
    
    # Remove table formatting
    text = re.sub(r'\|', ' ', text)
    text = re.sub(r'-+\s*\|', '', text)
    
    # Remove list markers
    text = re.sub(r'^\s*[-*]\s*', '• ', text, flags=re.MULTILINE)
    text = re.sub(r'^\s*\d+\.\s*', '• ', text, flags=re.MULTILINE)
    
    # Remove horizontal rules
    text = re.sub(r'^[-*_]{3,}$', '', text, flags=re.MULTILINE)
    
    # Clean up extra whitespace
    text = re.sub(r'\n\s*\n', '\n\n', text)
    text = text.strip()
    
    return text
