from nicegui import ui, app, run
from pathlib import Path
import logging
import math
from datetime import datetime
from typing import Optional, Dict, Any, List

from components.sidebar import sidebar
from components.header import header
from components.book_card import has_disk_cover
from core.database.mongo_manager import mongo_db
from core.auth.jwt_handler import get_current_user_role
from ui.pages.book_details_service import book_details_service
from components.book_details import (
    open_cover_dialog,
    open_edit_metadata_dialog,
    open_delete_dialog,
    open_borrow_dialog,
    render_reading_card,
    render_specs_grid,
)

logger = logging.getLogger("BOOK_DETAILS")


class BookDetailsPage:
    """
    Modular, high-performance Book Details & Preview view controller.
    Coordinates between BookDetailsService and presentation components.
    """

    def __init__(self, book_id: str):
        self.book_id = str(book_id).strip()
        self.book: Optional[Dict[str, Any]] = None
        self.reading_progress: Optional[Dict[str, Any]] = None
        self.content_container = None
        self.reading_card_container = None

    async def init(self):
        user_id = app.storage.user.get('user_id') or app.storage.user.get('token') or 'guest'
        self.book, self.reading_progress = await book_details_service.load_book_data(self.book_id, user_id)
        if not self.book:
            ui.notify("Book not found in library.", type='negative')
            ui.navigate.to('/books')
            return

        if self.book and user_id:
            try:
                self.book['is_favorite'] = await mongo_db.is_book_favorited(user_id, self.book_id)
            except Exception:
                pass

        self.render_content()

    def get_effective_total_pages(self) -> int:
        return book_details_service.get_effective_total_pages(self.book, self.reading_progress)

    @staticmethod
    def format_synopsis_text(raw_text: str) -> str:
        return book_details_service.format_synopsis_text(raw_text)

    def refresh_ui(self):
        if self.content_container:
            self.content_container.clear()
            self.render_content()

    def render_reading_card(self):
        if not self.reading_card_container or not self.book:
            return
        render_reading_card(
            container=self.reading_card_container,
            book=self.book,
            reading_progress=self.reading_progress,
            total_pages=self.get_effective_total_pages(),
            on_status_change=self.update_reading_status,
            on_page_change=self.update_page_number,
        )

    async def update_reading_status(self, new_status: str):
        if not self.book:
            return
        tot_pages = self.get_effective_total_pages()
        cur = int(self.reading_progress.get('current_page', 0)) if self.reading_progress else 0
        user_id = app.storage.user.get('user_id') or app.storage.user.get('token') or 'guest'

        res = book_details_service.calculate_reading_status(new_status, tot_pages, cur)
        self.book['reading_status'] = res['status']
        if not self.reading_progress:
            self.reading_progress = {}
        self.reading_progress.update(res)

        self.render_reading_card()
        ui.notify(f"Marked as {res['display_title']}", type='positive')

        try:
            if user_id:
                await mongo_db.progress.save_reading_progress(
                    user_id=user_id,
                    book_id=self.book_id,
                    current_page=res['current_page'],
                    total_pages=tot_pages,
                    status=res['status']
                )
        except Exception as err:
            logger.error(f"Error persisting reading status: {err}")

    async def update_page_number(self, page_val: int):
        if not self.book:
            return
        tot_pages = self.get_effective_total_pages()
        if page_val > tot_pages:
            tot_pages = page_val
            self.book['page_count'] = tot_pages

        user_id = app.storage.user.get('user_id') or app.storage.user.get('token') or 'guest'
        res = book_details_service.calculate_page_progress(page_val, tot_pages)

        self.book['reading_status'] = res['status']
        if not self.reading_progress:
            self.reading_progress = {}
        self.reading_progress.update(res)

        self.render_reading_card()
        ui.notify(f"Progress updated to page {res['current_page']} of {res['total_pages']}", type='positive')

        try:
            if user_id:
                await mongo_db.progress.save_reading_progress(
                    user_id=user_id,
                    book_id=self.book_id,
                    current_page=res['current_page'],
                    total_pages=res['total_pages'],
                    status=res['status']
                )
        except Exception as err:
            logger.error(f"Error persisting page progress: {err}")

    async def toggle_favorite(self):
        user_id = app.storage.user.get('user_id') or app.storage.user.get('token') or 'guest'
        is_fav = await book_details_service.toggle_favorite(self.book_id, user_id=user_id)
        if self.book:
            self.book['is_favorite'] = is_fav
        ui.notify("Saved to Favorites!" if is_fav else "Removed from Favorites.", type='positive' if is_fav else 'info')
        self.refresh_ui()

    async def generate_ai_synopsis(self, title: str, author_name: str, file_type: str):
        spinner_dialog = ui.dialog()
        with spinner_dialog, ui.card().classes('p-6 items-center gap-3 bg-white rounded-3xl shadow-2xl border border-slate-200 text-center'):
            ui.spinner('dots', size='3rem', color='indigo')
            ui.label('Generating Synopsis with AI...').classes('font-black text-slate-800 text-base')
            ui.label('Extracting document excerpt and synthesizing comprehensive overview.').classes('text-xs text-slate-500 max-w-xs')
        spinner_dialog.open()

        success, result = await book_details_service.generate_ai_synopsis(
            book_id=self.book_id,
            book=self.book,
            title=title,
            author_name=author_name,
            file_type=file_type,
        )
        spinner_dialog.close()

        if success:
            self.book['description'] = result
            self.book['summaries'] = [result]
            ui.notify("✨ Synopsis generated and saved successfully!", type='positive')
            self.refresh_ui()
        else:
            ui.notify(result, type='warning')

    def handle_download(self, title: str, file_type: str):
        target_path = mongo_db.resolve_document_path(self.book_id, self.book)
        if target_path and Path(target_path).exists():
            safe_title = "".join(c for c in title if c.isalnum() or c in (' ', '_', '-')).strip() or 'book'
            ext = Path(target_path).suffix or f".{file_type.lower()}"
            download_filename = f"{safe_title}{ext}"
            ui.download(target_path, filename=download_filename)
            ui.notify(f"Downloading {download_filename}...", type='info')
        else:
            ui.notify("Physical document file not found on disk.", type='warning')

    def render_content(self):
        if not self.book or not self.content_container:
            return

        title = self.book.get('title') or "Untitled Document"
        author_name = self.book.get('display_author') or (self.book.get('authors', ['Unknown'])[0] if self.book.get('authors') else 'Unknown')
        bid = self.book_id or str(self.book.get('id') or self.book.get('_id') or '')
        if has_disk_cover(bid):
            cover_url = f"/static_books/{bid}/cover.jpg"
        elif self.book.get('cover_image') and not str(self.book.get('cover_image')).endswith(('default_cover.png', 'default_cover.svg')):
            cover_url = self.book.get('cover_image')
        elif self.book.get('cover_url') and not str(self.book.get('cover_url')).endswith(('default_cover.png', 'default_cover.svg')):
            cover_url = self.book.get('cover_url')
        else:
            cover_url = "/static/default_cover.svg"

        self.book['cover_url'] = cover_url
        self.book['cover_image'] = cover_url
        raw_synopsis = self.book.get('description') or (self.book.get('summaries', [''])[0] if self.book.get('summaries') else '')
        synopsis_text = self.format_synopsis_text(raw_synopsis)
        has_real_synopsis = bool(synopsis_text and len(synopsis_text.strip()) > 30 and not synopsis_text.startswith("No synopsis"))

        file_type = (self.book.get('format') or self.book.get('file_type') or 'EPUB').upper()
        raw_date = self.book.get('date_added')
        formatted_date = mongo_db.books.format_added_date(raw_date) if hasattr(mongo_db, 'books') else 'Recently'
        
        page_val = self.book.get('page_count') or 0
        pages_str = f"{page_val} pages" if page_val > 0 else "Uncounted"
        est_minutes = max(1, math.ceil(page_val * 1.5)) if page_val > 0 else 15
        reading_time_str = f"~{est_minutes} min read" if est_minutes < 60 else f"~{est_minutes // 60}h {est_minutes % 60}m read"

        file_size_bytes = self.book.get('file_size', 0)
        file_size_str = f"{file_size_bytes / (1024*1024):.1f} MB" if file_size_bytes >= 1024*1024 else (f"{file_size_bytes / 1024:.0f} KB" if file_size_bytes > 0 else "Standard")

        lang_str = str(self.book.get('language') or 'en').upper()
        shelves = self.book.get('shelves', []) or []
        genres = self.book.get('genres', []) or self.book.get('subjects', []) or []
        publisher = self.book.get('publisher')
        pub_year = self.book.get('publication_year')
        is_favorite = bool(self.book.get('is_favorite', False))

        can_manage_catalog = get_current_user_role() in ('admin', 'librarian')

        with self.content_container:
            # Breadcrumbs
            primary_shelf = shelves[0] if (shelves and isinstance(shelves, list)) else (genres[0] if genres else 'Archive')
            with ui.row().classes('w-full items-center justify-between gap-2 mb-4 sm:mb-6 flex-wrap'):
                with ui.row().classes('items-center gap-2 text-xs sm:text-sm font-semibold text-slate-500'):
                    ui.button('Back to Archive', icon='arrow_back', on_click=lambda: ui.navigate.to('/books'))\
                        .props('flat dense size=sm color=indigo').classes('font-bold hover:bg-indigo-50 rounded-lg px-2')
                    ui.label('/').classes('text-slate-300')
                    ui.label('Library').classes('text-slate-500 hover:text-indigo-600 cursor-pointer').on('click', lambda: ui.navigate.to('/books'))
                    ui.label('/').classes('text-slate-300')
                    ui.label(str(primary_shelf)).classes('text-indigo-600 font-bold bg-indigo-50 px-2 py-0.5 rounded-md')
                    ui.label('/').classes('text-slate-300')
                    ui.label(title).classes('text-slate-700 truncate max-w-[200px] sm:max-w-md font-medium')

            # Main Two-Column Layout
            with ui.row().classes('w-full flex-col lg:flex-row gap-8 lg:gap-12 items-start'):
                # Left Column: Cover & Actions
                with ui.column().classes('w-full lg:w-72 xl:w-80 items-center lg:items-stretch gap-4 shrink-0'):
                    with ui.card().classes(
                        'group relative p-0 rounded-2xl sm:rounded-3xl overflow-hidden shadow-xl sm:shadow-2xl '
                        'border border-slate-200 bg-slate-100 w-52 sm:w-60 md:w-64 lg:w-full aspect-[2/3] cursor-pointer '
                        'hover:shadow-indigo-100 transition-all duration-300'
                    ).on('click', lambda: open_cover_dialog(title, cover_url)):
                        ui.image(cover_url).props('fit=cover no-native-menu').classes('w-full h-full transition-transform duration-500 group-hover:scale-105')
                        with ui.element('div').classes(
                            'absolute inset-0 bg-slate-900/40 opacity-0 group-hover:opacity-100 transition-opacity duration-300 '
                            'flex flex-col items-center justify-center gap-1.5 text-white backdrop-blur-[2px]'
                        ):
                            ui.icon('zoom_in', size='2.2rem')
                            ui.label('Preview Cover').classes('text-xs font-bold tracking-wider uppercase drop-shadow')
                        ui.tooltip('Click to preview full-size cover')

                    with ui.column().classes('w-full gap-2.5 mt-2'):
                        ui.button('Read Now', icon='menu_book', on_click=lambda: ui.navigate.to(f"/read/{self.book_id}"))\
                            .props('unelevated rounded-xl size=lg color=indigo').classes('w-full font-bold shadow-md shadow-indigo-100 py-3 text-sm sm:text-base')
                        ui.button('Borrow Physical Copy', icon='local_library', on_click=lambda: open_borrow_dialog(self.book_id, self.book))\
                            .props('unelevated rounded-xl size=md color=emerald-700').classes('w-full font-bold shadow-md shadow-emerald-100 py-2.5 text-xs sm:text-sm bg-emerald-600 hover:bg-emerald-700 text-white')
                        ui.button(f"Download {file_type}", icon='download', on_click=lambda: self.handle_download(title, file_type))\
                            .props('outline rounded-xl size=md color=slate').classes('w-full font-bold bg-white text-slate-700 hover:bg-slate-50 hover:text-indigo-600 border border-slate-200 py-2.5 text-xs sm:text-sm shadow-xs')

                    self.reading_card_container = ui.column().classes('w-full')
                    self.render_reading_card()

                    if can_manage_catalog:
                        with ui.row().classes('w-full justify-center pt-1'):
                            ui.button(
                                'Remove Document',
                                icon='delete_outline',
                                on_click=lambda: open_delete_dialog(self.book_id, title, on_deleted=lambda: ui.navigate.to('/books'))
                            ).props('flat dense size=sm color=red-7').classes('font-bold hover:bg-red-50 rounded-xl px-3 py-1 text-xs')

                # Right Column: Metadata, Specs, Synopsis & AI
                with ui.column().classes('flex-1 w-full gap-6'):
                    with ui.column().classes('w-full gap-2'):
                        with ui.row().classes('w-full justify-between items-start gap-4 flex-wrap sm:flex-nowrap'):
                            ui.label(title).classes('text-2xl sm:text-3xl lg:text-4xl font-black text-slate-900 leading-tight tracking-tight flex-1')
                            with ui.row().classes('items-center gap-2 shrink-0'):
                                fav_icon = 'favorite' if is_favorite else 'favorite_border'
                                fav_color = 'red-6' if is_favorite else 'grey-7'
                                fav_bg = 'bg-red-50 border-red-200 text-red-600' if is_favorite else 'bg-white border-slate-200 text-slate-700'
                                with ui.button(icon=fav_icon, on_click=self.toggle_favorite)\
                                    .props(f'flat round dense size=md color={fav_color}').classes(f'border rounded-xl p-2 {fav_bg} shadow-xs hover:scale-105 transition-transform'):
                                    ui.tooltip('Favorited' if is_favorite else 'Add to Favorites')

                                if can_manage_catalog:
                                    def on_metadata_saved(updates: Dict[str, Any]):
                                        self.book.update(updates)
                                        self.refresh_ui()

                                    with ui.button('Edit Metadata', icon='edit', on_click=lambda: open_edit_metadata_dialog(self.book_id, self.book, on_metadata_saved))\
                                        .props('flat dense size=sm color=indigo').classes('bg-indigo-50 border border-indigo-200 text-indigo-700 font-bold rounded-xl px-3 py-1.5 shadow-xs hover:bg-indigo-100'):
                                        ui.tooltip('Edit Title, Author, Tags, and Info')

                        with ui.row().classes('items-center gap-2'):
                            ui.label(f"by {author_name}").classes('text-base sm:text-xl text-indigo-600 font-bold')

                    render_specs_grid(
                        file_type=file_type,
                        lang_str=lang_str,
                        pages_str=pages_str,
                        reading_time_str=reading_time_str,
                        file_size_str=file_size_str,
                        formatted_date=formatted_date,
                        publisher=publisher,
                        pub_year=pub_year,
                        shelves=shelves,
                        genres=genres,
                    )

                    ui.separator().classes('opacity-40 my-1')

                    # Synopsis Section
                    with ui.column().classes('w-full gap-2.5'):
                        with ui.row().classes('w-full items-center justify-between'):
                            with ui.row().classes('items-center gap-2'):
                                ui.icon('subject', size='18px').classes('text-indigo-600')
                                ui.label('SYNOPSIS').classes('text-xs font-black text-slate-500 uppercase tracking-widest')
                                if has_real_synopsis and len(synopsis_text) > 280:
                                    with ui.row().classes('items-center gap-1 text-[10px] font-bold text-slate-400 bg-slate-100 border border-slate-200/60 px-2 py-0.5 rounded-md'):
                                        ui.icon('unfold_more', size='12px')
                                        ui.label('Scrollable')

                            ui.button(
                                'Regenerate with AI' if has_real_synopsis else '✨ Generate with AI',
                                icon='auto_awesome',
                                on_click=lambda: self.generate_ai_synopsis(title, author_name, file_type)
                            ).props('flat dense size=sm color=indigo').classes('font-bold hover:bg-indigo-50 rounded-lg px-2')

                        if has_real_synopsis:
                            with ui.card().classes('w-full p-4 sm:p-6 bg-slate-50/70 rounded-2xl border border-slate-200 shadow-xs relative overflow-hidden'):
                                with ui.column().classes('w-full max-h-72 sm:max-h-80 lg:max-h-[360px] overflow-y-auto pr-2 sm:pr-3 overscroll-contain synopsis-scroll-container'):
                                    ui.markdown(synopsis_text).classes('synopsis-markdown w-full text-slate-700 leading-relaxed text-sm sm:text-base break-words')
                        else:
                            with ui.card().classes('w-full p-5 sm:p-6 bg-gradient-to-r from-indigo-50/60 to-purple-50/40 rounded-2xl border border-dashed border-indigo-200 flex flex-col sm:flex-row items-center justify-between gap-4'):
                                with ui.row().classes('items-center gap-3.5'):
                                    with ui.element('div').classes('p-3 rounded-2xl bg-indigo-100 text-indigo-700 shadow-sm shrink-0'):
                                        ui.icon('auto_awesome', size='24px')
                                    with ui.column().classes('gap-0.5'):
                                        ui.label('No synopsis available for this document').classes('font-bold text-slate-800 text-sm')
                                        ui.label('Libre-Library can extract content and generate a comprehensive overview.').classes('text-xs text-slate-500')
                                ui.button('✨ Generate Synopsis with AI', on_click=lambda: self.generate_ai_synopsis(title, author_name, file_type))\
                                    .props('unelevated rounded-xl size=sm color=indigo font-bold').classes('shadow-md shadow-indigo-100 shrink-0')

                    ui.separator().classes('opacity-40 my-1')

                    # AI Tools
                    with ui.column().classes('w-full gap-3 mt-1'):
                        ui.label('AI TOOLS FOR THIS DOCUMENT').classes('text-xs font-black text-slate-400 uppercase tracking-widest')
                        with ui.row().classes('w-full grid grid-cols-1 md:grid-cols-3 gap-3.5'):
                            def open_chat():
                                app.storage.user['chat_focus_book_id'] = self.book_id
                                app.storage.user['chat_focus_book_title'] = title
                                ui.navigate.to('/chat')

                            with ui.card().classes('p-4 sm:p-5 bg-white hover:bg-cyan-50/30 rounded-2xl border border-slate-200 hover:border-cyan-300 shadow-xs hover:shadow-md transition-all flex flex-col justify-between gap-3 cursor-pointer group').on('click', open_chat):
                                with ui.column().classes('gap-2'):
                                    with ui.element('div').classes('w-10 h-10 rounded-xl bg-cyan-50 flex items-center justify-center border border-cyan-100 group-hover:scale-105 transition-transform p-1.5 shadow-2xs'):
                                        ui.image('/static/tars_icon.svg').classes('w-full h-full object-contain').props('no-spinner')
                                    ui.label('Chat with Book').classes('font-bold text-slate-900 text-sm')
                                    ui.label('Ask TARS deep questions with pre-scoped document RAG citations.').classes('text-xs text-slate-500 leading-relaxed')
                                with ui.row().classes('items-center gap-1 text-xs font-bold text-cyan-700'):
                                    ui.label('Ask TARS AI')
                                    ui.icon('arrow_forward', size='14px')

                            def open_summarizer():
                                app.storage.user['summarize_book_id'] = self.book_id
                                ui.navigate.to('/summarizer')

                            with ui.card().classes('p-4 sm:p-5 bg-white hover:bg-emerald-50/30 rounded-2xl border border-slate-200 hover:border-emerald-300 shadow-xs hover:shadow-md transition-all flex flex-col justify-between gap-3 cursor-pointer group').on('click', open_summarizer):
                                with ui.column().classes('gap-2'):
                                    with ui.element('div').classes('w-10 h-10 rounded-xl bg-emerald-50 text-emerald-600 flex items-center justify-center border border-emerald-100 group-hover:scale-105 transition-transform'):
                                        ui.icon('summarize', size='20px')
                                    ui.label('Executive Summary').classes('font-bold text-slate-900 text-sm')
                                    ui.label('Produce executive summaries, key takeaways, and chapter breakdown.').classes('text-xs text-slate-500 leading-relaxed')
                                with ui.row().classes('items-center gap-1 text-xs font-bold text-emerald-600'):
                                    ui.label('Open Summarizer')
                                    ui.icon('arrow_forward', size='14px')

                            with ui.card().classes('p-4 sm:p-5 bg-white hover:bg-purple-50/30 rounded-2xl border border-slate-200 hover:border-purple-300 shadow-xs hover:shadow-md transition-all flex flex-col justify-between gap-3 cursor-pointer group').on('click', lambda: ui.navigate.to('/planner')):
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
        with ui.column().classes('w-full min-h-fit pt-[calc(4.5rem+env(safe-area-inset-top,0px))] px-4 sm:px-6 md:pt-24 md:px-8 lg:px-12 max-w-7xl mx-auto pb-16 safe-pb-mobile-nav'):
            self.content_container = ui.column().classes('w-full')


async def book_page(book_id: str):
    app.storage.client['page_path'] = '/books'
    page = BookDetailsPage(book_id)
    page.build_ui()
    await page.init()