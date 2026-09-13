from nicegui import ui, app
from components.sidebar import sidebar
from components.header import header
from components.bottom_nav import bottom_nav
from core.database.mongo_manager import mongo_db
from pathlib import Path
from core.config import settings

class BookDetailsPage:
    def __init__(self, book_id: str):
        self.book_id = book_id
        self.book = None
        self.content_container = None

    async def init(self):
        self.book = await mongo_db.get_book_details(self.book_id)
        if not self.book:
            ui.notify("Book not found.", type='negative')
            ui.navigate.to('/books')
            return
        self.render_content()

    def render_content(self):
        if not self.content_container or not self.book:
            return

        author_name = "Unknown"
        authors_data = self.book.get('display_author') or self.book.get('authors')
        if isinstance(authors_data, list) and authors_data:
            first = authors_data[0]
            author_name = first.get('name', 'Unknown') if isinstance(first, dict) else str(first)
        elif isinstance(authors_data, str):
            author_name = authors_data

        title = self.book.get('title', 'Untitled')
        summaries = self.book.get('summaries')
        desc = summaries[0] if summaries and isinstance(summaries, list) else self.book.get('description', 'No synopsis available for this document.')
        
        # Cover resolution
        disk_cover = settings.BASE_DIR / 'data' / 'books' / self.book_id / 'cover.jpg'
        if disk_cover.exists():
            cover_url = f"/static_books/{self.book_id}/cover.jpg"
        elif self.book.get('cover_image') and not str(self.book.get('cover_image')).endswith('default_cover.png'):
            cover_url = self.book.get('cover_image')
        else:
            cover_url = "/static/default_cover.svg"

        with self.content_container:
            with ui.row().classes('w-full flex-col md:flex-row gap-6 md:gap-12 items-start'):
                
                # LEFT: Cover & Quick Actions
                with ui.column().classes('w-full md:w-1/3 lg:w-1/4 items-center'):
                    with ui.card().classes('p-0 rounded-2xl sm:rounded-3xl overflow-hidden shadow-xl sm:shadow-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 w-44 sm:w-52 md:w-64 aspect-[2/3]'):
                        ui.image(cover_url).classes('w-full h-full object-cover')
                    
                    with ui.column().classes('w-full max-w-xs gap-2.5 sm:gap-3 mt-4 sm:mt-6'):
                        with ui.button(on_click=lambda: ui.navigate.to(f"/read/{self.book_id}")) \
                            .classes('w-full bg-indigo-600 hover:bg-indigo-700 text-white rounded-2xl py-3 font-bold shadow-md'):
                            ui.icon('menu_book').classes('mr-2')
                            ui.label('Read Now')
                        
                        with ui.button(on_click=lambda: ui.navigate.to('/chat')) \
                            .classes('w-full bg-white dark:bg-slate-800 text-indigo-600 dark:text-indigo-400 border border-indigo-200 dark:border-indigo-800 hover:bg-indigo-50 dark:hover:bg-indigo-950/40 rounded-2xl py-3 font-bold'):
                            ui.icon('smart_toy').classes('mr-2')
                            ui.label('Ask TARS AI')

                # RIGHT: Metadata & Details
                with ui.column().classes('flex-1 gap-5 sm:gap-6 w-full'):
                    with ui.column().classes('gap-1'):
                        ui.label(title).classes('text-2xl sm:text-3xl md:text-5xl font-black text-slate-800 dark:text-slate-100 leading-tight tracking-tight')
                        ui.label(f"by {author_name}").classes('text-base sm:text-xl text-indigo-600 dark:text-indigo-400 font-semibold')

                    # Badges
                    with ui.row().classes('gap-2 my-1 flex-wrap'):
                        ui.label(self.book.get('file_type', 'E-BOOK').upper()).classes('px-3 py-1 bg-indigo-50 dark:bg-indigo-950/40 text-indigo-700 dark:text-indigo-300 text-xs font-bold rounded-full shadow-sm')
                        for lang in self.book.get('languages', ['en'])[:2]:
                            ui.label(lang.upper()).classes('px-3 py-1 bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300 text-xs font-bold rounded-full shadow-sm')

                    ui.separator().classes('opacity-50')
                    
                    # Context Box
                    genres = self.book.get('genres', []) or self.book.get('subjects', [])
                    if genres:
                        with ui.column().classes('gap-2 w-full p-4 sm:p-5 bg-slate-50 dark:bg-slate-800/60 rounded-2xl border border-slate-100 dark:border-slate-800'):
                            ui.label('Categories & Topics').classes('text-xs font-bold text-indigo-500 uppercase tracking-wider')
                            with ui.row().classes('gap-2 flex-wrap'):
                                for g in genres[:6]:
                                    with ui.row().classes('items-center gap-1 bg-purple-100/50 dark:bg-purple-950/40 px-2.5 py-1 rounded-lg'):
                                        ui.icon('tag', size='14px').classes('text-purple-600 dark:text-purple-400')
                                        ui.label(str(g)).classes('text-xs font-bold text-purple-700 dark:text-purple-300')

                    # Synopsis
                    with ui.column().classes('gap-2'):
                        ui.label('Synopsis').classes('text-xs font-bold text-slate-400 uppercase tracking-wider')
                        ui.markdown(desc).classes('text-slate-600 dark:text-slate-300 leading-relaxed text-sm sm:text-base max-w-prose break-words')

                    # File Details Box
                    with ui.row().classes('bg-slate-50 dark:bg-slate-800/60 p-4 sm:p-5 rounded-2xl border border-slate-100 dark:border-slate-800 gap-6 sm:gap-8 mt-2 flex-wrap'):
                        with ui.column().classes('gap-0.5'):
                            ui.label('Added On').classes('text-[10px] text-slate-400 uppercase font-bold')
                            date_str = mongo_db.format_added_date(self.book.get('added_at'))
                            ui.label(date_str).classes('font-bold text-slate-700 dark:text-slate-200 text-sm')
                        
                        with ui.column().classes('gap-0.5'):
                            ui.label('Format').classes('text-[10px] text-slate-400 uppercase font-bold')
                            ui.label(f"Digital {self.book.get('file_type', 'E-Book').upper()}").classes('font-bold text-slate-700 dark:text-slate-200 text-sm')

    def build_ui(self):
        drawer = sidebar()
        header(drawer_reference=drawer)
        bottom_nav()
        
        with ui.column().classes('w-full min-h-screen pt-20 px-3 sm:px-4 md:pt-24 md:px-8 max-w-7xl mx-auto bg-slate-50/50 dark:bg-transparent pb-32 md:pb-24'):
            ui.button('Back to Library', icon='arrow_back', on_click=lambda: ui.navigate.to('/books')) \
                .props('flat dense color=indigo size=md').classes('mb-3 sm:mb-4 font-bold')
            self.content_container = ui.column().classes('w-full')

async def book_page(book_id: str):
    app.storage.client['page_path'] = '/books' 
    page = BookDetailsPage(book_id)
    page.build_ui()
    await page.init()