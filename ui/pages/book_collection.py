from nicegui import ui, app
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime
from components.sidebar import sidebar
from components.header import header
from components.bottom_nav import bottom_nav
from components.book_card import book_card
from core.database.mongo_manager import mongo_db

logger = logging.getLogger("LIBRE_LIBRARY_COLLECTION")

def to_timestamp(val: Any) -> float:
    """Safely normalizes any date, timestamp, or string representation to a float timestamp."""
    if val is None:
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)
    if isinstance(val, datetime):
        return val.timestamp()
    if isinstance(val, str):
        try:
            return datetime.fromisoformat(val.replace('Z', '+00:00')).timestamp()
        except Exception:
            try:
                return float(val)
            except Exception:
                return 0.0
    return 0.0

class BookCollection:
    """
    Optimized Library Collection with server-side queries, reading status tabs,
    custom shelves, resilient datetime sorting, and zero bottom navigation.
    """
    def __init__(self):
        self.books: List[Dict[str, Any]] = []
        self.filtered_list: List[Dict[str, Any]] = []
        self.user_progress: Dict[str, Dict[str, Any]] = {}
        self.user_favorites: set = set()
        self.batch_size = 20
        self.current_index = 0

        self.state = {
            'search_term': '',
            'sort_by': 'Newest',
            'format_filter': 'All',
            'shelf_filter': 'All',
            'author_filter': 'All',
            'status_tab': 'all',  # 'all', 'favorites', 'reading', 'want_to_read', 'completed'
        }

        self.unique_formats = ['All', 'PDF', 'EPUB', 'DOCX', 'PPTX', 'TXT']
        self.unique_shelves = ['All']
        self.unique_authors = ['All']

        # UI References
        self.grid_container = None
        self.load_more_btn = None
        self.hero_count_label = None
        self.format_select = None
        self.shelf_select = None
        self.author_select = None
        self.status_tab_container = None

    async def load_books(self):
        """Loads books and user reading statuses from database."""
        if 'search_filter' in app.storage.client:
            self.state['search_term'] = app.storage.client.pop('search_filter')

        try:
            uid = app.storage.user.get('user_id') or app.storage.user.get('token')
            if uid:
                try:
                    prog_list = await mongo_db.get_reading_history(uid, limit=1000)
                    self.user_progress = {p.get('book_id'): p for p in prog_list if p.get('book_id')}
                except Exception:
                    self.user_progress = {}

                try:
                    fav_docs = await mongo_db.get_favorite_books(limit=1000)
                    self.user_favorites = {b.get('id') for b in fav_docs if b.get('id')}
                except Exception:
                    self.user_favorites = set()

            all_books = await mongo_db.get_all_books(limit=2000, sort_by='newest')
            self.books = all_books or []

            # Extract distinct shelves
            shelves = set()
            authors = set()
            for b in self.books:
                s = b.get('custom_shelf')
                if s and isinstance(s, str) and s.strip():
                    shelves.add(s.strip())

                auth = b.get('display_author') or b.get('authors', 'Unknown')
                if isinstance(auth, list) and auth:
                    auth = auth[0].get('name', str(auth[0])) if isinstance(auth[0], dict) else str(auth[0])
                if auth and str(auth).lower() != 'unknown':
                    authors.add(str(auth).strip())

            self.unique_shelves = ['All'] + sorted(list(shelves))
            self.unique_authors = ['All'] + sorted(list(authors))

            if self.shelf_select:
                self.shelf_select.options = self.unique_shelves
                if self.shelf_select.value not in self.unique_shelves:
                    self.shelf_select.value = 'All'
                self.shelf_select.update()

            if self.author_select:
                self.author_select.options = self.unique_authors
                if self.author_select.value not in self.unique_authors:
                    self.author_select.value = 'All'
                self.author_select.update()

            self.render_status_tabs()
            self.apply_filters_and_sort()

        except Exception as e:
            logger.error(f"Error loading books: {e}", exc_info=True)
            ui.notify(f"Error loading library: {e}", type='negative')
            self.books = []

    def render_status_tabs(self):
        """Renders 1-click status pill filters."""
        if not self.status_tab_container:
            return
        self.status_tab_container.clear()

        # Count per category
        fav_count = sum(1 for b in self.books if b.get('is_favorite') or b.get('id') in self.user_favorites)
        reading_count = sum(1 for b in self.books if self.user_progress.get(b.get('id'), {}).get('status') == 'reading')
        want_count = sum(1 for b in self.books if self.user_progress.get(b.get('id'), {}).get('status') == 'want_to_read')
        done_count = sum(1 for b in self.books if self.user_progress.get(b.get('id'), {}).get('status') == 'completed')

        tabs = [
            ('all', 'All Books', len(self.books), None),
            ('favorites', '★ Favorites', fav_count, 'amber'),
            ('reading', '📖 Currently Reading', reading_count, 'indigo'),
            ('want_to_read', '🏷️ Want to Read', want_count, 'blue'),
            ('completed', '✅ Completed', done_count, 'emerald'),
        ]

        with self.status_tab_container:
            for tab_id, label, count, color_hint in tabs:
                is_active = self.state['status_tab'] == tab_id
                if is_active:
                    pill_classes = 'bg-indigo-600 text-white font-bold shadow-sm'
                    badge_classes = 'bg-white/20 text-white'
                else:
                    pill_classes = 'bg-slate-100 text-slate-700 hover:bg-slate-200 font-medium'
                    badge_classes = 'bg-slate-200 text-slate-700'

                def make_click(tid=tab_id):
                    self.state['status_tab'] = tid
                    self.render_status_tabs()
                    self.apply_filters_and_sort()

                with ui.button(on_click=make_click).props('unelevated rounded-full dense size=sm').classes(f'shrink-0 px-3 py-1 text-xs transition-all {pill_classes}'):
                    ui.label(label)
                    with ui.element('span').classes(f'ml-1.5 px-1.5 py-0.2 rounded-full text-[10px] {badge_classes}'):
                        ui.label(str(count))

    def apply_filters_and_sort(self):
        """Filters and sorts the book list safely without type comparison crashes."""
        temp_list = self.books.copy()

        # 1. Reading Status Filter
        st = self.state['status_tab']
        if st == 'favorites':
            temp_list = [b for b in temp_list if b.get('is_favorite') or b.get('id') in self.user_favorites]
        elif st in ('reading', 'want_to_read', 'completed'):
            temp_list = [b for b in temp_list if self.user_progress.get(b.get('id'), {}).get('status') == st]

        # 2. Text Search
        query = self.state['search_term'].lower().strip()
        if query:
            temp_list = [
                b for b in temp_list
                if query in str(b.get('title', '')).lower() or
                   query in str(b.get('display_author', '')).lower() or
                   query in str(b.get('authors', '')).lower()
            ]

        # 3. Format Filter
        fmt = self.state['format_filter']
        if fmt != 'All':
            temp_list = [
                b for b in temp_list
                if fmt.lower() in [k.lower() for k in b.get('formats', {}).keys()] or
                   fmt.lower() == str(b.get('file_type', '')).lower()
            ]

        # 4. Custom Shelf Filter
        shelf = self.state['shelf_filter']
        if shelf != 'All':
            temp_list = [b for b in temp_list if str(b.get('custom_shelf', '')).strip() == shelf]

        # 5. Author Filter
        author = self.state['author_filter']
        if author != 'All':
            temp_list = [
                b for b in temp_list
                if author in str(b.get('display_author', '')) or author in str(b.get('authors', ''))
            ]

        # 6. Safe Sorting (Guaranteed no datetime vs float TypeErrors)
        sort_mode = self.state['sort_by']
        if sort_mode == 'Newest':
            temp_list.sort(key=lambda x: to_timestamp(x.get('added_at') or x.get('created_at')), reverse=True)
        elif sort_mode == 'Oldest':
            temp_list.sort(key=lambda x: to_timestamp(x.get('added_at') or x.get('created_at')))
        elif sort_mode == 'A-Z':
            temp_list.sort(key=lambda x: str(x.get('title') or '').lower())
        elif sort_mode == 'Author':
            temp_list.sort(key=lambda x: str(x.get('display_author') or x.get('authors') or '').lower())

        self.filtered_list = temp_list

        if self.hero_count_label:
            self.hero_count_label.text = f"{len(self.filtered_list)} books available"

        self.current_index = 0
        if self.grid_container:
            self.grid_container.clear()

        self.load_more_batch()

    def load_more_batch(self):
        """Infinite scroll: renders next batch of book cards."""
        start = self.current_index
        end = start + self.batch_size
        batch = self.filtered_list[start:end]

        with self.grid_container:
            if not self.filtered_list:
                with ui.column().classes('col-span-full items-center justify-center py-16 text-center'):
                    ui.icon('menu_book', size='3.5em').classes('text-slate-300 mb-2')
                    ui.label("No books found matching this filter").classes('text-base font-bold text-slate-500')
                    ui.button('Reset Filters', on_click=lambda: (
                        self.state.update({'search_term': '', 'format_filter': 'All', 'shelf_filter': 'All', 'author_filter': 'All', 'status_tab': 'all'}),
                        self.render_status_tabs(),
                        self.apply_filters_and_sort()
                    )).props('flat color=indigo size=sm').classes('mt-2 font-bold')
                return

            is_admin = app.storage.user.get('role') == 'admin'
            delete_cb = self.prompt_delete if is_admin else None

            for book in batch:
                book_card(book, action_target='book', on_delete=delete_cb)

        self.current_index = end

        if self.load_more_btn:
            if self.current_index >= len(self.filtered_list):
                self.load_more_btn.disable()
                self.load_more_btn.text = 'End of Collection'
            else:
                self.load_more_btn.enable()
                self.load_more_btn.text = 'Load More Books'

    def prompt_delete(self, book_id: str, title: str):
        """Shows deletion confirmation dialog (admin restricted)."""
        if app.storage.user.get('role') != 'admin':
            ui.notify("Administrator privileges required to delete books.", type='warning')
            return

        with ui.dialog() as dialog, ui.card().classes('w-[calc(100vw-1.5rem)] max-w-md p-5 sm:p-6 rounded-2xl bg-white border border-slate-200 shadow-2xl'):
            ui.label(f"Delete '{title}'?").classes('text-base sm:text-lg font-bold text-rose-600')
            ui.label("This will permanently remove the file, metadata, and AI knowledge chunks.").classes('text-xs sm:text-sm text-slate-500 mt-1')

            with ui.row().classes('w-full justify-end gap-2.5 mt-5 sm:mt-6'):
                ui.button('Cancel', on_click=dialog.close).props('flat color=grey')

                async def confirm():
                    dialog.close()
                    if app.storage.user.get('role') != 'admin':
                        ui.notify("Administrator privileges required to delete books.", type='negative')
                        return
                    success = await mongo_db.delete_book(book_id)
                    if success:
                        ui.notify(f"Deleted '{title}'", type='positive')
                        await self.load_books()
                    else:
                        ui.notify("Failed to delete book", type='negative')

                ui.button('Delete', color='red', on_click=confirm).props('unelevated font-bold rounded')
        dialog.open()


    def build_ui(self):
        drawer = sidebar()
        header(drawer_reference=drawer)
        bottom_nav()

        with ui.column().classes('w-full min-h-[100dvh] pt-[calc(4.5rem+env(safe-area-inset-top,0px))] px-3 sm:px-4 md:pt-24 md:px-8 max-w-7xl mx-auto pb-[calc(5rem+env(safe-area-inset-bottom,0px))] md:pb-16'):

            # --- HERO / FILTER BAR ---
            with ui.column().classes('w-full bg-white border border-slate-200 p-4 sm:p-6 mb-4 sm:mb-6 rounded-2xl sm:rounded-3xl shadow-sm gap-4'):
                with ui.row().classes('w-full items-center justify-between gap-4 flex-wrap'):
                    with ui.column().classes('gap-0.5'):
                        ui.label('Library Archive').classes('text-2xl sm:text-3xl font-black text-slate-900 tracking-tight')
                        self.hero_count_label = ui.label('Loading collection...').classes('text-slate-500 font-medium text-xs sm:text-sm')

                    with ui.row().classes('items-center gap-2 flex-grow sm:flex-grow-0 max-w-md w-full sm:w-auto'):
                        ui.input(placeholder='Search Title or Author... (Press /)',
                                 on_change=lambda e: (self.state.update({'search_term': e.value}), self.apply_filters_and_sort())) \
                            .bind_value(self.state, 'search_term') \
                            .props('id=global-search-input outlined rounded dense icon=search clearable bg-color=white') \
                            .classes('flex-1 sm:w-72 text-sm')

                        ui.button('OPDS Feed', icon='rss_feed', on_click=lambda: ui.run_javascript("""
                            navigator.clipboard.writeText(window.location.origin + '/opds');
                            alert('OPDS Catalog Feed URL copied: ' + window.location.origin + '/opds');
                        """)).props('outline rounded-xl color=indigo size=sm').classes('hidden md:inline-flex text-xs font-bold') \
                           .tooltip('Copy OPDS Feed URL for KOReader / Moon+ Reader')

                        ui.button(icon='refresh', on_click=self.load_books) \
                            .props('flat round dense color=indigo size=md') \
                            .tooltip('Reload Library')

                # Reading Status & Collections Filter Tabs (Horizontal swipe chips on mobile)
                self.status_tab_container = ui.row().classes('w-full gap-1.5 sm:gap-2 items-center flex-nowrap overflow-x-auto no-scrollbar touch-pan-x py-1')

                # Filter Controls Toolbar: 2 columns on mobile, 4 columns on desktop (Format, Shelf, Author, Sort)
                with ui.grid().classes('w-full grid-cols-2 md:grid-cols-4 gap-2 sm:gap-2.5 pt-2 border-t border-slate-100'):
                    self.format_select = ui.select(self.unique_formats, value='All', label='Format',
                              on_change=lambda e: (self.state.update({'format_filter': e.value}), self.apply_filters_and_sort())) \
                        .props('outlined rounded dense options-dense bg-color=white').classes('w-full text-sm')

                    self.shelf_select = ui.select(self.unique_shelves, value='All', label='Custom Shelf',
                              on_change=lambda e: (self.state.update({'shelf_filter': e.value}), self.apply_filters_and_sort())) \
                        .props('outlined rounded dense options-dense bg-color=white').classes('w-full text-sm')

                    self.author_select = ui.select(self.unique_authors, value='All', label='Author',
                              on_change=lambda e: (self.state.update({'author_filter': e.value}), self.apply_filters_and_sort())) \
                        .props('outlined rounded dense options-dense bg-color=white').classes('w-full text-sm')

                    ui.select(['Newest', 'Oldest', 'A-Z', 'Author'], value='Newest', label='Sort By',
                              on_change=lambda e: (self.state.update({'sort_by': e.value}), self.apply_filters_and_sort())) \
                        .props('outlined rounded dense options-dense bg-color=white').classes('w-full text-sm')

            # --- BOOKS GRID ---
            with ui.column().classes('w-full items-center'):
                with ui.grid().classes('w-full gap-3 sm:gap-4 md:gap-6 grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 mb-8') as self.grid_container:
                    pass

                self.load_more_btn = ui.button('Load More Books', on_click=self.load_more_batch) \
                    .props('outline color=indigo rounded').classes('w-full sm:w-48 font-bold')

async def books_page():
    app.storage.client['page_path'] = '/books'
    page = BookCollection()
    page.build_ui()
    await page.load_books()