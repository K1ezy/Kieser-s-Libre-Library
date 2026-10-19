import base64
from typing import List, Dict, Any, Callable, Optional
from datetime import datetime
from nicegui import ui
from core.database.mongo_manager import mongo_db
from core.auth.jwt_handler import get_current_user_role

PROGRAM_OPTIONS = [
    "All", "BSCS", "BSIT", "BSED", "BEED", "BSBA", "BSHM", "Crim", "Nursing", "GENERAL"
]
STATUS_OPTIONS = ["All", "Checked In", "Checked Out"]


def render_visitor_logs_table(
    container: ui.element,
    logs: List[Dict[str, Any]],
    date_val: str,
    prog_val: str
) -> None:
    """Renders high-density desktop table and touch-friendly mobile cards for daily visitor logs."""
    container.clear()

    rows = []
    for l in logs:
        rows.append({
            'id': l.get('id'),
            'date': l.get('date_str'),
            'time_in': l.get('time_in_str', '-'),
            'time_out': l.get('time_out_str', '-'),
            'student_id': l.get('institutional_id') or l.get('student_id', '-'),
            'name': l.get('name', 'Visitor'),
            'role': l.get('role', 'Student'),
            'year_level': l.get('year_level', '1st Year'),
            'program': l.get('program', 'GENERAL'),
            'purpose': l.get('purpose', 'Study / Review'),
            'purpose_attained': l.get('purpose_attained', 'Yes'),
            'duration': f"{l.get('duration_minutes', 0)} mins" if l.get('status') == 'Checked Out' else 'Active Inside',
            'status': l.get('status', 'Checked In')
        })

    columns = [
        {'name': 'time_in', 'label': 'Time-In', 'field': 'time_in', 'align': 'left', 'sortable': True},
        {'name': 'time_out', 'label': 'Time-Out', 'field': 'time_out', 'align': 'left', 'sortable': True},
        {'name': 'student_id', 'label': 'Institutional ID', 'field': 'student_id', 'align': 'left', 'sortable': True},
        {'name': 'name', 'label': 'Full Name', 'field': 'name', 'align': 'left', 'sortable': True},
        {'name': 'role', 'label': 'Role', 'field': 'role', 'align': 'center'},
        {'name': 'program', 'label': 'Program / Dept', 'field': 'program', 'align': 'center', 'sortable': True},
        {'name': 'purpose', 'label': 'Purpose of Visit', 'field': 'purpose', 'align': 'left'},
        {'name': 'duration', 'label': 'Duration', 'field': 'duration', 'align': 'center'},
        {'name': 'status', 'label': 'Status', 'field': 'status', 'align': 'center', 'sortable': True},
    ]

    with container:
        if not rows:
            with ui.element('div').classes('w-full p-8 text-center bg-slate-50 rounded-2xl border border-dashed border-slate-200'):
                ui.icon('inbox', size='36px').classes('text-slate-300 mb-1')
                ui.label('No visitor logs found matching the filter criteria.').classes('text-xs text-slate-500 font-bold')
        else:
            # 1. Desktop High-Density Table (>=768px)
            with ui.element('div').classes('hidden md:block w-full overflow-x-auto rounded-2xl border border-slate-200'):
                ui.table(columns=columns, rows=rows, row_key='id').classes('w-full').props('flat dense')

            # 2. Mobile Touch-Optimized Cards (<768px)
            with ui.element('div').classes('block md:hidden w-full flex flex-col gap-3'):
                for r in rows:
                    is_in = r.get('status') == 'Checked In'
                    status_bg = 'bg-emerald-50 text-emerald-700 border-emerald-200' if is_in else 'bg-slate-100 text-slate-700 border-slate-200'
                    status_icon = 'login' if is_in else 'logout'

                    with ui.card().classes('w-full p-4 rounded-2xl bg-white border border-slate-200 shadow-2xs hover:border-indigo-200 transition-all'):
                        with ui.row().classes('w-full items-start justify-between gap-2 mb-2'):
                            with ui.row().classes('items-center gap-2.5 min-w-0 flex-1'):
                                ui.avatar(icon='person', color='indigo-50', text_color='indigo-700', size='36px') \
                                    .classes('border border-indigo-100 shrink-0 font-bold')
                                with ui.column().classes('gap-0 min-w-0 flex-1'):
                                    ui.label(r.get('name', 'Student')).classes('text-sm font-black text-slate-900 truncate')
                                    with ui.row().classes('items-center gap-1.5 flex-wrap'):
                                        ui.label(r.get('program', 'GENERAL')).classes('text-[10px] font-black text-indigo-700 bg-indigo-50 px-1.5 py-0.2 rounded border border-indigo-200')
                                        ui.label(r.get('role', 'Student')).classes('text-[10px] text-purple-700 font-medium')
                            with ui.element('div').classes(f'px-2.5 py-0.5 rounded-full text-[10px] font-black uppercase border shrink-0 flex items-center gap-1 {status_bg}'):
                                ui.icon(status_icon, size='12px')
                                ui.label(r.get('status'))

                        with ui.row().classes('w-full items-center justify-between text-[11px] text-slate-600 bg-slate-50 p-2.5 rounded-xl border border-slate-100 mb-2 flex-wrap gap-1'):
                            with ui.row().classes('items-center gap-1'):
                                ui.icon('badge', size='14px').classes('text-slate-400')
                                ui.label(f"ID: {r.get('student_id')}").classes('font-mono font-bold text-slate-700')
                            with ui.row().classes('items-center gap-1'):
                                ui.icon('flag', size='14px').classes('text-slate-400')
                                ui.label(r.get('purpose', 'Study')).classes('italic text-slate-700 truncate max-w-[150px]')

                        with ui.row().classes('w-full items-center justify-between text-[11px] text-slate-400 pt-1 border-t border-slate-100'):
                            with ui.row().classes('items-center gap-2'):
                                ui.label(f"In: {r.get('time_in')}").classes('font-mono font-medium text-slate-600')
                                if r.get('time_out') != '-':
                                    ui.label(f"Out: {r.get('time_out')}").classes('font-mono font-medium text-slate-500')
                            ui.label(r.get('duration')).classes('font-bold text-indigo-600')


def render_dashboard_kpis(metrics: Dict[str, Any], date_str: str) -> None:
    """Renders real-time KPI indicator cards."""
    with ui.grid().classes('w-full grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4 mb-4'):
        kpis = [
            ("how_to_reg", f"Visitors Logged ({date_str})", str(metrics.get("visitors_today", 0)), "text-indigo-600", "bg-indigo-50"),
            ("sensor_door", "Currently Inside Library", str(metrics.get("currently_inside", 0)), "text-emerald-600", "bg-emerald-50"),
            ("task_alt", "Completed Check-Outs", str(metrics.get("completed_visits", 0)), "text-blue-600", "bg-blue-50"),
            ("timer", "Average Visit Duration", f"{metrics.get('avg_duration_minutes', 0.0)}m", "text-purple-600", "bg-purple-50"),
        ]
        for icon_name, label, val, text_col, bg_col in kpis:
            with ui.card().classes('p-3.5 sm:p-4 rounded-2xl bg-white border border-slate-200 shadow-2xs'):
                with ui.row().classes('items-center gap-2 mb-1'):
                    with ui.element('div').classes(f'p-1.5 rounded-xl {bg_col} {text_col}'):
                        ui.icon(icon_name, size='18px')
                    ui.label(label).classes('text-[11px] font-bold text-slate-400 uppercase tracking-wider truncate')
                ui.label(val).classes('text-xl sm:text-2xl font-black text-slate-900')


def render_program_breakdown(program_distribution: Dict[str, int]) -> None:
    """Renders horizontal program distribution chips."""
    if not program_distribution:
        return
    with ui.row().classes('w-full items-center gap-2 p-3 bg-slate-50 rounded-2xl border border-slate-200 mb-4 flex-wrap'):
        ui.label('Program Foot Traffic:').classes('text-xs font-bold text-slate-500 uppercase tracking-wider')
        for prog, count in program_distribution.items():
            with ui.element('span').classes('text-[11px] font-bold px-2.5 py-0.5 rounded-full bg-white border border-slate-200 text-slate-700 shadow-2xs'):
                ui.label(f"{prog}: {count}")
