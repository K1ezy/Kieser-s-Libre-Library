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
            from pypdf import PdfReader
            reader = PdfReader(str(path))
            pages = []
            for i, page in enumerate(reader.pages):
                extracted = page.extract_text()
                if extracted and extracted.strip():
                    pages.append(f"[Page {i+1}]\n{extracted.strip()}")
            text = "\n\n".join(pages)

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