from nicegui import ui, app
from core.auth.jwt_handler import clear_user_session

def sidebar(chat_interface=None) -> ui.left_drawer:
    """
    Global Navigation Sidebar:
    Auto-opens on desktop, smoothly overlays/slides on mobile.
    Clean light color theory with zero dark mode clutter.
    """
    with ui.left_drawer(value=False, fixed=True).props('show-if-above').classes(
        'bg-white border-r border-slate-200 flex flex-col z-50 w-72 max-w-[85vw] shadow-sm'
    ) as drawer:

        # 1. LOGO AREA (Only on mobile overlay; desktop top bar already shows brand header)
        with ui.row().classes('w-full h-16 sm:h-20 items-center justify-between px-5 border-b border-slate-200 flex-none md:hidden'):
            with ui.row().classes('items-center gap-2.5'):
                with ui.element('div').classes('p-2 rounded-xl bg-indigo-50 text-indigo-600 flex items-center justify-center border border-indigo-100 shadow-sm'):
                    ui.icon('local_library', size='sm')
                ui.label('Libre Library').classes('text-xl font-black text-slate-900 tracking-tight')
            ui.button(icon='close', on_click=drawer.hide).props('flat round dense color=grey-7 size=md')

        # 2. NAVIGATION LINKS
        with ui.column().classes('w-full p-4 gap-1 flex-grow overflow-y-auto no-scrollbar'):

            def nav_link(text: str, icon: str, target: str):
                is_active = app.storage.client.get('page_path') == target
                base_classes = 'w-full flex items-center gap-3 px-3.5 py-2.5 rounded-xl transition-all duration-200 no-underline group cursor-pointer'
                if is_active:
                    color_classes = 'bg-indigo-50 text-indigo-700 font-bold shadow-sm border border-indigo-100/60'
                else:
                    color_classes = 'text-slate-600 hover:bg-slate-100 hover:text-slate-900 font-medium'

                with ui.link(target=target).classes(f'{base_classes} {color_classes}').on('click', lambda: drawer.hide()):
                    ui.icon(icon).classes('text-xl group-hover:scale-105 transition-transform')
                    ui.label(text).classes('text-sm')

            # MAIN
            ui.label('MAIN').classes('text-[10px] font-bold text-slate-400 uppercase px-2 mt-2 mb-1 tracking-widest')
            nav_link('Home', 'dashboard', '/')
            nav_link('Library Archive', 'library_books', '/books')

            # AI & TOOLS
            ui.label('AI & TOOLS').classes('text-[10px] font-bold text-slate-400 uppercase px-2 mt-4 mb-1 tracking-widest')
            nav_link('TARS AI Librarian', 'smart_toy', '/chat')
            nav_link('Study Planner', 'event_note', '/planner')
            nav_link('AI Summarizer', 'summarize', '/summarizer')
            nav_link('Ingest & Upload', 'cloud_upload', '/upload')

            # CAMPUS SERVICES (SRS Chapter 1 & 2 Modules)
            ui.label('CAMPUS SERVICES').classes('text-[10px] font-bold text-slate-400 uppercase px-2 mt-4 mb-1 tracking-widest')
            nav_link('Library Attendance & Pass', 'qr_code_scanner', '/attendance')
            nav_link('Book Requisitions', 'post_add', '/requisitions')
            nav_link('Program Analytics', 'insights', '/analytics')

            # ADMIN
            user_current_role = app.storage.user.get('role', 'student').lower()
            if user_current_role in ['admin', 'librarian']:
                ui.separator().classes('my-2 opacity-60')
                ui.label('ADMINISTRATION').classes('text-[10px] font-bold text-slate-400 uppercase px-2 mb-1 tracking-widest')
                nav_link('Admin Console', 'admin_panel_settings', '/admin')

        # 3. FOOTER: USER PROFILE & SIGN OUT
        user_name = app.storage.user.get('username') or 'Account'
        user_role = app.storage.user.get('role', 'user')

        with ui.row().classes('w-full p-3.5 border-t border-slate-200 bg-slate-50 flex-none items-center justify-between gap-2'):
            with ui.row().classes('items-center gap-2.5 flex-1 min-w-0 cursor-pointer').on('click', lambda: (drawer.hide(), ui.navigate.to('/profile'))):
                ui.avatar(icon='person', color='indigo-50', text_color='indigo', size='32px') \
                    .classes('border border-indigo-200 shrink-0 shadow-sm')
                with ui.column().classes('gap-0 flex-1 min-w-0'):
                    ui.label(user_name).classes('text-xs font-bold text-slate-900 truncate w-full leading-tight')
                    ui.label(user_role.upper()).classes('text-[9px] font-bold text-indigo-600 uppercase tracking-wider leading-none')

            with ui.button(icon='logout', on_click=lambda: (clear_user_session(), ui.navigate.to('/login'))) \
                    .props('flat round dense color=grey-6 size=sm') \
                    .classes('hover:text-rose-600 transition-colors shrink-0'):
                ui.tooltip('Sign Out')

    return drawer