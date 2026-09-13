from nicegui import ui, app
from ui.theme import toggle_dark_mode, get_current_mode_value
from core.auth.jwt_handler import clear_user_session

def sidebar(chat_interface=None) -> ui.left_drawer:
    """
    Renders the global navigation sidebar with full dark mode support.
    Responsive: Auto-opens on Desktop, Auto-closes/Overlays on Mobile.
    """
    
    # 1. CREATE DRAWER
    with ui.left_drawer(value=None, fixed=True).classes(
        'bg-white dark:bg-slate-900 border-r border-slate-200 dark:border-slate-800 flex flex-col z-50'
    ) as drawer:
        
        # 2. LOGO AREA
        with ui.row().classes('w-full h-20 items-center justify-between px-5 border-b border-slate-200 dark:border-slate-800 flex-none'):
            with ui.row().classes('items-center'):
                with ui.element('div').classes('p-2 rounded-xl bg-indigo-50 dark:bg-indigo-900/40 text-indigo-600 dark:text-indigo-400 flex items-center justify-center'):
                    ui.icon('local_library', size='sm')
                ui.label('Libre Library').classes('text-xl font-black text-slate-800 dark:text-slate-100 tracking-tight ml-2.5')
            ui.button(icon='close', on_click=drawer.hide).props('flat round dense color=grey-7 size=md').classes('md:hidden')

        # 3. NAVIGATION LINKS (Scrollable Area)
        with ui.column().classes('w-full p-4 gap-1.5 flex-grow overflow-y-auto no-scrollbar'):
            
            def nav_link(text: str, icon: str, target: str):
                is_active = app.storage.client.get('page_path') == target
                
                base_classes = 'w-full flex items-center gap-3 px-3.5 py-3 rounded-xl transition-all duration-200 no-underline group'
                if is_active:
                    color_classes = 'bg-indigo-50 dark:bg-indigo-950/60 text-indigo-600 dark:text-indigo-400 font-bold shadow-sm'
                else:
                    color_classes = 'text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800 hover:text-slate-900 dark:hover:text-slate-100 font-medium'
                
                with ui.link(target=target).classes(f'{base_classes} {color_classes}'):
                    ui.icon(icon).classes('text-xl group-hover:scale-110 transition-transform') 
                    ui.label(text).classes('text-sm')

            # --- MAIN SECTION ---
            ui.label('MAIN').classes('text-[10px] font-bold text-slate-400 uppercase px-2 mt-2 mb-1 tracking-widest')
            nav_link('Home', 'dashboard', '/')
            nav_link('Library', 'library_books', '/books')
            nav_link('My Profile', 'person', '/profile')
            
            # --- TOOLS SECTION ---
            ui.label('TOOLS').classes('text-[10px] font-bold text-slate-400 uppercase px-2 mt-6 mb-1 tracking-widest')
            nav_link('AI Assistant', 'smart_toy', '/chat')
            nav_link('Upload Book', 'cloud_upload', '/upload')
            nav_link('Study Planner', 'event_note', '/planner')
            nav_link('AI Summarizer', 'summarize', '/summarizer') 

            # --- ADMIN SECTION ---
            if app.storage.user.get('role') == 'admin':
                ui.separator().classes('my-2 opacity-50')
                ui.label('ADMIN').classes('text-[10px] font-bold text-slate-400 uppercase px-2 mb-1 tracking-widest')
                nav_link('Admin Console', 'admin_panel_settings', '/admin')

            ui.separator().classes('my-2 opacity-40')
            
            # --- LOGOUT ITEM ---
            with ui.item(on_click=lambda: (clear_user_session(), ui.navigate.to('/login'))) \
                    .classes('w-full rounded-xl text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-950/30 transition-colors cursor-pointer px-3.5 py-2'):
                with ui.item_section().props('avatar'):
                    ui.icon('logout', color='red')
                with ui.item_section():
                    ui.label('Logout').classes('font-medium text-sm')

        # 4. FOOTER: SESSION & SETTINGS
        with ui.column().classes('w-full p-4 border-t border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-950/60 flex-none gap-3'):
            
            # Chat Session Controls
            if chat_interface:
                ui.label('SESSION CONTROLS').classes('text-[10px] font-bold text-slate-400 uppercase tracking-widest')
                
                chat_interface.session_input = ui.input(
                    label='Session ID', 
                    value=chat_interface.session_id,
                    placeholder="Paste ID..."
                ).props('outlined dense clearable bg-white').classes('w-full text-sm sm:text-xs')
                
                with ui.row().classes('w-full gap-2'):
                    ui.button('Load', icon='sync', on_click=chat_interface.load_specific_session) \
                        .props('flat dense size=sm color=indigo').classes('flex-1 rounded-lg')
                    
                    ui.button('New', icon='add', on_click=chat_interface.start_new_chat) \
                        .props('flat dense size=sm color=green').classes('flex-1 rounded-lg')
                
                if hasattr(chat_interface, 'teaching_mode'):
                    with ui.row().classes('w-full items-center justify-between'):
                        ui.label('Teaching Mode').classes('text-xs text-slate-600 dark:text-slate-400 font-medium')
                        ui.switch(
                            value=chat_interface.teaching_mode, 
                            on_change=chat_interface.toggle_teaching_mode
                        ).props('dense color=indigo size=xs')

            # Dark Mode Toggle
            with ui.row().classes('w-full items-center justify-between pt-1'):
                with ui.row().classes('items-center gap-2'):
                    ui.icon('dark_mode', size='xs').classes('text-slate-500')
                    ui.label('Dark Mode').classes('text-xs text-slate-600 dark:text-slate-400 font-medium')
                
                ui.switch(
                    value=get_current_mode_value(), 
                    on_change=toggle_dark_mode
                ).props('color=indigo dense size=xs')

    return drawer