from nicegui import ui, app, run
from pathlib import Path
import asyncio
import logging
import math
from datetime import datetime
from typing import Optional, Dict, Any, List

from components.sidebar import sidebar
from components.header import header
from components.bottom_nav import bottom_nav
from core.database.mongo_manager import mongo_db
from core.config import settings
from core.ai_engine.llm_engine import tars_engine
from core.utils.text_extractor import extract_text_from_file

logger = logging.getLogger("BOOK_DETAILS")


class BookDetailsPage:
    """
    Comprehensive, high-performance Book Details & Preview view.
    
    Fixes & Enhancements:
    - Tight aspect-ratio cover container with fit="cover" (permanently fixes 'white chin')
    - Full-resolution cover zoom lightbox modal
    - Native Quasar CTA buttons with clear labels (permanently fixes 'phantom empty pill')
    - Wide desktop-optimized layout (max-w-7xl) with HCI-focused information hierarchy
    - Inline 'Edit Metadata' dialog for title, author, shelves, tags, publisher, and year
    - Dynamic 'Generate Synopsis with AI' CTA for empty or custom descriptions
    - Rich Document Specs Grid: Format, Language, Pages, Est. Reading Time, File Size, Added Date
    - Scoped Document Actions: 'Chat with Book' (pre-scoped TARS RAG), 'Executive Summary', 'Flashcards'
    - Local file downloader and persistent reading progress tracker
    - Delete/Archive book dialog with confirmation safety
    """

    def __init__(self, book_id: str):
        self.book_id = str(book_id).strip()
        self.book: Optional[Dict[str, Any]] = None
        self.reading_progress: Optional[Dict[str, Any]] = None
        self.content_container = None
        self.reading_card_container = None

    async def init(self):
        self.book = await mongo_db.get_book_details(self.book_id)
        if not self.book:
            ui.notify("Book not found in library.", type='negative')
            ui.navigate.to('/books')
            return

        user_id = app.storage.user.get('user_id') or app.storage.user.get('token') or 'guest'
        try:
            self.reading_progress = await mongo_db.get_reading_progress(user_id, self.book_id)
        except Exception:
            self.reading_progress = None

        self.render_content()

    def refresh_ui(self):
        if self.content_container:
            self.content_container.clear()
            self.render_content()

    def render_reading_card(self):
        if not self.reading_card_container or not self.book:
            return

        self.reading_card_container.clear()

        # 1. Status normalization
        raw_status = self.book.get('reading_status', 'want_to_read')
        if self.reading_progress and self.reading_progress.get('status'):
            raw_status = self.reading_progress.get('status')

        if raw_status in ('to_read', 'want_to_read'):
            normalized_status = 'want_to_read'
        elif raw_status in ('reading', 'currently_reading', 'in_progress'):
            normalized_status = 'reading'
        elif raw_status in ('completed', 'done', 'finished'):
            normalized_status = 'completed'
        else:
            normalized_status = 'want_to_read'

        # 2. Pages and progress percentage calculation
        page_count = self.book.get('page_count') or 1
        total_pages = int(page_count) if isinstance(page_count, (int, float)) and page_count > 0 else 1

        current_page = 0
        progress_percent = 0.0

        if self.reading_progress:
            total_pages = int(self.reading_progress.get('total_pages', total_pages)) or total_pages
            current_page = int(self.reading_progress.get('current_page', 0))
            progress_percent = float(self.reading_progress.get('progress_percent', 0.0))

        if total_pages <= 0:
            total_pages = 1

        if normalized_status == 'completed':
            current_page = total_pages
            progress_percent = 100.0
        elif normalized_status == 'want_to_read':
            current_page = 0
            progress_percent = 0.0
        elif normalized_status == 'reading':
            if current_page <= 0:
                current_page = 1
            elif current_page > total_pages:
                current_page = total_pages
            progress_percent = round((current_page / max(total_pages, 1)) * 100.0, 1)

        # 3. Visual configuration for badges and progress bar
        status_configs = {
            'completed': {
                'badge_bg': 'bg-emerald-50',
                'badge_text': 'text-emerald-700',
                'badge_border': 'border-emerald-200',
                'badge_label': 'Completed',
                'badge_icon': 'check_circle',
                'bar_color': 'emerald',
                'subtext': f"Finished • {total_pages} pages (100%)",
            },
            'reading': {
                'badge_bg': 'bg-indigo-50',
                'badge_text': 'text-indigo-700',
                'badge_border': 'border-indigo-200',
                'badge_label': 'Currently Reading',
                'badge_icon': 'auto_stories',
                'bar_color': 'indigo',
                'subtext': f"Page {current_page} of {total_pages} ({progress_percent:.0f}%)",
            },
            'want_to_read': {
                'badge_bg': 'bg-amber-50',
                'badge_text': 'text-amber-700',
                'badge_border': 'border-amber-200',
                'badge_label': 'Want to Read',
                'badge_icon': 'bookmark',
                'bar_color': 'amber',
                'subtext': "Not started yet (0%)",
            },
        }
        cfg = status_configs[normalized_status]

        with self.reading_card_container:
            with ui.card().classes(
                'w-full p-4 bg-slate-50/90 rounded-2xl border border-slate-200 shadow-xs flex flex-col gap-3 transition-all duration-300'
            ):
                # Header row: Title & Active Badge
                with ui.row().classes('w-full justify-between items-center'):
                    with ui.row().classes('items-center gap-1.5'):
                        ui.icon('auto_stories', size='18px').classes('text-indigo-600')
                        ui.label('Reading Status').classes('text-xs font-black text-slate-800 uppercase tracking-wider')

                    with ui.element('div').classes(
                        f'px-2.5 py-0.5 rounded-lg text-xs font-bold border flex items-center gap-1 {cfg["badge_bg"]} {cfg["badge_text"]} {cfg["badge_border"]}'
                    ):
                        ui.icon(cfg['badge_icon'], size='13px')
                        ui.label(cfg['badge_label'])

                # Linear Progress Bar
                progress_fraction = min(max(progress_percent / 100.0, 0.0), 1.0)
                ui.linear_progress(value=progress_fraction, show_value=False)\
                    .props(f'rounded color={cfg["bar_color"]} size=6px track-color=grey-3')

                # Subtext & Percentage Info
                with ui.row().classes('w-full justify-between items-center text-[11px] text-slate-500 font-medium'):
                    ui.label(cfg['subtext'])
                    ui.label(f"{progress_percent:.0f}%").classes('font-bold text-slate-700')

                # The 3 Status Selector Buttons
                with ui.row().classes('w-full grid grid-cols-3 gap-1.5 pt-1'):
                    # 1. Want to Read
                    wtr_active = (normalized_status == 'want_to_read')
                    wtr_cls = (
                        'bg-amber-500 text-white shadow-sm ring-2 ring-amber-300/60 font-bold'
                        if wtr_active else
                        'bg-white text-slate-700 hover:bg-amber-50/70 hover:text-amber-700 border border-slate-200 font-semibold'
                    )
                    with ui.button(on_click=lambda: self.update_reading_status('want_to_read'))\
                        .props('flat dense size=sm')\
                        .classes(f'flex flex-col items-center justify-center py-2 px-1 rounded-xl transition-all duration-200 {wtr_cls}'):
                        ui.icon('bookmark', size='16px').classes('shrink-0')
                        ui.label('Want to read').classes('text-[10px] sm:text-[11px] leading-tight text-center mt-0.5 truncate w-full')

                    # 2. Currently Reading
                    cr_active = (normalized_status == 'reading')
                    cr_cls = (
                        'bg-indigo-600 text-white shadow-sm ring-2 ring-indigo-300/60 font-bold'
                        if cr_active else
                        'bg-white text-slate-700 hover:bg-indigo-50/70 hover:text-indigo-700 border border-slate-200 font-semibold'
                    )
                    with ui.button(on_click=lambda: self.update_reading_status('reading'))\
                        .props('flat dense size=sm')\
                        .classes(f'flex flex-col items-center justify-center py-2 px-1 rounded-xl transition-all duration-200 {cr_cls}'):
                        ui.icon('auto_stories', size='16px').classes('shrink-0')
                        ui.label('Currently reading').classes('text-[10px] sm:text-[11px] leading-tight text-center mt-0.5 truncate w-full')

                    # 3. Completed
                    done_active = (normalized_status == 'completed')
                    done_cls = (
                        'bg-emerald-600 text-white shadow-sm ring-2 ring-emerald-300/60 font-bold'
                        if done_active else
                        'bg-white text-slate-700 hover:bg-emerald-50/70 hover:text-emerald-700 border border-slate-200 font-semibold'
                    )
                    with ui.button(on_click=lambda: self.update_reading_status('completed'))\
                        .props('flat dense size=sm')\
                        .classes(f'flex flex-col items-center justify-center py-2 px-1 rounded-xl transition-all duration-200 {done_cls}'):
                        ui.icon('check_circle', size='16px').classes('shrink-0')
                        ui.label('Completed').classes('text-[10px] sm:text-[11px] leading-tight text-center mt-0.5 truncate w-full')

                # Active page quick updater (appears when Currently Reading)
                if normalized_status == 'reading':
                    with ui.row().classes('w-full items-center justify-between gap-2 pt-2 mt-1 border-t border-slate-200/60'):
                        ui.label('Active page:').classes('text-[11px] text-slate-500 font-semibold')
                        with ui.row().classes('items-center gap-1'):
                            page_num = ui.number(value=current_page, min=1, max=total_pages, step=1)\
                                .props('outlined dense size=xs').classes('w-20 text-xs bg-white rounded-lg')
                            with ui.button(
                                icon='check',
                                on_click=lambda: self.update_page_number(int(page_num.value or 1))
                            ).props('flat round dense size=xs color=indigo').classes('bg-indigo-50 hover:bg-indigo-100 p-1'):
                                ui.tooltip('Save page progress')

    async def update_reading_status(self, new_status: str):
        if not self.book:
            return

        # 1. Normalize status
        if new_status in ('to_read', 'want_to_read'):
            status_key = 'want_to_read'
            cur_page = 0
            pct_val = 0.0
            display_title = 'Want to Read'
        elif new_status in ('reading', 'currently_reading', 'in_progress'):
            status_key = 'reading'
            cur = int(self.reading_progress.get('current_page', 0)) if self.reading_progress else 0
            tot = self.book.get('page_count') or 1
            tot = int(tot) if isinstance(tot, (int, float)) and tot > 0 else 1
            cur_page = cur if (0 < cur < tot) else 1
            pct_val = round((cur_page / max(tot, 1)) * 100.0, 1)
            display_title = 'Currently Reading'
        elif new_status in ('completed', 'done', 'finished'):
            status_key = 'completed'
            tot = self.book.get('page_count') or 1
            tot = int(tot) if isinstance(tot, (int, float)) and tot > 0 else 1
            cur_page = tot
            pct_val = 100.0
            display_title = 'Completed'
        else:
            status_key = new_status
            cur_page = 0
            pct_val = 0.0
            display_title = new_status.replace('_', ' ').title()

        page_count = self.book.get('page_count') or 1
        tot_pages = int(page_count) if isinstance(page_count, (int, float)) and page_count > 0 else 1

        # 2. Update local state immediately
        self.book['reading_status'] = status_key
        if not self.reading_progress:
            self.reading_progress = {}
        self.reading_progress['status'] = status_key
        self.reading_progress['current_page'] = cur_page
        self.reading_progress['total_pages'] = tot_pages
        self.reading_progress['progress_percent'] = pct_val

        # 3. Update UI reactively in place (fast, responsive, zero white-screen)
        self.render_reading_card()
        ui.notify(f"Marked as {display_title}", type='positive')

        # 4. Async DB persistence
        user_id = app.storage.user.get('user_id') or app.storage.user.get('token') or 'guest'
        try:
            await mongo_db.update_book_reading_status(self.book_id, status_key)
            if user_id:
                await mongo_db.progress.save_reading_progress(
                    user_id=user_id,
                    book_id=self.book_id,
                    current_page=cur_page,
                    total_pages=tot_pages,
                    status=status_key
                )
        except Exception as err:
            logger.error(f"Error persisting reading status: {err}")

    async def update_page_number(self, page_val: int):
        if not self.book:
            return

        page_count = self.book.get('page_count') or 1
        tot_pages = int(page_count) if isinstance(page_count, (int, float)) and page_count > 0 else 1
        page_val = max(1, min(page_val, tot_pages))
        pct_val = round((page_val / max(tot_pages, 1)) * 100.0, 1)
        status_key = 'completed' if page_val >= tot_pages else 'reading'

        self.book['reading_status'] = status_key
        if not self.reading_progress:
            self.reading_progress = {}
        self.reading_progress['status'] = status_key
        self.reading_progress['current_page'] = page_val
        self.reading_progress['total_pages'] = tot_pages
        self.reading_progress['progress_percent'] = pct_val

        self.render_reading_card()
        ui.notify(f"Updated: Page {page_val} of {tot_pages} ({pct_val:.0f}%)", type='positive')

        user_id = app.storage.user.get('user_id') or app.storage.user.get('token') or 'guest'
        try:
            await mongo_db.update_book_reading_status(self.book_id, status_key)
            if user_id:
                await mongo_db.progress.save_reading_progress(
                    user_id=user_id,
                    book_id=self.book_id,
                    current_page=page_val,
                    total_pages=tot_pages,
                    status=status_key
                )
        except Exception as err:
            logger.error(f"Error persisting page progress: {err}")

    def render_content(self):
        if not self.content_container or not self.book:
            return

        # -------------------------------------------------------------
        # 1. METADATA EXTRACTION & RESOLUTION
        # -------------------------------------------------------------
        title = self.book.get('title') or 'Untitled'
        
        # Author resolution
        author_name = "Unknown"
        authors_data = self.book.get('display_author') or self.book.get('authors')
        if isinstance(authors_data, list) and authors_data:
            first = authors_data[0]
            author_name = first.get('name', 'Unknown') if isinstance(first, dict) else str(first)
        elif isinstance(authors_data, str) and authors_data.strip():
            author_name = authors_data.strip()

        # Document physical file resolution
        doc_path = mongo_db.resolve_document_path(self.book_id, self.book)
        file_type = (self.book.get('file_type') or 'E-Book').upper()
        if doc_path and Path(doc_path).exists():
            ext = Path(doc_path).suffix.lower().replace('.', '').upper()
            if ext:
                file_type = ext

        # File size calculation
        file_size_bytes = self.book.get('file_size')
        if not file_size_bytes and doc_path and Path(doc_path).exists():
            try:
                file_size_bytes = Path(doc_path).stat().st_size
            except Exception:
                file_size_bytes = 0

        if file_size_bytes:
            if file_size_bytes >= 1024 * 1024:
                file_size_str = f"{file_size_bytes / (1024 * 1024):.1f} MB"
            else:
                file_size_str = f"{file_size_bytes / 1024:.0f} KB"
        else:
            file_size_str = "Unknown"

        # Page count & estimated reading time calculation
        page_count = self.book.get('page_count')
        if not page_count and doc_path and Path(doc_path).exists():
            ext_lower = Path(doc_path).suffix.lower()
            if ext_lower == '.pdf':
                try:
                    import fitz
                    pdf_doc = fitz.open(doc_path)
                    page_count = pdf_doc.page_count
                    pdf_doc.close()
                    # Cache back to database
                    asyncio.create_task(mongo_db.update_book_metadata(self.book_id, {'page_count': page_count}))
                    self.book['page_count'] = page_count
                except Exception:
                    pass

        if page_count and page_count > 0:
            est_mins = int(page_count * 1.5)
            if est_mins >= 60:
                reading_time_str = f"~{est_mins / 60:.1f} hrs"
            else:
                reading_time_str = f"~{est_mins} mins"
            pages_str = f"{page_count} Pages"
        else:
            reading_time_str = "~2.0 hrs"
            pages_str = "Standard Length"

        # Added date resolution
        raw_added = self.book.get('added_at')
        formatted_date = mongo_db.format_added_date(raw_added)
        if formatted_date == "Recently" and doc_path and Path(doc_path).exists():
            try:
                mtime = Path(doc_path).stat().st_mtime
                formatted_date = datetime.fromtimestamp(mtime).strftime("%b %d, %Y")
            except Exception:
                pass

        # Language resolution
        langs = self.book.get('languages') or ['en']
        lang_str = langs[0] if isinstance(langs, list) and langs else str(langs)

        # Synopsis resolution
        summaries = self.book.get('summaries')
        raw_desc = summaries[0] if summaries and isinstance(summaries, list) else self.book.get('description', '')
        has_real_synopsis = bool(raw_desc and raw_desc.strip() and raw_desc.strip() != 'No synopsis available for this document.')
        synopsis_text = raw_desc.strip() if has_real_synopsis else ""

        # Cover URL resolution
        disk_cover = settings.BASE_DIR / 'data' / 'books' / self.book_id / 'cover.jpg'
        if disk_cover.exists():
            cover_url = f"/static_books/{self.book_id}/cover.jpg"
        elif self.book.get('cover_image') and not str(self.book.get('cover_image')).endswith(('default_cover.png', 'default_cover.svg')):
            cover_url = self.book.get('cover_image')
        else:
            cover_url = "/static/default_cover.svg"

        # Shelves / Genres resolution
        shelves = self.book.get('shelves', []) or []
        genres = self.book.get('genres', []) or self.book.get('subjects', []) or []
        publisher = self.book.get('publisher') or ""
        pub_year = self.book.get('publication_year') or ""
        is_favorite = bool(self.book.get('is_favorite', False))

        user_id = app.storage.user.get('user_id') or app.storage.user.get('token') or 'guest'

        # -------------------------------------------------------------
        # 2. DIALOGS (Cover Lightbox, Edit Metadata, Delete Confirmation)
        # -------------------------------------------------------------
        # Cover Zoom Dialog
        def open_cover_dialog():
            with ui.dialog() as cover_dialog, ui.card().classes(
                'p-4 sm:p-5 bg-white/95 backdrop-blur-md rounded-3xl max-w-lg w-full items-center shadow-2xl border border-slate-200'
            ):
                with ui.row().classes('w-full justify-between items-center px-1 pb-3 border-b border-slate-100'):
                    with ui.column().classes('gap-0 max-w-[80%]'):
                        ui.label(title).classes('font-bold text-slate-800 text-sm sm:text-base truncate')
                        ui.label('Front Page Cover Preview').classes('text-xs text-indigo-600 font-semibold')
                    ui.button(icon='close', on_click=cover_dialog.close).props('flat round dense size=sm color=grey')
                with ui.element('div').classes('w-full max-h-[72vh] flex items-center justify-center overflow-hidden rounded-2xl my-3 bg-slate-50 border border-slate-100 shadow-inner'):
                    ui.image(cover_url).classes('max-h-[70vh] object-contain rounded-xl shadow-md')
                with ui.row().classes('w-full justify-end pt-1'):
                    ui.button('Close', on_click=cover_dialog.close).props('unelevated rounded-xl size=sm color=indigo font-bold')
            cover_dialog.open()

        # Edit Metadata Dialog
        def open_edit_metadata_dialog():
            with ui.dialog() as edit_dialog, ui.card().classes(
                'w-[calc(100vw-2rem)] max-w-2xl p-5 sm:p-6 bg-white rounded-3xl shadow-2xl border border-slate-200 max-h-[90vh] flex flex-col'
            ):
                with ui.row().classes('w-full justify-between items-center pb-3 border-b border-slate-100'):
                    with ui.row().classes('items-center gap-2'):
                        with ui.element('div').classes('p-2 rounded-xl bg-indigo-50 text-indigo-600'):
                            ui.icon('edit_note', size='20px')
                        ui.label('Edit Book Metadata').classes('text-lg font-black text-slate-900')
                    ui.button(icon='close', on_click=edit_dialog.close).props('flat round dense size=sm color=grey')

                with ui.column().classes('w-full gap-3.5 py-4 overflow-y-auto flex-grow no-scrollbar'):
                    title_input = ui.input(label='Title', value=title).props('outlined dense rounded').classes('w-full')
                    author_input = ui.input(label='Author(s)', value=author_name if author_name != 'Unknown' else '').props('outlined dense rounded').classes('w-full')
                    
                    with ui.row().classes('w-full gap-3 flex-col sm:flex-row'):
                        shelves_val = ", ".join(shelves) if isinstance(shelves, list) else str(shelves)
                        shelves_input = ui.input(label='Shelf / Category', value=shelves_val).props('outlined dense rounded').classes('flex-1')
                        
                        tags_val = ", ".join(genres) if isinstance(genres, list) else str(genres)
                        tags_input = ui.input(label='Tags / Genres (comma-separated)', value=tags_val).props('outlined dense rounded').classes('flex-1')

                    with ui.row().classes('w-full gap-3 flex-col sm:flex-row'):
                        pub_input = ui.input(label='Publisher', value=str(publisher)).props('outlined dense rounded').classes('flex-1')
                        year_input = ui.input(label='Publication Year', value=str(pub_year)).props('outlined dense rounded').classes('flex-1')

                    desc_input = ui.textarea(label='Synopsis / Description', value=synopsis_text).props('outlined rounded rows=5').classes('w-full text-sm')

                with ui.row().classes('w-full justify-end gap-2.5 pt-3 border-t border-slate-100'):
                    ui.button('Cancel', on_click=edit_dialog.close).props('flat rounded-xl color=grey font-bold size=sm')
                    
                    async def save_metadata():
                        new_title = title_input.value.strip() or title
                        new_author = author_input.value.strip() or 'Unknown'
                        new_pub = pub_input.value.strip()
                        new_year = year_input.value.strip()
                        new_desc = desc_input.value.strip()

                        clean_shelves = [s.strip() for s in shelves_input.value.split(',') if s.strip()]
                        clean_genres = [g.strip() for g in tags_input.value.split(',') if g.strip()]

                        updates = {
                            'title': new_title,
                            'display_author': new_author,
                            'authors': [new_author],
                            'publisher': new_pub,
                            'publication_year': new_year,
                            'description': new_desc,
                            'shelves': clean_shelves,
                            'genres': clean_genres,
                        }

                        success = await mongo_db.update_book_metadata(self.book_id, updates)
                        if success:
                            self.book.update(updates)
                            edit_dialog.close()
                            ui.notify('Book metadata updated successfully!', type='positive')
                            self.refresh_ui()
                        else:
                            ui.notify('Failed to save metadata updates.', type='negative')

                    ui.button('Save Changes', icon='save', on_click=save_metadata).props('unelevated rounded-xl color=indigo font-bold size=sm shadow-md')

            edit_dialog.open()

        # Delete Confirmation Dialog
        def open_delete_dialog():
            with ui.dialog() as del_dialog, ui.card().classes('p-5 sm:p-6 bg-white rounded-3xl max-w-md w-full shadow-2xl border border-slate-200'):
                with ui.row().classes('items-center gap-3 text-red-600 mb-2'):
                    with ui.element('div').classes('p-2.5 rounded-2xl bg-red-50 text-red-600 border border-red-100'):
                        ui.icon('warning', size='24px')
                    ui.label('Delete Document').classes('text-lg font-black text-slate-900')
                
                ui.label(
                    f"Are you sure you want to permanently remove '{title}' from your library? "
                    "This action cannot be undone."
                ).classes('text-sm text-slate-600 leading-relaxed mb-4')
                
                with ui.row().classes('w-full justify-end gap-2'):
                    ui.button('Cancel', on_click=del_dialog.close).props('flat rounded-xl color=grey font-bold size=sm')
                    
                    async def do_delete():
                        del_dialog.close()
                        success = await mongo_db.delete_book(self.book_id)
                        if success:
                            ui.notify(f"'{title}' has been deleted.", type='positive')
                            ui.navigate.to('/books')
                        else:
                            ui.notify('Could not delete document.', type='negative')

                    ui.button('Delete Permanently', icon='delete_forever', on_click=do_delete)\
                        .props('unelevated rounded-xl color=red font-bold size=sm shadow-md')

            del_dialog.open()

        # -------------------------------------------------------------
        # 3. INTERACTIVE ACTION HANDLERS
        # -------------------------------------------------------------
        def handle_download():
            target_path = mongo_db.resolve_document_path(self.book_id, self.book)
            if target_path and Path(target_path).exists():
                safe_title = "".join(c for c in title if c.isalnum() or c in (' ', '_', '-')).strip() or 'book'
                ext = Path(target_path).suffix or f".{file_type.lower()}"
                download_filename = f"{safe_title}{ext}"
                ui.download(target_path, filename=download_filename)
                ui.notify(f"Downloading {download_filename}...", type='info')
            else:
                ui.notify("Physical document file not found on disk.", type='warning')

        def open_chat_scoped():
            app.storage.user['chat_focus_book_id'] = self.book_id
            app.storage.user['chat_focus_book_title'] = title
            ui.navigate.to('/chat')

        def open_summarizer_scoped():
            app.storage.user['summarize_book_id'] = self.book_id
            ui.navigate.to('/summarizer')

        async def toggle_favorite():
            new_state = not is_favorite
            success = await mongo_db.toggle_book_favorite(self.book_id)
            if success:
                self.book['is_favorite'] = new_state
                ui.notify("Saved to Favorites!" if new_state else "Removed from Favorites.", type='positive' if new_state else 'info')
                self.refresh_ui()
            else:
                ui.notify("Failed to update favorite status.", type='warning')

        async def generate_ai_synopsis():
            spinner_dialog = ui.dialog()
            with spinner_dialog, ui.card().classes('p-6 items-center gap-3 bg-white rounded-3xl shadow-2xl border border-slate-200 text-center'):
                ui.spinner('dots', size='3rem', color='indigo')
                ui.label('Generating Synopsis with AI...').classes('font-black text-slate-800 text-base')
                ui.label('Extracting document excerpt and synthesizing comprehensive overview.').classes('text-xs text-slate-500 max-w-xs')
            spinner_dialog.open()

            try:
                target_path = mongo_db.resolve_document_path(self.book_id, self.book)
                extracted_text = ""
                if target_path and Path(target_path).exists():
                    extracted_text = await run.io_bound(extract_text_from_file, target_path)

                if not extracted_text or not extracted_text.strip():
                    extracted_text = f"Title: {title}. Author: {author_name}. File format: {file_type}."

                excerpt = extracted_text[:12000]
                prompt = (
                    f"You are an expert literary curator and researcher for Libre-Library. "
                    f"Write an engaging, clear, and comprehensive 2 to 3 paragraph synopsis "
                    f"for the following document titled '{title}' by '{author_name}'.\n\n"
                    f"Document Excerpt:\n{excerpt}\n\n"
                    f"Format output in clean markdown paragraphs. Do not include metadata preambles, greetings, or conclusions."
                )

                generated = await tars_engine.generate_response(prompt)
                clean_synopsis = generated.strip() if generated else ""

                if clean_synopsis:
                    await mongo_db.progress.save_book_summary(self.book_id, clean_synopsis)
                    await mongo_db.update_book_metadata(self.book_id, {'description': clean_synopsis})
                    self.book['description'] = clean_synopsis
                    self.book['summaries'] = [clean_synopsis]
                    spinner_dialog.close()
                    ui.notify("✨ Synopsis generated and saved successfully!", type='positive')
                    self.refresh_ui()
                else:
                    spinner_dialog.close()
                    ui.notify("AI could not produce a synopsis. Please try again.", type='warning')
            except Exception as err:
                spinner_dialog.close()
                logger.error(f"Error generating AI synopsis: {err}")
                ui.notify(f"Generation error: {err}", type='negative')

        # -------------------------------------------------------------
        # 4. VIEWPORT LAYOUT & COMPONENT ASSEMBLY
        # -------------------------------------------------------------
        with self.content_container:
            # BREADCRUMBS BAR
            primary_shelf = shelves[0] if (shelves and isinstance(shelves, list)) else (genres[0] if genres else 'Archive')
            with ui.row().classes('w-full items-center justify-between gap-2 mb-4 sm:mb-6 flex-wrap'):
                with ui.row().classes('items-center gap-2 text-xs sm:text-sm font-semibold text-slate-500'):
                    ui.button('Back to Archive', icon='arrow_back', on_click=lambda: ui.navigate.to('/books'))\
                        .props('flat dense size=sm color=indigo').classes('font-bold hover:bg-indigo-50 rounded-lg px-2')
                    ui.label('/').classes('text-slate-300')
                    ui.label('Library').classes('text-slate-500 hover:text-indigo-600 cursor-pointer')\
                        .on('click', lambda: ui.navigate.to('/books'))
                    ui.label('/').classes('text-slate-300')
                    ui.label(str(primary_shelf)).classes('text-indigo-600 font-bold bg-indigo-50 px-2 py-0.5 rounded-md')
                    ui.label('/').classes('text-slate-300')
                    ui.label(title).classes('text-slate-700 truncate max-w-[200px] sm:max-w-md font-medium')

            # MAIN TWO-COLUMN RESPONSIVE GRID
            with ui.row().classes('w-full flex-col lg:flex-row gap-8 lg:gap-12 items-start'):
                
                # =====================================================
                # LEFT COLUMN: COVER, PRIMARY CTAs & READING STATE
                # =====================================================
                with ui.column().classes('w-full lg:w-72 xl:w-80 items-center lg:items-stretch gap-4 shrink-0'):
                    
                    # 1. COVER CARD (No white chin, tight aspect-ratio, hover zoom)
                    with ui.card().classes(
                        'group relative p-0 rounded-2xl sm:rounded-3xl overflow-hidden shadow-xl sm:shadow-2xl '
                        'border border-slate-200 bg-slate-100 w-52 sm:w-60 md:w-64 lg:w-full aspect-[2/3] cursor-pointer '
                        'hover:shadow-indigo-100 transition-all duration-300'
                    ).on('click', open_cover_dialog):
                        ui.image(cover_url).props('fit=cover no-native-menu').classes(
                            'w-full h-full transition-transform duration-500 group-hover:scale-105'
                        )
                        with ui.element('div').classes(
                            'absolute inset-0 bg-slate-900/40 opacity-0 group-hover:opacity-100 '
                            'transition-opacity duration-300 flex flex-col items-center justify-center gap-1.5 text-white backdrop-blur-[2px]'
                        ):
                            ui.icon('zoom_in', size='2.2rem')
                            ui.label('Preview Cover').classes('text-xs font-bold tracking-wider uppercase drop-shadow')
                        ui.tooltip('Click to preview full-size cover')

                    # 2. ACTION BUTTONS STACK (Native Quasar labels - NO phantom empty pills)
                    with ui.column().classes('w-full gap-2.5 mt-2'):
                        # Primary CTA: Read Now
                        ui.button('Read Now', icon='menu_book', on_click=lambda: ui.navigate.to(f"/read/{self.book_id}"))\
                            .props('unelevated rounded-xl size=lg color=indigo')\
                            .classes('w-full font-bold shadow-md shadow-indigo-100 py-3 text-sm sm:text-base')

                        # Secondary CTA: Download Document
                        ui.button(f"Download {file_type}", icon='download', on_click=handle_download)\
                            .props('outline rounded-xl size=md color=slate')\
                            .classes('w-full font-bold bg-white text-slate-700 hover:bg-slate-50 hover:text-indigo-600 border border-slate-200 py-2.5 text-xs sm:text-sm shadow-xs')

                    # 3. READING STATE TRACKER CARD
                    self.reading_card_container = ui.column().classes('w-full')
                    self.render_reading_card()

                    # 4. UTILITY & DANGER ACTIONS
                    with ui.row().classes('w-full justify-center pt-1'):
                        ui.button('Remove Document', icon='delete_outline', on_click=open_delete_dialog)\
                            .props('flat dense size=sm color=red-7')\
                            .classes('font-bold hover:bg-red-50 rounded-xl px-3 py-1 text-xs')

                # =====================================================
                # RIGHT COLUMN: METADATA SPECS, SYNOPSIS & AI TOOLS
                # =====================================================
                with ui.column().classes('flex-1 w-full gap-6'):
                    
                    # 1. TITLE, AUTHOR & TOP CONTROLS ROW
                    with ui.column().classes('w-full gap-2'):
                        with ui.row().classes('w-full justify-between items-start gap-4 flex-wrap sm:flex-nowrap'):
                            ui.label(title).classes('text-2xl sm:text-3xl lg:text-4xl font-black text-slate-900 leading-tight tracking-tight flex-1')
                            
                            # Top Controls: Favorite & Edit
                            with ui.row().classes('items-center gap-2 shrink-0'):
                                # Favorite Toggle Button
                                fav_icon = 'favorite' if is_favorite else 'favorite_border'
                                fav_color = 'red-6' if is_favorite else 'grey-7'
                                fav_bg = 'bg-red-50 border-red-200 text-red-600' if is_favorite else 'bg-white border-slate-200 text-slate-700'
                                with ui.button(icon=fav_icon, on_click=toggle_favorite)\
                                    .props(f'flat round dense size=md color={fav_color}')\
                                    .classes(f'border rounded-xl p-2 {fav_bg} shadow-xs hover:scale-105 transition-transform'):
                                    ui.tooltip('Favorited' if is_favorite else 'Add to Favorites')

                                # Edit Metadata Button
                                with ui.button('Edit Metadata', icon='edit', on_click=open_edit_metadata_dialog)\
                                    .props('flat dense size=sm color=indigo')\
                                    .classes('bg-indigo-50 border border-indigo-200 text-indigo-700 font-bold rounded-xl px-3 py-1.5 shadow-xs hover:bg-indigo-100'):
                                    ui.tooltip('Edit Title, Author, Tags, and Info')

                        # Author with inline edit clue
                        with ui.row().classes('items-center gap-2'):
                            ui.label(f"by {author_name}").classes('text-base sm:text-xl text-indigo-600 font-bold')
                            if author_name == "Unknown":
                                ui.button('Set Author', icon='edit', on_click=open_edit_metadata_dialog)\
                                    .props('flat dense size=xs color=grey-7')\
                                    .classes('text-xs font-semibold underline text-slate-500 hover:text-indigo-600')

                    # 2. DOCUMENT SPECS PILL GRID
                    with ui.row().classes('w-full gap-2 sm:gap-2.5 flex-wrap items-center'):
                        # Format Pill
                        with ui.row().classes('items-center gap-1.5 px-3 py-1.5 bg-indigo-50 text-indigo-700 border border-indigo-100 rounded-xl text-xs font-bold shadow-xs'):
                            ui.icon('description', size='15px')
                            ui.label(file_type)

                        # Language Pill
                        with ui.row().classes('items-center gap-1.5 px-3 py-1.5 bg-slate-100 text-slate-700 border border-slate-200 rounded-xl text-xs font-bold shadow-xs'):
                            ui.icon('translate', size='15px')
                            ui.label(lang_str.upper())

                        # Page Count Pill
                        with ui.row().classes('items-center gap-1.5 px-3 py-1.5 bg-slate-100 text-slate-700 border border-slate-200 rounded-xl text-xs font-bold shadow-xs'):
                            ui.icon('auto_stories', size='15px')
                            ui.label(pages_str)

                        # Reading Time Estimate Pill
                        with ui.row().classes('items-center gap-1.5 px-3 py-1.5 bg-slate-100 text-slate-700 border border-slate-200 rounded-xl text-xs font-bold shadow-xs'):
                            ui.icon('schedule', size='15px')
                            ui.label(reading_time_str)

                        # File Size Pill
                        with ui.row().classes('items-center gap-1.5 px-3 py-1.5 bg-slate-100 text-slate-700 border border-slate-200 rounded-xl text-xs font-bold shadow-xs'):
                            ui.icon('save', size='15px')
                            ui.label(file_size_str)

                        # Added Date Pill
                        with ui.row().classes('items-center gap-1.5 px-3 py-1.5 bg-slate-100 text-slate-700 border border-slate-200 rounded-xl text-xs font-bold shadow-xs'):
                            ui.icon('calendar_today', size='15px')
                            ui.label(f"Added {formatted_date}")

                    # Publisher & Year Sub-row (if available)
                    if publisher or pub_year:
                        with ui.row().classes('items-center gap-2 text-xs font-semibold text-slate-500'):
                            ui.icon('business', size='15px').classes('text-slate-400')
                            meta_parts = []
                            if publisher: meta_parts.append(str(publisher))
                            if pub_year: meta_parts.append(str(pub_year))
                            ui.label(" • ".join(meta_parts))

                    # Tags & Categories Chips
                    combined_tags = []
                    for t in (shelves if isinstance(shelves, list) else [shelves]) + (genres if isinstance(genres, list) else [genres]):
                        if t and str(t).strip() and str(t).strip() not in combined_tags:
                            combined_tags.append(str(t).strip())

                    if combined_tags:
                        with ui.row().classes('gap-1.5 flex-wrap items-center mt-0.5'):
                            ui.label('Tags:').classes('text-[11px] font-black text-slate-400 uppercase tracking-widest mr-1')
                            for tag in combined_tags[:8]:
                                with ui.row().classes('items-center gap-1 bg-purple-50 text-purple-700 border border-purple-200 px-2.5 py-0.5 rounded-lg text-xs font-bold shadow-xs'):
                                    ui.icon('tag', size='12px').classes('text-purple-500')
                                    ui.label(tag)

                    ui.separator().classes('opacity-40 my-1')

                    # 3. SYNOPSIS SECTION (with AI Generation CTA)
                    with ui.column().classes('w-full gap-2.5'):
                        with ui.row().classes('w-full items-center justify-between'):
                            ui.label('SYNOPSIS').classes('text-xs font-black text-slate-400 uppercase tracking-widest')
                            ui.button(
                                'Regenerate with AI' if has_real_synopsis else '✨ Generate with AI',
                                icon='auto_awesome',
                                on_click=generate_ai_synopsis
                            ).props('flat dense size=sm color=indigo').classes('font-bold hover:bg-indigo-50 rounded-lg px-2')

                        if has_real_synopsis:
                            with ui.card().classes('w-full p-5 sm:p-6 bg-slate-50/70 rounded-2xl border border-slate-200 shadow-xs'):
                                ui.markdown(synopsis_text).classes('text-slate-700 leading-relaxed text-sm sm:text-base max-w-prose break-words')
                        else:
                            # Dynamic Interactive Empty State
                            with ui.card().classes(
                                'w-full p-5 sm:p-6 bg-gradient-to-r from-indigo-50/60 to-purple-50/40 rounded-2xl '
                                'border border-dashed border-indigo-200 flex flex-col sm:flex-row items-center sm:items-center justify-between gap-4'
                            ):
                                with ui.row().classes('items-center gap-3.5'):
                                    with ui.element('div').classes('p-3 rounded-2xl bg-indigo-100 text-indigo-700 shadow-sm shrink-0'):
                                        ui.icon('auto_awesome', size='24px')
                                    with ui.column().classes('gap-0.5'):
                                        ui.label('No synopsis available for this document').classes('font-bold text-slate-800 text-sm')
                                        ui.label('Libre-Library can extract content and generate a comprehensive overview.').classes('text-xs text-slate-500')
                                
                                ui.button('✨ Generate Synopsis with AI', on_click=generate_ai_synopsis)\
                                    .props('unelevated rounded-xl size=sm color=indigo font-bold')\
                                    .classes('shadow-md shadow-indigo-100 shrink-0')

                    ui.separator().classes('opacity-40 my-1')

                    # 4. AI TOOLS FOR THIS DOCUMENT GRID
                    with ui.column().classes('w-full gap-3 mt-1'):
                        ui.label('AI TOOLS FOR THIS DOCUMENT').classes('text-xs font-black text-slate-400 uppercase tracking-widest')
                        with ui.row().classes('w-full grid grid-cols-1 md:grid-cols-3 gap-3.5'):
                            
                            # Tool 1: Chat with Book (pre-scoped RAG)
                            with ui.card().classes(
                                'p-4 sm:p-5 bg-white hover:bg-indigo-50/30 rounded-2xl border border-slate-200 '
                                'hover:border-indigo-300 shadow-xs hover:shadow-md transition-all flex flex-col justify-between gap-3 cursor-pointer group'
                            ).on('click', open_chat_scoped):
                                with ui.column().classes('gap-2'):
                                    with ui.element('div').classes('w-10 h-10 rounded-xl bg-indigo-50 text-indigo-600 flex items-center justify-center border border-indigo-100 group-hover:scale-105 transition-transform'):
                                        ui.icon('smart_toy', size='20px')
                                    ui.label('Chat with Book').classes('font-bold text-slate-900 text-sm')
                                    ui.label('Ask TARS deep questions with pre-scoped document RAG citations.').classes('text-xs text-slate-500 leading-relaxed')
                                with ui.row().classes('items-center gap-1 text-xs font-bold text-indigo-600'):
                                    ui.label('Ask TARS AI')
                                    ui.icon('arrow_forward', size='14px')

                            # Tool 2: Document Summarizer
                            with ui.card().classes(
                                'p-4 sm:p-5 bg-white hover:bg-emerald-50/30 rounded-2xl border border-slate-200 '
                                'hover:border-emerald-300 shadow-xs hover:shadow-md transition-all flex flex-col justify-between gap-3 cursor-pointer group'
                            ).on('click', open_summarizer_scoped):
                                with ui.column().classes('gap-2'):
                                    with ui.element('div').classes('w-10 h-10 rounded-xl bg-emerald-50 text-emerald-600 flex items-center justify-center border border-emerald-100 group-hover:scale-105 transition-transform'):
                                        ui.icon('summarize', size='20px')
                                    ui.label('Executive Summary').classes('font-bold text-slate-900 text-sm')
                                    ui.label('Produce executive summaries, key takeaways, and chapter breakdown.').classes('text-xs text-slate-500 leading-relaxed')
                                with ui.row().classes('items-center gap-1 text-xs font-bold text-emerald-600'):
                                    ui.label('Open Summarizer')
                                    ui.icon('arrow_forward', size='14px')

                            # Tool 3: Study Flashcards
                            with ui.card().classes(
                                'p-4 sm:p-5 bg-white hover:bg-purple-50/30 rounded-2xl border border-slate-200 '
                                'hover:border-purple-300 shadow-xs hover:shadow-md transition-all flex flex-col justify-between gap-3 cursor-pointer group'
                            ).on('click', lambda: ui.navigate.to('/planner')):
                                with ui.column().classes('gap-2'):
                                    with ui.element('div').classes('w-10 h-10 rounded-xl bg-purple-50 text-purple-600 flex items-center justify-center border border-purple-100 group-hover:scale-105 transition-transform'):
                                        ui.icon('school', size='20px')
                                    ui.label('Study Flashcards').classes('font-bold text-slate-900 text-sm')
                                    ui.label('Turn core concepts from this book into interactive spaced repetition decks.').classes('text-xs text-slate-500 leading-relaxed')
                                with ui.row().classes('items-center gap-1 text-xs font-bold text-purple-600'):
                                    ui.label('Open Study Planner')
                                    ui.icon('arrow_forward', size='14px')

    def build_ui(self):
        drawer = sidebar()
        header(drawer_reference=drawer)
        bottom_nav()

        with ui.column().classes(
            'w-full min-h-[100dvh] pt-[calc(4.5rem+env(safe-area-inset-top,0px))] '
            'px-4 sm:px-6 md:pt-24 md:px-8 lg:px-12 max-w-7xl mx-auto '
            'pb-[calc(5rem+env(safe-area-inset-bottom,0px))] md:pb-16'
        ):
            self.content_container = ui.column().classes('w-full')


async def book_page(book_id: str):
    app.storage.client['page_path'] = '/books'
    page = BookDetailsPage(book_id)
    page.build_ui()
    await page.init()