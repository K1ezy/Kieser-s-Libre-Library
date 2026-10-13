from nicegui import ui, app
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime
from components.sidebar import sidebar
from components.header import header
from components.bottom_nav import bottom_nav
from components.book_card import book_card
from core.database.mongo_manager import mongo_db
from core.auth.jwt_handler import get_current_user_role

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
        self.batch_size = 28
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
        self.sort_select = None
        self.search_input = None
        self.active_filter_summary = None
        self.reset_filter_btn = None
        self.status_tab_container = None

    def reset_filters(self):
        """Clears all active search and filter constraints."""
        self.state['search_term'] = ''
        self.state['format_filter'] = 'All'
        self.state['shelf_filter'] = 'All'
        self.state['author_filter'] = 'All'
        self.state['sort_by'] = 'Newest'
        self.state['status_tab'] = 'all'
        if self.search_input:
            self.search_input.value = ''
        if self.format_select:
            self.format_select.value = 'All'
        if self.shelf_select:
            self.shelf_select.value = 'All'
        if self.author_select:
            self.author_select.value = 'All'
        if self.sort_select:
            self.sort_select.value = 'Newest'
        self.render_status_tabs()
        self.apply_filters_and_sort()

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

            catalog_proj = {
                "_id": 0, "id": 1, "title": 1, "display_author": 1, "authors": 1,
                "file_type": 1, "formats": 1, "cover_image": 1, "custom_shelf": 1,
                "added_at": 1, "created_at": 1, "is_favorite": 1
            }
            all_books = await mongo_db.get_all_books(limit=2000, sort_by='newest', projection=catalog_proj)
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
        reading_count = sum(1 for b in self.books if self.user_progress.get(b.get('id'), {}).get('status') in ('reading', 'currently_reading'))
        want_count = sum(1 for b in self.books if self.user_progress.get(b.get('id'), {}).get('status') in ('want_to_read', 'to_read'))
        done_count = sum(1 for b in self.books if self.user_progress.get(b.get('id'), {}).get('status') in ('completed', 'done'))

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
        elif st == 'reading':
            temp_list = [b for b in temp_list if self.user_progress.get(b.get('id'), {}).get('status') in ('reading', 'currently_reading')]
        elif st == 'want_to_read':
            temp_list = [b for b in temp_list if self.user_progress.get(b.get('id'), {}).get('status') in ('want_to_read', 'to_read')]
        elif st == 'completed':
            temp_list = [b for b in temp_list if self.user_progress.get(b.get('id'), {}).get('status') in ('completed', 'done')]

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
            if len(self.filtered_list) == len(self.books):
                self.hero_count_label.text = f"{len(self.filtered_list)} books available"
            else:
                self.hero_count_label.text = f"Showing {len(self.filtered_list)} of {len(self.books)} books"

        if self.active_filter_summary:
            is_filtered = (
                bool(self.state['search_term'].strip()) or
                self.state['format_filter'] != 'All' or
                self.state['shelf_filter'] != 'All' or
                self.state['author_filter'] != 'All' or
                self.state['sort_by'] != 'Newest' or
                self.state['status_tab'] != 'all'
            )
            if is_filtered:
                self.active_filter_summary.text = f"{len(self.filtered_list)} matches"
                if self.reset_filter_btn:
                    self.reset_filter_btn.set_visibility(True)
            else:
                self.active_filter_summary.text = f"{len(self.books)} books total"
                if self.reset_filter_btn:
                    self.reset_filter_btn.set_visibility(False)

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

            can_delete = get_current_user_role() in ('admin', 'librarian')
            delete_cb = self.prompt_delete if can_delete else None

            for book in batch:
                b_id = book.get('id')
                if b_id and b_id in self.user_progress:
                    book['progress_percent'] = self.user_progress[b_id].get('progress_percent')
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
        """Shows deletion confirmation dialog (admin/librarian restricted)."""
        if get_current_user_role() not in ('admin', 'librarian'):
            ui.notify("Administrator or Librarian privileges required to delete books.", type='warning')
            return

        with ui.dialog() as dialog, ui.card().classes('w-[calc(100vw-1.5rem)] max-w-md p-5 sm:p-6 rounded-2xl bg-white border border-slate-200 shadow-2xl'):
            ui.label(f"Delete '{title}'?").classes('text-base sm:text-lg font-bold text-rose-600')
            ui.label("This will permanently remove the file, metadata, and AI knowledge chunks.").classes('text-xs sm:text-sm text-slate-500 mt-1')

            with ui.row().classes('w-full justify-end gap-2.5 mt-5 sm:mt-6'):
                ui.button('Cancel', on_click=dialog.close).props('flat color=grey')

                async def confirm():
                    confirm_btn.props('loading')
                    if get_current_user_role() not in ('admin', 'librarian'):
                        ui.notify("Administrator or Librarian privileges required to delete books.", type='negative')
                        dialog.close()
                        return
                    success = await mongo_db.delete_book(book_id)
                    dialog.close()
                    if success:
                        ui.notify(f"Deleted '{title}'", type='positive')
                        await self.load_books()
                    else:
                        ui.notify("Failed to delete book", type='negative')

                confirm_btn = ui.button('Delete', color='red', on_click=confirm).props('unelevated font-bold rounded')
        dialog.open()


    def build_ui(self):
        drawer = sidebar()
        header(drawer_reference=drawer)
        bottom_nav()

        with ui.column().classes('w-full min-h-[100dvh] pt-[calc(4.5rem+env(safe-area-inset-top,0px))] px-3 sm:px-6 md:pt-24 md:px-10 max-w-[1700px] mx-auto pb-[calc(5rem+env(safe-area-inset-bottom,0px))] md:pb-16'):

            # --- COMPACT WORKSPACE HEADER (Streamlined Document Workspace) ---
            with ui.row().classes('w-full justify-between items-center mb-4 sm:mb-5 gap-3 flex-wrap'):
                with ui.row().classes('items-center gap-3'):
                    with ui.element('div').classes('p-2.5 rounded-xl bg-indigo-50 border border-indigo-100 text-indigo-600 shadow-xs shrink-0 flex items-center justify-center'):
                        ui.icon('local_library', size='sm')
                    with ui.column().classes('gap-0.5'):
                        with ui.row().classes('items-center gap-2.5 flex-wrap'):
                            ui.label('Library Archive').classes('text-xl sm:text-2xl font-black text-slate-900 tracking-tight')
                            self.hero_count_label = ui.label('Loading collection...').classes(
                                'text-xs font-bold bg-indigo-50 text-indigo-700 px-2.5 py-0.5 rounded-full border border-indigo-200/80 shadow-xs'
                            )
                        ui.label('Search, filter, and organize your document collection and reading catalog.').classes('text-xs sm:text-sm text-slate-500 font-medium')
                
                # Workspace Actions: OPDS Feed & Refresh
                with ui.row().classes('items-center gap-2'):
                    ui.button('OPDS Feed', icon='rss_feed', on_click=lambda: ui.run_javascript("""
                        navigator.clipboard.writeText(window.location.origin + '/opds');
                        alert('OPDS Catalog Feed URL copied: ' + window.location.origin + '/opds');
                    """)).props('flat dense rounded-xl text-color=slate-700 size=sm font-bold')\
                       .classes('bg-white hover:bg-slate-50 border border-slate-200 text-slate-700 shadow-xs')\
                       .tooltip('Copy OPDS Feed URL for KOReader / Moon+ Reader')

                    ui.button(icon='refresh', on_click=self.load_books)\
                        .props('flat dense round text-color=slate-700 size=sm')\
                        .classes('bg-white hover:bg-slate-50 border border-slate-200 text-slate-700 shadow-xs')\
                        .tooltip('Reload Library Catalog')

            # --- FILTER & SEARCH CONTROL CENTER WINDOW ---
            with ui.card().classes('w-full bg-white border border-slate-200 p-4 sm:p-6 mb-6 sm:mb-8 rounded-2xl sm:rounded-3xl shadow-sm gap-4'):
                
                # 1. Search Bar & Summary
                with ui.row().classes('w-full items-center justify-between gap-3 flex-wrap'):
                    with ui.row().classes('items-center gap-2 flex-1 min-w-[240px]'):
                        self.search_input = ui.input(placeholder='Search Title, Author, or Keyword... (Press /)',
                                 on_change=lambda e: (self.state.update({'search_term': e.value}), self.apply_filters_and_sort())) \
                            .bind_value(self.state, 'search_term') \
                            .props('id=global-search-input outlined rounded-xl dense icon=search clearable bg-color=slate-50') \
                            .classes('w-full text-sm')

                    with ui.row().classes('items-center gap-2 shrink-0'):
                        self.active_filter_summary = ui.label('').classes('text-xs font-bold text-slate-500')
                        self.reset_filter_btn = ui.button('Reset Filters', icon='restart_alt', on_click=self.reset_filters) \
                            .props('flat rounded-xl color=indigo size=sm font-bold').classes('text-xs')
                        self.reset_filter_btn.set_visibility(False)

                # 2. Reading Status Tabs
                self.status_tab_container = ui.row().classes('w-full gap-1.5 sm:gap-2 items-center flex-nowrap overflow-x-auto no-scrollbar touch-pan-x py-1')

                # 3. Filter Controls: 4 Columns with Clean Micro-Headers (eliminates duplicate label rendering)
                with ui.grid().classes('w-full grid-cols-2 md:grid-cols-4 gap-3 sm:gap-4 pt-3 border-t border-slate-100'):
                    
                    # Column 1: Format
                    with ui.column().classes('gap-1 w-full'):
                        with ui.row().classes('items-center gap-1.5 px-0.5'):
                            ui.icon('picture_as_pdf', size='14px').classes('text-indigo-600')
                            ui.label('Format').classes('text-[11px] font-bold text-slate-500 uppercase tracking-wider')
                        self.format_select = ui.select(self.unique_formats, value='All',
                                  on_change=lambda e: (self.state.update({'format_filter': e.value}), self.apply_filters_and_sort())) \
                            .props('outlined rounded-xl dense options-dense bg-color=slate-50').classes('w-full text-xs sm:text-sm font-medium')

                    # Column 2: Custom Shelf
                    with ui.column().classes('gap-1 w-full'):
                        with ui.row().classes('items-center gap-1.5 px-0.5'):
                            ui.icon('collections_bookmark', size='14px').classes('text-indigo-600')
                            ui.label('Custom Shelf').classes('text-[11px] font-bold text-slate-500 uppercase tracking-wider')
                        self.shelf_select = ui.select(self.unique_shelves, value='All',
                                  on_change=lambda e: (self.state.update({'shelf_filter': e.value}), self.apply_filters_and_sort())) \
                            .props('outlined rounded-xl dense options-dense bg-color=slate-50').classes('w-full text-xs sm:text-sm font-medium')

                    # Column 3: Author
                    with ui.column().classes('gap-1 w-full'):
                        with ui.row().classes('items-center gap-1.5 px-0.5'):
                            ui.icon('person', size='14px').classes('text-indigo-600')
                            ui.label('Author').classes('text-[11px] font-bold text-slate-500 uppercase tracking-wider')
                        self.author_select = ui.select(self.unique_authors, value='All',
                                  on_change=lambda e: (self.state.update({'author_filter': e.value}), self.apply_filters_and_sort())) \
                            .props('outlined rounded-xl dense options-dense bg-color=slate-50').classes('w-full text-xs sm:text-sm font-medium')

                    # Column 4: Sort By
                    with ui.column().classes('gap-1 w-full'):
                        with ui.row().classes('items-center gap-1.5 px-0.5'):
                            ui.icon('swap_vert', size='14px').classes('text-indigo-600')
                            ui.label('Sort By').classes('text-[11px] font-bold text-slate-500 uppercase tracking-wider')
                        self.sort_select = ui.select(['Newest', 'Oldest', 'A-Z', 'Author'], value='Newest',
                                  on_change=lambda e: (self.state.update({'sort_by': e.value}), self.apply_filters_and_sort())) \
                            .props('outlined rounded-xl dense options-dense bg-color=slate-50').classes('w-full text-xs sm:text-sm font-medium')

            # --- BOOKS GRID (Fluid Auto-Adjusting Layout across all mobile & desktop viewports) ---
            with ui.column().classes('w-full mb-8'):
                with ui.element('div').classes('w-full fluid-book-grid') as self.grid_container:
                    pass

                with ui.row().classes('w-full justify-center mt-6'):
                    self.load_more_btn = ui.button('Load More Books', on_click=self.load_more_batch) \
                        .props('outline color=indigo rounded').classes('w-full sm:w-48 font-bold')

async def books_page():
    app.storage.client['page_path'] = '/books'
    page = BookCollection()
    page.build_ui()
    await page.load_books()