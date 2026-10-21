from datetime import datetime
from typing import Optional, Dict, Any, List
from nicegui import ui, app

from components.sidebar import sidebar
from components.header import header
from core.database.mongo_manager import mongo_db
from core.auth.jwt_handler import get_current_user_role
from core.events import attendance_event_bus
from components.attendance import (
    generate_qr_base64,
    render_digital_pass_card,
    PURPOSE_OPTIONS,
    render_scanner_station,
    render_live_doorway_feed,
    render_attendee_dossier_card,
    PROGRAM_OPTIONS,
    render_visitor_logs_table,
    render_dashboard_kpis,
    render_program_breakdown,
)

__all__ = ['generate_qr_base64', 'attendance_page', 'PURPOSE_OPTIONS', 'PROGRAM_OPTIONS']


async def attendance_page():
    """
    Automated QR-Code Entrance Attendance System and Visitor Log Terminal.
    Complies with SRS Chapter 1 (Specific Objective 3), Chapter 2 (FR 3, NFR 1),
    and Form FM-LIBS-009: Daily Library Visitor / Entrance Log Summary.
    """
    app.storage.client['page_path'] = '/attendance'

    drawer = sidebar()
    header(drawer_reference=drawer)

    # User context
    user_id = app.storage.user.get('user_id')
    user_name = app.storage.user.get('username') or 'Student'
    user_role = get_current_user_role()
    is_staff = user_role in ['admin', 'librarian']
    is_admin = (user_role == 'admin')
    user_profile = await mongo_db.get_user_profile(user_id) if user_id else {}
    student_id = (
        user_profile.get('institutional_id')
        or user_profile.get('student_id')
        or (f"26-{str(user_id)[:5].upper()}" if user_id else "26-00001")
    )
    user_program = user_profile.get('program') or user_profile.get('department') or "BSCS"
    user_address = user_profile.get('address') or "NEMSU Tandag Campus"
    user_year_level = user_profile.get('year_level') or "1st Year"
    user_department = user_profile.get('department') or user_program

    # State
    active_purpose = {'val': "Study / Review"}
    filter_state = {
        'date': datetime.now().strftime("%Y-%m-%d"),
        'program': 'All',
        'status': 'All'
    }
    refresh_table_data = None

    # Mobile-safe Zero-Overlap CSS Injection
    ui.add_head_html('''
    <style>
    /* Zero-overlap & Fluid responsive constraints */
    .mobile-safe-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(130px, 1fr));
        gap: 0.5rem;
        width: 100%;
    }
    @media (max-width: 640px) {
        .kiosk-stack-mobile {
            flex-direction: column !important;
            width: 100% !important;
        }
        .kiosk-btn-full {
            width: 100% !important;
            min-height: 44px !important;
        }
    }
    </style>
    ''')

    with ui.column().classes(
        'w-full min-h-fit pt-[calc(4.5rem+env(safe-area-inset-top,0px))] '
        'px-3 sm:px-6 md:pt-24 md:px-10 max-w-[1600px] mx-auto pb-16 safe-pb-mobile-nav'
    ):
        # 1. Page Title Banner
        with ui.column().classes('gap-1 mb-6'):
            with ui.row().classes('items-center gap-2.5 flex-wrap'):
                with ui.element('div').classes('p-2.5 rounded-2xl bg-indigo-50 text-indigo-600 border border-indigo-100 shadow-sm'):
                    ui.icon('qr_code_scanner', size='28px')
                with ui.column().classes('gap-0'):
                    ui.label('Library Entrance Attendance System').classes('text-2xl sm:text-3xl font-black text-slate-900 tracking-tight')
                    ui.label('Automated QR check-in terminal & Form FM-LIBS-009 visitor log (NEMSU Tandag Campus)').classes('text-xs sm:text-sm text-slate-500')

        # 2. Real-time Entrance Stats Bar
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
                    with ui.card().classes('p-3.5 sm:p-4 rounded-2xl bg-white border border-slate-200 shadow-2xs'):
                        with ui.row().classes('items-center gap-2 mb-1'):
                            with ui.element('div').classes(f'p-1.5 rounded-xl {bg_col} {text_col}'):
                                ui.icon(icon_name, size='18px')
                            ui.label(label_text).classes('text-[11px] font-bold text-slate-400 uppercase tracking-wider')
                        ui.label(val_text).classes('text-xl sm:text-2xl font-black text-slate-900')

        await refresh_stats()

        # 3. Tab Navigation (RBAC Guarded: Daily Visitor Logs visible ONLY to Admin & Librarian)
        with ui.tabs().classes('w-full bg-slate-100/80 p-1 rounded-2xl mb-6 text-slate-600') as tabs:
            tab_scanner = ui.tab('scanner', label='Entrance Fast Scanner', icon='qr_code_scanner')
            tab_pass = ui.tab('pass', label='My Library QR Pass', icon='badge')
            if is_staff:
                tab_logs = ui.tab('logs', label='Form FM-LIBS-009 Logbook', icon='receipt_long')

        initial_tab = tab_pass if user_role == 'student' else tab_scanner
        with ui.tab_panels(tabs, value=initial_tab).classes('w-full bg-transparent p-0'):

            # TAB 1: Fast Entrance Scanner
            with ui.tab_panel(tab_scanner).classes('p-0'):
                refresh_doorway_stream = None

                scanner_wrapper = (
                    ui.grid().classes('w-full grid-cols-1 lg:grid-cols-12 gap-6')
                    if is_admin
                    else ui.column().classes('w-full max-w-4xl mx-auto gap-5')
                )

                with scanner_wrapper:
                    scanner_col = (
                        ui.column().classes('lg:col-span-7 gap-5')
                        if is_admin
                        else ui.column().classes('w-full gap-5')
                    )
                    with scanner_col:
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

                                # Acoustic Audio Feedback (Web Audio API)
                                if act == 'checkin':
                                    ui.run_javascript('if(window.playLibreChime) window.playLibreChime("checkin");')
                                    ui.notify(msg, type='positive', duration=4000)
                                elif act == 'checkout':
                                    ui.run_javascript('if(window.playLibreChime) window.playLibreChime("checkout");')
                                    ui.notify(msg, type='info', duration=4000)
                                elif act == 'cooldown':
                                    ui.run_javascript('if(window.playLibreChime) window.playLibreChime("cooldown");')
                                    ui.notify(msg, type='warning', duration=4000)

                                # Visual Attendee Dossier Card
                                if 'banner' in feedback_banner_holder and feedback_banner_holder['banner']:
                                    with feedback_banner_holder['banner']:
                                        def dismiss_banner():
                                            if 'banner' in feedback_banner_holder and feedback_banner_holder['banner']:
                                                feedback_banner_holder['banner'].clear()

                                        render_attendee_dossier_card(
                                            entry=entry,
                                            action=act,
                                            duration_minutes=res.get('duration_minutes', 1),
                                            on_dismiss=dismiss_banner,
                                        )

                                await refresh_stats()
                                if is_admin and refresh_doorway_stream is not None:
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

                    # Right: Live Doorway Feed (STRICTLY Admin Only - Hidden from Students, Faculty, and Librarians)
                    if is_admin:
                        with ui.column().classes('lg:col-span-5 gap-4'):
                            with ui.card().classes('w-full p-5 rounded-3xl bg-white border border-slate-200 shadow-sm'):
                                with ui.row().classes('w-full items-center justify-between mb-3'):
                                    with ui.row().classes('items-center gap-2'):
                                        ui.element('div').classes('w-2.5 h-2.5 rounded-full bg-emerald-500 animate-pulse')
                                        ui.label('LIVE DOORWAY STREAM').classes('text-xs font-black text-slate-900 uppercase tracking-wider')
                                    ui.label('Real-time Logs (Admin Only)').classes('text-[11px] font-bold text-slate-400')

                                live_feed_container = ui.column().classes('w-full gap-2.5 max-h-[520px] overflow-y-auto')

                                async def refresh_doorway_stream_impl():
                                    recent_logs = await mongo_db.get_today_attendance_logs(limit=10)
                                    render_live_doorway_feed(live_feed_container, recent_logs)

                                refresh_doorway_stream = refresh_doorway_stream_impl
                                await refresh_doorway_stream()

                    async def on_doorway_scan_update(event_payload):
                        try:
                            await refresh_stats()
                            if is_admin and refresh_doorway_stream is not None:
                                await refresh_doorway_stream()
                            if is_staff and refresh_table_data is not None:
                                await refresh_table_data()
                        except Exception:
                            pass

                    # Event bus subscription: only admins and staff need live updates on this terminal
                    if is_admin or is_staff:
                        unsub_doorway = attendance_event_bus.subscribe("*", on_doorway_scan_update)
                        try:
                            from nicegui import context
                            if context.client:
                                context.client.on_disconnect(unsub_doorway)
                        except Exception:
                            pass

            # TAB 2: Digital Pass (Default for Students)
            with ui.tab_panel(tab_pass).classes('p-0'):
                user_initial_attendance = await mongo_db.get_user_today_attendance(
                    identifier=student_id, user_id=user_id
                )

                render_digital_pass_card(
                    user_name=user_name,
                    student_id=student_id,
                    user_program=user_program,
                    user_role=user_role,
                    user_address=user_address,
                    user_year_level=user_year_level,
                    user_department=user_department,
                    user_id=user_id,
                    initial_attendance=user_initial_attendance,
                )

            # TAB 3: Daily Visitor Log Summary (FM-LIBS-009) - Strictly Staff (Admin/Librarian) Only
            if is_staff:
                with ui.tab_panel(tab_logs).classes('p-0'):
                    with ui.card().classes('w-full p-4 sm:p-6 rounded-3xl bg-white border border-slate-200 shadow-sm'):
                        with ui.row().classes('w-full items-center justify-between gap-3 mb-4 flex-wrap'):
                            with ui.column().classes('gap-0.5'):
                                with ui.row().classes('items-center gap-2'):
                                    ui.label('Daily Library Visitor / Entrance Log Summary').classes('text-base sm:text-lg font-black text-slate-900')
                                    ui.label('FORM FM-LIBS-009').classes('text-[11px] font-bold bg-indigo-50 text-indigo-700 px-2.5 py-0.5 rounded-full border border-indigo-200')
                                ui.label('Official institutional visitor record replacing paper logbooks (NEMSU Tandag Campus)').classes('text-xs text-slate-500')

                            with ui.row().classes('items-center gap-2 flex-wrap'):
                                prog_select = ui.select(PROGRAM_OPTIONS, value='All', label='Program').props('dense rounded outlined options-dense').classes('w-28 text-xs')
                                status_select = ui.select(["All", "Checked In", "Checked Out"], value='All', label='Status').props('dense rounded outlined options-dense').classes('w-28 text-xs')
                                date_input = ui.input(value=filter_state['date'], label='Date (YYYY-MM-DD)').props('dense rounded outlined').classes('w-32 text-xs')

                                def export_fmlibs_csv():
                                    d_val = date_input.value.strip() or filter_state['date']
                                    p_val = prog_select.value if prog_select.value != 'All' else None
                                    import base64
                                    csv_str = mongo_db.export_fmlibs009_csv(current_loaded_logs, d_val, p_val)
                                    b64 = base64.b64encode(csv_str.encode('utf-8')).decode('utf-8')
                                    fname = f"NEMSU_FM-LIBS-009_Visitor_Log_{d_val}_{p_val or 'All'}.csv"
                                    ui.run_javascript(f'''
                                        const a = document.createElement('a');
                                        a.href = 'data:text/csv;base64,{b64}';
                                        a.download = '{fname}';
                                        a.click();
                                    ''')
                                    ui.notify('FM-LIBS-009 Logbook exported successfully!', type='positive')

                                ui.button('Export FM-LIBS-009 (CSV)', icon='download', on_click=export_fmlibs_csv)\
                                    .props('unelevated rounded-xl color=indigo size=sm font-bold shadow-xs')

                        kpi_container = ui.element('div').classes('w-full')
                        prog_container = ui.element('div').classes('w-full')
                        table_container = ui.element('div').classes('w-full overflow-x-auto')
                        current_loaded_logs = []

                        async def refresh_table_data_impl():
                            nonlocal current_loaded_logs
                            chosen_date = date_input.value.strip() or None
                            chosen_prog = prog_select.value if prog_select.value != 'All' else None
                            chosen_stat = status_select.value if status_select.value != 'All' else None

                            live_kpis = await mongo_db.get_attendance_live_metrics(chosen_date)
                            kpi_container.clear()
                            with kpi_container:
                                render_dashboard_kpis(live_kpis, chosen_date or filter_state['date'])

                            prog_container.clear()
                            with prog_container:
                                render_program_breakdown(live_kpis.get('program_distribution', {}))

                            logs = await mongo_db.attendance.get_logs_filtered(
                                date_str=chosen_date,
                                program=chosen_prog,
                                status=chosen_stat,
                                limit=300
                            )
                            current_loaded_logs = logs
                            render_visitor_logs_table(table_container, logs, date_input.value, prog_select.value)

                        refresh_table_data = refresh_table_data_impl
                        prog_select.on('update:model-value', refresh_table_data)
                        status_select.on('update:model-value', refresh_table_data)
                        date_input.on('keydown.enter', refresh_table_data)
                        await refresh_table_data()
