from typing import Dict, Any
from nicegui import ui


def render_profile_stats(stats: Dict[str, Any]) -> None:
    """Renders the readership and system activity stats grid."""
    ui.label('ACTIVITY STATS & READERSHIP').classes('text-[11px] sm:text-xs font-bold text-slate-400 uppercase tracking-widest mb-3')
    with ui.grid().classes('grid-cols-2 md:grid-cols-4 gap-3 w-full'):
        def stat_badge(label, value, icon, color):
            with ui.column().classes(f'p-3.5 sm:p-4 rounded-2xl bg-{color}-50 border border-{color}-200/80 items-center justify-center text-center shadow-2xs'):
                ui.icon(icon, size='sm').classes(f'text-{color}-600 mb-1')
                ui.label(str(value)).classes(f'text-xl sm:text-2xl font-bold text-{color}-700 leading-none')
                ui.label(label).classes(f'text-[9px] sm:text-[10px] font-bold text-{color}-600 uppercase tracking-wider mt-1')

        stat_badge('Tasks Done', stats.get('tasks_done', 0), 'check_circle', 'emerald')
        stat_badge('Books Read', stats.get('books', 0), 'library_books', 'indigo')
        stat_badge('System Status', 'Online', 'wifi', 'sky')
        stat_badge('TARS AI Assistant', 'Active', 'smart_toy', 'purple')
