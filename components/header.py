from nicegui import ui, app
from core.database.mongo_manager import mongo_db
from core.auth.jwt_handler import clear_user_session
import logging

# Setup Logger
logger = logging.getLogger("APP_HEADER")

def header(drawer_reference=None):
    """
    The Main Application Header with glassmorphism and fast indexed search.
    """

    # --- LOGIC: SEARCH HANDLER ---
    async def handle_search(e):
        """Executes fast server-side search."""
        try:
            query = e.sender.value.strip()
        except AttributeError:
            query = str(getattr(e, 'value', '')).strip()

        if not query:
            return

        try:
            # 1. Indexed Server-Side Search
            matches = await mongo_db.search_books(query, limit=10)

            # 2. Navigation Logic
            if len(matches) == 1:
                target_book = matches[0]
                ui.notify(f"Opening '{target_book.get('title')}'...", type='positive')
                ui.navigate.to(f"/book/{target_book.get('id')}")
            elif len(matches) > 1:
                ui.notify(f"Found {len(matches)} matches.", type='info')
                app.storage.client['search_filter'] = query
                ui.navigate.to('/books')
            else:
                ui.notify(f"No books found for '{query}'", type='warning')

        except Exception as err:
            logger.error(f"Search Error: {err}")
            ui.notify("Search temporarily unavailable.", type='negative')
        finally:
            if hasattr(e, 'sender') and hasattr(e.sender, 'value'):
                e.sender.value = ""

    # --- UI: MOBILE SEARCH DIALOG ---
    def open_mobile_search():
        with ui.dialog() as search_dialog, ui.card().classes('w-full m-4 p-4 rounded-2xl shadow-xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800'):
            ui.label('Search Library').classes('text-lg font-bold text-slate-800 dark:text-slate-100 mb-2')
            mobile_input = ui.input(placeholder='Book title, author, topic...') \
                .props('rounded outlined autofocus prepend-icon=search') \
                .classes('w-full')

            mobile_input.on('keydown.enter', lambda e: (handle_search(mobile_input), search_dialog.close()))

            with ui.row().classes('w-full justify-end mt-4 gap-2'):
                ui.button('Cancel', on_click=search_dialog.close).props('flat color=grey')
                ui.button('Search', on_click=lambda: (handle_search(mobile_input), search_dialog.close())) \
                    .props('unelevated color=indigo')
        search_dialog.open()

    # --- UI: MAIN HEADER LAYOUT ---
    with ui.header().classes(
        'bg-white/90 dark:bg-slate-900/90 backdrop-blur-md border-b border-slate-200/80 '
        'dark:border-slate-800/80 items-center px-3 md:px-6 h-16 fixed top-0 w-full z-40'
    ).props('elevated=False'):

        # 1. LEFT SECTION: NAVIGATION & BRAND
        with ui.row().classes('items-center gap-2'):
            if drawer_reference:
                ui.button(icon='menu', on_click=drawer_reference.toggle) \
                    .props('flat round dense color=grey-8') \
                    .tooltip('Toggle Sidebar')

            with ui.row().classes('cursor-pointer items-center gap-2.5').on('click', lambda: ui.navigate.to('/')):
                with ui.element('div').classes('p-2 rounded-xl bg-indigo-50 dark:bg-indigo-900/40 text-indigo-600 dark:text-indigo-400 flex items-center justify-center'):
                    ui.icon('auto_stories', size='sm')
                ui.label('Libre Library').classes('text-xl font-black text-slate-800 dark:text-slate-100 hidden sm:block tracking-tight')

        ui.space()

        # 2. CENTER SECTION: DESKTOP SEARCH
        with ui.row().classes('hidden md:flex flex-grow max-w-xl mx-4'):
            search_input = ui.input(placeholder='Search books, authors, or topics...') \
                .props('rounded outlined dense prepend-icon=search bg-color=slate-50') \
                .classes('w-full transition-all focus-within:shadow-md focus-within:bg-white dark:focus-within:bg-slate-800')
            search_input.on('keydown.enter', handle_search)

        ui.space()

        # 3. RIGHT SECTION: ACTIONS & PROFILE
        with ui.row().classes('items-center gap-1.5'):
            ui.button(icon='search', on_click=open_mobile_search) \
                .props('flat round dense color=grey-7') \
                .classes('md:hidden')

            # Quick Actions Menu
            with ui.button(icon='add_circle').props('flat round dense color=indigo'):
                with ui.menu().classes('bg-white dark:bg-slate-900 shadow-xl border border-slate-100 dark:border-slate-800 rounded-2xl p-1'):
                    ui.menu_item('Upload Book', on_click=lambda: ui.navigate.to('/upload')).props('prepend-icon=cloud_upload')
                    ui.menu_item('New Study Task', on_click=lambda: ui.navigate.to('/planner')).props('prepend-icon=check_circle')

            # Profile Menu
            with ui.button().props('flat round dense no-caps'):
                ui.avatar(icon='person', color='indigo-50', text_color='indigo', size='md')
                with ui.menu().classes('bg-white dark:bg-slate-900 shadow-xl border border-slate-100 dark:border-slate-800 rounded-2xl p-1'):
                    ui.menu_item('My Profile', on_click=lambda: ui.navigate.to('/profile')).props('prepend-icon=person')
                    ui.menu_item('Logout', on_click=lambda: (clear_user_session(), ui.navigate.to('/login'))) \
                        .classes('text-red-600').props('prepend-icon=logout')