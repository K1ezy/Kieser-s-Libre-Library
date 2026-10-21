import io
import time
import base64
from typing import Callable, Any, Optional, Dict
from nicegui import ui

from core.events import attendance_event_bus
from core.database.mongo_manager import mongo_db


def generate_qr_png_bytes(payload_text: str) -> bytes:
    """
    Generates high-contrast, high-error-correction (ERROR_CORRECT_H) PNG bytes
    for fast camera lens and physical turnstile scanner recognition (< 0.2s).
    """
    clean_text = str(payload_text or "LIBRE-PASS").strip() or "LIBRE-PASS"
    # Ensure payload contains prefix if valid ID
    if not clean_text.upper().startswith("LIBRE-ID:") and re_is_id(clean_text):
        clean_text = f"LIBRE-ID:{clean_text}"

    try:
        import qrcode
        qr = qrcode.QRCode(
            version=2,
            error_correction=qrcode.constants.ERROR_CORRECT_H,
            box_size=10,
            border=3,
        )
        qr.add_data(clean_text)
        qr.make(fit=True)
        img = qr.make_image(fill_color="#0F172A", back_color="#FFFFFF")
        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        return buffer.getvalue()
    except Exception:
        # Fallback 1x1 png or basic buffer
        return b""


def re_is_id(val: str) -> bool:
    import re
    return bool(re.match(r"^(\d{2}-\d{5}|\d{4}-[A-Z0-9]{5})$", str(val).strip()))


def generate_qr_base64(payload_text: str) -> str:
    """Generates a high-contrast base64 PNG QR code data URI."""
    raw_bytes = generate_qr_png_bytes(payload_text)
    if raw_bytes:
        b64_str = base64.b64encode(raw_bytes).decode('utf-8')
        return f"data:image/png;base64,{b64_str}"

    clean_text = str(payload_text or "LIBRE-PASS").strip()
    return f"https://api.qrserver.com/v1/create-qr-code/?size=250x250&data={clean_text}"


def render_digital_pass_card(
    user_name: str,
    student_id: str,
    user_program: str,
    user_role: str,
    user_address: str = "NEMSU Tandag Campus",
    user_year_level: str = "1st Year",
    user_department: str = "",
    user_id: Optional[str] = None,
    initial_attendance: Optional[Dict[str, Any]] = None,
    on_self_checkin: Optional[Callable[[], Any]] = None,
) -> None:
    """
    Renders a responsive, mobile-safe Digital PVC ID & Library QR Pass.
    Features:
    - Real-Time Scan Reflection: Instantly reflects check-ins and check-outs on the attendee's side
      as soon as the librarian or admin scans their QR code.
    - Live Presence Badge: Displays active check-in duration, time-in, and purpose with glowing status.
    - Device Audio Feedback: Plays pleasant check-in/out chimes directly on the attendee's device.
    - Today's Activity Timeline: Shows scan history for the current day.
    """
    qr_data_url = generate_qr_base64(student_id)
    norm_role = str(user_role or 'student').upper()
    norm_prog = str(user_program or 'GENERAL').upper()
    display_dept = user_department or user_program or "General Studies"
    display_address = user_address or "NEMSU Tandag Campus"

    # Adapt designation label
    if norm_role in ('FACULTY', 'PROFESSOR'):
        level_label = "FACULTY"
    elif norm_role in ('LIBRARIAN', 'CO-LIBRARIAN'):
        level_label = "LIBRARY STAFF"
    elif norm_role == 'ADMIN':
        level_label = "ADMINISTRATOR"
    else:
        level_label = str(user_year_level or '1st Year').upper()

    # Web Audio Synthesized Chime Script (available on attendee's browser)
    ui.add_head_html('''
    <script>
    if (!window.playLibreChime) {
        window.playLibreChime = function(actionType) {
            try {
                const ctx = new (window.AudioContext || window.webkitAudioContext)();
                const now = ctx.currentTime;
                const osc = ctx.createOscillator();
                const gain = ctx.createGain();
                gain.connect(ctx.destination);
                osc.connect(gain);

                if (actionType === "checkin") {
                    osc.frequency.setValueAtTime(880, now);
                    osc.frequency.setValueAtTime(1174.66, now + 0.1);
                    gain.gain.setValueAtTime(0.2, now);
                    gain.gain.exponentialRampToValueAtTime(0.01, now + 0.25);
                    osc.start(now);
                    osc.stop(now + 0.25);
                } else if (actionType === "checkout") {
                    osc.frequency.setValueAtTime(587.33, now);
                    osc.frequency.setValueAtTime(440, now + 0.12);
                    gain.gain.setValueAtTime(0.2, now);
                    gain.gain.exponentialRampToValueAtTime(0.01, now + 0.3);
                    osc.start(now);
                    osc.stop(now + 0.3);
                } else {
                    osc.frequency.setValueAtTime(440, now);
                    gain.gain.setValueAtTime(0.15, now);
                    gain.gain.exponentialRampToValueAtTime(0.01, now + 0.18);
                    osc.start(now);
                    osc.stop(now + 0.18);
                }
            } catch(e) {}
        };
    }
    </script>
    ''')

    # Attendee Attendance State
    status_state = {
        'data': initial_attendance or {
            'is_inside': False,
            'status': 'Not Visited Today',
            'active_entry': None,
            'latest_entry': None,
            'today_visits': [],
            'total_duration_today_minutes': 0,
        }
    }

    presence_container = None
    history_container = None
    duration_label_holder = {}

    def render_presence_badge():
        data = status_state['data']
        is_inside = data.get('is_inside', False)
        active_entry = data.get('active_entry')
        latest_entry = data.get('latest_entry')

        if is_inside and active_entry:
            ts_in = float(active_entry.get('timestamp_in') or time.time())
            elapsed = max(1, round((time.time() - ts_in) / 60))
            purpose = active_entry.get('purpose', 'Study / Review')
            t_in_str = active_entry.get('time_in_str') or 'Earlier today'

            with ui.column().classes(
                'w-full p-3.5 rounded-2xl bg-emerald-50 border-2 border-emerald-400 '
                'shadow-sm mb-3 items-center text-center gap-1.5 transition-all'
            ):
                with ui.row().classes('items-center justify-center gap-2'):
                    ui.element('div').classes('w-2.5 h-2.5 rounded-full bg-emerald-500 animate-ping')
                    ui.label('CURRENTLY INSIDE LIBRE-LIBRARY').classes(
                        'text-[11px] font-black tracking-wider text-emerald-800 uppercase'
                    )
                with ui.row().classes('items-center justify-center gap-2 text-xs flex-wrap'):
                    with ui.row().classes('items-center gap-1 text-emerald-700 font-bold'):
                        ui.icon('login', size='15px')
                        ui.label(f'Time-In: {t_in_str}')
                    with ui.row().classes('items-center gap-1 text-emerald-700 font-black'):
                        ui.icon('timer', size='15px')
                        duration_label_holder['lbl'] = ui.label(f'Inside for {elapsed}m')
                ui.label(f'Purpose: {purpose} • Verified by Library Terminal').classes(
                    'text-[10px] text-emerald-600 font-medium'
                )

        elif latest_entry and latest_entry.get('status') == 'Checked Out':
            t_in = latest_entry.get('time_in_str', '')
            t_out = latest_entry.get('time_out_str', '')
            dur = latest_entry.get('duration_minutes', 0)
            with ui.column().classes(
                'w-full p-2.5 rounded-2xl bg-slate-100 border border-slate-300 '
                'shadow-2xs mb-3 items-center text-center gap-0.5 transition-all'
            ):
                with ui.row().classes('items-center justify-center gap-1.5'):
                    ui.icon('check_circle', size='16px').classes('text-slate-600')
                    ui.label('CHECKED OUT • COMPLETED VISIT').classes(
                        'text-[10px] font-black tracking-wider text-slate-700 uppercase'
                    )
                ui.label(f'Departed at {t_out} • Duration: {dur}m ({t_in} - {t_out})').classes(
                    'text-[11px] text-slate-600 font-medium'
                )
        else:
            with ui.row().classes(
                'w-full p-2 rounded-2xl bg-indigo-50/80 border border-indigo-100 '
                'mb-3 items-center justify-center gap-1.5 text-center'
            ):
                ui.icon('qr_code_scanner', size='15px').classes('text-indigo-600')
                ui.label('READY TO SCAN • Present this QR pass to Library Staff').classes(
                    'text-[10px] font-bold text-indigo-700'
                )

    def render_history_list():
        visits = status_state['data'].get('today_visits', [])
        if not visits:
            with ui.row().classes('w-full items-center justify-center py-3 text-slate-400 gap-1.5 text-xs'):
                ui.icon('info', size='16px')
                ui.label('No visits logged yet today. Present your QR code upon entry.')
            return

        with ui.column().classes('w-full gap-2'):
            for v in visits:
                st = v.get('status', 'Checked In')
                is_active = st == 'Checked In'
                bg_col = 'bg-emerald-50/60 border-emerald-200' if is_active else 'bg-slate-50 border-slate-200'
                dot_col = 'bg-emerald-500 animate-pulse' if is_active else 'bg-slate-400'
                status_text = 'Inside Now' if is_active else f"Finished ({v.get('duration_minutes', 0)}m)"

                with ui.row().classes(f'w-full p-2.5 rounded-xl border {bg_col} items-center justify-between text-xs'):
                    with ui.row().classes('items-center gap-2 min-w-0'):
                        ui.element('div').classes(f'w-2 h-2 rounded-full {dot_col} shrink-0')
                        with ui.column().classes('gap-0 min-w-0'):
                            ui.label(f"{v.get('purpose', 'Study / Review')}").classes('font-bold text-slate-800 truncate')
                            ui.label(f"In: {v.get('time_in_str', '-')} • Out: {v.get('time_out_str', '-')}").classes('text-[10px] text-slate-500')
                    ui.label(status_text).classes(
                        f"text-[10px] font-black px-2 py-0.5 rounded-full shrink-0 "
                        f"{'bg-emerald-100 text-emerald-800' if is_active else 'bg-slate-200 text-slate-700'}"
                    )

    # Reactive Event Bus Subscription (Real-time scan reflection from librarian station)
    async def handle_realtime_scan(event: Dict[str, Any]):
        act = event.get('action')
        entry = event.get('entry', {})
        msg = event.get('message', 'Attendance scanned.')

        # 1. Acoustic feedback on attendee's device
        if act == 'checkin':
            ui.run_javascript('if(window.playLibreChime) window.playLibreChime("checkin");')
            ui.notify(f"🎉 Check-In Verified! Scanned by Librarian at {entry.get('time_in_str', '')}.", type='positive', duration=5000)
        elif act == 'checkout':
            ui.run_javascript('if(window.playLibreChime) window.playLibreChime("checkout");')
            ui.notify(f"👋 Check-Out Logged! Visit completed: {entry.get('duration_minutes', 1)}m. Goodbye!", type='info', duration=5000)
        elif act == 'cooldown':
            ui.run_javascript('if(window.playLibreChime) window.playLibreChime("cooldown");')
            ui.notify(msg, type='warning', duration=4000)

        # 2. Synchronize database state
        try:
            fresh = await mongo_db.get_user_today_attendance(identifier=student_id, user_id=user_id)
            status_state['data'] = fresh
        except Exception:
            if act == 'checkin':
                status_state['data']['is_inside'] = True
                status_state['data']['active_entry'] = entry
                status_state['data']['latest_entry'] = entry
            elif act == 'checkout':
                status_state['data']['is_inside'] = False
                status_state['data']['active_entry'] = None
                status_state['data']['latest_entry'] = entry

        # 3. Update DOM
        if presence_container:
            presence_container.clear()
            with presence_container:
                render_presence_badge()
        if history_container:
            history_container.clear()
            with history_container:
                render_history_list()

    unsub_id = attendance_event_bus.subscribe(student_id, handle_realtime_scan)
    unsub_uid = attendance_event_bus.subscribe(user_id, handle_realtime_scan) if user_id else (lambda: None)

    with ui.column().classes('w-full items-center justify-center py-2 px-2 sm:px-4'):
        # 1. Main PVC Card Container (Fluid max-w-md, zero pixel overhang)
        with ui.card().classes(
            'w-full max-w-sm sm:max-w-md p-5 sm:p-7 rounded-3xl bg-white border border-slate-200 '
            'shadow-xl relative overflow-hidden text-center gap-0'
        ):
            # University Top Gradient Accent Strip
            with ui.element('div').classes('w-full h-3 bg-gradient-to-r from-indigo-600 via-purple-600 to-indigo-800 absolute top-0 left-0'):
                pass

            # University Header Typography
            with ui.column().classes('w-full items-center gap-0.5 mb-3 mt-2'):
                ui.label('NORTH EASTERN MINDANAO STATE UNIVERSITY').classes('text-[10px] sm:text-xs font-black text-slate-800 tracking-wider')
                ui.label('Tandag Campus • Libre-Library Digital Pass • FM-LIBS-009').classes('text-[9px] sm:text-[10px] text-slate-400 font-bold uppercase tracking-widest')

            # Real-Time Presence Status Badge (Reflects Scan Events Live)
            presence_container = ui.column().classes('w-full gap-0')
            with presence_container:
                render_presence_badge()

            # 1-Tap Intended Visit Purpose Selector (Dynamically encoded into the QR payload)
            selected_purpose = {'val': 'Study / Review'}
            purpose_options = [
                ("Study / Review", "menu_book"),
                ("Research / Thesis", "science"),
                ("Book Borrow / Return", "swap_horiz"),
                ("E-Library / Digital OPAC", "computer"),
                ("Group Discussion", "groups"),
            ]

            ui.label('VISIT PURPOSE (AUTO-EMBEDDED IN QR):').classes(
                'text-[9px] font-black text-slate-400 tracking-wider uppercase mb-1'
            )
            chips_box = ui.element('div').classes('w-full flex flex-wrap items-center justify-center gap-1 mb-2.5')
            qr_img_holder = {}

            def update_selected_purpose(p_name: str):
                selected_purpose['val'] = p_name
                render_pass_purpose_chips()
                dynamic_payload = f"LIBRE-ID:{student_id}|PURPOSE:{p_name}"
                if 'img' in qr_img_holder and qr_img_holder['img']:
                    qr_img_holder['img'].set_source(generate_qr_base64(dynamic_payload))

            def render_pass_purpose_chips():
                chips_box.clear()
                with chips_box:
                    for label, icon_name in purpose_options:
                        is_sel = (selected_purpose['val'] == label)
                        cls = (
                            'bg-indigo-600 text-white font-bold border-indigo-600 shadow-xs'
                            if is_sel else
                            'bg-slate-50 text-slate-600 border-slate-200 hover:bg-slate-100'
                        )
                        ui.button(
                            label,
                            icon=icon_name,
                            on_click=lambda l=label: update_selected_purpose(l)
                        ).props('unelevated no-caps size=xs').classes(
                            f'px-2 py-0.5 rounded-lg text-[10px] border transition-all {cls}'
                        )

            render_pass_purpose_chips()

            # QR Code Display Frame (Reflects Dynamic Payload)
            init_payload = f"LIBRE-ID:{student_id}|PURPOSE:{selected_purpose['val']}"
            with ui.element('div').classes(
                'p-3.5 bg-slate-50 border-2 border-dashed border-indigo-200 rounded-3xl inline-block mx-auto mb-3 shadow-xs '
                'w-44 h-44 sm:w-52 sm:h-52 flex items-center justify-center overflow-hidden'
            ):
                qr_img_holder['img'] = ui.image(generate_qr_base64(init_payload)).classes('w-full h-full object-contain rounded-2xl')

            # Full Name & Role Badges
            ui.label(user_name).classes('text-lg sm:text-2xl font-black text-slate-900 leading-tight mb-2 break-words')

            with ui.row().classes('items-center justify-center gap-1.5 mb-3 flex-wrap'):
                ui.label(norm_role).classes('text-[10px] font-black text-purple-700 bg-purple-50 border border-purple-200 px-2.5 py-0.5 rounded-full')
                ui.label(level_label).classes('text-[10px] font-black text-emerald-700 bg-emerald-50 border border-emerald-200 px-2.5 py-0.5 rounded-full')
                ui.label(norm_prog).classes('text-[10px] font-black text-indigo-700 bg-indigo-50 border border-indigo-200 px-2.5 py-0.5 rounded-full')

            # Department & Residential Address Box
            with ui.column().classes('w-full p-2.5 rounded-2xl bg-slate-50 border border-slate-200/90 gap-1 mb-3 text-left'):
                with ui.row().classes('items-center gap-1.5 text-xs'):
                    ui.icon('domain', size='14px').classes('text-indigo-600 shrink-0')
                    ui.label('Dept:').classes('text-[10px] font-black text-slate-400 uppercase')
                    ui.label(display_dept).classes('text-xs font-bold text-slate-800 truncate flex-1')

                with ui.row().classes('items-center gap-1.5 text-xs'):
                    ui.icon('home', size='14px').classes('text-emerald-600 shrink-0')
                    ui.label('Address:').classes('text-[10px] font-black text-slate-400 uppercase')
                    ui.label(display_address).classes('text-xs font-semibold text-slate-700 truncate flex-1')

            # Prominent Institutional ID Box
            with ui.element('div').classes(
                'w-full p-2.5 rounded-2xl bg-slate-900 border border-slate-800 text-white flex flex-col items-center justify-center gap-0.5 mb-3'
            ):
                ui.label('INSTITUTIONAL ID NUMBER').classes('text-[9px] font-bold text-slate-400 tracking-widest uppercase')
                ui.label(student_id).classes('text-lg sm:text-xl font-black font-mono tracking-wider text-emerald-400')

            ui.label('Hold this QR pass in front of the doorway terminal upon Arrival (Time-In) and Departure (Time-Out).').classes('text-[11px] sm:text-xs text-slate-500 mb-4 px-2 leading-relaxed')

            # Action Buttons Row (Self-Scan disabled: physical gate verification strictly required)
            with ui.row().classes('w-full justify-center gap-2 flex-wrap sm:flex-nowrap pt-2 border-t border-slate-100'):
                def download_qr():
                    payload = f"LIBRE-ID:{student_id}|PURPOSE:{selected_purpose['val']}"
                    raw_bytes = generate_qr_png_bytes(payload)
                    b64 = base64.b64encode(raw_bytes).decode('utf-8')
                    ui.run_javascript(f'''
                        const a = document.createElement('a');
                        a.href = 'data:image/png;base64,{b64}';
                        a.download = 'NEMSU_Library_QR_Pass_{student_id}.png';
                        a.click();
                    ''')
                    ui.notify(f'QR Pass downloaded ({selected_purpose["val"]})!', type='positive')

                ui.button('Download PNG', icon='download', on_click=download_qr)\
                    .props('outline rounded-xl color=indigo size=sm font-bold').classes('flex-1 min-h-[40px] text-xs')

                ui.button('Print Pass', icon='print', on_click=lambda: ui.run_javascript('window.print();'))\
                    .props('flat rounded-xl color=slate size=sm font-bold').classes('flex-1 min-h-[40px] text-xs')

        # 2. Today's Visit Activity Timeline Card
        with ui.card().classes(
            'w-full max-w-sm sm:max-w-md p-4 sm:p-5 rounded-3xl bg-white border border-slate-200 '
            'shadow-md mt-4 text-left gap-2'
        ):
            with ui.row().classes('w-full items-center justify-between pb-2 border-b border-slate-100'):
                with ui.row().classes('items-center gap-2'):
                    ui.icon('history', size='18px').classes('text-indigo-600')
                    ui.label("Today's Attendance Activity").classes('text-xs font-black text-slate-800 uppercase tracking-wider')
                total_dur = status_state['data'].get('total_duration_today_minutes', 0)
                ui.label(f'Total: {total_dur}m').classes('text-[11px] font-bold text-slate-500 bg-slate-100 px-2 py-0.5 rounded-full')

            history_container = ui.column().classes('w-full gap-2 pt-1')
            with history_container:
                render_history_list()

    # Gentle background poll for elapsed minute counter & fallback synchronization
    async def periodic_attendance_sync():
        try:
            fresh = await mongo_db.get_user_today_attendance(identifier=student_id, user_id=user_id)
            prev_status = status_state['data'].get('status')
            status_state['data'] = fresh

            # Update elapsed label if inside
            if fresh.get('is_inside') and fresh.get('active_entry') and 'lbl' in duration_label_holder:
                ts_in = float(fresh['active_entry'].get('timestamp_in') or time.time())
                elapsed = max(1, round((time.time() - ts_in) / 60))
                duration_label_holder['lbl'].set_text(f'Inside for {elapsed}m')

            # Re-render if status changed
            if fresh.get('status') != prev_status:
                if presence_container:
                    presence_container.clear()
                    with presence_container:
                        render_presence_badge()
                if history_container:
                    history_container.clear()
                    with history_container:
                        render_history_list()
        except Exception:
            pass

    poll_timer = ui.timer(5.0, periodic_attendance_sync)

    # Disconnect cleanup to prevent memory leaks
    def cleanup():
        try:
            unsub_id()
            unsub_uid()
            poll_timer.cancel()
        except Exception:
            pass

    try:
        from nicegui import context
        if context.client:
            context.client.on_disconnect(cleanup)
    except Exception:
        pass

