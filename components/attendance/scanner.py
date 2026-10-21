from nicegui import ui
from typing import Dict, Any, List, Callable, Optional


PURPOSE_OPTIONS = [
    ("Study / Review", "menu_book"),
    ("Research / Thesis", "science"),
    ("Book Borrow / Return", "swap_horiz"),
    ("E-Library / Digital OPAC", "computer"),
    ("Group Discussion", "groups"),
]


def render_scanner_station(
    student_id: str,
    active_purpose: Dict[str, str],
    on_scan: Callable[[str, str, str], Any],
    feedback_banner_holder: Dict[str, Any]
) -> None:
    """Renders the entrance scanner card with camera runner, purpose selector, and barcode field."""
    with ui.card().classes('w-full p-4 sm:p-6 rounded-3xl bg-white border border-slate-200 shadow-sm gap-0'):
        with ui.row().classes('items-center justify-between w-full mb-1 flex-wrap gap-2'):
            with ui.row().classes('items-center gap-2'):
                ui.label('ENTRANCE DOOR SCANNER').classes('text-xs font-black text-indigo-600 uppercase tracking-wider')
                ui.label('FM-LIBS-009 Terminal').classes('text-[10px] font-bold text-slate-400 bg-slate-100 px-2 py-0.5 rounded')
            with ui.row().classes('items-center gap-1 text-[11px] font-bold text-emerald-600 bg-emerald-50 px-2.5 py-0.5 rounded-full border border-emerald-200'):
                ui.icon('bolt', size='14px').classes('text-amber-500')
                ui.label('Latency: < 0.2s')

        ui.label('Hold student QR pass or NEMSU ID barcode in front of the camera or USB scanner').classes('text-xs text-slate-500 mb-4')

        # 1. Responsive 1-Tap Purpose of Visit Grid (Zero-overlap guarantee)
        ui.label('PURPOSE OF VISIT (SELECT BEFORE TIME-IN):').classes('text-[11px] font-bold text-slate-500 uppercase tracking-wider mb-2')
        purpose_container = ui.element('div').classes('w-full grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-2 mb-5')

        # Normalize active_purpose value to match without leading emoji if present
        current_val = active_purpose.get('val', 'Study / Review')
        for label, _ in PURPOSE_OPTIONS:
            if label.lower() in current_val.lower():
                active_purpose['val'] = label
                break

        def render_purpose_chips():
            purpose_container.clear()
            with purpose_container:
                for label, icon_name in PURPOSE_OPTIONS:
                    is_active = (active_purpose['val'] == label)
                    chip_cls = (
                        'bg-indigo-600 text-white border-indigo-600 shadow-xs'
                        if is_active
                        else 'bg-slate-50 text-slate-600 border-slate-200 hover:bg-slate-100 hover:text-slate-900'
                    )
                    ui.button(
                        label,
                        icon=icon_name,
                        on_click=lambda l=label: select_purpose(l),
                    ).props('unelevated no-caps').classes(
                        f'w-full px-2.5 py-2 rounded-xl text-xs font-semibold border transition-all duration-150 min-h-[44px] break-words {chip_cls}'
                    )

        kiosk_reset_timer = [None]

        def select_purpose(selected_label: str):
            active_purpose['val'] = selected_label
            render_purpose_chips()
            # Fix 5: Auto-reset Kiosk Purpose chip to default ("Study / Review") 5s after any non-default selection
            if selected_label != "Study / Review":
                if kiosk_reset_timer[0]:
                    try:
                        kiosk_reset_timer[0].cancel()
                    except Exception:
                        pass
                import threading
                def auto_reset():
                    active_purpose['val'] = "Study / Review"
                    try:
                        render_purpose_chips()
                    except Exception:
                        pass
                t = threading.Timer(5.0, auto_reset)
                t.daemon = True
                t.start()
                kiosk_reset_timer[0] = t

        render_purpose_chips()

        # Hidden event bridge element directly wired to on_scan
        scan_carrier = ui.element('div').classes('hidden')

        async def handle_direct_camera_scan(args):
            raw_val = args.get('val') if isinstance(args, dict) else args
            val = str(raw_val or '').strip()
            if val:
                manual_input.value = val
                await on_scan(val, active_purpose['val'], year_select.value)

        scan_carrier.on('scan_received', lambda e: handle_direct_camera_scan(e.args))
        ui.on('libre_qr_scan', lambda e: handle_direct_camera_scan(e.args))

        ui.add_head_html(f'''
        <script>
        window.libreScannerCarrierId = {scan_carrier.id};
        </script>
        ''')

        window_carrier_script = f'''
        window.libreScannerCarrierId = {scan_carrier.id};
        '''
        ui.run_javascript(window_carrier_script)

        # 2. Camera Viewport with html5-qrcode and Web Audio API Synthesis
        scanner_state = {'camera_active': False}
        viewport_box = ui.element('div').classes(
            'relative w-full aspect-video max-h-[360px] rounded-2xl bg-slate-950 border border-slate-800 '
            'overflow-hidden flex flex-col items-center justify-center p-4 text-center shadow-inner'
        )

        ui.add_body_html('''
        <script src="https://unpkg.com/html5-qrcode@2.3.8/html5-qrcode.min.js"></script>
        <script>
        window.libreScannerRunning = false;
        window.html5QrCodeInstance = null;

        // Fix 3: Unified 2.5-second frontend debounce across all scan vectors
        window.libreLastScannedPayload = "";
        window.libreLastScannedTime = 0;
        window.libreCanScan = function(payload) {
            const now = Date.now();
            const clean = String(payload || "").trim().toUpperCase();
            if (!clean) return false;
            if (clean === window.libreLastScannedPayload && (now - window.libreLastScannedTime) < 2500) {
                return false;
            }
            window.libreLastScannedPayload = clean;
            window.libreLastScannedTime = now;
            return true;
        };

        window.playLibreChime = function(actionType) {
            try {
                const ctx = new (window.AudioContext || window.webkitAudioContext)();
                const now = ctx.currentTime;
                const osc = ctx.createOscillator();
                const gain = ctx.createGain();
                gain.connect(ctx.destination);
                osc.connect(gain);

                if (actionType === "checkin") {
                    // Double High Chime
                    osc.frequency.setValueAtTime(880, now);
                    osc.frequency.setValueAtTime(1174.66, now + 0.1);
                    gain.gain.setValueAtTime(0.2, now);
                    gain.gain.exponentialRampToValueAtTime(0.01, now + 0.25);
                    osc.start(now);
                    osc.stop(now + 0.25);
                } else if (actionType === "checkout") {
                    // Warm Departure Chime
                    osc.frequency.setValueAtTime(587.33, now);
                    osc.frequency.setValueAtTime(440, now + 0.12);
                    gain.gain.setValueAtTime(0.2, now);
                    gain.gain.exponentialRampToValueAtTime(0.01, now + 0.3);
                    osc.start(now);
                    osc.stop(now + 0.3);
                } else {
                    // Cooldown / Notice Chime
                    osc.frequency.setValueAtTime(440, now);
                    gain.gain.setValueAtTime(0.15, now);
                    gain.gain.exponentialRampToValueAtTime(0.01, now + 0.18);
                    osc.start(now);
                    osc.stop(now + 0.18);
                }
            } catch(e) {}
        };

        window.startLibreScanner = function() {
            if (window.libreScannerRunning) return;
            try {
                window.html5QrCodeInstance = new Html5Qrcode("reader");

                const qrCodeSuccessCallback = (decodedText, decodedResult) => {
                    // Fix 3: Shared frontend debounce guard
                    if (!window.libreCanScan(decodedText)) {
                        return;
                    }

                    let cleanId = decodedText.trim();
                    if (cleanId.toUpperCase().startsWith("LIBRE-ID:")) {
                        cleanId = cleanId.substring(9).trim();
                    }

                    // Fix 4: Single Primary Reliable Event Dispatch to NiceGUI Backend (fallback on error only)
                    let dispatched = false;
                    try {
                        if (typeof emitEvent === "function") {
                            emitEvent("libre_qr_scan", { val: cleanId });
                            dispatched = true;
                        }
                    } catch(err) {
                        dispatched = false;
                    }

                    if (!dispatched) {
                        try {
                            const targetId = window.libreScannerCarrierId;
                            if (targetId !== undefined && targetId !== null) {
                                if (window.socket && typeof window.socket.emit === "function") {
                                    window.socket.emit("event", {
                                        id: targetId,
                                        name: "scan_received",
                                        args: [{ val: cleanId }]
                                    });
                                } else if (typeof getElement === "function") {
                                    const carrierEl = getElement(targetId);
                                    if (carrierEl && carrierEl.$emit) {
                                        carrierEl.$emit("scan_received", { val: cleanId });
                                    }
                                }
                            }
                        } catch(sockErr) {
                            console.warn("Scan socket fallback dispatch notice:", sockErr);
                        }
                    }

                    // 2. Visual Mirror on Manual Input Field with reactive events
                    const inputEl = document.querySelector('#attendance-manual-input input') || document.querySelector('#attendance-manual-input');
                    if (inputEl) {
                        inputEl.value = cleanId;
                        inputEl.dispatchEvent(new Event('input', { bubbles: true }));
                        inputEl.dispatchEvent(new Event('change', { bubbles: true }));
                    }
                };
                const config = { fps: 15, qrbox: { width: 220, height: 220 } };
                window.html5QrCodeInstance.start({ facingMode: "environment" }, config, qrCodeSuccessCallback)
                    .then(() => { window.libreScannerRunning = true; })
                    .catch(err => {
                        console.warn("Camera start notice:", err);
                        const r = document.getElementById("reader");
                        if (r) r.innerHTML = '<div class="text-slate-300 text-xs p-4 text-center">Camera stream unavailable or permission denied. Please use the barcode input below.</div>';
                    });
            } catch(e) {
                console.error("Scanner init error:", e);
            }
        };

        window.stopLibreScanner = function() {
            if (window.html5QrCodeInstance && window.libreScannerRunning) {
                window.html5QrCodeInstance.stop().then(() => {
                    window.libreScannerRunning = false;
                }).catch(err => console.warn("Stop scanner error:", err));
            }
        };
        </script>
        ''')

        def render_camera_viewport():
            viewport_box.clear()
            with viewport_box:
                # Top-right Latency Badge inside viewport
                with ui.row().classes(
                    'absolute top-3 right-3 z-10 items-center gap-1.5 px-3 py-1 rounded-full '
                    'bg-slate-800/90 border border-slate-700 text-emerald-400 text-xs font-semibold backdrop-blur-xs'
                ):
                    ui.icon('bolt', size='14px').classes('text-amber-400')
                    ui.label('Response Time: < 0.2s')

                if not scanner_state['camera_active']:
                    with ui.element('div').classes(
                        'w-16 h-16 rounded-2xl bg-indigo-500/10 border border-indigo-500/20 '
                        'text-indigo-400 flex items-center justify-center mb-3'
                    ):
                        ui.icon('qr_code_scanner', size='36px')
                    ui.label('Camera Scanner on Standby').classes('text-base font-bold text-white')
                    ui.label(
                        'Hold student QR pass or NEMSU ID barcode in front of the lens once activated.'
                    ).classes('text-xs text-slate-400 max-w-sm mt-1 mb-5 leading-normal')
                    ui.button(
                        'ACTIVATE CAMERA SCANNER',
                        icon='videocam',
                        on_click=toggle_camera,
                    ).props('unelevated no-caps').classes(
                        'px-5 py-2.5 rounded-xl text-xs font-bold bg-indigo-600 hover:bg-indigo-500 '
                        'text-white shadow-md transition-all hover:scale-105 min-h-[44px]'
                    )
                else:
                    ui.html('<div id="reader" style="width: 100%; max-width: 480px; min-height: 240px; margin: auto;"></div>', sanitize=False, tag='div').classes('w-full')
                    ui.run_javascript(f'window.libreScannerCarrierId = {scan_carrier.id}; setTimeout(function(){{ window.startLibreScanner(); }}, 150);')
                    with ui.row().classes('absolute bottom-3 left-0 right-0 justify-center z-10'):
                        ui.button(
                            'STOP CAMERA SCANNER',
                            icon='videocam_off',
                            on_click=toggle_camera,
                        ).props('unelevated no-caps').classes(
                            'px-4 py-2 rounded-lg text-xs font-bold bg-rose-600 hover:bg-rose-500 text-white shadow-md'
                        )

        def toggle_camera():
            if scanner_state['camera_active']:
                ui.run_javascript('window.stopLibreScanner();')
                scanner_state['camera_active'] = False
            else:
                scanner_state['camera_active'] = True
            render_camera_viewport()

        render_camera_viewport()

        ui.separator().classes('my-5')

        # 3. Live Status Confirmation Banner Card Holder
        feedback_banner_holder['banner'] = ui.element('div').classes('w-full')

        # 4. Rapid ID / Barcode Input Bar (Dual-Mode USB Barcode Gun Support)
        with ui.row().classes('w-full items-center justify-between mb-1.5 flex-wrap gap-1'):
            ui.label('RAPID ID / BARCODE GUN INPUT:').classes('text-xs font-bold text-slate-500 uppercase tracking-wider')
            with ui.row().classes(
                'items-center gap-1 cursor-pointer px-2 py-0.5 rounded-md bg-indigo-50 border border-indigo-100 hover:bg-indigo-100 transition-colors'
            ).on('click', lambda: set_self_input()):
                ui.icon('flash_on', size='14px').classes('text-amber-500')
                ui.label(f'Fill My ID: {student_id}').classes('text-[11px] font-bold text-indigo-700')

        with ui.row().classes('w-full items-center gap-2.5 flex-wrap sm:flex-nowrap'):
            manual_input = ui.input(placeholder='Scan QR/barcode gun or enter ID/username (e.g. 23-00128, 2024-9BFCB)...') \
                .classes('flex-1 text-sm min-h-[44px]').props('id="attendance-manual-input" rounded-xl outlined dense autofocus')
            year_select = ui.select(["1st Year", "2nd Year", "3rd Year", "4th Year", "Graduate"], value="1st Year") \
                .classes('w-full sm:w-32 sm:shrink-0 text-sm').props('rounded-xl outlined dense options-dense')

            def set_self_input():
                manual_input.value = student_id

            async def do_submit():
                val = (manual_input.value or '').strip()
                if not val:
                    ui.notify('Please enter or scan a Student or Faculty ID', type='warning')
                    return
                await on_scan(val, active_purpose['val'], year_select.value)
                manual_input.value = ""

            manual_input.on('keydown.enter', do_submit)
            ui.button('Record Scan', icon='how_to_reg', on_click=do_submit) \
                .props('id="attendance-submit-btn" unelevated rounded-xl color=slate-900 text-color=white size=md font-bold') \
                .classes('w-full sm:w-auto min-h-[44px] px-6 shrink-0 shadow-sm hover:bg-slate-800 active:scale-95 transition-all text-xs')


def render_live_doorway_feed(container: ui.column, recent_logs: List[Dict[str, Any]]) -> None:
    """Renders the real-time entrance stream of visitors."""
    container.clear()
    with container:
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
                            ui.label(f"ID: {r.get('institutional_id') or r.get('student_id')}").classes('text-[10px] text-slate-400 font-mono')
                        ui.label(r.get('purpose', 'Study')).classes('text-[10px] text-slate-500 italic truncate')

                with ui.column().classes('items-end shrink-0 gap-1'):
                    with ui.element('div').classes(f'px-2 py-0.5 rounded-full text-[10px] font-black uppercase border {status_bg}'):
                        ui.label(r.get('status'))
                    ui.label(r.get('time_in_str', '')).classes('text-[10px] font-mono text-slate-400')


def render_attendee_dossier_card(
    entry: Dict[str, Any],
    action: str = "checkin",
    duration_minutes: int = 0,
    on_dismiss: Optional[Callable[[], Any]] = None
) -> None:
    """
    Renders a prominent, zero-overlap Live Attendee Verification Dossier Card:
    - Full Name, Photo / Avatar, Institutional ID Number
    - Role badge (Student, Faculty, Librarian, Admin)
    - Department & Program
    - Year Level (Students) or Staff Designation (Faculty / Staff)
    - Residential / Campus Address
    - Active Borrowing & Overdue Standing Badge
    - Timestamp & Check-in/Check-out Action Pill
    """
    role = str(entry.get('role', 'Student')).strip().capitalize()
    name = entry.get('name') or "Visitor"
    inst_id = entry.get('institutional_id') or entry.get('student_id') or "Unknown ID"
    dept = entry.get('department') or entry.get('program') or "General Education"
    prog = entry.get('program') or ""
    year_level = entry.get('year_level') or "1st Year"
    address = entry.get('address') or "NEMSU Tandag Campus"
    avatar_url = entry.get('avatar_url') or ""
    active_loans = int(entry.get('active_loans_count') or 0)
    overdue_loans = int(entry.get('overdue_loans_count') or 0)
    purpose = entry.get('purpose') or "Study / Review"
    time_str = entry.get('time_in_str') or ""

    # Role-based color palette and labels
    if role.lower() == 'faculty':
        role_badge_cls = 'bg-indigo-100 text-indigo-800 border-indigo-200'
        avatar_bg = 'bg-indigo-600 text-white'
        designation_label = "Designation / Rank"
        designation_val = "Faculty Member"
    elif role.lower() in ('librarian', 'co-librarian'):
        role_badge_cls = 'bg-purple-100 text-purple-800 border-purple-200'
        avatar_bg = 'bg-purple-600 text-white'
        designation_label = "Designation"
        designation_val = "Library Staff"
    elif role.lower() == 'admin':
        role_badge_cls = 'bg-amber-100 text-amber-800 border-amber-200'
        avatar_bg = 'bg-amber-600 text-white'
        designation_label = "Designation"
        designation_val = "System Administrator"
    else:
        role_badge_cls = 'bg-emerald-100 text-emerald-800 border-emerald-200'
        avatar_bg = 'bg-emerald-600 text-white'
        designation_label = "Year Level"
        designation_val = year_level

    # Action Banner Styling
    if action == 'checkin':
        border_cls = 'border-emerald-300'
        accent_bar = 'from-emerald-500 to-teal-600'
        status_badge_cls = 'bg-emerald-600 text-white'
        status_label = f"✓ CHECKED IN • {time_str}"
    elif action == 'checkout':
        border_cls = 'border-blue-300'
        accent_bar = 'from-blue-500 to-indigo-600'
        status_badge_cls = 'bg-blue-600 text-white'
        status_label = f"👋 CHECKED OUT • Stay: {duration_minutes} min(s)"
    else:
        border_cls = 'border-amber-300'
        accent_bar = 'from-amber-500 to-orange-500'
        status_badge_cls = 'bg-amber-600 text-white'
        status_label = "⏳ ACTIVE SESSION • Cooldown"

    with ui.card().classes(
        f'w-full p-0 rounded-3xl bg-white border-2 {border_cls} shadow-xl relative overflow-hidden mb-4 transition-all animate-fade-in'
    ):
        # Top gradient accent bar
        ui.element('div').classes(f'w-full h-2.5 bg-gradient-to-r {accent_bar}')

        with ui.column().classes('p-4 sm:p-5 w-full gap-3.5'):
            # Header Row: Avatar, Full Name, ID, Role Badge, and Dismiss/Action Status
            with ui.row().classes('w-full items-start justify-between gap-3 flex-wrap sm:flex-nowrap'):
                with ui.row().classes('items-center gap-3.5 min-w-0 flex-1'):
                    # Avatar or Initials Badge
                    if avatar_url:
                        ui.image(avatar_url).classes('w-14 h-14 sm:w-16 sm:h-16 rounded-2xl object-cover border-2 border-indigo-200 shadow-sm shrink-0')
                    else:
                        initials = "".join([part[0] for part in name.split()[:2]]).upper() or "ID"
                        with ui.element('div').classes(
                            f'w-14 h-14 sm:w-16 sm:h-16 rounded-2xl {avatar_bg} flex items-center justify-center font-black text-lg sm:text-xl shrink-0 shadow-sm'
                        ):
                            ui.label(initials)

                    # Name & Badges
                    with ui.column().classes('gap-1 min-w-0 flex-1'):
                        with ui.row().classes('items-center gap-2 flex-wrap'):
                            ui.label(name).classes('text-lg sm:text-xl font-black text-slate-900 leading-tight break-words')
                            with ui.element('div').classes(f'px-2.5 py-0.5 rounded-full text-[10px] font-black uppercase border {role_badge_cls}'):
                                ui.label(role)

                        with ui.row().classes('items-center gap-2 flex-wrap text-xs'):
                            # Institutional ID Box
                            with ui.row().classes('items-center gap-1 bg-slate-900 text-emerald-400 px-2.5 py-0.5 rounded-lg font-mono font-black text-xs shadow-xs'):
                                ui.icon('badge', size='14px')
                                ui.label(inst_id)

                            ui.label(f"• Purpose: {purpose}").classes('text-slate-500 font-medium')

                # Right side: Status Badge
                with ui.column().classes('items-end shrink-0 gap-1'):
                    with ui.element('div').classes(f'px-3 py-1 rounded-xl text-xs font-black uppercase shadow-xs {status_badge_cls}'):
                        ui.label(status_label)
                    if on_dismiss:
                        ui.button(icon='close', on_click=on_dismiss).props('flat dense round size=xs color=grey-6')

            ui.separator().classes('my-0.5 opacity-60')

            # Grid of 3 Key ID Info Panels
            with ui.grid().classes('w-full grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-2.5'):
                # 1. Department / Program
                with ui.element('div').classes('p-2.5 rounded-2xl bg-slate-50 border border-slate-200/80 flex flex-col gap-0.5'):
                    with ui.row().classes('items-center gap-1 text-slate-400 text-[10px] font-black uppercase tracking-wider'):
                        ui.icon('domain', size='14px').classes('text-indigo-500')
                        ui.label('Department / Program')
                    disp_dept = dept if dept == prog or not prog else f"{dept} ({prog})"
                    ui.label(disp_dept).classes('text-xs font-bold text-slate-800 break-words')

                # 2. Year Level or Staff Designation
                with ui.element('div').classes('p-2.5 rounded-2xl bg-slate-50 border border-slate-200/80 flex flex-col gap-0.5'):
                    with ui.row().classes('items-center gap-1 text-slate-400 text-[10px] font-black uppercase tracking-wider'):
                        ui.icon('school', size='14px').classes('text-purple-500')
                        ui.label(designation_label)
                    ui.label(designation_val).classes('text-xs font-bold text-slate-800 break-words')

                # 3. Residential / Campus Address
                with ui.element('div').classes('p-2.5 rounded-2xl bg-slate-50 border border-slate-200/80 flex flex-col gap-0.5 sm:col-span-2 md:col-span-1'):
                    with ui.row().classes('items-center gap-1 text-slate-400 text-[10px] font-black uppercase tracking-wider'):
                        ui.icon('home', size='14px').classes('text-emerald-500')
                        ui.label('Address')
                    ui.label(address).classes('text-xs font-bold text-slate-800 break-words')

            # Circulation Standing Banner
            if overdue_loans > 0:
                with ui.card().classes('w-full p-2.5 rounded-2xl bg-rose-50 border border-rose-200 text-rose-900 flex flex-row items-center justify-between gap-2 shadow-2xs'):
                    with ui.row().classes('items-center gap-2 min-w-0'):
                        ui.icon('warning', size='20px').classes('text-rose-600 shrink-0')
                        with ui.column().classes('gap-0'):
                            ui.label('OVERDUE BOOKS DETECTED').classes('text-xs font-black text-rose-700 tracking-wider uppercase')
                            ui.label(f"This patron currently has {overdue_loans} overdue library book(s). Please advise return or renewal.").classes('text-[11px] text-rose-600')
                    ui.badge(f"{overdue_loans} Overdue", color='red').props('rounded font-bold')
            elif active_loans > 0:
                with ui.card().classes('w-full p-2.5 rounded-2xl bg-blue-50/80 border border-blue-200 text-blue-900 flex flex-row items-center justify-between gap-2 shadow-2xs'):
                    with ui.row().classes('items-center gap-2 min-w-0'):
                        ui.icon('menu_book', size='18px').classes('text-blue-600 shrink-0')
                        with ui.column().classes('gap-0'):
                            ui.label('ACTIVE LIBRARY LOANS').classes('text-xs font-black text-blue-700 tracking-wider uppercase')
                            ui.label(f"Currently borrowing {active_loans} book(s) in good standing.").classes('text-[11px] text-blue-600')
                    ui.badge(f"{active_loans} Borrowed", color='blue').props('rounded font-bold')
            else:
                with ui.card().classes('w-full p-2 rounded-2xl bg-emerald-50/60 border border-emerald-100 text-emerald-900 flex flex-row items-center justify-between gap-2 shadow-2xs'):
                    with ui.row().classes('items-center gap-2 min-w-0'):
                        ui.icon('check_circle', size='16px').classes('text-emerald-600 shrink-0')
                        ui.label('Library Standing: Good Standing • 0 Overdue Items').classes('text-[11px] font-bold text-emerald-700')
                    ui.badge("Clear", color='positive').props('rounded font-bold text-[10px]')
