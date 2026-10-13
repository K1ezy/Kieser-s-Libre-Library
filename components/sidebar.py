from nicegui import ui, app
from core.auth.jwt_handler import clear_user_session, get_current_user_role

def sidebar(chat_interface=None) -> ui.left_drawer:
    """
    Role-Based Global Navigation Sidebar:
    Dynamically renders personalized navigation trees tailored to
    Student, Faculty, Librarian, and Administrator personas.
    Complies with SRS Chapter 1 & 2 4-Tier RBAC architecture.
    """
    user_role = get_current_user_role()
    is_admin = user_role == 'admin'
    is_librarian = user_role in ['admin', 'librarian']
    is_faculty = user_role in ['admin', 'librarian', 'faculty']

    with ui.left_drawer(value=False, fixed=True).props('show-if-above').classes(
        'bg-white border-r border-slate-200 flex flex-col z-50 w-72 max-w-[85vw] shadow-sm'
    ) as drawer:

        # 1. LOGO AREA (Mobile overlay; desktop top bar already shows brand header)
        with ui.row().classes('w-full h-16 sm:h-20 items-center justify-between px-5 border-b border-slate-200 flex-none md:hidden'):
            with ui.row().classes('items-center gap-2.5'):
                with ui.element('div').classes('p-2 rounded-xl bg-indigo-50 text-indigo-600 flex items-center justify-center border border-indigo-100 shadow-sm'):
                    ui.icon('local_library', size='sm')
                ui.label('Libre Library').classes('text-xl font-black text-slate-900 tracking-tight')
            ui.button(icon='close', on_click=drawer.hide).props('flat round dense color=grey-7 size=md')

        # 2. DYNAMIC NAVIGATION LINKS (Role-Specific)
        with ui.column().classes('w-full p-4 gap-1 flex-grow overflow-y-auto no-scrollbar'):

            current_path = app.storage.client.get('page_path', '/')

            def nav_link(text: str, icon: str, target: str, badge_text: str = None):
                is_active = (current_path == target) or (target != '/' and str(current_path).startswith(target))
                base_classes = 'w-full flex items-center justify-between px-3.5 py-2.5 rounded-xl transition-all duration-200 no-underline group cursor-pointer'
                if is_active:
                    color_classes = 'bg-indigo-50 text-indigo-700 font-bold shadow-sm border border-indigo-100/60'
                else:
                    color_classes = 'text-slate-600 hover:bg-slate-100 hover:text-slate-900 font-medium'

                with ui.link(target=target).classes(f'{base_classes} {color_classes}').on('click', lambda: drawer.hide()):
                    with ui.row().classes('items-center gap-3 min-w-0'):
                        ui.icon(icon).classes('text-xl group-hover:scale-105 transition-transform')
                        ui.label(text).classes('text-sm truncate')
                    if badge_text:
                        ui.label(badge_text).classes('text-[10px] font-bold px-1.5 py-0.5 rounded-md bg-indigo-100 text-indigo-700')

            # -------------------------------------------------------------
            # SECTION 1: ACADEMIC CORE (Universal for All Roles)
            # -------------------------------------------------------------
            ui.label('ACADEMIC CORE').classes('text-[10px] font-bold text-slate-400 uppercase px-2 mt-2 mb-1 tracking-widest')
            nav_link('Home', 'dashboard', '/')
            nav_link('Library Archive', 'library_books', '/books')

            # -------------------------------------------------------------
            # SECTION 2: AI LEARNING WORKSTATION (Universal for All Roles)
            # -------------------------------------------------------------
            ui.label('AI TOOLS & RESEARCH').classes('text-[10px] font-bold text-slate-400 uppercase px-2 mt-4 mb-1 tracking-widest')
            nav_link('TARS AI Librarian', 'smart_toy', '/chat')
            nav_link('Study Planner', 'event_note', '/planner')
            nav_link('AI Summarizer', 'summarize', '/summarizer')

            # -------------------------------------------------------------
            # SECTION 3: ROLE-SPECIFIC CAMPUS MODULES
            # -------------------------------------------------------------
            if user_role == 'student':
                # Student View: Focused on Personal Access & Pass
                ui.label('CAMPUS ACCESS').classes('text-[10px] font-bold text-slate-400 uppercase px-2 mt-4 mb-1 tracking-widest')
                nav_link('My Digital Pass', 'badge', '/attendance')

            elif user_role == 'faculty':
                # Faculty View: Curricular Requests & Program Metrics
                ui.label('FACULTY SERVICES').classes('text-[10px] font-bold text-slate-400 uppercase px-2 mt-4 mb-1 tracking-widest')
                nav_link('Book Requisitions', 'post_add', '/requisitions')
                nav_link('My Digital Pass', 'badge', '/attendance')
                nav_link('Program Analytics', 'insights', '/analytics')

            elif is_librarian:
                # Librarian & Admin View: Operational Station & Catalog Ingestion
                ui.label('LIBRARY OPERATIONS').classes('text-[10px] font-bold text-slate-400 uppercase px-2 mt-4 mb-1 tracking-widest')
                nav_link('Librarian Hub', 'local_library', '/librarian', badge_text='OPS')
                nav_link('Entrance & Pass Terminal', 'badge', '/attendance')
                nav_link('Book Requisitions', 'post_add', '/requisitions')
                nav_link('Ingest & Upload', 'cloud_upload', '/upload')
                nav_link('Program Analytics', 'insights', '/analytics')

            # -------------------------------------------------------------
            # SECTION 4: SYSTEM GOVERNANCE (System Administrator Only)
            # -------------------------------------------------------------
            if is_admin:
                ui.separator().classes('my-2 opacity-60')
                ui.label('SYSTEM GOVERNANCE').classes('text-[10px] font-bold text-slate-400 uppercase px-2 mb-1 tracking-widest')
                nav_link('Admin Console', 'admin_panel_settings', '/admin', badge_text='IT GOV')

        # 3. FOOTER: USER PROFILE & ROLE BADGE
        user_name = app.storage.user.get('username') or 'Account'

        # Role Visual Styling Palette
        role_styles = {
            'student': ('bg-emerald-50 text-emerald-700 border-emerald-200', 'school'),
            'faculty': ('bg-blue-50 text-blue-700 border-blue-200', 'cast_for_education'),
            'librarian': ('bg-purple-50 text-purple-700 border-purple-200', 'local_library'),
            'admin': ('bg-amber-50 text-amber-700 border-amber-200', 'admin_panel_settings'),
        }
        badge_cls, role_icon = role_styles.get(user_role, ('bg-indigo-50 text-indigo-700 border-indigo-200', 'person'))

        with ui.row().classes('w-full p-3.5 border-t border-slate-200 bg-slate-50 flex-none items-center justify-between gap-2'):
            with ui.row().classes('items-center gap-2.5 flex-1 min-w-0 cursor-pointer').on('click', lambda: (drawer.hide(), ui.navigate.to('/profile'))):
                with ui.element('div').classes(f'w-8 h-8 rounded-full flex items-center justify-center border {badge_cls} shadow-xs shrink-0'):
                    ui.icon(role_icon, size='16px')
                with ui.column().classes('gap-0 flex-1 min-w-0'):
                    ui.label(user_name).classes('text-xs font-bold text-slate-900 truncate w-full leading-tight')
                    with ui.row().classes('items-center gap-1'):
                        ui.label(user_role.upper()).classes(f'text-[9px] font-black uppercase tracking-wider px-1.5 py-0.2 rounded border {badge_cls} leading-normal')

            with ui.button(icon='logout', on_click=lambda: (clear_user_session(), ui.navigate.to('/login'))) \
                    .props('flat round dense color=grey-6 size=sm') \
                    .classes('hover:text-rose-600 transition-colors shrink-0'):
                ui.tooltip('Sign Out')

    return drawer