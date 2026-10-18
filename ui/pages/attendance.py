from datetime import datetime
from typing import Optional, Dict, Any, List
from nicegui import ui, app

from components.sidebar import sidebar
from components.header import header
from core.database.mongo_manager import mongo_db
from core.auth.jwt_handler import get_current_user_role
from components.attendance import (
    generate_qr_base64,
    render_digital_pass_card,
    PURPOSE_OPTIONS,
    render_scanner_station,
    render_live_doorway_feed,
    PROGRAM_OPTIONS,
    render_visitor_logs_table,
)

__all__ = ['generate_qr_base64', 'attendance_page', 'PURPOSE_OPTIONS', 'PROGRAM_OPTIONS']


async def attendance_page():
    """
    Automated QR-Code Entrance Attendance System and Visitor Log Terminal.
    Complies with SRS Chapter 1 (Specific Objective 3), Chapter 2 (FR 3, NFR 1),
    and Section 2.2 ("Daily Library Visitor / Entrance Log Summary").
    """
    app.storage.client['page_path'] = '/attendance'

    drawer = sidebar()
    header(drawer_reference=drawer)

    # User context
    user_id = app.storage.user.get('user_id')
    user_name = app.storage.user.get('username') or 'Student'
    user_role = get_current_user_role()
    is_staff = user_role in ['admin', 'librarian']
    user_profile = await mongo_db.get_user_profile(user_id)
    student_id = user_profile.get('student_id') or (f"2024-{str(user_id)[:5].upper()}" if user_id else "2024-001")
    user_program = user_profile.get('program') or "BSCS"

    # State
    active_purpose = {'val': "📚 Study / Review"}
    filter_state = {
        'date': datetime.now().strftime("%Y-%m-%d"),
        'program': 'All'
    }
    refresh_table_data = None

    with ui.column().classes(
        'w-full min-h-fit pt-[calc(4.5rem+env(safe-area-inset-top,0px))] '
        'px-3 sm:px-6 md:pt-24 md:px-10 max-w-[1600px] mx-auto pb-16'
    ):
        # Page Title Banner
        with ui.column().classes('gap-1 mb-6'):
            with ui.row().classes('items-center gap-2.5'):
                with ui.element('div').classes('p-2.5 rounded-2xl bg-indigo-50 text-indigo-600 border border-indigo-100 shadow-sm'):
                    ui.icon('qr_code_scanner', size='28px')
                with ui.column().classes('gap-0'):
                    ui.label('Library Entrance Attendance System').classes('text-2xl sm:text-3xl font-black text-slate-900 tracking-tight')
                    ui.label('Automated QR check-in terminal & daily visitor log summary (NEMSU Tandag Campus)').classes('text-xs sm:text-sm text-slate-500')

        # Real-time Entrance Stats Bar
        stats_container = ui.row().classes('w-full grid grid-cols-2 sm:grid-cols-4 gap-3 sm:gap-4 mb-6')

        async def refresh_stats():
            import asyncio
            stats_container.clear()
            today_logs, active_count, total_all = await asyncio.gather(
                mongo_db.get_today_attendance_logs(limit=500),
                mongo_db.get_active_checked_in_count(),
                mongo_db.get_total_visitors_count()
            )

            with stats_container:
                stat_cards = [
                    ("how_to_reg", "Visitors Today", str(len(today_logs)), "text-indigo-600", "bg-indigo-50"),
                    ("sensor_door", "Currently Inside", str(active_count), "text-emerald-600", "bg-emerald-50"),
                    ("school", "My Program", user_program, "text-blue-600", "bg-blue-50"),
                    ("history", "Total Logged", str(total_all), "text-purple-600", "bg-purple-50"),
                ]
                for icon_name, label_text, val_text, text_col, bg_col in stat_cards:
                    with ui.card().classes('p-3.5 sm:p-4 rounded-2xl bg-white border border-slate-200 shadow-sm'):
                        with ui.row().classes('items-center gap-2 mb-1'):
                            with ui.element('div').classes(f'p-1.5 rounded-xl {bg_col} {text_col}'):
                                ui.icon(icon_name, size='18px')
                            ui.label(label_text).classes('text-[11px] font-bold text-slate-400 uppercase tracking-wider')
                        ui.label(val_text).classes('text-xl sm:text-2xl font-black text-slate-900')

        await refresh_stats()

        # Tab Navigation (RBAC Guarded: Daily Visitor Logs visible ONLY to Admin & Librarian)
        with ui.tabs().classes('w-full bg-slate-100/80 p-1 rounded-2xl mb-6 text-slate-600') as tabs:
            tab_scanner = ui.tab('scanner', label='Entrance Fast Scanner', icon='qr_code_scanner')
            tab_pass = ui.tab('pass', label='My Library QR Pass', icon='badge')
            if is_staff:
                tab_logs = ui.tab('logs', label='Daily Visitor Logs', icon='receipt_long')

        initial_tab = tab_pass if user_role == 'student' else tab_scanner
        with ui.tab_panels(tabs, value=initial_tab).classes('w-full bg-transparent p-0'):

            # TAB 1: Fast Entrance Scanner
            with ui.tab_panel(tab_scanner).classes('p-0'):
                with ui.grid().classes('w-full grid-cols-1 lg:grid-cols-12 gap-6'):
                    with ui.column().classes('lg:col-span-7 gap-5'):
                        feedback_banner_holder = {}

                        async def handle_scan(val: str, purpose: str, year_level: str):
                            res = await mongo_db.record_attendance_scan(
                                identifier=val,
                                purpose=purpose,
                                name=user_name if val == student_id else "",
                                program=user_program if val == student_id else "",
                                year_level=year_level
                            )
                            if 'banner' in feedback_banner_holder and feedback_banner_holder['banner']:
                                feedback_banner_holder['banner'].clear()

                            if res.get('success'):
                                act = res.get('action')
                                entry = res.get('entry') or {}
                                msg = res.get('message', 'Attendance logged.')
                                ui.notify(msg, type='positive' if act == 'checkin' else 'info', duration=4000)

                                if 'banner' in feedback_banner_holder and feedback_banner_holder['banner']:
                                    with feedback_banner_holder['banner']:
                                        is_checkin = act == 'checkin'
                                        banner_bg = 'bg-emerald-50 border-emerald-200 text-emerald-900' if is_checkin else 'bg-blue-50 border-blue-200 text-blue-900'
                                        banner_icon = 'verified' if is_checkin else 'waving_hand'
                                        with ui.card().classes(f'w-full p-3.5 rounded-2xl border mb-3 flex flex-row items-center justify-between gap-3 {banner_bg} shadow-sm animate-fade-in'):
                                            with ui.row().classes('items-center gap-3 min-w-0 flex-1'):
                                                ui.icon(banner_icon, size='24px').classes('text-emerald-600' if is_checkin else 'text-blue-600')
                                                with ui.column().classes('gap-0 min-w-0 flex-1'):
                                                    ui.label(entry.get('name', val)).classes('text-sm font-black truncate')
                                                    ui.label(f"{entry.get('program', 'BSCS')} ({entry.get('year_level', '1st Year')}) • {entry.get('purpose', 'Study')} • {entry.get('time_in_str', '')}").classes('text-xs opacity-80')
                                            with ui.element('div').classes('px-2.5 py-1 rounded-xl text-xs font-black uppercase bg-white/80 shadow-xs shrink-0'):
                                                ui.label("CHECKED IN" if is_checkin else f"OUT ({res.get('duration_minutes', 0)}m)")

                                await refresh_stats()
                                await refresh_doorway_stream()
                                if is_staff and refresh_table_data is not None:
                                    await refresh_table_data()
                            else:
                                ui.notify(res.get('error', 'Check-in failed'), type='negative')

                        render_scanner_station(
                            student_id=student_id,
                            active_purpose=active_purpose,
                            on_scan=handle_scan,
                            feedback_banner_holder=feedback_banner_holder,
                        )

                    # Right: Live Doorway Feed
                    with ui.column().classes('lg:col-span-5 gap-4'):
                        with ui.card().classes('w-full p-5 rounded-3xl bg-white border border-slate-200 shadow-sm'):
                            with ui.row().classes('w-full items-center justify-between mb-3'):
                                with ui.row().classes('items-center gap-2'):
                                    ui.element('div').classes('w-2.5 h-2.5 rounded-full bg-emerald-500 animate-pulse')
                                    ui.label('LIVE DOORWAY STREAM').classes('text-xs font-black text-slate-900 uppercase tracking-wider')
                                ui.label('Real-time Logs').classes('text-[11px] font-bold text-slate-400')

                            live_feed_container = ui.column().classes('w-full gap-2.5 max-h-[520px] overflow-y-auto')

                            async def refresh_doorway_stream():
                                recent_logs = await mongo_db.get_today_attendance_logs(limit=10)
                                render_live_doorway_feed(live_feed_container, recent_logs)

                            await refresh_doorway_stream()

            # TAB 2: Digital Pass (Default for Students)
            with ui.tab_panel(tab_pass).classes('p-0'):
                async def handle_self_checkin():
                    res = await mongo_db.record_attendance_scan(
                        identifier=student_id,
                        name=user_name,
                        program=user_program,
                        purpose=active_purpose['val'],
                        user_id=user_id
                    )
                    if res.get('success'):
                        ui.notify(res.get('message'), type='positive', duration=4000)
                        await refresh_stats()
                    else:
                        ui.notify(res.get('error'), type='negative')

                render_digital_pass_card(
                    user_name=user_name,
                    student_id=student_id,
                    user_program=user_program,
                    user_role=user_role,
                    on_self_checkin=handle_self_checkin,
                )

            # TAB 3: Daily Visitor Log Summary (FM-LIBS-009) - Strictly Staff (Admin/Librarian) Only
            if is_staff:
                with ui.tab_panel(tab_logs).classes('p-0'):
                    with ui.card().classes('w-full p-5 sm:p-6 rounded-3xl bg-white border border-slate-200 shadow-sm'):
                        with ui.row().classes('w-full items-center justify-between gap-3 mb-4 flex-wrap'):
                            with ui.column().classes('gap-0.5'):
                                with ui.row().classes('items-center gap-2'):
                                    ui.label('Daily Library Visitor / Entrance Log Summary').classes('text-base sm:text-lg font-black text-slate-900')
                                    ui.label('FM-LIBS-009').classes('text-[11px] font-bold bg-indigo-50 text-indigo-700 px-2.5 py-0.5 rounded-full border border-indigo-200')
                                ui.label('Formal institutional visitor log record replacing pen-and-paper entrance sheets (NEMSU Tandag Campus)').classes('text-xs text-slate-500')

                            with ui.row().classes('items-center gap-2 flex-wrap'):
                                prog_select = ui.select(PROGRAM_OPTIONS, value='All', label='Program').props('dense rounded outlined options-dense').classes('w-28 text-xs')
                                date_input = ui.input(value=filter_state['date'], label='Date (YYYY-MM-DD)').props('dense rounded outlined').classes('w-36 text-xs')

                        table_container = ui.element('div').classes('w-full overflow-x-auto')

                        async def refresh_table_data_impl():
                            chosen_date = date_input.value.strip() or None
                            chosen_prog = prog_select.value if prog_select.value != 'All' else None
                            logs = await mongo_db.get_filtered_attendance_logs(chosen_date, chosen_prog, limit=200)
                            render_visitor_logs_table(table_container, logs, date_input.value, prog_select.value)

                        refresh_table_data = refresh_table_data_impl
                        prog_select.on('update:model-value', refresh_table_data)
                        date_input.on('keydown.enter', refresh_table_data)
                        await refresh_table_data()
