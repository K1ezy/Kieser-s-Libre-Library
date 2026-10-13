from nicegui import ui, app
from core.auth.jwt_handler import get_current_user_role

def bottom_nav():
    """
    Mobile Bottom Navigation Dock (md:hidden):
    Provides seamless one-handed thumb navigation across primary features.
    Dynamically tailors destination tabs to user persona.
    """
    current_path = app.storage.client.get('page_path', '/')
    user_role = get_current_user_role()

    # Core 4 destinations shared across all roles
    destinations = [
        ('/', 'Home', 'dashboard'),
        ('/books', 'Library', 'local_library'),
        ('/chat', 'TARS AI', 'smart_toy'),
        ('/planner', 'Planner', 'event_note'),
    ]

    # Dynamic 5th destination tailored to user persona
    if user_role in ('admin', 'librarian'):
        destinations.append(('/upload', 'Ingest', 'cloud_upload'))
    elif user_role == 'faculty':
        destinations.append(('/requisitions', 'Requests', 'post_add'))
    else:  # student
        destinations.append(('/attendance', 'My Pass', 'badge'))

    with ui.element('nav').classes(
        'fixed bottom-0 left-0 right-0 z-40 md:hidden '
        'bg-white/95 backdrop-blur-md '
        'border-t border-slate-200 '
        'pb-[max(4px,env(safe-area-inset-bottom,0px))] '
        'shadow-lg select-none transition-all'
    ):
        with ui.row().classes('w-full items-center justify-around px-1 py-1 sm:py-1.5 flex-nowrap'):
            for target_url, label, icon in destinations:
                is_active = (current_path == target_url) or (target_url != '/' and str(current_path).startswith(target_url))
                
                if is_active:
                    pill_classes = 'text-indigo-600 font-bold'
                    icon_classes = 'text-indigo-600 scale-110'
                    bg_classes = 'bg-indigo-50/90 border border-indigo-100/70 shadow-xs'
                else:
                    pill_classes = 'text-slate-500 font-medium'
                    icon_classes = 'text-slate-400'
                    bg_classes = 'hover:bg-slate-50 active:bg-slate-100'

                with ui.link(target=target_url).classes(
                    f'flex flex-col items-center justify-center min-w-0 flex-1 max-w-[72px] min-h-[48px] h-12 py-1 px-1 rounded-xl '
                    f'no-underline transition-all duration-150 touch-manipulation {bg_classes} {pill_classes}'
                ):
                    ui.icon(icon, size='20px').classes(f'transition-transform {icon_classes}')
                    ui.label(label).classes('text-[10px] leading-tight tracking-tight mt-0.5 truncate w-full text-center')
