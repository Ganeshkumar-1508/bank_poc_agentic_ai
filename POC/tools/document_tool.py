# tools/document_tool.py
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Type, Optional, List

from crewai.tools import BaseTool
from markdown_pdf import MarkdownPdf, Section
from pydantic import BaseModel, Field

from tools.config import PDF_OUTPUT_DIR, SESSION_OUTPUT_DIR


# ---------------------------------------------------------------------------
# MarkdownPDFTool — Markdown → styled PDF
# ---------------------------------------------------------------------------

class MarkdownPDFInput(BaseModel):
    title: str = Field(..., description="Report title")
    markdown_content: str = Field(..., description="Markdown text to convert to PDF")
    filename: str = Field(default="", description="Optional output filename hint (auto-generated if empty)")
    graph_image_path: Optional[str] = Field(default=None, description="Optional path to Neo4j network graph image")
    subject_image_path: Optional[str] = Field(default=None, description="Optional path to subject portrait image")
    social_media_section: Optional[str] = Field(
        default=None,
        description="Optional SOCIAL_MEDIA_SECTION block from WikidataOSINTTool. Injected as '## Social Media Presence'."
    )
    relatives_section: Optional[str] = Field(
        default=None,
        description="Optional RELATIVES_SECTION block from WikidataOSINTTool. Injected as '## Family & Associates'."
    )
    biography_section: Optional[str] = Field(
        default=None,
        description="Optional BIOGRAPHY_SECTION block from WikidataOSINTTool. Injected as '## Biographical Profile'."
    )


class MarkdownPDFTool(BaseTool):
    """Converts Markdown text into a styled PDF with optional images and tables."""

    name: str = "Markdown Report Generator"
    description: str = "Converts Markdown text into a styled PDF document using markdown-pdf."
    args_schema: Type[BaseModel] = MarkdownPDFInput

    def _run(self, title, markdown_content, filename="", graph_image_path=None,
             subject_image_path=None, social_media_section=None, relatives_section=None,
             biography_section=None) -> str:
        if filename:
            safe_stem = Path(filename).stem
            real_ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            safe_name = f"{safe_stem}_{real_ts}.pdf"
            filepath = str(SESSION_OUTPUT_DIR / safe_name)
        else:
            real_ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            safe_name = f"report_{real_ts}.pdf"
            filepath = str(PDF_OUTPUT_DIR / safe_name)

        try:
            if markdown_content and "\\n" in markdown_content and "\n" not in markdown_content:
                markdown_content = markdown_content.replace("\\n", "\n")
            markdown_content = markdown_content.replace("\r\n", "\n").replace("\r", "\n")

            if subject_image_path and ("WIKIDATA_IMAGE_PATH:" in subject_image_path or "WIKIDATA_IMAGE:" in subject_image_path):
                for line in subject_image_path.splitlines():
                    line = line.strip()
                    if line.startswith("WIKIDATA_IMAGE_PATH:"):
                        subject_image_path = line.split(":", 1)[1].strip()
                        break
                else:
                    subject_image_path = None

            if isinstance(subject_image_path, str):
                subject_image_path = subject_image_path.strip().strip("'").strip(chr(92)).strip('"')

            # Parse social media section → Markdown tables
            sm_md = ""
            if social_media_section:
                raw_sm = social_media_section
                if raw_sm.startswith("SOCIAL_MEDIA_SECTION:"):
                    raw_sm = raw_sm.split(":", 1)[1]
                raw_sm = raw_sm.strip()
                if raw_sm and "No social media" not in raw_sm:
                    sm_lines = ["## Social Media Presence", ""]
                    for line in raw_sm.splitlines():
                        s = line.strip()
                        if s.startswith("Accounts:"):
                            sm_lines += ["### Accounts", "", "| Platform | Username | Profile URL |", "|----------|----------|-------------|"]
                        elif s.startswith("Follower Counts"):
                            sm_lines += ["", "### Follower Counts", "", "| Platform | Followers | As Of |", "|----------|-----------|-------|"]
                        elif s.startswith("• ") and "@" in s:
                            parts = s[2:].split()
                            at_token = next((p for p in parts if p.startswith("@")), "")
                            url_token = next((p for p in parts if p.startswith("http")), "")
                            platform = s[2:s.index(at_token)].strip() if at_token else s[2:]
                            sm_lines.append(f"| {platform} | {at_token} | {url_token} |")
                        elif s.startswith("• ") and "followers" in s:
                            parts = s[2:].split("followers")
                            platform_count = parts[0].strip()
                            as_of_part = parts[1].strip().lstrip("(").rstrip(")").replace("as of", "").strip() if len(parts) > 1 else ""
                            tokens = platform_count.rsplit(None, 1)
                            platform = tokens[0].strip() if len(tokens) > 1 else platform_count
                            count = tokens[-1] if len(tokens) > 1 else ""
                            sm_lines.append(f"| {platform} | {count} | {as_of_part} |")
                        elif s.startswith("Wikidata"):
                            sm_lines += ["", f"*{s}*"]
                    sm_md = "\n".join(sm_lines) + "\n\n"

            # Parse relatives section → Markdown table
            rel_md = ""
            if relatives_section:
                raw_rel = relatives_section
                if raw_rel.startswith("RELATIVES_SECTION:"):
                    raw_rel = raw_rel.split(":", 1)[1]
                raw_rel = raw_rel.strip()
                if raw_rel and "No relatives found" not in raw_rel:
                    rel_lines = ["## Family & Associates", "", "| Relationship | Name | Wikidata |", "|---|---|---|"]
                    for line in raw_rel.splitlines():
                        s = line.strip()
                        if not s or s.startswith("[ FAMILY") or s.startswith("Relation") or s.startswith("---"):
                            continue
                        parts = s.split()
                        if len(parts) >= 3:
                            url = parts[-1]
                            rel = parts[0]
                            name_part = " ".join(parts[1:-1])
                            rel_lines.append(f"| {rel} | {name_part} | [{url}]({url}) |")
                    rel_md = "\n".join(rel_lines) + "\n\n"

            graph_exists = bool(graph_image_path and Path(graph_image_path).exists())
            subject_exists = bool(subject_image_path and Path(subject_image_path).exists())

            # Ensure subject image exists in a known directory
            if subject_exists and not graph_exists:
                img_root = str(Path(subject_image_path).parent)
            elif graph_exists:
                img_root = str(Path(graph_image_path).parent)
                if subject_exists and str(Path(subject_image_path).parent) != img_root:
                    dest = Path(img_root) / Path(subject_image_path).name
                    shutil.copy2(subject_image_path, dest)
                    subject_image_path = str(dest)
            else:
                img_root = None

            content_has_own_title = markdown_content.lstrip().startswith("# ")

            # --- Build the title / header block (always H1) ---
            title_block = ""
            if content_has_own_title:
                # Content already starts with an H1 — we keep it as-is,
                # but bio/sm/rel sections (all H2) must NOT precede it.
                # Solution: insert them AFTER the first H1 block.
                title_block = ""
            else:
                title_block = (
                    f"# {title}\n\n"
                    f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"
                )

            # Parse biography section → Markdown
            bio_md = ""
            if biography_section:
                raw_bio = biography_section
                if raw_bio.startswith("BIOGRAPHY_SECTION:"):
                    raw_bio = raw_bio.split(":", 1)[1]
                raw_bio = raw_bio.strip()
                if raw_bio and "No biography data" not in raw_bio:
                    bio_lines = ["## Biographical Profile", ""]
                    for line in raw_bio.splitlines():
                        s = line.strip()
                        if not s or s.startswith("[ BIOGRAPHY ]"):
                            continue
                        if ":" in s:
                            parts = s.split(":", 1)
                            field = parts[0].strip()
                            value = parts[1].strip()
                            bio_lines.append(f"**{field}:** {value}")
                    if len(bio_lines) > 2:
                        bio_md = "\n".join(bio_lines) + "\n\n"

            # Collect all H2-level supplementary sections
            supplement_md = ""
            if subject_exists:
                img_filename = Path(subject_image_path).name
                supplement_md += (
                    f'<div align="center">\n\n'
                    f"![Subject Portrait]({img_filename})\n\n"
                    f"</div>\n\n"
                )
            if bio_md:
                supplement_md += bio_md
            if sm_md:
                supplement_md += sm_md + "\n\n"
            if rel_md:
                supplement_md += rel_md

            # --- Assemble final markdown (H1 always first) ---
            if content_has_own_title:
                # Insert supplementary H2 sections right after the first H1 line(s)
                # so the TOC hierarchy is respected: H1 → H2 → ...
                lines = markdown_content.splitlines()
                insert_idx = 0
                # Skip past the first H1 (and any immediately following non-heading lines)
                for i, line in enumerate(lines):
                    if line.strip().startswith("# ") and not line.strip().startswith("##"):
                        insert_idx = i + 1
                        # Also skip blank lines right after the title
                        while insert_idx < len(lines) and lines[insert_idx].strip() == "":
                            insert_idx += 1
                        break
                # If we found an H1, insert supplements after it; otherwise prepend
                if insert_idx > 0:
                    final_markdown = (
                        "\n".join(lines[:insert_idx]) + "\n\n"
                        + supplement_md + "\n"
                        + "\n".join(lines[insert_idx:])
                    )
                else:
                    # No H1 found despite content_has_own_title — add one
                    final_markdown = (
                        f"# {title}\n\n" + supplement_md + "\n"
                        + "---\n\n" + markdown_content
                    )
            else:
                final_markdown = title_block + supplement_md + "---\n\n" + markdown_content

            if graph_exists:
                final_markdown += (
                    f"\n\n## Entity Relationship Network\n\n"
                    f"![Network Graph]({Path(graph_image_path).name})\n"
                )

            # --- Determine safe TOC level ---
            # markdown-pdf requires the first heading to be H1 when toc_level >= 1.
            _first_h = re.search(r'^(#{1,6})\s', final_markdown, re.MULTILINE)
            _use_toc = 2 if (_first_h and len(_first_h.group(1)) == 1) else 0

            section_kwargs = {"root": img_root} if img_root else {}
            try:
                pdf = MarkdownPdf(toc_level=_use_toc, optimize=True)
            except TypeError:
                try:
                    pdf = MarkdownPdf(toc_level=_use_toc)
                except TypeError:
                    pdf = MarkdownPdf()

            pdf.meta["title"] = title
            pdf.add_section(Section(final_markdown, **section_kwargs))
            pdf.save(filepath)

            # Persist PDF blob to SQLite for durable storage
            try:
                import sqlite3 as _sqlite3
                from tools.config import DB_PATH as _DB_PATH
                _blob = Path(filepath).read_bytes()
                with _sqlite3.connect(_DB_PATH) as _conn:
                    _conn.execute("""
                        CREATE TABLE IF NOT EXISTS session_artifacts (
                            artifact_id INTEGER PRIMARY KEY AUTOINCREMENT,
                            filename TEXT NOT NULL, file_blob BLOB NOT NULL,
                            created_at TEXT DEFAULT (datetime('now'))
                        )
                    """)
                    _conn.execute("INSERT INTO session_artifacts (filename, file_blob) VALUES (?, ?)",
                                  (safe_name, _blob))
                    _conn.commit()
            except Exception:
                pass

            return filepath

        except Exception as e:
            return f"Error generating PDF: {e}"


# ---------------------------------------------------------------------------
# Document loading — Markdown and PDF
# ---------------------------------------------------------------------------

class FilePathInput(BaseModel):
    file_path: str = Field(..., description="Absolute or relative path to the file to load.")
    max_chars: int = Field(default=8000, description="Maximum characters to return (0 = unlimited).")


class AMLReportInput(BaseModel):
    file_path: str = Field(..., description="Path to an AML report (.md or .pdf). Type is auto-detected.")
    max_chars: int = Field(default=8000, description="Maximum characters to return (0 = unlimited).")


def _truncate(text: str, max_chars: int) -> str:
    if max_chars <= 0 or len(text) <= max_chars:
        return text
    return text[:max_chars] + f"\n\n... [TRUNCATED at {max_chars} chars — set max_chars=0 for full content]"


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
        return "(PDF loaded but contained no extractable text — may be scanned/image-only.)"
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
        "Loads and returns the full text content of a Markdown (.md) file. "
        "Use to read back AML reports, research summaries, or any stored Markdown document. "
        "Input: file_path, max_chars (optional, default 8000; 0 for full document)."
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
        "Loads and returns the full text content of a PDF (.pdf) file, page by page. "
        "Use to read back AML compliance reports or any stored PDF. "
        "Input: file_path, max_chars (optional, default 8000; 0 for full document). "
        "Note: image-only / scanned PDFs may return empty content."
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
    description: str = (
        "Loads a previously generated AML compliance report from disk. "
        "Accepts both Markdown (.md) and PDF (.pdf) — detects the type automatically. "
        "Use for secondary review, re-scoring, appeal processing, or compliance audit. "
        "Input: file_path, max_chars (optional, default 8000; 0 for full document)."
    )
    args_schema: Type[BaseModel] = AMLReportInput

    def _run(self, file_path: str, max_chars: int = 8000) -> str:
        try:
            ext = Path(file_path).suffix.lower()
            if ext == ".md":
                text = _load_markdown(file_path)
            elif ext == ".pdf":
                text = _load_pdf(file_path)
            else:
                return f"AML_REPORT_LOAD_ERROR: Unsupported file type '{ext}'. Only .md and .pdf supported."
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
