import base64
from typing import List, Dict, Any, Callable
from nicegui import ui
from core.database.mongo_manager import mongo_db

PROGRAM_OPTIONS = [
    "All", "BSCS", "BSIT", "BSED", "BEED", "BSBA", "BSHM", "Crim", "Nursing", "GENERAL"
]


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
            'student_id': l.get('student_id', '-'),
            'name': l.get('name', 'Visitor'),
            'year_level': l.get('year_level', '1st Year'),
            'program': l.get('program', 'GENERAL'),
            'purpose': l.get('purpose', 'Study'),
            'purpose_attained': l.get('purpose_attained', 'Yes'),
            'duration': f"{l.get('duration_minutes', 0)} mins" if l.get('status') == 'Checked Out' else 'Active',
            'status': l.get('status', 'Checked In')
        })

    columns = [
        {'name': 'time_in', 'label': 'Time-In', 'field': 'time_in', 'align': 'left', 'sortable': True},
        {'name': 'time_out', 'label': 'Time-Out', 'field': 'time_out', 'align': 'left', 'sortable': True},
        {'name': 'student_id', 'label': 'Student ID', 'field': 'student_id', 'align': 'left', 'sortable': True},
        {'name': 'name', 'label': 'Student Name', 'field': 'name', 'align': 'left', 'sortable': True},
        {'name': 'year_level', 'label': 'Year', 'field': 'year_level', 'align': 'center'},
        {'name': 'program', 'label': 'Major / Program', 'field': 'program', 'align': 'center', 'sortable': True},
        {'name': 'purpose', 'label': 'Purpose of Visit', 'field': 'purpose', 'align': 'left'},
        {'name': 'purpose_attained', 'label': 'Attained', 'field': 'purpose_attained', 'align': 'center'},
        {'name': 'duration', 'label': 'Duration', 'field': 'duration', 'align': 'center'},
        {'name': 'status', 'label': 'Status', 'field': 'status', 'align': 'center', 'sortable': True},
    ]

    with container:
        if not rows:
            ui.label('No visitor logs found matching the filter criteria.').classes('text-xs text-slate-400 italic p-6 text-center w-full')
        else:
            # 1. Desktop High-Density Table (>=768px)
            with ui.element('div').classes('hidden md:block w-full overflow-x-auto'):
                ui.table(columns=columns, rows=rows, row_key='id').classes('w-full mobile-card-table').props('flat bordered')

            # 2. Mobile Touch-Optimized Cards (<768px)
            with ui.element('div').classes('block md:hidden w-full flex flex-col gap-3'):
                for r in rows:
                    is_in = r.get('status') == 'Checked In'
                    status_bg = 'bg-emerald-50 text-emerald-700 border-emerald-200' if is_in else 'bg-slate-100 text-slate-700 border-slate-200'
                    status_icon = 'login' if is_in else 'logout'

                    with ui.card().classes('w-full p-4 rounded-2xl bg-white border border-slate-200 shadow-xs hover:border-indigo-200 transition-all'):
                        with ui.row().classes('w-full items-start justify-between gap-2 mb-2'):
                            with ui.row().classes('items-center gap-2.5 min-w-0 flex-1'):
                                ui.avatar(icon='person', color='indigo-50', text_color='indigo-700', size='36px') \
                                    .classes('border border-indigo-100 shrink-0 font-bold')
                                with ui.column().classes('gap-0 min-w-0 flex-1'):
                                    ui.label(r.get('name', 'Student')).classes('text-sm font-black text-slate-900 truncate')
                                    with ui.row().classes('items-center gap-1.5 flex-wrap'):
                                        ui.label(r.get('program', 'GENERAL')).classes('text-[10px] font-black text-indigo-700 bg-indigo-50 px-1.5 py-0.2 rounded border border-indigo-200')
                                        ui.label(r.get('year_level', '')).classes('text-[10px] text-slate-500 font-medium')
                            with ui.element('div').classes(f'px-2.5 py-0.5 rounded-full text-[10px] font-black uppercase border shrink-0 flex items-center gap-1 {status_bg}'):
                                ui.icon(status_icon, size='12px')
                                ui.label(r.get('status'))

                        with ui.row().classes('w-full items-center justify-between text-[11px] text-slate-600 bg-slate-50 p-2 rounded-xl border border-slate-100 mb-2 flex-wrap gap-1'):
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

        # Export CSV helper (FM-LIBS-009 Format)
        with ui.row().classes('w-full justify-between items-center mt-4 flex-wrap gap-2'):
            ui.label('Institutional Reference: FM-LIBS-009 (College of Arts & Sciences / General Entrance Log)').classes('text-xs text-slate-400 font-medium')

            def export_csv():
                if not rows:
                    ui.notify("No data to export", type='warning')
                    return
                csv_content = mongo_db.export_fmlibs009_csv(logs, date_val, prog_val)
                b64 = base64.b64encode(csv_content.encode('utf-8')).decode('utf-8')
                filename = f"NEMSU_FM-LIBS-009_Visitor_Log_{date_val or 'All'}.csv"
                ui.run_javascript(f'''
                    const a = document.createElement('a');
                    a.href = 'data:text/csv;base64,{b64}';
                    a.download = '{filename}';
                    a.click();
                ''')
                ui.notify("FM-LIBS-009 Visitor Log exported successfully!", type='positive')

            ui.button('Export FM-LIBS-009 Logbook (CSV)', icon='download', on_click=export_csv) \
                .props('unelevated rounded-xl color=indigo size=sm font-bold shadow-xs')
