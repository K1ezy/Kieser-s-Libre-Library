from nicegui import ui, app

def bottom_nav():
    """
    Renders a sleek, native-feeling bottom navigation bar for mobile phone screens.
    Visible on mobile/tablets (< md breakpoint), hidden on desktop screens.
    Provides instant 1-tap thumb navigation with safe-area support.
    """
    current_path = app.storage.client.get('page_path', '/')

    items = [
        {'title': 'Home', 'icon': 'dashboard', 'route': '/'},
        {'title': 'Library', 'icon': 'local_library', 'route': '/books'},
        {'title': 'TARS AI', 'icon': 'smart_toy', 'route': '/chat'},
        {'title': 'Planner', 'icon': 'event_note', 'route': '/planner'},
        {'title': 'Profile', 'icon': 'person', 'route': '/profile'},
    ]

    with ui.element('nav').classes(
        'md:hidden fixed bottom-0 left-0 right-0 z-40 '
        'bg-white/95 dark:bg-slate-900/95 backdrop-blur-md '
        'border-t border-slate-200/80 dark:border-slate-800/80 '
        'pt-1.5 pb-[max(6px,env(safe-area-inset-bottom))] px-2 shadow-lg shadow-slate-900/5'
    ):
        with ui.row().classes('w-full items-center justify-around gap-1'):
            for item in items:
                is_active = (current_path == item['route']) or (item['route'] != '/' and current_path.startswith(item['route']))

                if is_active:
                    container_cls = 'flex-1 flex flex-col items-center justify-center py-1 px-1 rounded-xl bg-indigo-50 dark:bg-indigo-950/60 text-indigo-600 dark:text-indigo-400 font-bold transition-all duration-200 no-underline'
                    icon_cls = 'text-xl drop-shadow-sm'
                    label_cls = 'text-[10px] font-bold tracking-tight'
                else:
                    container_cls = 'flex-1 flex flex-col items-center justify-center py-1 px-1 rounded-xl text-slate-500 dark:text-slate-400 hover:text-slate-800 dark:hover:text-slate-200 font-medium transition-all duration-200 no-underline active:scale-95'
                    icon_cls = 'text-xl'
                    label_cls = 'text-[10px] font-medium tracking-tight'

                with ui.link(target=item['route']).classes(container_cls):
                    ui.icon(item['icon']).classes(icon_cls)
                    ui.label(item['title']).classes(label_cls)
