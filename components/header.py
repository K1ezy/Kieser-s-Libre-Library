from nicegui import ui, app
from core.database.mongo_manager import mongo_db
from core.auth.jwt_handler import clear_user_session, get_current_user_role
import logging

logger = logging.getLogger(__name__)

_client_avatar_refreshers = {}


def refresh_header_avatar():
    """Triggers real-time synchronization of the top navbar profile picture across the app."""
    try:
        from nicegui import context
        client_id = context.client.id
        ref = _client_avatar_refreshers.get(client_id)
        if ref:
            ref.refresh()
    except Exception as err:
        logger.debug(f"Navbar avatar refresh skipped: {err}")


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
        with ui.dialog() as search_dialog, ui.card().classes('w-full max-w-md p-5 rounded-t-3xl sm:rounded-3xl shadow-2xl bg-white border border-slate-200'):
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
                    .props('flat round dense color=grey-8 size=md aria-label="Open Navigation Menu"') \
                    .classes('w-10 h-10 flex items-center justify-center hover:bg-slate-100 rounded-full transition-colors') \
                    .tooltip('Toggle Sidebar')

            with ui.row().classes('cursor-pointer items-center gap-2.5 min-w-0 group').on('click', lambda: ui.navigate.to('/')):
                with ui.element('div').classes('p-1.5 rounded-xl bg-sky-50 flex items-center justify-center shrink-0 border border-sky-100/80 shadow-xs group-hover:scale-105 transition-transform'):
                    ui.image('/static/Libre-Library_icon.svg').classes('w-7 h-7 sm:w-8 sm:h-8 object-contain').props('no-spinner')
                ui.label('Libre Library').classes('text-base sm:text-xl font-black text-slate-900 tracking-tight truncate max-w-[130px] xs:max-w-none')

        ui.space()

        # 2. CENTER: DESKTOP SEARCH INPUT
        with ui.row().classes('hidden md:flex flex-grow max-w-xl mx-4'):
            search_input = ui.input(placeholder='Search books, authors, or topics... (Press / to focus)') \
                .props('id=global-header-search rounded outlined dense prepend-icon=search bg-color=slate-50') \
                .classes('w-full transition-all focus-within:shadow-md focus-within:bg-white text-xs')
            search_input.on('keydown.enter', handle_search)

        ui.space()

        # 3. RIGHT: MOBILE SEARCH, KEYBOARD SHORTCUTS, TARS AI & USER PROFILE
        with ui.row().classes('items-center gap-1 sm:gap-2 shrink-0'):
            with ui.button(on_click=lambda: ui.navigate.to('/chat')) \
                .props('flat round dense color=grey-7 size=md') \
                .tooltip('Ask TARS AI Librarian') \
                .classes('hidden sm:inline-flex p-1'):
                ui.image('/static/tars_icon.svg').classes('w-5 h-5 object-contain').props('no-spinner')

            ui.button(icon='keyboard', on_click=lambda: ui.run_javascript('window.LibreAccessibility && window.LibreAccessibility.showHelp()')) \
                .props('flat round dense color=grey-7 size=md') \
                .tooltip('Keyboard Shortcuts (?)') \
                .classes('hidden sm:inline-flex')

            ui.button(icon='search', on_click=open_mobile_search) \
                .props('flat round dense color=grey-7 size=md') \
                .classes('md:hidden')

            user_name = app.storage.user.get('username') or 'Account'
            full_name = app.storage.user.get('name') or user_name
            user_role = get_current_user_role()

            def _get_header_initials(name_val: str, user_val: str) -> str:
                clean = (name_val or user_val or 'AD').strip()
                parts = clean.split()
                if len(parts) >= 2:
                    return f"{parts[0][0]}{parts[1][0]}".upper()
                return clean[:2].upper() if clean else 'AD'

            initials = _get_header_initials(full_name, user_name)

            # Lazy background sync for users with active sessions before storage migration
            if 'avatar_url' not in app.storage.user and app.storage.user.get('user_id'):
                async def _sync_missing_avatar():
                    try:
                        u_profile = await mongo_db.get_user_profile(user_id=app.storage.user.get('user_id'))
                        if u_profile:
                            app.storage.user['avatar_url'] = u_profile.get('avatar_url') or ''
                            app.storage.user['cover_url'] = u_profile.get('cover_url') or ''
                            app.storage.user['name'] = u_profile.get('name') or ''
                            refresh_header_avatar()
                    except Exception:
                        pass
                ui.timer(0.05, _sync_missing_avatar, once=True)

            @ui.refreshable
            def render_navbar_avatar():
                avatar_url = app.storage.user.get('avatar_url')
                with ui.button().props('flat round dense no-caps size=md').classes('p-0.5 ml-0.5 sm:ml-1 relative group'):
                    # 1. Profile Photo Wrapper with fallback initials
                    with ui.element('div').classes(
                        'relative w-8 h-8 rounded-full border border-slate-200 shadow-xs '
                        'navbar-avatar overflow-hidden shrink-0 flex items-center justify-center bg-slate-100'
                    ):
                        if avatar_url:
                            ui.image(avatar_url).classes('w-full h-full object-cover rounded-full').props('no-spinner')
                        else:
                            ui.element('div').classes(
                                'w-full h-full bg-gradient-to-tr from-indigo-600 to-violet-500 '
                                'flex items-center justify-center text-white text-[11px] font-bold select-none'
                            ).text = initials

                    # 2. Dynamic 10px Green Online Status Ring / Dot
                    ui.element('span').classes(
                        'absolute bottom-0 right-0 w-2.5 h-2.5 rounded-full bg-emerald-500 '
                        'border-2 border-white ring-1 ring-emerald-500/20 pointer-events-none'
                    )

                    # 3. Dropdown Menu
                    with ui.menu().props('anchor="bottom right" self="top right"').classes(
                        'bg-white shadow-2xl border border-slate-200 rounded-2xl p-2 min-w-[210px]'
                    ):
                        with ui.row().classes('px-3 py-2 border-b border-slate-100 mb-1 items-center gap-2.5'):
                            with ui.element('div').classes(
                                'w-9 h-9 rounded-full overflow-hidden border border-slate-200 shrink-0 flex items-center justify-center bg-slate-100 shadow-xs'
                            ):
                                if avatar_url:
                                    ui.image(avatar_url).classes('w-full h-full object-cover')
                                else:
                                    ui.element('div').classes(
                                        'w-full h-full bg-indigo-600 flex items-center justify-center text-white text-xs font-bold'
                                    ).text = initials
                            with ui.column().classes('gap-0 flex-1 min-w-0'):
                                ui.label(user_name).classes('text-xs font-bold text-slate-900 truncate w-full')
                                ui.label(user_role.upper()).classes('text-[9px] font-bold text-indigo-600 uppercase tracking-wider')

                        ui.menu_item('Account Profile', on_click=lambda: ui.navigate.to('/profile')).props('prepend-icon=person').classes('text-xs font-medium')

                        ui.separator().classes('my-1')
                        def sign_out():
                            clear_user_session()
                            ui.notify("Signed out successfully.", type='info')
                            ui.navigate.to('/login')
                        ui.menu_item('Sign Out', on_click=sign_out).props('prepend-icon=logout').classes('text-xs font-bold text-rose-600')

            try:
                from nicegui import context
                _client_avatar_refreshers[context.client.id] = render_navbar_avatar
            except Exception:
                pass

            render_navbar_avatar()