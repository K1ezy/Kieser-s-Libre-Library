from nicegui import ui, app
import logging
from typing import Dict, Any, List
from components.sidebar import sidebar
from components.header import header
from components.book_card import book_card
from core.database.mongo_manager import mongo_db

# Setup Logger
logger = logging.getLogger("LIBRE_LIBRARY_COLLECTION")

class BookCollection:
    """
    Optimized Library Collection with server-side search, filtering,
    pagination, and unified book cards.
    """
    def __init__(self):
        self.books: List[Dict[str, Any]] = []
        self.filtered_list: List[Dict[str, Any]] = []
        self.batch_size = 20
        self.current_index = 0
        
        # Filter State
        self.state = {
            'search_term': '',
            'sort_by': 'Newest',
            'format_filter': 'All',
            'author_filter': 'All',
        }
        
        self.unique_formats = ['All', 'PDF', 'EPUB', 'DOCX', 'PPTX', 'TXT']
        self.unique_authors = ['All']
        
        # UI References
        self.grid_container = None
        self.load_more_btn = None
        self.hero_count_label = None
        self.format_select = None
        self.author_select = None

    async def load_books(self):
        """Loads books using indexed queries and extracts unique author options."""
        if 'search_filter' in app.storage.client:
            self.state['search_term'] = app.storage.client.pop('search_filter')

        try:
            # Query books from DB
            all_books = await mongo_db.get_all_books(
                limit=1000,
                sort_by=self.state['sort_by']
            )
            self.books = all_books or []
            
            # Extract distinct authors for filter dropdown
            authors = set()
            for b in self.books:
                auth = b.get('display_author') or b.get('authors', 'Unknown')
                if isinstance(auth, list) and auth:
                    auth = auth[0].get('name', str(auth[0])) if isinstance(auth[0], dict) else str(auth[0])
                if auth and str(auth).lower() != 'unknown':
                    authors.add(str(auth))

            self.unique_authors = ['All'] + sorted(list(authors))
            if self.author_select:
                self.author_select.options = self.unique_authors
                if self.author_select.value not in self.unique_authors:
                    self.author_select.value = 'All'
                self.author_select.update()

            self.apply_filters_and_sort()

        except Exception as e:
            logger.error(f"Error loading books: {e}", exc_info=True)
            ui.notify(f"Error loading library: {e}", type='negative')
            self.books = []

    def apply_filters_and_sort(self):
        """Filters and sorts the book list, resetting pagination."""
        temp_list = self.books.copy()
        query = self.state['search_term'].lower().strip()

        if query:
            temp_list = [
                b for b in temp_list
                if query in b.get('title', '').lower() or 
                   query in str(b.get('display_author', '')).lower() or
                   query in str(b.get('authors', '')).lower()
            ]

        fmt = self.state['format_filter']
        if fmt != 'All':
            temp_list = [
                b for b in temp_list
                if fmt.lower() in [k.lower() for k in b.get('formats', {}).keys()] or
                   fmt.lower() == str(b.get('file_type', '')).lower()
            ]

        author = self.state['author_filter']
        if author != 'All':
            temp_list = [
                b for b in temp_list
                if author in str(b.get('display_author', '')) or author in str(b.get('authors', ''))
            ]

        sort_mode = self.state['sort_by']
        if sort_mode == 'Newest':
            temp_list.sort(key=lambda x: x.get('added_at', 0) if isinstance(x.get('added_at'), (int, float)) else 0, reverse=True)
        elif sort_mode == 'Oldest':
            temp_list.sort(key=lambda x: x.get('added_at', 0) if isinstance(x.get('added_at'), (int, float)) else 0)
        elif sort_mode == 'A-Z':
            temp_list.sort(key=lambda x: x.get('title', '').lower())
        elif sort_mode == 'Author':
            temp_list.sort(key=lambda x: str(x.get('display_author') or x.get('authors', '')).lower())

        self.filtered_list = temp_list

        if self.hero_count_label:
            self.hero_count_label.text = f"{len(self.filtered_list)} books available"

        self.current_index = 0
        if self.grid_container:
            self.grid_container.clear()

        self.load_more_batch()

    def load_more_batch(self):
        """Infinite scroll: renders next batch of unified book cards."""
        start = self.current_index
        end = start + self.batch_size
        batch = self.filtered_list[start:end]

        with self.grid_container:
            for book in batch:
                book_card(book, action_target='read', on_delete=self.prompt_delete)

        self.current_index = end

        if self.load_more_btn:
            if self.current_index >= len(self.filtered_list):
                self.load_more_btn.disable()
                self.load_more_btn.text = 'End of Collection'
            else:
                self.load_more_btn.enable()
                self.load_more_btn.text = 'Load More Books'

    def prompt_delete(self, book_id: str, title: str):
        """Shows deletion confirmation dialog."""
        with ui.dialog() as dialog, ui.card().classes('p-6 rounded-2xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 shadow-2xl'):
            ui.label(f"Delete '{title}'?").classes('text-lg font-bold text-red-600')
            ui.label("This will permanently remove the file, metadata, and AI knowledge chunks.").classes('text-sm text-slate-500 dark:text-slate-400 mt-1')
            
            with ui.row().classes('w-full justify-end gap-3 mt-6'):
                ui.button('Cancel', on_click=dialog.close).props('flat color=grey')
                
                async def confirm():
                    dialog.close()
                    success = await mongo_db.delete_book(book_id)
                    if success:
                        ui.notify(f"Deleted '{title}'", type='positive')
                        await self.load_books()
                    else:
                        ui.notify("Failed to delete book", type='negative')

                ui.button('Delete', color='red', on_click=confirm).props('unelevated')
        dialog.open()

    def build_ui(self):
        drawer = sidebar()
        header(drawer_reference=drawer)

        with ui.column().classes('w-full min-h-screen pt-20 px-4 md:pt-24 md:px-8 max-w-7xl mx-auto bg-slate-50/50 dark:bg-transparent'):
            
            # --- HERO / FILTER BAR ---
            with ui.column().classes('w-full bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 px-6 py-6 mb-8 rounded-3xl shadow-sm'):
                with ui.row().classes('w-full items-end justify-between gap-4 wrap'):
                    with ui.column().classes('gap-1'):
                        ui.label('Library Archive').classes('text-3xl font-black text-slate-900 dark:text-slate-100 tracking-tight')
                        self.hero_count_label = ui.label('Loading collection...').classes('text-slate-500 dark:text-slate-400 font-medium')
                    
                    with ui.row().classes('w-full md:w-auto gap-2.5 items-center flex-wrap'):
                        # Format Filter
                        self.format_select = ui.select(self.unique_formats, value='All', label='Format',
                                  on_change=lambda e: (self.state.update({'format_filter': e.value}), self.apply_filters_and_sort())) \
                            .props('outlined dense options-dense').classes('w-full md:w-32')

                        # Author Filter
                        self.author_select = ui.select(self.unique_authors, value='All', label='Author',
                                  on_change=lambda e: (self.state.update({'author_filter': e.value}), self.apply_filters_and_sort())) \
                            .props('outlined dense options-dense').classes('w-full md:w-48')

                        # Sorting
                        ui.select(['Newest', 'Oldest', 'A-Z', 'Author'], value='Newest', label='Sort By',
                                  on_change=lambda e: (self.state.update({'sort_by': e.value}), self.apply_filters_and_sort())) \
                            .props('outlined dense options-dense').classes('w-full md:w-32')

                        # Live Local Filter
                        ui.input(placeholder='Filter Title/Author...', 
                                 on_change=lambda e: (self.state.update({'search_term': e.value}), self.apply_filters_and_sort())) \
                            .bind_value(self.state, 'search_term') \
                            .props('outlined rounded dense icon=search clearable').classes('w-full md:w-60')

                        # Refresh
                        ui.button(icon='refresh', on_click=self.load_books).props('flat round dense color=indigo').tooltip('Reload Library')

            # --- BOOKS GRID ---
            with ui.column().classes('w-full pb-24 items-center'):
                with ui.grid().classes('w-full gap-4 md:gap-6 grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 mb-8') as self.grid_container:
                    pass

                self.load_more_btn = ui.button('Load More Books', on_click=self.load_more_batch) \
                    .props('outline color=indigo rounded').classes('w-full md:w-48 font-bold')

async def books_page():
    app.storage.client['page_path'] = '/books'
    page = BookCollection()
    page.build_ui()
    await page.load_books()