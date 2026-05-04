# tools/document_tool.py
"""
ReportLab-based AML Compliance PDF generator.
Drop-in replacement for the original markdown-pdf version.
Produces branded, multi-page AML compliance reports matching the reference PDF style.
"""

import hashlib
import os
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Type, Optional, List, Tuple

from crewai.tools import BaseTool
from pydantic import BaseModel, Field

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm, cm

_pt = 1  # ReportLab default unit is points; 1 point = 1
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT, TA_JUSTIFY
from reportlab.platypus import (
    BaseDocTemplate,
    PageTemplate,
    Frame,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    Image,
    KeepTogether,
    PageBreak,
    NextPageTemplate,
    Flowable,
    HRFlowable,
)
from reportlab.platypus.tableofcontents import TableOfContents
from reportlab.pdfgen import canvas
from reportlab.lib.colors import HexColor
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# ---------------------------------------------------------------------------
# Configuration & Output Directories
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PDF_OUTPUT_DIR = PROJECT_ROOT / "outputs" / "pdfs"
SESSION_OUTPUT_DIR = PROJECT_ROOT / "outputs" / "sessions"
DB_PATH = PROJECT_ROOT / "bank_poc.db"

for d in [PDF_OUTPUT_DIR, SESSION_OUTPUT_DIR, DB_PATH.parent]:
    d.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Color Palette (matching reference PDFs exactly)
# ---------------------------------------------------------------------------

NAVY = HexColor("#1E4F77")
DARK_TEXT = HexColor("#2B3D4F")
BODY_GRAY = HexColor("#545454")
LIGHT_GRAY = HexColor("#878787")
MEDIUM_GRAY = HexColor("#808080")
ALT_ROW = HexColor("#F5F5F5")
TABLE_BORDER = HexColor("#CCCCCC")
GREEN_APPROVED = HexColor("#26AD60")
RED_REJECTED = HexColor("#BF382A")
CONFIDENTIAL_RED = HexColor("#BF382A")
WHITE = colors.white
BLACK = colors.black
LIGHT_BG = HexColor("#F2F2F4")

# Page dimensions (A4)
PAGE_W, PAGE_H = A4  # 595.27 x 841.89 pt
MARGIN_LEFT = 50
MARGIN_RIGHT = 50
MARGIN_TOP = 50
MARGIN_BOTTOM = 40
CONTENT_W = PAGE_W - MARGIN_LEFT - MARGIN_RIGHT

# ---------------------------------------------------------------------------
# Font Registration - Cross-platform support
# ---------------------------------------------------------------------------

import platform


def _get_font_path():
    """Find Times New Roman or similar serif font on the current system."""
    system = platform.system()

    if system == "Windows":
        # Windows font paths
        possible_paths = [
            "C:/Windows/Fonts/times.ttf",
            "C:/Windows/Fonts/timesbd.ttf",
            os.path.expandvars("%WINDIR%/Fonts/times.ttf"),
        ]
    elif system == "Darwin":  # macOS
        possible_paths = [
            "/Library/Fonts/Times New Roman.ttf",
            "/System/Library/Fonts/Times New Roman.ttf",
            "/System/Library/Fonts/Supplemental/Times New Roman.ttf",
        ]
    else:  # Linux
        possible_paths = [
            "/usr/share/fonts/truetype/english/Times-New-Roman.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSerif-Regular.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",
        ]

    for path in possible_paths:
        if os.path.isfile(path):
            return path
    return None


_FONT_PATH = _get_font_path()
if _FONT_PATH:
    try:
        pdfmetrics.registerFont(TTFont("TNR", _FONT_PATH))
        _FONT = "TNR"
        print(f"[document_tool] Registered font: {_FONT} from {_FONT_PATH}")
    except Exception as e:
        print(f"[document_tool] Failed to register font {_FONT_PATH}: {e}")
        _FONT = "Times-Roman"
else:
    _FONT = "Times-Roman"
    print("[document_tool] Using built-in Times-Roman font (no custom font found)")

_FONT_BOLD = "Times-Bold"
_FONT_ITALIC = "Times-Italic"
_FONT_BOLD_ITALIC = "Times-BoldItalic"


# ---------------------------------------------------------------------------
# Import build_session_output_path at module level (avoids circular import in _run)
# ---------------------------------------------------------------------------

try:
    from tools.config import build_session_output_path
except ImportError:
    # Fallback if import fails
    def build_session_output_path(
        first_name: str, last_name: str, decision: str, ext: str = "pdf"
    ) -> Path:
        """Fallback session path builder if config import fails."""
        datetime_str = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        safe_first = first_name.strip().replace(" ", "_")
        safe_last = last_name.strip().replace(" ", "_")
        safe_dec = decision.strip().upper().replace(" ", "_")
        filename = f"{safe_first}_{safe_last}_{datetime_str}_{safe_dec}.{ext}"
        return SESSION_OUTPUT_DIR / filename


# ---------------------------------------------------------------------------
# Custom Flowables
# ---------------------------------------------------------------------------


class SectionHeading(Flowable):
    """Numbered section heading styled like the reference PDFs."""

    def __init__(self, text, level=1, table_number=None):
        Flowable.__init__(self)
        self.text = text
        self.level = level
        self.table_number = table_number
        self._width = CONTENT_W
        self._height = 26 if level == 1 else 20

    def wrap(self, availWidth, availHeight):
        self._width = availWidth
        return self._width, self._height

    def draw(self):
        c = self.canv
        if self.level == 1:
            c.setFont(_FONT_BOLD, 20)
            c.setFillColor(NAVY)
            y = self._height - 20
        elif self.level == 2:
            c.setFont(_FONT_BOLD, 16)
            c.setFillColor(NAVY)
            y = self._height - 16
        else:
            c.setFont(_FONT_BOLD, 13)
            c.setFillColor(DARK_TEXT)
            y = self._height - 13
        c.drawString(11, y, self.text)


class TableCaption(Flowable):
    """Table caption below tables."""

    def __init__(self, text):
        Flowable.__init__(self)
        self.text = text
        self._height = 14

    def wrap(self, availWidth, availHeight):
        return availWidth, self._height

    def draw(self):
        c = self.canv
        c.setFont(_FONT, 9)
        c.setFillColor(BODY_GRAY)
        c.drawCentredString(CONTENT_W / 2, 2, self.text)


class MetadataLine(Flowable):
    """Metadata line: Timestamp / Report ID / Classification — rendered at bottom of pre-content sections."""

    def __init__(self, report_id, timestamp, classification="CONFIDENTIAL"):
        Flowable.__init__(self)
        self.report_id = report_id
        self.timestamp = timestamp
        self.classification = classification
        self._height = 16

    def wrap(self, availWidth, availHeight):
        return availWidth, self._height

    def draw(self):
        c = self.canv
        c.setFont(_FONT, 8)
        c.setFillColor(LIGHT_GRAY)
        text = f"Timestamp: {self.timestamp}  Report ID: {self.report_id}  Classification: {self.classification}"
        c.drawString(0, 2, text)


# ---------------------------------------------------------------------------
# Markdown Parser  →  ReportLab Flowables
# ---------------------------------------------------------------------------


class MarkdownParser:
    """Converts Markdown text into a list of ReportLab Flowable objects."""

    def __init__(self):
        self._table_counter = 0

    def parse(self, md: str) -> list:
        """Parse full Markdown text and return list of Flowables."""
        flowables = []
        self._table_counter = 0
        lines = md.split("\n")
        i = 0
        while i < len(lines):
            line = lines[i]

            # Skip empty lines
            if not line.strip():
                i += 1
                continue

            # H1
            if line.startswith("# ") and not line.startswith("##"):
                flowables.append(SectionHeading(line[2:].strip(), level=1))
                flowables.append(Spacer(1, 4))
                i += 1
                continue

            # H2
            if line.startswith("## ") and not line.startswith("###"):
                flowables.append(SectionHeading(line[3:].strip(), level=2))
                flowables.append(Spacer(1, 4))
                i += 1
                continue

            # H3
            if line.startswith("### "):
                flowables.append(SectionHeading(line[4:].strip(), level=3))
                flowables.append(Spacer(1, 2))
                i += 1
                continue

            # Horizontal rule
            if line.strip() in ("---", "***", "___"):
                flowables.append(Spacer(1, 6))
                flowables.append(
                    HRFlowable(
                        width="100%",
                        thickness=0.5,
                        color=TABLE_BORDER,
                        spaceAfter=6,
                        spaceBefore=0,
                    )
                )
                i += 1
                continue

            # Table detection: | ... | ... |
            if (
                "|" in line
                and i + 1 < len(lines)
                and re.match(r"^\|[\s\-:|]+\|$", lines[i + 1].strip())
            ):
                table_data, i = self._parse_table(lines, i)
                flowables.append(table_data)
                continue

            # Bold paragraph (like **Label:** value lines)
            if line.strip().startswith("**") and line.strip().endswith("**"):
                flowables.append(Spacer(1, 2))
                flowables.append(self._make_paragraph(line.strip()))
                flowables.append(Spacer(1, 2))
                i += 1
                continue

            # Bullet point
            if re.match(r"^\s*[-*]\s", line):
                flowables.append(self._make_bullet(line))
                i += 1
                continue

            # Numbered list
            if re.match(r"^\s*\d+\.\s", line):
                flowables.append(self._make_numbered(line))
                i += 1
                continue

            # Collect paragraph (multi-line, until empty line or heading)
            para_lines = []
            while i < len(lines):
                l = lines[i]
                if (
                    not l.strip()
                    or l.startswith("#")
                    or l.strip() in ("---", "***", "___")
                    or "|" in l
                ):
                    break
                para_lines.append(l)
                i += 1
            if para_lines:
                text = " ".join(l.strip() for l in para_lines)
                flowables.append(self._make_paragraph(text, justify=True))
                flowables.append(Spacer(1, 4))

            # Safety: ensure i is always incremented (prevents infinite loop on unexpected input)
            if i < len(lines) and not para_lines:
                i += 1

        return flowables

    def _parse_table(self, lines, start_idx) -> Tuple[Flowable, int]:
        """Parse a Markdown table into a styled ReportLab Table."""
        self._table_counter += 1

        # Parse header row
        header_line = lines[start_idx].strip()
        headers = [c.strip() for c in header_line.strip("|").split("|")]

        # Skip separator row
        sep_idx = start_idx + 1
        sep_line = lines[sep_idx]

        # Parse data rows
        data_rows = []
        i = start_idx + 2
        while i < len(lines) and "|" in lines[i]:
            row_text = lines[i].strip()
            cells = [c.strip() for c in row_text.strip("|").split("|")]
            data_rows.append(cells)
            i += 1

        # Build table data with Paragraph wrapping
        all_data = []
        header_row = []
        for h in headers:
            header_row.append(
                Paragraph(
                    f"<b>{self._inline_format(h)}</b>",
                    ParagraphStyle(
                        "th",
                        fontName=_FONT_BOLD,
                        fontSize=10,
                        textColor=WHITE,
                        leading=14,
                        alignment=TA_CENTER,
                    ),
                )
            )
        all_data.append(header_row)

        cell_style = ParagraphStyle(
            "td",
            fontName=_FONT,
            fontSize=9.5,
            textColor=DARK_TEXT,
            leading=13,
            alignment=TA_LEFT,
        )

        for row in data_rows:
            table_row = []
            for cell in row:
                table_row.append(Paragraph(self._inline_format(cell), cell_style))
            all_data.append(table_row)

        if not all_data:
            return Spacer(1, 0), i

        # Calculate column widths
        num_cols = len(headers)
        col_width = CONTENT_W / num_cols

        # Build table with styling
        table = Table(all_data, colWidths=[col_width] * num_cols)
        style_cmds = [
            # Header
            ("BACKGROUND", (0, 0), (-1, 0), NAVY),
            ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
            ("FONTNAME", (0, 0), (-1, 0), _FONT_BOLD),
            ("FONTSIZE", (0, 0), (-1, 0), 10),
            ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
            ("TOPPADDING", (0, 0), (-1, 0), 8),
            # Alternating rows
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, ALT_ROW]),
            # Grid
            ("GRID", (0, 0), (-1, -1), 0.5, TABLE_BORDER),
            ("BOX", (0, 0), (-1, -1), 0.5, MEDIUM_GRAY),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 1), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 1), (-1, -1), 5),
        ]
        table.setStyle(TableStyle(style_cmds))

        # Build descriptive caption from first header cell
        first_header = headers[0].strip() if headers else ""
        caption_text = (
            f"Table {self._table_counter}: {first_header}"
            if first_header
            else f"Table {self._table_counter}"
        )
        caption = TableCaption(caption_text)
        return KeepTogether([table, caption]), i

    def _make_paragraph(self, text: str, justify=False) -> Paragraph:
        alignment = TA_JUSTIFY if justify else TA_LEFT
        style = ParagraphStyle(
            "body",
            fontName=_FONT,
            fontSize=10.5,
            textColor=DARK_TEXT,
            leading=15,
            alignment=alignment,
            spaceAfter=2,
        )
        return Paragraph(self._inline_format(text), style)

    def _make_bullet(self, line: str) -> Paragraph:
        text = re.sub(r"^\s*[-*]\s+", "", line)
        style = ParagraphStyle(
            "bullet",
            fontName=_FONT,
            fontSize=10.5,
            textColor=DARK_TEXT,
            leading=15,
            leftIndent=20,
            bulletIndent=8,
            alignment=TA_LEFT,
            spaceBefore=2,
            spaceAfter=2,
        )
        return Paragraph(f"\u2022  {self._inline_format(text)}", style)

    def _make_numbered(self, line: str) -> Paragraph:
        text = re.sub(r"^\s*\d+\.\s+", "", line)
        style = ParagraphStyle(
            "numbered",
            fontName=_FONT,
            fontSize=10.5,
            textColor=DARK_TEXT,
            leading=15,
            leftIndent=20,
            bulletIndent=8,
            alignment=TA_LEFT,
            spaceBefore=2,
            spaceAfter=2,
        )
        return Paragraph(self._inline_format(text), style)

    @staticmethod
    def _inline_format(text: str) -> str:
        """Convert basic Markdown inline formatting to ReportLab XML tags."""
        # Bold: **text** → <b>text</b>
        text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
        # Italic: *text* → <i>text</i>
        text = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"<i>\1</i>", text)
        # Code: `text` → <font face="Courier">text</font>
        text = re.sub(r"`(.+?)`", r'<font face="Courier">\1</font>', text)
        # Links: [text](url) → <a href="url">text</a>
        text = re.sub(
            r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2" color="#1E4F77">\1</a>', text
        )
        return text


# ---------------------------------------------------------------------------
# Page Template Callbacks
# ---------------------------------------------------------------------------


def _draw_header_footer(canvas_obj, doc):
    """Draw header and footer on every body page."""
    canvas_obj.saveState()

    # Header line
    canvas_obj.setStrokeColor(MEDIUM_GRAY)
    canvas_obj.setLineWidth(0.5)
    canvas_obj.line(MARGIN_LEFT, PAGE_H - 38, PAGE_W - MARGIN_RIGHT, PAGE_H - 38)

    # Header text
    canvas_obj.setFont(_FONT, 8)
    canvas_obj.setFillColor(LIGHT_GRAY)
    canvas_obj.drawString(MARGIN_LEFT, PAGE_H - 32, "AML Compliance Report")
    canvas_obj.drawRightString(PAGE_W - MARGIN_RIGHT, PAGE_H - 32, "CONFIDENTIAL")

    # Footer line
    canvas_obj.line(MARGIN_LEFT, 34, PAGE_W - MARGIN_RIGHT, 34)

    # Footer text
    canvas_obj.setFont(_FONT, 8)
    canvas_obj.setFillColor(LIGHT_GRAY)
    page_num = canvas_obj.getPageNumber() - 1  # cover is page 0 internally
    date_str = datetime.now().strftime("%Y-%m-%d")
    canvas_obj.drawRightString(
        PAGE_W - MARGIN_RIGHT, 22, f"Page {page_num}  {date_str}"
    )

    canvas_obj.restoreState()


def _draw_cover(canvas_obj, doc):
    """Draw the cover page."""
    canvas_obj.saveState()

    # Top decorative line
    canvas_obj.setStrokeColor(MEDIUM_GRAY)
    canvas_obj.setLineWidth(0.5)
    canvas_obj.line(MARGIN_LEFT, PAGE_H - 40, PAGE_W - MARGIN_RIGHT, PAGE_H - 40)

    # Bottom decorative line
    canvas_obj.line(MARGIN_LEFT, 40, PAGE_W - MARGIN_RIGHT, 40)

    # Header text
    canvas_obj.setFont(_FONT, 8)
    canvas_obj.setFillColor(LIGHT_GRAY)
    canvas_obj.drawString(
        MARGIN_LEFT, PAGE_H - 32, "AML Compliance Report CONFIDENTIAL"
    )

    # Footer
    canvas_obj.line(MARGIN_LEFT, 34, PAGE_W - MARGIN_RIGHT, 34)
    date_str = datetime.now().strftime("%Y-%m-%d")
    canvas_obj.drawRightString(PAGE_W - MARGIN_RIGHT, 22, f"Page 1  {date_str}")

    canvas_obj.restoreState()


# ---------------------------------------------------------------------------
# PDF Document Builder
# ---------------------------------------------------------------------------


class AMLReportBuilder:
    """
    Builds a professional AML Compliance Report PDF using ReportLab.
    Matches the visual style of the reference PDFs.
    """

    def __init__(self, title: str, filepath: str):
        self.title = title
        self.filepath = filepath
        self.story = []
        self.parser = MarkdownParser()
        self._subject_name = ""
        self._decision = None  # "PASS" or "FAIL"
        self._risk_score = None
        self._report_date = datetime.now()
        self._report_id = ""

    def set_decision(
        self, decision: str, risk_score: int = None, subject_name: str = ""
    ):
        """Set cover page decision info."""
        self._decision = decision.upper() if decision else None
        self._risk_score = risk_score
        self._subject_name = subject_name

    def build(
        self,
        markdown_content: str,
        subject_image_path: str = None,
        graph_image_path: str = None,
        social_media_section: str = None,
        relatives_section: str = None,
        biography_section: str = None,
    ) -> str:
        """Build the complete PDF and save to filepath - with detailed logging."""
        try:
            print("[AMLReportBuilder] Starting PDF build...")

            # Pre-process markdown
            if (
                markdown_content
                and "\\n" in markdown_content
                and "\n" not in markdown_content
            ):
                markdown_content = markdown_content.replace("\\n", "\n")
            markdown_content = markdown_content.replace("\r\n", "\n").replace(
                "\r", "\n"
            )

            # Extract decision from content if not explicitly set
            if not self._decision:
                self._decision = self._detect_decision(markdown_content)
            if not self._subject_name:
                self._subject_name = self._detect_subject(markdown_content)
            if not self._risk_score:
                self._risk_score = self._detect_risk_score(markdown_content)

            print(
                f"[AMLReportBuilder] Decision: {self._decision}, Subject: {self._subject_name}, Risk Score: {self._risk_score}"
            )

            self._report_id = (
                f"AML-{datetime.now().strftime('%Y%m%d%H%M%S')}-{hashlib.md5(self.title.encode()).hexdigest()[:4].upper()}"
                if not self._report_id
                else self._report_id
            )

            # Build the story
            print("[AMLReportBuilder] Building cover page...")
            self._build_cover_page()

            print("[AMLReportBuilder] Building table of contents...")
            self._build_toc()

            print("[AMLReportBuilder] Building body content...")
            self._build_body(
                markdown_content,
                subject_image_path,
                graph_image_path,
                social_media_section,
                relatives_section,
                biography_section,
            )

            # Create the document
            print(f"[AMLReportBuilder] Creating PDF at: {self.filepath}")
            self._create_pdf()

            # Verify the PDF was actually written to disk
            if not Path(self.filepath).exists():
                return f"Error generating PDF: File not found at {self.filepath} after build"

            file_size = Path(self.filepath).stat().st_size
            print(
                f"[AMLReportBuilder] PDF created successfully: {self.filepath} ({file_size} bytes)"
            )

            # Persist to SQLite
            print("[AMLReportBuilder] Persisting to SQLite...")
            self._persist_to_sqlite()

            print("[AMLReportBuilder] Build complete!")
            return self.filepath

        except Exception as e:
            import traceback

            error_detail = traceback.format_exc()
            print(f"[AMLReportBuilder] ERROR during build: {error_detail}")
            return f"Error generating PDF: {e}"

    def _detect_decision(self, md: str) -> Optional[str]:
        """Try to detect PASS/FAIL from markdown content."""
        upper = md.upper()
        if (
            "APPLICATION APPROVED" in upper
            or "DECISION: PASS" in upper
            or "PASS - APPLICATION" in upper
        ):
            return "PASS"
        if (
            "APPLICATION REJECTED" in upper
            or "DECISION: FAIL" in upper
            or "REJECT" in upper
        ):
            return "FAIL"
        return None

    def _detect_subject(self, md: str) -> str:
        """Try to extract subject name from content."""
        m = re.search(
            r"[Ss]ubject\s*(?:Name)?[:\s]+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)", md
        )
        return m.group(1) if m else ""

    def _detect_risk_score(self, md: str) -> Optional[int]:
        """Try to extract risk score from content."""
        m = re.search(r"(?:Risk Score|score)[:\s]+(\d+)\s*/\s*100", md, re.IGNORECASE)
        return int(m.group(1)) if m else None

    def _build_cover_page(self):
        """Build the cover page elements."""
        # Spacer to push content down
        self.story.append(Spacer(1, 90))

        # Title
        title_style = ParagraphStyle(
            "cover_title",
            fontName=_FONT_BOLD,
            fontSize=32,
            textColor=NAVY,
            leading=38,
            alignment=TA_CENTER,
            spaceAfter=6,
        )
        if self._decision == "FAIL":
            self.story.append(Paragraph("Application Rejection Report", title_style))
        elif self._decision == "PASS":
            self.story.append(
                Paragraph("Application Approval and<br/>Compliance Report", title_style)
            )
        else:
            self.story.append(Paragraph(self.title, title_style))

        # Decorative line
        self.story.append(Spacer(1, 12))
        self.story.append(
            HRFlowable(
                width="60%", thickness=1, color=NAVY, spaceAfter=20, spaceBefore=0
            )
        )

        # Decision badge
        if self._decision:
            badge_color = GREEN_APPROVED if self._decision == "PASS" else RED_REJECTED
            badge_text = (
                "APPLICATION APPROVED"
                if self._decision == "PASS"
                else "APPLICATION REJECTED"
            )
            badge_style = ParagraphStyle(
                "badge",
                fontName=_FONT_BOLD,
                fontSize=18,
                textColor=WHITE,
                leading=24,
                alignment=TA_CENTER,
            )
            badge_data = [[Paragraph(badge_text, badge_style)]]
            badge_table = Table(badge_data, colWidths=[300])
            badge_table.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, -1), badge_color),
                        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                        ("TOPPADDING", (0, 0), (-1, -1), 10),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
                        ("LEFTPADDING", (0, 0), (-1, -1), 0),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                        ("ROUNDEDCORNERS", [4, 4, 4, 4]),
                    ]
                )
            )
            self.story.append(badge_table)

        # Risk score badge (shown on cover for PASS cases, matching reference_pass.pdf)
        # FAIL cover in reference_fail.pdf does NOT show the risk score on the cover page
        if self._risk_score is not None and self._decision != "FAIL":
            self.story.append(Spacer(1, 14))
            score_color = (
                GREEN_APPROVED
                if self._risk_score < 40
                else (RED_REJECTED if self._risk_score >= 61 else HexColor("#E6A817"))
            )
            score_label = (
                "LOW RISK"
                if self._risk_score < 21
                else (
                    "MEDIUM RISK"
                    if self._risk_score < 41
                    else ("HIGH RISK" if self._risk_score < 61 else "CRITICAL")
                )
            )

            score_num_style = ParagraphStyle(
                "score_num",
                fontName=_FONT_BOLD,
                fontSize=28,
                textColor=score_color,
                leading=32,
                alignment=TA_CENTER,
            )
            score_label_style = ParagraphStyle(
                "score_label",
                fontName=_FONT,
                fontSize=12,
                textColor=BODY_GRAY,
                leading=16,
                alignment=TA_CENTER,
            )

            score_data = [
                [Paragraph(f"{self._risk_score}/100", score_num_style)],
                [Paragraph(f"Risk Score  ({score_label})", score_label_style)],
            ]
            score_table = Table(score_data, colWidths=[200])
            score_table.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, -1), LIGHT_BG),
                        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                        ("TOPPADDING", (0, 0), (0, 0), 10),
                        ("BOTTOMPADDING", (0, -1), (0, -1), 8),
                        ("BOX", (0, 0), (-1, -1), 0.5, TABLE_BORDER),
                        ("ROUNDEDCORNERS", [4, 4, 4, 4]),
                    ]
                )
            )
            self.story.append(score_table)

        # Subject info (shown for PASS, not for FAIL — matching reference PDFs)
        self.story.append(Spacer(1, 24))
        info_style = ParagraphStyle(
            "cover_info",
            fontName=_FONT,
            fontSize=12,
            textColor=BODY_GRAY,
            leading=16,
            alignment=TA_CENTER,
        )
        if self._subject_name and self._decision == "PASS":
            name_style = ParagraphStyle(
                "cover_name",
                fontName=_FONT_BOLD,
                fontSize=16,
                textColor=BODY_GRAY,
                leading=20,
                alignment=TA_CENTER,
                spaceAfter=10,
            )
            self.story.append(Paragraph(f"Subject: {self._subject_name}", name_style))

        date_str = self._report_date.strftime("%B %d, %Y")
        self.story.append(Paragraph(f"Report Date: {date_str}", info_style))
        self.story.append(Spacer(1, 4))
        self.story.append(Paragraph("Generated by AML Compliance System", info_style))
        self.story.append(
            Paragraph("Automated Anti-Money Laundering Screening", info_style)
        )

        # CONFIDENTIAL
        self.story.append(Spacer(1, 24))
        self.story.append(
            HRFlowable(
                width="60%",
                thickness=0.5,
                color=LIGHT_GRAY,
                spaceAfter=10,
                spaceBefore=0,
            )
        )
        conf_style = ParagraphStyle(
            "confidential",
            fontName=_FONT_BOLD,
            fontSize=10,
            textColor=CONFIDENTIAL_RED,
            leading=14,
            alignment=TA_CENTER,
        )
        self.story.append(Paragraph("CONFIDENTIAL", conf_style))

        # Page break to TOC
        self.story.append(NextPageTemplate("body"))
        self.story.append(PageBreak())

    def _build_toc(self):
        """Build the Table of Contents page."""
        self.story.append(SectionHeading("Table of Contents", level=1))
        self.story.append(Spacer(1, 12))

        toc = TableOfContents()
        toc.levelStyles = [
            ParagraphStyle(
                "toc1",
                fontName=_FONT,
                fontSize=12,
                textColor=DARK_TEXT,
                leading=24,
                leftIndent=20,
                spaceBefore=4,
            ),
            ParagraphStyle(
                "toc2",
                fontName=_FONT,
                fontSize=10,
                textColor=BODY_GRAY,
                leading=22,
                leftIndent=40,
                spaceBefore=2,
            ),
        ]
        self.story.append(toc)
        self.story.append(NextPageTemplate("body"))
        self.story.append(PageBreak())

    def _build_body(
        self,
        md: str,
        subject_image_path: str,
        graph_image_path: str,
        social_media_section: str,
        relatives_section: str,
        biography_section: str,
    ):
        """Build the body content from Markdown."""
        print("[AMLReportBuilder._build_body] Starting body content build...")

        # Prepend supplementary sections (biography, social media, relatives)
        pre_content = ""

        # Biography section
        if biography_section:
            print("[AMLReportBuilder._build_body] Parsing biography section...")
            bio_md = self._parse_biography(biography_section)
            pre_content += bio_md

        # Social media section
        if social_media_section:
            print("[AMLReportBuilder._build_body] Parsing social media section...")
            sm_md = self._parse_social_media(social_media_section)
            pre_content += sm_md

        # Relatives section
        if relatives_section:
            print("[AMLReportBuilder._build_body] Parsing relatives section...")
            rel_md = self._parse_relatives(relatives_section)
            pre_content += rel_md

        # Parse main markdown content into flowables first
        print("[AMLReportBuilder._build_body] Parsing markdown content...")
        flowables = self.parser.parse(md)
        print(f"[AMLReportBuilder._build_body] Parsed {len(flowables)} flowables")

        # Insert subject image at the beginning if available
        # Issue 2 Fix: Properly handle Wikidata image inclusion in reports
        if subject_image_path and Path(subject_image_path).exists():
            print(
                f"[AMLReportBuilder._build_body] Including subject image: {subject_image_path}"
            )
            new_flowables = []
            # Add Subject Portrait heading
            new_flowables.append(SectionHeading("Subject Portrait", level=2))
            new_flowables.append(Spacer(1, 4))
            try:
                img = Image(subject_image_path, width=150, height=150)
                img.hAlign = "CENTER"
                new_flowables.append(img)
                new_flowables.append(Spacer(1, 12))
                print(
                    f"[AMLReportBuilder._build_body] Successfully added subject image to report"
                )
            except Exception as e:
                print(
                    f"[AMLReportBuilder._build_body] Warning: Could not add subject image: {e}"
                )
                new_flowables.append(
                    Paragraph(
                        "[Subject image could not be loaded]",
                        ParagraphStyle(
                            "err",
                            fontName=_FONT_ITALIC,
                            fontSize=10,
                            textColor=LIGHT_GRAY,
                            alignment=TA_CENTER,
                        ),
                    )
                )
                new_flowables.append(Spacer(1, 12))
            # Add remaining flowables
            new_flowables.extend(flowables)
            flowables = new_flowables

        # Append graph image at the end
        if graph_image_path and Path(graph_image_path).exists():
            flowables.append(Spacer(1, 12))
            flowables.append(
                SectionHeading("Entity Relationship Network (Neo4j Graph)", level=1)
            )
            flowables.append(Spacer(1, 6))
            try:
                img = Image(graph_image_path, width=CONTENT_W - 20, height=250)
                img.hAlign = "CENTER"
                flowables.append(img)
            except Exception:
                flowables.append(
                    Paragraph(
                        "[Graph image could not be loaded]",
                        ParagraphStyle(
                            "err",
                            fontName=_FONT_ITALIC,
                            fontSize=10,
                            textColor=LIGHT_GRAY,
                            alignment=TA_CENTER,
                        ),
                    )
                )

        # Insert metadata line after pre-content sections (biography/social/family)
        # This appears between the family table and subject identity in reference_fail.pdf
        timestamp_str = self._report_date.strftime("%Y-%m-%d %H:%M:%S")
        # Build a short report ID from subject initials
        if self._subject_name:
            initials = "".join(w[0] for w in self._subject_name.split() if w).upper()[
                :2
            ]
            short_id = f"AML-{initials}-{self._report_date.strftime('%Y%m%d')}-001"
        else:
            short_id = self._report_id[:20]
        metadata = MetadataLine(report_id=short_id, timestamp=timestamp_str)
        # Insert after the relatives/pre-content section but before main content
        # Find the last pre-content element (family table, social media, or biography)
        insert_idx = 0
        pre_section_names = (
            "Family and Associates",
            "Social Media Presence",
            "Biographical Profile",
        )
        for idx, f in enumerate(flowables):
            if isinstance(f, SectionHeading) and any(
                name in f.text for name in pre_section_names
            ):
                # Walk past all flowables belonging to this section
                insert_idx = idx + 1
                while insert_idx < len(flowables) and not isinstance(
                    flowables[insert_idx], SectionHeading
                ):
                    insert_idx += 1
        if insert_idx > 0:
            flowables.insert(insert_idx, Spacer(1, 6))
            flowables.insert(insert_idx + 1, metadata)

        # Add disclaimer at the end of the report
        disclaimer_text = (
            "This compliance report is generated by an automated AML screening system and is intended "
            "solely for internal compliance and regulatory purposes. The findings, risk assessments, and "
            "recommendations contained herein are based on data available from external sources at the time of "
            "screening and should not be construed as legal advice. The bank assumes no liability for decisions "
            "made based solely on this automated report. All compliance decisions should be reviewed by a "
            "qualified compliance officer in accordance with the institution's internal policies and applicable "
            "regulatory requirements."
        )
        flowables.append(Spacer(1, 16))
        flowables.append(
            HRFlowable(width="100%", thickness=0.5, color=TABLE_BORDER, spaceAfter=8)
        )
        disclaimer_style = ParagraphStyle(
            "disclaimer",
            fontName=_FONT_ITALIC,
            fontSize=9,
            textColor=LIGHT_GRAY,
            leading=13,
            alignment=TA_JUSTIFY,
            spaceBefore=4,
            spaceAfter=4,
        )
        flowables.append(
            Paragraph(
                "<b>Disclaimer</b>",
                ParagraphStyle(
                    "disc_title",
                    fontName=_FONT_BOLD,
                    fontSize=10,
                    textColor=BODY_GRAY,
                    leading=14,
                    spaceBefore=2,
                    spaceAfter=4,
                ),
            )
        )
        flowables.append(Paragraph(disclaimer_text, disclaimer_style))

        self.story.extend(flowables)

    def _parse_biography(self, raw: str) -> str:
        """Parse BIOGRAPHY_SECTION into Markdown table. Extracts Wikidata Q-ID for source link."""
        if raw.startswith("BIOGRAPHY_SECTION:"):
            raw = raw.split(":", 1)[1]
        raw = raw.strip()
        if not raw or "No biography data" in raw:
            return ""

        lines = ["## Biographical Profile\n", "| Field | Details |", "|---|---|"]
        wikidata_url = ""
        for line in raw.splitlines():
            s = line.strip()
            if not s or s.startswith("[ BIOGRAPHY ]"):
                continue
            if ":" in s:
                parts = s.split(":", 1)
                field = parts[0].strip()
                value = parts[1].strip()
                lines.append(f"| {field} | {value} |")
            # Capture Wikidata URL if present (case-insensitive check)
            if "wikidata.org/wiki/q" in s.lower():
                m = re.search(
                    r"(https?://www\.wikidata\.org/wiki/Q\d+)", s, re.IGNORECASE
                )
                if m:
                    wikidata_url = m.group(1)
        # Store Wikidata URL for social media section source link
        self._wikidata_source_url = wikidata_url
        return "\n".join(lines) + "\n\n"

    def _parse_social_media(self, raw: str) -> str:
        """Parse SOCIAL_MEDIA_SECTION into Markdown table. Adds Wikidata source link."""
        if raw.startswith("SOCIAL_MEDIA_SECTION:"):
            raw = raw.split(":", 1)[1]
        raw = raw.strip()
        if not raw or "No social media" in raw:
            return ""

        lines = ["## Social Media Presence\n"]
        for line in raw.splitlines():
            s = line.strip()
            if s.startswith("Accounts:"):
                lines += [
                    "### Accounts\n",
                    "| Platform | Username | Profile URL |",
                    "|---|---|---|",
                ]
            elif s.startswith("Follower Counts"):
                lines += [
                    "### Follower Counts\n",
                    "| Platform | Followers | As Of |",
                    "|---|---|---|",
                ]
            elif s.startswith("- ") and "@" in s:
                parts = s[2:].split()
                at_token = next((p for p in parts if p.startswith("@")), "")
                url_token = next((p for p in parts if p.startswith("http")), "")
                platform = s[2 : s.index(at_token)].strip() if at_token else s[2:]
                lines.append(f"| {platform} | {at_token} | {url_token} |")
            elif s.startswith("- ") and "followers" in s:
                parts = s[2:].split("followers")
                pc = parts[0].strip()
                as_of = (
                    parts[1]
                    .strip()
                    .lstrip("(")
                    .rstrip(")")
                    .replace("as of", "")
                    .strip()
                    if len(parts) > 1
                    else ""
                )
                tokens = pc.rsplit(None, 1)
                platform = tokens[0] if len(tokens) > 1 else pc
                count = tokens[-1] if len(tokens) > 1 else ""
                lines.append(f"| {platform} | {count} | {as_of} |")
            # Capture Wikidata URL from the social media section itself
            if "wikidata.org/wiki/q" in s.lower() and not getattr(
                self, "_wikidata_source_url", ""
            ):
                m = re.search(
                    r"(https?://www\.wikidata\.org/wiki/Q\d+)", s, re.IGNORECASE
                )
                if m:
                    self._wikidata_source_url = m.group(1)

        # Add Wikidata source link if we have one
        source_url = getattr(self, "_wikidata_source_url", "")
        if source_url:
            lines.append(f"\nSource: {source_url}")
        return "\n".join(lines) + "\n\n"

    def _parse_relatives(self, raw: str) -> str:
        """Parse RELATIVES_SECTION into Markdown table with individual Wikidata links per person."""
        if raw.startswith("RELATIVES_SECTION:"):
            raw = raw.split(":", 1)[1]
        raw = raw.strip()
        if not raw or "No relatives found" in raw:
            return ""

        lines = [
            "## Family and Associates\n",
            "| Relationship | Name | Wikidata |",
            "|---|---|---|",
        ]
        for line in raw.splitlines():
            s = line.strip()
            if (
                not s
                or s.startswith("[ FAMILY")
                or s.startswith("Relation")
                or s.startswith("---")
            ):
                continue
            # Try to extract: Relationship Name URL
            # Also handle format: Relationship Name (extra info) URL
            url_match = re.search(r"(https?://\S+)", s)
            if url_match:
                url = url_match.group(1).rstrip(".,;")
                before_url = s[: url_match.start()].strip()
                parts = before_url.split(None, 1)
                rel = parts[0] if parts else ""
                name = parts[1] if len(parts) > 1 else ""
                # Each person's Wikidata link points to THEIR own page
                link = f"[View]({url})"
                lines.append(f"| {rel} | {name} | {link} |")
            else:
                # No URL found — just relationship and name
                parts = s.split(None, 1)
                if len(parts) >= 2:
                    rel = parts[0]
                    name = parts[1]
                    lines.append(f"| {rel} | {name} | N/A |")
        return "\n".join(lines) + "\n\n"

    def _create_pdf(self):
        """Create the PDF document with page templates."""
        print("[AMLReportBuilder._create_pdf] Setting up frames...")

        # Body frame
        body_frame = Frame(
            MARGIN_LEFT,
            MARGIN_BOTTOM + 15,
            CONTENT_W,
            PAGE_H - MARGIN_TOP - MARGIN_BOTTOM - 35,
            id="body",
        )

        # Cover frame (larger usable area)
        cover_frame = Frame(
            MARGIN_LEFT,
            MARGIN_BOTTOM + 15,
            CONTENT_W,
            PAGE_H - MARGIN_TOP - MARGIN_BOTTOM - 35,
            id="cover",
        )

        print("[AMLReportBuilder._create_pdf] Creating page templates...")
        # Page templates
        cover_template = PageTemplate(
            id="cover", frames=[cover_frame], onPage=_draw_cover
        )
        body_template = PageTemplate(
            id="body", frames=[body_frame], onPage=_draw_header_footer
        )

        print(f"[AMLReportBuilder._create_pdf] Building document at: {self.filepath}")
        # Build document
        doc = BaseDocTemplate(
            self.filepath,
            pagesize=A4,
            leftMargin=MARGIN_LEFT,
            rightMargin=MARGIN_RIGHT,
            topMargin=MARGIN_TOP,
            bottomMargin=MARGIN_BOTTOM,
            title=self.title,
            author="AML Compliance System",
            subject="AML Compliance Report",
            creator="AML Compliance System",
        )
        doc.addPageTemplates([cover_template, body_template])

        print(
            f"[AMLReportBuilder._create_pdf] Calling multiBuild with {len(self.story)} story elements..."
        )
        # Generate TOC (needs multi-build)
        doc.multiBuild(self.story)
        print("[AMLReportBuilder._create_pdf] multiBuild completed successfully")

    def _persist_to_sqlite(self):
        """Save the PDF blob to SQLite for durable storage - with timeout and error handling."""
        try:
            import sqlite3

            # Check if file exists before reading
            if not Path(self.filepath).exists():
                print(
                    f"[AMLReportBuilder] Warning: PDF file not found at {self.filepath}, skipping SQLite persistence"
                )
                return

            blob = Path(self.filepath).read_bytes()
            safe_name = Path(self.filepath).name

            # Ensure DB_PATH parent directory exists
            DB_PATH.parent.mkdir(parents=True, exist_ok=True)

            # Use timeout to avoid hanging on locked database
            with sqlite3.connect(str(DB_PATH), timeout=10.0) as conn:
                conn.execute("PRAGMA journal_mode=WAL")  # Better concurrency
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS session_artifacts (
                        artifact_id INTEGER PRIMARY KEY AUTOINCREMENT,
                        filename TEXT NOT NULL, 
                        file_blob BLOB NOT NULL,
                        created_at TEXT DEFAULT (datetime('now'))
                    )
                """
                )
                conn.execute(
                    "INSERT INTO session_artifacts (filename, file_blob) VALUES (?, ?)",
                    (safe_name, blob),
                )
                conn.commit()
            print(
                f"[AMLReportBuilder] PDF persisted to SQLite: {safe_name} ({len(blob)} bytes)"
            )

        except sqlite3.Error as e:
            print(f"[AMLReportBuilder] SQLite error (non-fatal): {e}")
        except Exception as e:
            print(
                f"[AMLReportBuilder] Failed to persist PDF to SQLite (non-fatal): {e}"
            )


# ---------------------------------------------------------------------------
# CrewAI Tool Interface (drop-in replacement)
# ---------------------------------------------------------------------------


class MarkdownPDFInput(BaseModel):
    title: str = Field(..., description="Report title")
    markdown_content: str = Field(..., description="Markdown text to convert to PDF")
    filename: str = Field(
        default="",
        description="Optional output filename hint. If empty, the tool auto-detects client name and decision from the markdown content to build a proper session path.",
    )
    graph_image_path: Optional[str] = Field(
        default=None,
        description="Optional path to Neo4j network graph image. Accepts raw 'GRAPH_IMAGE_PATH: ...' format — tool will extract the path automatically.",
    )
    subject_image_path: Optional[str] = Field(
        default=None,
        description="Optional path to subject portrait image. Accepts raw 'WIKIDATA_IMAGE_PATH: ...' format — tool will extract the path automatically.",
    )
    social_media_section: Optional[str] = Field(
        default=None,
        description="Optional SOCIAL_MEDIA_SECTION block from WikidataOSINTTool.",
    )
    relatives_section: Optional[str] = Field(
        default=None,
        description="Optional RELATIVES_SECTION block from WikidataOSINTTool.",
    )
    biography_section: Optional[str] = Field(
        default=None,
        description="Optional BIOGRAPHY_SECTION block from WikidataOSINTTool.",
    )


# ---------------------------------------------------------------------------
# Auto-detection helpers — the tool parses the markdown content itself
# to extract client name and PASS/FAIL decision, so it always saves to
# the correct session path regardless of what the LLM agent passes.
# ---------------------------------------------------------------------------


def _extract_client_name_from_md(md: str) -> Tuple[str, str]:
    """
    Extract first_name and last_name from AML report markdown content.

    Tries multiple patterns in order of reliability:
      1. AML Compliance Report header: "# AML Compliance Report — First Last"
      2. Subject Name row in identity table: "Subject Name | First Last"
      3. Subject: label: "Subject: First Last"
      4. First bold name pattern: "**First Last**"
    """
    # Pattern 1: Report header line
    m = re.search(
        r"#\s*AML\s+Compliance\s+Report\s*[—\-–]+\s*([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)",
        md,
    )
    if m:
        parts = m.group(1).strip().split(None, 1)
        return (parts[0], parts[1]) if len(parts) == 2 else (parts[0], "")

    # Pattern 2: Table row with Subject Name / Full Name
    m = re.search(
        r"\|\s*(?:Subject\s+Name|Full\s+Name)\s*\|\s*([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s*\|",
        md,
    )
    if m:
        parts = m.group(1).strip().split(None, 1)
        return (parts[0], parts[1]) if len(parts) == 2 else (parts[0], "")

    # Pattern 3: "Subject:" label
    m = re.search(r"[Ss]ubject\s*(?:Name)?[:\s]+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)", md)
    if m:
        parts = m.group(1).strip().split(None, 1)
        return (parts[0], parts[1]) if len(parts) >= 2 else (parts[0], "")

    # Pattern 4: Bold name in executive summary area
    m = re.search(r"\*\*([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,4})\*\*", md)
    if m:
        parts = m.group(1).strip().split(None, 1)
        return (parts[0], parts[1]) if len(parts) >= 2 else (parts[0], "")

    return ("", "")


def _extract_decision_from_md(md: str) -> str:
    """
    Extract PASS/FAIL decision from AML report markdown content.

    Tries multiple patterns in order of reliability.
    Returns "PASS", "FAIL", or "" (empty string if not detected).
    """
    upper = md.upper()

    # Explicit decision lines
    if re.search(r"DECISION\s*:\s*PASS", upper):
        return "PASS"
    if re.search(r"DECISION\s*:\s*FAIL", upper):
        return "FAIL"

    # Application status phrases
    if "APPLICATION APPROVED" in upper or "PASS - APPLICATION" in upper:
        return "PASS"
    if "APPLICATION REJECTED" in upper or "TRANSACTION BLOCKED" in upper:
        return "FAIL"

    # More general patterns
    if re.search(r"\bPASS\b", upper) and not re.search(r"\bFAIL\b", upper):
        return "PASS"
    if re.search(r"\bFAIL\b", upper) and not re.search(r"\bPASS\b", upper):
        return "FAIL"

    return ""


def _extract_image_path_from_md(md: str, prefix: str) -> Optional[str]:
    """
    Extract an image path from markdown content by looking for lines like:
      GRAPH_IMAGE_PATH: outputs/graphs/...
      WIKIDATA_IMAGE_PATH: outputs/images/...

    Returns the extracted path string, or None.
    """
    pattern = rf"{prefix}\s*:\s*(\S+\.(?:png|jpg|jpeg|gif|webp))"
    m = re.search(pattern, md, re.IGNORECASE)
    if m:
        return m.group(1).strip().strip("'\"")
    return None


class MarkdownPDFTool(BaseTool):
    """
    Converts Markdown text into a styled AML Compliance PDF using ReportLab.

    AUTO-SAVE BEHAVIOUR:
      The tool automatically detects the client name and PASS/FAIL decision
      from the markdown content itself. It then uses `build_session_output_path()`
      to save the PDF to the correct session directory:

          outputs/sessions/{First}_{Last}_{YYYY-MM-DD_HH-MM-SS}_{PASS|FAIL}.pdf

      This ensures the report is ALWAYS stored to the correct path with a
      deterministic filename — even if the LLM agent doesn't pass `filename`.

      The tool also:
        - Auto-extracts GRAPH_IMAGE_PATH and WIKIDATA_IMAGE_PATH from the
          markdown content if they're present (no need for the agent to
          pass them separately — but the agent CAN still pass them as
          explicit parameters for override).
        - Persists the PDF to SQLite for durable storage.
    """

    name: str = "Markdown Report Generator"
    description: str = (
        "Converts Markdown text into a professionally styled AML Compliance PDF document. "
        "Automatically detects the client name and PASS/FAIL decision from the report content "
        "and saves the PDF to the correct session output directory. "
        "Produces branded reports with cover page, Table of Contents, headers/footers, "
        "styled tables, decision badges, and risk score displays."
    )
    args_schema: Type[BaseModel] = MarkdownPDFInput

    def _run(
        self,
        title,
        markdown_content,
        filename="",
        graph_image_path=None,
        subject_image_path=None,
        social_media_section=None,
        relatives_section=None,
        biography_section=None,
    ) -> str:

        print("[MarkdownPDFTool] Starting PDF generation...")

        # ── Step 0: Ensure output directories exist ─────────────────────
        for d in [PDF_OUTPUT_DIR, SESSION_OUTPUT_DIR, DB_PATH.parent]:
            d.mkdir(parents=True, exist_ok=True)
        print("[MarkdownPDFTool] Output directories verified")

        # ── Step 1: Pre-process markdown ──────────────────────────────
        if (
            markdown_content
            and "\\n" in markdown_content
            and "\n" not in markdown_content
        ):
            markdown_content = markdown_content.replace("\\n", "\n")
        markdown_content = markdown_content.replace("\r\n", "\n").replace("\r", "\n")

        # ── Step 2: Auto-detect client name & decision from content ───
        first_name, last_name = _extract_client_name_from_md(markdown_content)
        decision = _extract_decision_from_md(markdown_content)

        print(
            f"[MarkdownPDFTool] Auto-detected client: '{first_name} {last_name}', decision: '{decision or 'UNKNOWN'}'"
        )

        # ── Step 3: Auto-extract image paths from content ─────────────
        # Only use auto-extracted paths if the agent didn't pass them explicitly
        if not graph_image_path:
            auto_graph = _extract_image_path_from_md(
                markdown_content, "GRAPH_IMAGE_PATH"
            )
            if auto_graph:
                graph_image_path = auto_graph
                print(
                    f"[MarkdownPDFTool] Auto-extracted graph_image_path: {graph_image_path}"
                )

        if not subject_image_path:
            auto_subject = _extract_image_path_from_md(
                markdown_content, "WIKIDATA_IMAGE_PATH"
            )
            if auto_subject:
                subject_image_path = auto_subject
                print(
                    f"[MarkdownPDFTool] Auto-extracted subject_image_path: {subject_image_path}"
                )

        # ── Step 4: Clean image paths (strip prefix labels) ───────────
        if subject_image_path and (
            "WIKIDATA_IMAGE_PATH:" in subject_image_path
            or "WIKIDATA_IMAGE:" in subject_image_path
        ):
            for line in subject_image_path.splitlines():
                line = line.strip()
                if line.startswith("WIKIDATA_IMAGE_PATH:"):
                    subject_image_path = line.split(":", 1)[1].strip()
                    break
            else:
                subject_image_path = None

        if isinstance(subject_image_path, str):
            subject_image_path = (
                subject_image_path.strip().strip("'").strip("\\").strip('"')
            )

        if graph_image_path and (
            "GRAPH_IMAGE_PATH:" in graph_image_path
            or "GRAPH_IMAGE:" in graph_image_path
        ):
            for line in graph_image_path.splitlines():
                line = line.strip()
                if line.startswith("GRAPH_IMAGE_PATH:"):
                    graph_image_path = line.split(":", 1)[1].strip()
                    break
            else:
                graph_image_path = None

        if isinstance(graph_image_path, str):
            graph_image_path = (
                graph_image_path.strip().strip("'").strip("\\").strip('"')
            )

        # ── Step 5: Determine output filepath ─────────────────────────
        # Priority: use build_session_output_path() if we have a client name,
        # otherwise fall back to filename hint, otherwise generic path.
        # NOTE: build_session_output_path is imported at module level
        if first_name and last_name:
            # Use the canonical session path builder
            safe_decision = decision if decision in ("PASS", "FAIL") else "UNKNOWN"
            session_path = build_session_output_path(
                first_name=first_name,
                last_name=last_name,
                decision=safe_decision,
                ext="pdf",
            )
            filepath = str(session_path)
            print(f"[MarkdownPDFTool] Using auto-detected session path: {filepath}")
        elif filename:
            safe_stem = Path(filename).stem
            real_ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            safe_name = f"{safe_stem}_{real_ts}.pdf"
            filepath = str(SESSION_OUTPUT_DIR / safe_name)
            print(f"[MarkdownPDFTool] Using filename hint path: {filepath}")
        else:
            real_ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            safe_name = f"report_{real_ts}.pdf"
            filepath = str(PDF_OUTPUT_DIR / safe_name)
            print(f"[MarkdownPDFTool] Using generic report path: {filepath}")

        # ── Step 6: Build the PDF ─────────────────────────────────────
        print("[MarkdownPDFTool] Creating AMLReportBuilder...")
        builder = AMLReportBuilder(title=title, filepath=filepath)

        # Pre-set decision on the builder so cover page is correct
        if decision:
            builder.set_decision(
                decision=decision, subject_name=f"{first_name} {last_name}".strip()
            )

        print("[MarkdownPDFTool] Calling builder.build()...")
        result = builder.build(
            markdown_content=markdown_content,
            subject_image_path=subject_image_path,
            graph_image_path=graph_image_path,
            social_media_section=social_media_section,
            relatives_section=relatives_section,
            biography_section=biography_section,
        )

        # ── Step 7: Verify and log ────────────────────────────────────
        if result and not result.startswith("Error"):
            if Path(result).exists():
                file_size = Path(result).stat().st_size
                print(
                    f"[MarkdownPDFTool] PDF generated & verified: {result} ({file_size} bytes)"
                )
            else:
                print(
                    f"[MarkdownPDFTool] WARNING: PDF reported but not found at: {result}"
                )
        else:
            print(f"[MarkdownPDFTool] PDF generation FAILED: {result}")

        return result


# ---------------------------------------------------------------------------
# Document loading tools (unchanged from original)
# ---------------------------------------------------------------------------


class FilePathInput(BaseModel):
    file_path: str = Field(
        ..., description="Absolute or relative path to the file to load."
    )
    max_chars: int = Field(
        default=8000, description="Maximum characters to return (0 = unlimited)."
    )


class AMLReportInput(BaseModel):
    file_path: str = Field(
        ..., description="Path to an AML report (.md or .pdf). Type is auto-detected."
    )
    max_chars: int = Field(
        default=8000, description="Maximum characters to return (0 = unlimited)."
    )


def _truncate(text: str, max_chars: int) -> str:
    if max_chars <= 0 or len(text) <= max_chars:
        return text
    return text[:max_chars] + f"\n\n... [TRUNCATED at {max_chars} chars]"


def _load_markdown(file_path: str) -> str:
    from langchain_community.document_loaders import UnstructuredMarkdownLoader

    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Markdown file not found: {file_path}")
    loader = UnstructuredMarkdownLoader(str(path), mode="single")
    docs = loader.load()
    if not docs:
        return "(File loaded but contained no extractable text.)"
    return "\n\n".join(doc.page_content for doc in docs if doc.page_content.strip())


def _load_pdf(file_path: str) -> str:
    from langchain_community.document_loaders import PyPDFLoader

    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"PDF file not found: {file_path}")
    pages = PyPDFLoader(str(path)).load()
    if not pages:
        return "(PDF loaded but contained no text.)"
    parts = []
    for doc in pages:
        page_num = doc.metadata.get("page", "?")
        content = doc.page_content.strip()
        if content:
            parts.append(f"--- Page {page_num} ---\n{content}")
    return "\n\n".join(parts) if parts else "(PDF had no text content.)"


class MarkdownLoaderTool(BaseTool):
    """Loads a Markdown (.md) file and returns its full text content."""

    name: str = "Markdown Document Loader"
    description: str = (
        "Loads and returns the full text content of a Markdown (.md) file."
    )
    args_schema: Type[BaseModel] = FilePathInput

    def _run(self, file_path: str, max_chars: int = 8000) -> str:
        try:
            return _truncate(_load_markdown(file_path), max_chars)
        except (FileNotFoundError, ValueError) as e:
            return f"MARKDOWN_LOAD_ERROR: {e}"
        except ImportError as e:
            return f"MARKDOWN_LOAD_ERROR: Missing dependency — {e}"
        except Exception as e:
            return f"MARKDOWN_LOAD_ERROR: {e}"


class PDFLoaderTool(BaseTool):
    """Loads a PDF file and returns its text content page by page."""

    name: str = "PDF Document Loader"
    description: str = (
        "Loads and returns the full text content of a PDF (.pdf) file, page by page."
    )
    args_schema: Type[BaseModel] = FilePathInput

    def _run(self, file_path: str, max_chars: int = 8000) -> str:
        try:
            return _truncate(_load_pdf(file_path), max_chars)
        except (FileNotFoundError, ValueError) as e:
            return f"PDF_LOAD_ERROR: {e}"
        except ImportError as e:
            return f"PDF_LOAD_ERROR: Missing dependency — {e}"
        except Exception as e:
            return f"PDF_LOAD_ERROR: {e}"


class AMLReportLoaderTool(BaseTool):
    """Unified loader for AML reports — accepts both .md and .pdf files."""

    name: str = "AML Report Loader"
    description: str = "Loads a previously generated AML compliance report from disk."
    args_schema: Type[BaseModel] = AMLReportInput

    def _run(self, file_path: str, max_chars: int = 8000) -> str:
        try:
            ext = Path(file_path).suffix.lower()
            if ext == ".md":
                text = _load_markdown(file_path)
            elif ext == ".pdf":
                text = _load_pdf(file_path)
            else:
                return f"AML_REPORT_LOAD_ERROR: Unsupported file type '{ext}'."
            return _truncate(text, max_chars)
        except (FileNotFoundError, ValueError) as e:
            return f"AML_REPORT_LOAD_ERROR: {e}"
        except ImportError as e:
            return f"AML_REPORT_LOAD_ERROR: Missing dependency — {e}"
        except Exception as e:
            return f"AML_REPORT_LOAD_ERROR: {e}"


# Module-level singletons
markdown_loader_tool = MarkdownLoaderTool()
pdf_loader_tool = PDFLoaderTool()
aml_report_loader_tool = AMLReportLoaderTool()
