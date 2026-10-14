import re
import asyncio
import logging
from pathlib import Path
from typing import Optional, Dict, Any, Tuple
from nicegui import run

from core.database.mongo_manager import mongo_db
from core.ai_engine.llm_engine import tars_engine
from core.utils.text_extractor import extract_text_from_file
from core.auth.jwt_handler import get_current_user_role

logger = logging.getLogger("BOOK_DETAILS_SERVICE")


class BookDetailsService:
    """
    Dedicated business logic & database service for Book Details view.
    Decoupled from UI rendering to ensure 100% unit-testability and clean separation of concerns.
    """

    @staticmethod
    def format_synopsis_text(raw_text: str) -> str:
        """
        Cleans and normalizes book synopsis content:
        - Strips Unicode mojibake / corrupted replacement characters
        - Normalizes curly/smart quotes and dashes to standard typography
        - Removes raw dashed divider lines that falsely trigger Markdown Setext <h2> headings
        - Collapses excess whitespace
        """
        if not raw_text:
            return ""

        text = raw_text.replace("\ufffd", "'").replace("\x92", "'").replace("\x91", "'")
        text = text.replace("\x93", '"').replace("\x94", '"')
        text = text.replace("\u2018", "'").replace("\u2019", "'")
        text = text.replace("\u201c", '"').replace("\u201d", '"')
        text = text.replace("\u2014", " - ").replace("\u2013", "-")

        lines = text.splitlines()
        clean_lines = []
        for line in lines:
            stripped = line.strip()
            if re.match(r"^[-=_*~]{3,}$", stripped):
                clean_lines.append("")
            else:
                clean_lines.append(stripped)

        text = "\n".join(clean_lines)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    async def load_book_data(self, book_id: str, user_id: str) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
        """Loads book details and user reading progress from MongoDB with automatic page count resolution."""
        book = await mongo_db.get_book_details(book_id)
        if not book:
            return None, None

        if not book.get('page_count') or int(book.get('page_count', 0)) <= 1:
            try:
                resolved_pc = await mongo_db.get_or_resolve_page_count(book_id, book)
                if resolved_pc > 0:
                    book['page_count'] = resolved_pc
            except Exception:
                pass

        reading_progress = None
        try:
            reading_progress = await mongo_db.get_reading_progress(user_id, book_id)
        except Exception:
            pass

        return book, reading_progress

    def get_effective_total_pages(self, book: Optional[Dict[str, Any]], reading_progress: Optional[Dict[str, Any]]) -> int:
        """Determines authoritative total page count from metadata, user progress, or fallback."""
        book_pages = 0
        if book and isinstance(book.get('page_count'), (int, float)):
            book_pages = int(book['page_count'])

        prog_pages = 0
        if reading_progress and isinstance(reading_progress.get('total_pages'), (int, float)):
            prog_pages = int(reading_progress['total_pages'])

        tot = max(book_pages, prog_pages)
        return tot if tot > 1 else (tot if tot == 1 else 100)

    @staticmethod
    def calculate_reading_status(new_status: str, total_pages: int, current_page: int = 0) -> Dict[str, Any]:
        """Calculates normalized reading status coordinates and percentages."""
        if new_status in ('to_read', 'want_to_read'):
            status_key = 'want_to_read'
            cur_page = 0
            pct_val = 0.0
            display_title = 'Want to Read'
        elif new_status in ('reading', 'currently_reading', 'in_progress'):
            status_key = 'reading'
            cur_page = current_page if (0 < current_page < total_pages) else 1
            pct_val = round((cur_page / max(total_pages, 1)) * 100.0, 1)
            display_title = 'Currently Reading'
        elif new_status in ('completed', 'done', 'finished'):
            status_key = 'completed'
            cur_page = total_pages
            pct_val = 100.0
            display_title = 'Completed'
        else:
            status_key = new_status
            cur_page = 0
            pct_val = 0.0
            display_title = new_status.replace('_', ' ').title()

        return {
            'status': status_key,
            'current_page': cur_page,
            'total_pages': total_pages,
            'progress_percent': pct_val,
            'display_title': display_title
        }

    @staticmethod
    def calculate_page_progress(page_val: int, total_pages: int) -> Dict[str, Any]:
        """Calculates normalized page coordinates and percentages."""
        effective_total = max(page_val, total_pages)
        clamped_page = max(1, min(page_val, effective_total))
        pct_val = round((clamped_page / max(effective_total, 1)) * 100.0, 1)
        status_key = 'completed' if (clamped_page >= effective_total and effective_total > 1) else 'reading'

        return {
            'status': status_key,
            'current_page': clamped_page,
            'total_pages': effective_total,
            'progress_percent': pct_val
        }

    async def save_reading_status(
        self,
        book_id: str,
        user_id: str,
        new_status: str,
        total_pages: int,
        current_page: int = 0
    ) -> Dict[str, Any]:
        """Normalizes and persists reading status updates strictly per user."""
        res = self.calculate_reading_status(new_status, total_pages, current_page)
        try:
            if user_id:
                await mongo_db.progress.save_reading_progress(
                    user_id=user_id,
                    book_id=book_id,
                    current_page=res['current_page'],
                    total_pages=total_pages,
                    status=res['status']
                )
        except Exception as err:
            logger.error(f"Error persisting reading status: {err}")

        return res

    async def save_page_progress(
        self,
        book_id: str,
        user_id: str,
        page_val: int,
        total_pages: int
    ) -> Dict[str, Any]:
        """Normalizes and persists active page stepper coordinates strictly per user."""
        effective_total = max(page_val, total_pages)
        clamped_page = max(1, min(page_val, effective_total))
        pct_val = round((clamped_page / max(effective_total, 1)) * 100.0, 1)
        status_key = 'completed' if (clamped_page >= effective_total and effective_total > 1) else 'reading'

        try:
            if user_id:
                await mongo_db.progress.save_reading_progress(
                    user_id=user_id,
                    book_id=book_id,
                    current_page=clamped_page,
                    total_pages=effective_total,
                    status=status_key
                )
        except Exception as err:
            logger.error(f"Error persisting page progress: {err}")

        return {
            'status': status_key,
            'current_page': clamped_page,
            'total_pages': effective_total,
            'progress_percent': pct_val
        }

    async def update_metadata(self, book_id: str, updates: Dict[str, Any]) -> Tuple[bool, str]:
        """RBAC-protected book metadata updater (Librarian/Admin only)."""
        if get_current_user_role() not in ('admin', 'librarian'):
            return False, "Unauthorized. Only Librarians and Administrators can edit metadata."

        success = await mongo_db.update_book_metadata(book_id, updates)
        return (True, "Metadata updated successfully.") if success else (False, "Failed to persist metadata updates.")

    async def delete_book(self, book_id: str) -> Tuple[bool, str]:
        """RBAC-protected document removal (Librarian/Admin only)."""
        if get_current_user_role() not in ('admin', 'librarian'):
            return False, "Unauthorized. Only Librarians and Administrators can delete books."

        success = await mongo_db.delete_book(book_id)
        return (True, "Document permanently removed.") if success else (False, "Could not delete document.")

    async def toggle_favorite(self, book_id: str, user_id: Optional[str] = None) -> bool:
        """Toggles bookmark favorite status isolated to the user."""
        return await mongo_db.toggle_book_favorite(book_id, user_id=user_id)

    async def generate_ai_synopsis(
        self,
        book_id: str,
        book: Dict[str, Any],
        title: str,
        author_name: str,
        file_type: str
    ) -> Tuple[bool, str]:
        """Extracts text excerpt from document and generates an AI summary via TARS LLM Engine."""
        try:
            target_path = mongo_db.resolve_document_path(book_id, book)
            extracted_text = ""
            if target_path and Path(target_path).exists():
                extracted_text = await run.io_bound(extract_text_from_file, target_path)

            if not extracted_text or not extracted_text.strip():
                extracted_text = f"Title: {title}. Author: {author_name}. File format: {file_type}."

            excerpt = extracted_text[:3500]
            prompt = (
                f"You are an expert literary curator and researcher for Libre-Library. "
                f"Write an engaging, clear, and comprehensive 2 to 3 paragraph synopsis "
                f"for the following document titled '{title}' by '{author_name}'.\n\n"
                f"Document Excerpt:\n{excerpt}\n\n"
                f"Format output in clean markdown paragraphs. Do not include metadata preambles, greetings, or conclusions."
            )

            generated = await tars_engine.generate_response(prompt, max_tokens=350)
            clean_synopsis = self.format_synopsis_text(generated) if generated else ""

            if clean_synopsis:
                await mongo_db.progress.save_book_summary(book_id, clean_synopsis)
                await mongo_db.update_book_metadata(book_id, {'description': clean_synopsis})
                return True, clean_synopsis
            return False, "AI could not produce a synopsis. Please try again."
        except Exception as err:
            logger.error(f"Error generating AI synopsis: {err}")
            return False, f"Generation error: {err}"


book_details_service = BookDetailsService()
