import io
import time
import base64
from datetime import datetime
from typing import Optional, Dict, Any, List
from nicegui import ui, app, run

from components.sidebar import sidebar
from components.header import header
from components.bottom_nav import bottom_nav
from core.database.mongo_manager import mongo_db

PURPOSE_OPTIONS = [
    "📚 Study / Review",
    "🔬 Research / Thesis",
    "📖 Book Borrow / Return",
    "💻 E-Library / Digital OPAC",
    "👥 Group Discussion"
]

PROGRAM_OPTIONS = [
    "All", "BSCS", "BSIT", "BSED", "BEED", "BSBA", "BSHM", "Crim", "Nursing", "GENERAL"
]


def generate_qr_base64(payload_text: str) -> str:
    """Generates a high-contrast base64 PNG QR code data URI."""
    clean_text = str(payload_text or "LIBRE-PASS").strip() or "LIBRE-PASS"
    try:
        import qrcode
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=10,
            border=2,
        )
        qr.add_data(clean_text)
        qr.make(fit=True)
        img = qr.make_image(fill_color="#0f172a", back_color="#ffffff")
        buffer = io.BytesIO()
        img.save(buffer)
        b64_str = base64.b64encode(buffer.getvalue()).decode('utf-8')
        return f"data:image/png;base64,{b64_str}"
    except Exception:
        # Fallback SVG data URI if qrcode library has any issue
        return f"https://api.qrserver.com/v1/create-qr-code/?size=250x250&data={clean_text}"


async def attendance_page():
    """
    Automated QR-Code Entrance Attendance System and Visitor Log Terminal.
    Complies with SRS Chapter 1 (Specific Objective 3), Chapter 2 (FR 3, NFR 1),
    and Section 2.2 ("Daily Library Visitor / Entrance Log Summary").
    """
    app.storage.client['page_path'] = '/attendance'

    drawer = sidebar()
    header(drawer_reference=drawer)
    bottom_nav()

    # User context
    user_id = app.storage.user.get('user_id')
    user_name = app.storage.user.get('username') or 'Student'
    user_role = app.storage.user.get('role', 'student')
    user_profile = await mongo_db.get_user_profile(user_id)
    student_id = user_profile.get('student_id') or (f"2024-{str(user_id)[:5].upper()}" if user_id else "2024-001")
    user_program = user_profile.get('program') or "BSCS"

    # State
    active_purpose = {'val': "📚 Study / Review"}
    filter_state = {
        'date': datetime.now().strftime("%Y-%m-%d"),
        'program': 'All'
    }

    with ui.column().classes(
        'w-full min-h-[100dvh] pt-[calc(4.5rem+env(safe-area-inset-top,0px))] '
        'px-3 sm:px-6 md:pt-24 md:px-8 max-w-7xl mx-auto pb-[calc(5rem+env(safe-area-inset-bottom,0px))] md:pb-16'
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
            stats_container.clear()
            today_logs = await mongo_db.get_today_attendance_logs(limit=500)
            active_count = await mongo_db.get_active_checked_in_count()
            total_all = await mongo_db.get_total_visitors_count()

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

        # TAB NAVIGATION
        with ui.tabs().classes('w-full bg-slate-100/80 p-1 rounded-2xl mb-6 text-slate-600') as tabs:
            tab_scanner = ui.tab('scanner', label='Entrance Fast Scanner', icon='qr_code_scanner')
            tab_logs = ui.tab('logs', label='Daily Visitor Logs', icon='receipt_long')
            tab_pass = ui.tab('pass', label='My Library QR Pass', icon='badge')

        with ui.tab_panels(tabs, value=tab_scanner).classes('w-full bg-transparent p-0'):

            # =================================================================
            # TAB 1: FAST ENTRANCE SCANNER TERMINAL
            # =================================================================
            with ui.tab_panel(tab_scanner).classes('p-0'):
                with ui.grid().classes('w-full grid-cols-1 lg:grid-cols-12 gap-6'):

                    # Left: Scanner & Entry Station (7 cols)
                    with ui.column().classes('lg:col-span-7 gap-5'):
                        with ui.card().classes('w-full p-5 sm:p-6 rounded-3xl bg-white border border-slate-200 shadow-sm'):
                            ui.label('ENTRANCE DOOR SCANNER').classes('text-xs font-black text-indigo-600 uppercase tracking-wider mb-2')
                            ui.label('Hold student QR code or NEMSU ID barcode in front of the camera').classes('text-sm text-slate-600 mb-4')

                            # Purpose Selection Chips
                            ui.label('Purpose of Visit:').classes('text-xs font-bold text-slate-500 uppercase tracking-wider mb-1.5')
                            with ui.row().classes('gap-2 mb-4 flex-wrap'):
                                chip_elements = {}
                                for p in PURPOSE_OPTIONS:
                                    def select_purpose(chosen=p):
                                        active_purpose['val'] = chosen
                                        for opt, btn in chip_elements.items():
                                            if opt == chosen:
                                                btn.props('unelevated color=indigo')
                                            else:
                                                btn.props('flat color=grey-7')

                                    btn_el = ui.button(p, on_click=select_purpose).props(
                                        'rounded-xl size=sm font-bold ' + ('unelevated color=indigo' if p == active_purpose['val'] else 'flat color=grey-7')
                                    )
                                    chip_elements[p] = btn_el

                            # Camera Stream / HTML5 QR Scanner Viewport
                            with ui.element('div').classes('w-full rounded-2xl overflow-hidden bg-slate-900 border border-slate-300 relative flex flex-col items-center justify-center min-h-[260px] sm:min-h-[300px] shadow-inner'):
                                # Load html5-qrcode library & scanner runner via ui.add_body_html
                                ui.add_body_html('''
                                <script src="https://unpkg.com/html5-qrcode@2.3.8/html5-qrcode.min.js"></script>
                                <script>
                                window.libreScannerRunning = false;
                                window.startLibreScanner = function() {
                                    if (window.libreScannerRunning) return;
                                    const html5QrCode = new Html5Qrcode("reader");
                                    const qrCodeSuccessCallback = (decodedText, decodedResult) => {
                                        const inputEl = document.querySelector('#attendance-manual-input input');
                                        if (inputEl) {
                                            inputEl.value = decodedText;
                                            inputEl.dispatchEvent(new Event('input', { bubbles: true }));
                                            const submitBtn = document.querySelector('#attendance-submit-btn');
                                            if (submitBtn) submitBtn.click();
                                        }
                                    };
                                    const config = { fps: 10, qrbox: { width: 220, height: 220 } };
                                    html5QrCode.start({ facingMode: "environment" }, config, qrCodeSuccessCallback)
                                        .then(() => { window.libreScannerRunning = true; })
                                        .catch(err => {
                                            console.warn("Camera start notice:", err);
                                            const r = document.getElementById("reader");
                                            if (r) r.innerHTML = '<div class="text-slate-300 text-xs p-4 text-center">Camera stream offline or permission not granted. Use the manual/barcode input below.</div>';
                                        });
                                };
                                </script>
                                ''')
                                # HTML5 QR Code Mount Div
                                ui.html('<div id="reader" style="width: 100%; max-width: 480px; min-height: 240px; margin: auto;"></div>', sanitize=False, tag='div').classes('w-full')

                            with ui.row().classes('w-full justify-between items-center gap-2 mt-3 flex-wrap'):
                                ui.button('Activate Camera Scanner', icon='videocam', on_click=lambda: ui.run_javascript('window.startLibreScanner();')) \
                                    .props('unelevated rounded-xl color=indigo size=sm font-bold min-height=40px')
                                ui.label('⚡ Response Time: < 0.2s').classes('text-xs font-mono text-emerald-600 font-bold')

                            ui.separator().classes('my-4')

                            # Peak-End Rule: Dynamic Live Status Confirmation Banner Card
                            feedback_banner = ui.element('div').classes('w-full')

                            # Manual ID Input / Barcode Scanner Gun Field
                            with ui.row().classes('w-full items-center justify-between mb-1 flex-wrap gap-1'):
                                ui.label('Rapid ID / Barcode Input:').classes('text-xs font-bold text-slate-500 uppercase tracking-wider')
                                # Tesler's Law: 1-click self-test chip for presenter convenience
                                with ui.row().classes('items-center gap-1 cursor-pointer hover:opacity-80').on('click', lambda: set_self_input()):
                                    ui.icon('flash_on', size='14px').classes('text-amber-500')
                                    ui.label(f'Fill My ID: {student_id}').classes('text-[11px] font-bold text-indigo-600')

                            with ui.row().classes('w-full items-center gap-2 flex-wrap sm:flex-nowrap'):
                                manual_input = ui.input(placeholder='Scan barcode gun or type Student ID (e.g. 2024-001)...') \
                                    .classes('flex-1 text-base min-h-[44px]').props('id="attendance-manual-input" rounded outlined dense autofocus')

                                def set_self_input():
                                    manual_input.value = student_id

                                async def handle_manual_scan():
                                    val = manual_input.value.strip()
                                    if not val:
                                        ui.notify('Please enter or scan a Student ID', type='warning')
                                        return
                                    res = await mongo_db.record_attendance_scan(
                                        identifier=val,
                                        purpose=active_purpose['val'],
                                        name=user_name if val == student_id else "",
                                        program=user_program if val == student_id else ""
                                    )
                                    manual_input.value = ""
                                    feedback_banner.clear()

                                    if res.get('success'):
                                        act = res.get('action')
                                        entry = res.get('entry') or {}
                                        msg = res.get('message', 'Attendance logged.')
                                        ui.notify(msg, type='positive' if act == 'checkin' else 'info', duration=4000)

                                        # Peak-End Rule: Visual Delight Banner
                                        with feedback_banner:
                                            is_checkin = act == 'checkin'
                                            banner_bg = 'bg-emerald-50 border-emerald-200 text-emerald-900' if is_checkin else 'bg-blue-50 border-blue-200 text-blue-900'
                                            banner_icon = 'verified' if is_checkin else 'waving_hand'
                                            with ui.card().classes(f'w-full p-3.5 rounded-2xl border mb-3 flex flex-row items-center justify-between gap-3 {banner_bg} shadow-sm animate-fade-in'):
                                                with ui.row().classes('items-center gap-3 min-w-0 flex-1'):
                                                    ui.icon(banner_icon, size='24px').classes('text-emerald-600' if is_checkin else 'text-blue-600')
                                                    with ui.column().classes('gap-0 min-w-0 flex-1'):
                                                        ui.label(entry.get('name', val)).classes('text-sm font-black truncate')
                                                        ui.label(f"{entry.get('program', 'BSCS')} • {entry.get('purpose', 'Study')} • {entry.get('time_in_str', '')}").classes('text-xs opacity-80')
                                                with ui.element('div').classes('px-2.5 py-1 rounded-xl text-xs font-black uppercase bg-white/80 shadow-xs shrink-0'):
                                                    ui.label("CHECKED IN" if is_checkin else f"OUT ({res.get('duration_minutes', 0)}m)")

                                        await refresh_stats()
                                        await refresh_live_feed()
                                        await refresh_table()
                                    else:
                                        ui.notify(res.get('error', 'Check-in failed'), type='negative')

                                manual_input.on('keydown.enter', handle_manual_scan)
                                ui.button('Check In / Out', icon='login', on_click=handle_manual_scan) \
                                    .props('id="attendance-submit-btn" unelevated rounded-xl color=slate-900 text-color=white size=md font-bold') \
                                    .classes('w-full sm:w-auto min-h-[44px] px-5 shrink-0 shadow-sm hover:brightness-110 active:scale-95 transition-all')

                    # Right: Live Entrance Doorway Feed (5 cols)
                    with ui.column().classes('lg:col-span-5 gap-4'):
                        with ui.card().classes('w-full p-5 rounded-3xl bg-white border border-slate-200 shadow-sm'):
                            with ui.row().classes('w-full items-center justify-between mb-3'):
                                with ui.row().classes('items-center gap-2'):
                                    ui.element('div').classes('w-2.5 h-2.5 rounded-full bg-emerald-500 animate-pulse')
                                    ui.label('LIVE DOORWAY STREAM').classes('text-xs font-black text-slate-900 uppercase tracking-wider')
                                ui.label('Real-time Logs').classes('text-[11px] font-bold text-slate-400')

                            live_feed_container = ui.column().classes('w-full gap-2.5 max-h-[460px] overflow-y-auto')

                            async def refresh_live_feed():
                                live_feed_container.clear()
                                recent_logs = await mongo_db.get_today_attendance_logs(limit=10)
                                with live_feed_container:
                                    if not recent_logs:
                                        ui.label('No visitor check-ins recorded yet today.').classes('text-xs text-slate-400 italic text-center py-6 w-full')
                                        return
                                    for r in recent_logs:
                                        is_in = r.get('status') == 'Checked In'
                                        status_bg = 'bg-emerald-50 text-emerald-700 border-emerald-200' if is_in else 'bg-slate-100 text-slate-700 border-slate-200'
                                        with ui.row().classes('w-full p-3 rounded-2xl border border-slate-100 hover:border-slate-200 bg-slate-50/60 items-center justify-between gap-2'):
                                            with ui.row().classes('items-center gap-3 min-w-0 flex-1'):
                                                ui.avatar(icon='person', color='indigo-100', text_color='indigo-800', size='34px') \
                                                    .classes('shrink-0 border border-indigo-200')
                                                with ui.column().classes('gap-0 min-w-0 flex-1'):
                                                    ui.label(r.get('name', 'Student')).classes('text-xs font-bold text-slate-900 truncate')
                                                    with ui.row().classes('items-center gap-1.5 flex-wrap'):
                                                        ui.label(r.get('program', 'BSCS')).classes('text-[10px] font-black text-indigo-600 bg-indigo-50 px-1.5 py-0.2 rounded')
                                                        ui.label(f"ID: {r.get('student_id')}").classes('text-[10px] text-slate-400 font-mono')
                                                    ui.label(r.get('purpose', 'Study')).classes('text-[10px] text-slate-500 italic truncate')

                                            with ui.column().classes('items-end shrink-0 gap-1'):
                                                with ui.element('div').classes(f'px-2 py-0.5 rounded-full text-[10px] font-black uppercase border {status_bg}'):
                                                    ui.label(r.get('status'))
                                                ui.label(r.get('time_in_str', '')).classes('text-[10px] font-mono text-slate-400')

                            await refresh_live_feed()

            # =================================================================
            # TAB 2: DAILY VISITOR LOG SUMMARY (Chapter 2 Section 2.2 Report)
            # =================================================================
            with ui.tab_panel(tab_logs).classes('p-0'):
                with ui.card().classes('w-full p-5 sm:p-6 rounded-3xl bg-white border border-slate-200 shadow-sm'):
                    with ui.row().classes('w-full items-center justify-between gap-3 mb-4 flex-wrap'):
                        with ui.column().classes('gap-0.5'):
                            ui.label('Daily Library Visitor / Entrance Log Summary').classes('text-base sm:text-lg font-black text-slate-900')
                            ui.label('Formal institutional visitor log record replacing pen-and-paper entrance sheets').classes('text-xs text-slate-500')

                        # Filters Bar
                        with ui.row().classes('items-center gap-2 flex-wrap'):
                            prog_select = ui.select(PROGRAM_OPTIONS, value='All', label='Program') \
                                .props('dense rounded outlined options-dense').classes('w-28 text-xs')
                            date_input = ui.input(value=filter_state['date'], label='Date (YYYY-MM-DD)') \
                                .props('dense rounded outlined').classes('w-36 text-xs')

                    table_container = ui.element('div').classes('w-full overflow-x-auto')

                    async def refresh_table():
                        table_container.clear()
                        chosen_date = date_input.value.strip() or None
                        chosen_prog = prog_select.value if prog_select.value != 'All' else None
                        logs = await mongo_db.get_filtered_attendance_logs(chosen_date, chosen_prog, limit=200)

                        rows = []
                        for l in logs:
                            rows.append({
                                'id': l.get('id'),
                                'date': l.get('date_str'),
                                'time_in': l.get('time_in_str', '-'),
                                'time_out': l.get('time_out_str', '-'),
                                'student_id': l.get('student_id', '-'),
                                'name': l.get('name', 'Visitor'),
                                'program': l.get('program', 'GENERAL'),
                                'purpose': l.get('purpose', 'Study'),
                                'duration': f"{l.get('duration_minutes', 0)} mins" if l.get('status') == 'Checked Out' else 'Active',
                                'status': l.get('status', 'Checked In')
                            })

                        columns = [
                            {'name': 'time_in', 'label': 'Time-In', 'field': 'time_in', 'align': 'left', 'sortable': True},
                            {'name': 'time_out', 'label': 'Time-Out', 'field': 'time_out', 'align': 'left', 'sortable': True},
                            {'name': 'student_id', 'label': 'Student ID', 'field': 'student_id', 'align': 'left', 'sortable': True},
                            {'name': 'name', 'label': 'Student Name', 'field': 'name', 'align': 'left', 'sortable': True},
                            {'name': 'program', 'label': 'Program', 'field': 'program', 'align': 'center', 'sortable': True},
                            {'name': 'purpose', 'label': 'Purpose of Visit', 'field': 'purpose', 'align': 'left'},
                            {'name': 'duration', 'label': 'Duration', 'field': 'duration', 'align': 'center'},
                            {'name': 'status', 'label': 'Status', 'field': 'status', 'align': 'center', 'sortable': True},
                        ]

                        with table_container:
                            if not rows:
                                ui.label('No visitor logs found matching the filter criteria.').classes('text-xs text-slate-400 italic p-6 text-center w-full')
                            else:
                                ui.table(columns=columns, rows=rows, row_key='id').classes('w-full').props('flat bordered')

                        # Export CSV helper
                        with ui.row().classes('w-full justify-end mt-4'):
                            def export_csv():
                                if not rows:
                                    ui.notify("No data to export", type='warning')
                                    return
                                csv_lines = ["Date,Time-In,Time-Out,StudentID,Name,Program,Purpose,Duration,Status"]
                                for r in rows:
                                    csv_lines.append(f'"{r["date"]}","{r["time_in"]}","{r["time_out"]}","{r["student_id"]}","{r["name"]}","{r["program"]}","{r["purpose"]}","{r["duration"]}","{r["status"]}"')
                                csv_content = "\n".join(csv_lines)
                                b64 = base64.b64encode(csv_content.encode('utf-8')).decode('utf-8')
                                filename = f"NEMSU_Library_Visitor_Log_{date_input.value}.csv"
                                ui.run_javascript(f'''
                                    const a = document.createElement('a');
                                    a.href = 'data:text/csv;base64,{b64}';
                                    a.download = '{filename}';
                                    a.click();
                                ''')
                                ui.notify("Visitor log exported successfully!", type='positive')

                            ui.button('Export Log Summary (CSV)', icon='download', on_click=export_csv) \
                                .props('unelevated rounded-xl color=indigo size=sm font-bold')

                    prog_select.on('update:model-value', refresh_table)
                    date_input.on('keydown.enter', refresh_table)
                    await refresh_table()

            # =================================================================
            # TAB 3: MY DIGITAL LIBRARY QR PASS
            # =================================================================
            with ui.tab_panel(tab_pass).classes('p-0'):
                with ui.column().classes('w-full items-center justify-center py-4'):
                    # Official Digital ID Card Container
                    with ui.card().classes(
                        'w-full max-w-md p-6 sm:p-8 rounded-3xl bg-white border border-slate-200 shadow-xl '
                        'relative overflow-hidden text-center'
                    ):
                        # University Top Banner Accent
                        with ui.element('div').classes('w-full h-3 bg-gradient-to-r from-indigo-600 via-purple-600 to-indigo-800 absolute top-0 left-0'):
                            pass

                        with ui.column().classes('w-full items-center gap-1 mb-4 mt-2'):
                            ui.label('NORTH EASTERN MINDANAO STATE UNIVERSITY').classes('text-[10px] sm:text-xs font-black text-slate-800 tracking-wider')
                            ui.label('Tandag Campus • Libre-Library Digital Pass').classes('text-[10px] text-slate-400 font-bold uppercase tracking-widest')

                        # QR Code Display
                        qr_data_url = generate_qr_base64(student_id)
                        with ui.element('div').classes('p-3.5 bg-slate-50 border-2 border-dashed border-indigo-200 rounded-3xl inline-block mx-auto mb-4 shadow-sm'):
                            ui.image(qr_data_url).classes('w-44 h-44 sm:w-52 sm:h-52 rounded-2xl mx-auto')

                        # Student Details
                        ui.label(user_name).classes('text-xl sm:text-2xl font-black text-slate-900')
                        with ui.row().classes('items-center justify-center gap-2 mb-2'):
                            ui.label(student_id).classes('text-xs font-mono font-bold text-slate-600 bg-slate-100 px-2 py-0.5 rounded')
                            ui.label(user_program).classes('text-xs font-black text-indigo-700 bg-indigo-50 px-2.5 py-0.5 rounded-full border border-indigo-200')
                            ui.label(user_role.upper()).classes('text-[10px] font-black text-purple-700 bg-purple-50 px-2 py-0.5 rounded-full')

                        ui.label('Scan this QR code at the library entrance door scanner for automatic contactless check-in/out.').classes('text-xs text-slate-500 mb-4 px-4 leading-relaxed')

                        with ui.row().classes('w-full justify-center gap-3'):
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

                            ui.button('Self Check-In / Out Now', icon='how_to_reg', on_click=handle_self_checkin) \
                                .props('unelevated rounded-xl color=indigo size=sm font-bold shadow-md')
