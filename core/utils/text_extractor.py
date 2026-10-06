import os
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger("TEXT_EXTRACTOR")

def extract_text_from_file(filepath: str) -> str:
    """
    High-performance native text extractor for documents.
    Supports: PDF, EPUB, DOCX, PPTX, TXT, MD.
    Does not require heavy or unstable 'unstructured' dependencies.
    """
    path = Path(filepath)
    if not path.exists() or path.stat().st_size == 0:
        return ""

    ext = path.suffix.lower()
    text = ""

    try:
        if ext == '.pdf':
            extracted_pages = []
            try:
                import fitz  # PyMuPDF: C-accelerated high performance PDF engine
                doc = fitz.open(str(path))
                for i, page in enumerate(doc):
                    t = page.get_text()
                    if t and t.strip():
                        extracted_pages.append(f"[Page {i+1}]\n{t.strip()}")
                doc.close()
            except Exception as fitz_err:
                logger.debug(f"PyMuPDF unavailable or error ({fitz_err}), falling back to pypdf.")
                from pypdf import PdfReader
                reader = PdfReader(str(path))
                for i, page in enumerate(reader.pages):
                    extracted = page.extract_text()
                    if extracted and extracted.strip():
                        extracted_pages.append(f"[Page {i+1}]\n{extracted.strip()}")
            text = "\n\n".join(extracted_pages)

        elif ext == '.docx':
            import docx
            doc = docx.Document(str(path))
            parts = []
            for p in doc.paragraphs:
                if p.text.strip():
                    parts.append(p.text.strip())
            for table in doc.tables:
                for row in table.rows:
                    row_txt = [c.text.strip() for c in row.cells if c.text.strip()]
                    if row_txt:
                        parts.append(" | ".join(row_txt))
            text = "\n\n".join(parts)

        elif ext in ('.pptx', '.ppt'):
            from pptx import Presentation
            prs = Presentation(str(path))
            slides = []
            for i, slide in enumerate(prs.slides):
                slide_lines = []
                for shape in slide.shapes:
                    if hasattr(shape, "text") and shape.text.strip():
                        slide_lines.append(shape.text.strip())
                if slide.has_notes_slide and slide.notes_slide.notes_text_frame:
                    notes = slide.notes_slide.notes_text_frame.text.strip()
                    if notes:
                        slide_lines.append(f"[Notes: {notes}]")
                if slide_lines:
                    slides.append(f"--- Slide {i+1} ---\n" + "\n".join(slide_lines))
            text = "\n\n".join(slides)

        elif ext == '.epub':
            try:
                import ebooklib
                from ebooklib import epub
                from bs4 import BeautifulSoup
                book = epub.read_epub(str(path))
                parts = []
                for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT):
                    soup = BeautifulSoup(item.get_content(), 'html.parser')
                    t = soup.get_text()
                    if t.strip():
                        parts.append(t.strip())
                text = "\n\n".join(parts)
            except Exception as epub_err:
                logger.warning(f"EPUB extraction fallback: {epub_err}")

        elif ext in ('.txt', '.md', '.csv', '.json', '.log'):
            with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                text = f.read()

        else:
            logger.warning(f"Unsupported file extension for extraction: {ext}")
            return ""

    except Exception as e:
        logger.error(f"Error extracting text from {path.name}: {e}")
        return ""

    # Clean text: remove null bytes and strip excess whitespace
    if text:
        text = text.replace('\x00', '')
    return text.strip()


def extract_document_structure(filepath: str) -> list:
    """
    Extracts structured document units (pages, slides, or chapters) 
    with their respective page numbers.
    Returns: List of dicts [{"page": int, "type": str, "text": str}]
    """
    path = Path(filepath)
    if not path.exists() or path.stat().st_size == 0:
        return []

    ext = path.suffix.lower()
    sections = []

    try:
        if ext == '.pdf':
            try:
                import fitz  # PyMuPDF: C-accelerated structure parsing
                doc = fitz.open(str(path))
                for i, page in enumerate(doc):
                    t = page.get_text()
                    if t and t.strip():
                        clean = t.replace('\x00', '').strip()
                        if clean:
                            sections.append({"page": i + 1, "type": "page", "text": clean})
                doc.close()
            except Exception as fitz_err:
                logger.debug(f"PyMuPDF structured extraction fallback to pypdf: {fitz_err}")
                from pypdf import PdfReader
                reader = PdfReader(str(path))
                for i, page in enumerate(reader.pages):
                    extracted = page.extract_text()
                    if extracted and extracted.strip():
                        clean = extracted.replace('\x00', '').strip()
                        if clean:
                            sections.append({"page": i + 1, "type": "page", "text": clean})

        elif ext in ('.pptx', '.ppt'):
            from pptx import Presentation
            prs = Presentation(str(path))
            for i, slide in enumerate(prs.slides):
                slide_lines = []
                for shape in slide.shapes:
                    if hasattr(shape, "text") and shape.text.strip():
                        slide_lines.append(shape.text.strip())
                if slide.has_notes_slide and slide.notes_slide.notes_text_frame:
                    notes = slide.notes_slide.notes_text_frame.text.strip()
                    if notes:
                        slide_lines.append(f"[Notes: {notes}]")
                if slide_lines:
                    clean = "\n".join(slide_lines).replace('\x00', '').strip()
                    sections.append({"page": i + 1, "type": "slide", "text": clean})

        elif ext == '.epub':
            try:
                import ebooklib
                from ebooklib import epub
                from bs4 import BeautifulSoup
                book = epub.read_epub(str(path))
                idx = 1
                for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT):
                    soup = BeautifulSoup(item.get_content(), 'html.parser')
                    t = soup.get_text()
                    if t and t.strip():
                        clean = t.replace('\x00', '').strip()
                        sections.append({"page": idx, "type": "chapter", "text": clean})
                        idx += 1
            except Exception as e:
                logger.warning(f"Structured EPUB extraction notice: {e}")

        elif ext == '.docx':
            import docx
            doc = docx.Document(str(path))
            current_section = []
            sec_idx = 1
            for p in doc.paragraphs:
                if p.text.strip():
                    current_section.append(p.text.strip())
                # Group every ~20 paragraphs as a readable logical page/section
                if len(current_section) >= 20:
                    sections.append({"page": sec_idx, "type": "section", "text": "\n".join(current_section)})
                    sec_idx += 1
                    current_section = []
            if current_section:
                sections.append({"page": sec_idx, "type": "section", "text": "\n".join(current_section)})

        else:
            # Fallback for plain text, markdown, etc.
            raw = extract_text_from_file(filepath)
            if raw:
                # Split roughly by 3000 chars as virtual pages
                lines = raw.split('\n')
                curr_lines = []
                curr_len = 0
                page_idx = 1
                for line in lines:
                    curr_lines.append(line)
                    curr_len += len(line)
                    if curr_len > 3000:
                        sections.append({"page": page_idx, "type": "page", "text": "\n".join(curr_lines)})
                        page_idx += 1
                        curr_lines = []
                        curr_len = 0
                if curr_lines:
                    sections.append({"page": page_idx, "type": "page", "text": "\n".join(curr_lines)})

    except Exception as e:
        logger.error(f"Error in extract_document_structure: {e}")

    # Fallback to single page if nothing segmented
    if not sections:
        full = extract_text_from_file(filepath)
        if full:
            sections.append({"page": 1, "type": "document", "text": full})

    return sections