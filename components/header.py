from nicegui import ui, app
from core.database.mongo_manager import mongo_db
from core.auth.jwt_handler import clear_user_session
import logging

logger = logging.getLogger("APP_HEADER")

def header(drawer_reference=None):
    """
    Main Application Header with glassmorphism, responsive navigation, and fast indexed search.
    Clean light color theory matching with zero dark mode clutter.
    """
    async def handle_search(e):
        try:
            query = e.sender.value.strip()
        except AttributeError:
            query = str(getattr(e, 'value', '')).strip()

        if not query:
            return

        try:
            matches = await mongo_db.search_books(query, limit=10)
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

    def open_mobile_search():
        with ui.dialog() as search_dialog, ui.card().classes('w-[calc(100vw-2rem)] max-w-md p-5 rounded-3xl shadow-2xl bg-white border border-slate-200'):
            with ui.row().classes('w-full justify-between items-center mb-2'):
                ui.label('Search Library').classes('text-base font-black text-slate-800')
                ui.button(icon='close', on_click=search_dialog.close).props('flat round dense size=sm color=grey')

            mobile_input = ui.input(placeholder='Book title, author, topic...') \
                .props('rounded outlined autofocus prepend-icon=search') \
                .classes('w-full text-base')

            mobile_input.on('keydown.enter', lambda e: (handle_search(mobile_input), search_dialog.close()))

            with ui.row().classes('w-full justify-end mt-4 gap-2'):
                ui.button('Cancel', on_click=search_dialog.close).props('flat rounded-xl color=grey size=sm font-bold')
                ui.button('Search', on_click=lambda: (handle_search(mobile_input), search_dialog.close())) \
                    .props('unelevated rounded-xl color=indigo size=sm font-bold shadow-md')
        search_dialog.open()

    with ui.header().classes(
        'bg-white/95 backdrop-blur-md border-b border-slate-200 '
        'items-center px-3 sm:px-4 md:px-6 h-16 pt-[env(safe-area-inset-top,0px)] '
        'fixed top-0 w-full z-40 select-none shadow-sm'
    ).props('elevated=False'):

        # 1. LEFT: SIDEBAR TOGGLE & BRAND LOGO
        with ui.row().classes('items-center gap-1.5 sm:gap-2 shrink-0 min-w-0'):
            if drawer_reference:
                ui.button(icon='menu', on_click=drawer_reference.toggle) \
                    .props('flat round dense color=grey-8 size=md') \
                    .tooltip('Toggle Sidebar')

            with ui.row().classes('cursor-pointer items-center gap-2 min-w-0').on('click', lambda: ui.navigate.to('/')):
                with ui.element('div').classes('p-1.5 sm:p-2 rounded-xl bg-indigo-50 text-indigo-600 flex items-center justify-center shrink-0 border border-indigo-100 shadow-sm'):
                    ui.icon('local_library', size='sm')
                ui.label('Libre Library').classes('text-base sm:text-xl font-black text-slate-900 tracking-tight truncate max-w-[130px] xs:max-w-none')

        ui.space()

        # 2. CENTER: DESKTOP SEARCH INPUT
        with ui.row().classes('hidden md:flex flex-grow max-w-xl mx-4'):
            search_input = ui.input(placeholder='Search books, authors, or topics... (Press / to focus)') \
                .props('id=global-header-search rounded outlined dense prepend-icon=search bg-color=slate-50') \
                .classes('w-full transition-all focus-within:shadow-md focus-within:bg-white text-xs')
            search_input.on('keydown.enter', handle_search)

        ui.space()

        # 3. RIGHT: MOBILE SEARCH, KEYBOARD SHORTCUTS & USER PROFILE
        with ui.row().classes('items-center gap-1 sm:gap-2 shrink-0'):
            ui.button(icon='keyboard', on_click=lambda: ui.run_javascript('window.LibreAccessibility && window.LibreAccessibility.showHelp()')) \
                .props('flat round dense color=grey-7 size=md') \
                .tooltip('Keyboard Shortcuts (?)') \
                .classes('hidden sm:inline-flex')

            ui.button(icon='search', on_click=open_mobile_search) \
                .props('flat round dense color=grey-7 size=md') \
                .classes('md:hidden')

            user_name = app.storage.user.get('username') or 'Account'
            user_role = app.storage.user.get('role', 'user')

            with ui.button().props('flat round dense no-caps size=md').classes('p-0.5 ml-0.5 sm:ml-1'):
                ui.avatar(icon='person', color='indigo-50', text_color='indigo', size='32px') \
                    .classes('border border-indigo-200 shadow-sm')
                with ui.menu().classes('bg-white shadow-2xl border border-slate-200 rounded-2xl p-2 min-w-[190px]'):
                    with ui.row().classes('px-3 py-2 border-b border-slate-100 mb-1 items-center gap-2.5'):
                        ui.icon('account_circle', size='sm').classes('text-indigo-600')
                        with ui.column().classes('gap-0 flex-1 min-w-0'):
                            ui.label(user_name).classes('text-xs font-bold text-slate-900 truncate w-full')
                            ui.label(user_role.upper()).classes('text-[9px] font-bold text-indigo-600 uppercase tracking-wider')

                    ui.menu_item('Account Profile', on_click=lambda: ui.navigate.to('/profile')).props('prepend-icon=person').classes('text-xs font-medium')
                    if user_role == 'admin':
                        ui.menu_item('Admin Console', on_click=lambda: ui.navigate.to('/admin')).props('prepend-icon=admin_panel_settings').classes('text-xs font-medium')

                    ui.separator().classes('my-1')
                    def sign_out():
                        clear_user_session()
                        ui.notify("Signed out successfully.", type='info')
                        ui.navigate.to('/login')
                    ui.menu_item('Sign Out', on_click=sign_out).props('prepend-icon=logout').classes('text-xs font-bold text-rose-600')