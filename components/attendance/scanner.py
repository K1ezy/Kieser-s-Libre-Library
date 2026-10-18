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
    with ui.card().classes('w-full p-5 sm:p-6 rounded-3xl bg-white border border-slate-200 shadow-sm gap-0'):
        with ui.row().classes('items-center justify-between w-full mb-1'):
            ui.label('ENTRANCE DOOR SCANNER').classes('text-xs font-black text-indigo-600 uppercase tracking-wider')
            with ui.row().classes('items-center gap-1 text-[11px] font-bold text-emerald-600 bg-emerald-50 px-2 py-0.5 rounded-full border border-emerald-200'):
                ui.icon('bolt', size='14px').classes('text-amber-500')
                ui.label('Latency: < 0.2s')

        ui.label('Hold student QR pass or NEMSU ID barcode in front of the camera').classes('text-xs text-slate-500 mb-4')

        # 1. Interactive Purpose of Visit Pill Selector (Hick's & Fitts's Law)
        ui.label('PURPOSE OF VISIT:').classes('text-xs font-bold text-slate-500 uppercase tracking-wider mb-2')
        purpose_row = ui.row().classes('w-full flex-wrap gap-2 mb-5')

        # Normalize active_purpose value to match without leading emoji if present
        current_val = active_purpose.get('val', 'Study / Review')
        for label, _ in PURPOSE_OPTIONS:
            if label.lower() in current_val.lower():
                active_purpose['val'] = label
                break

        def render_purpose_chips():
            purpose_row.clear()
            with purpose_row:
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
                        f'px-3.5 py-2 rounded-lg text-xs font-semibold border transition-all duration-150 {chip_cls}'
                    )

        def select_purpose(selected_label: str):
            active_purpose['val'] = selected_label
            render_purpose_chips()

        render_purpose_chips()

        # 2. Camera Viewport with Intentional Standby State (Peak-End & Fitts's Law)
        scanner_state = {'camera_active': False}
        viewport_box = ui.element('div').classes(
            'relative w-full aspect-video rounded-2xl bg-slate-900 border border-slate-800 '
            'overflow-hidden flex flex-col items-center justify-center p-6 text-center shadow-inner'
        )

        ui.add_body_html('''
        <script src="https://unpkg.com/html5-qrcode@2.3.8/html5-qrcode.min.js"></script>
        <script>
        window.libreScannerRunning = false;
        window.html5QrCodeInstance = null;

        window.startLibreScanner = function() {
            if (window.libreScannerRunning) return;
            try {
                window.html5QrCodeInstance = new Html5Qrcode("reader");
                const qrCodeSuccessCallback = (decodedText, decodedResult) => {
                    const inputEl = document.querySelector('#attendance-manual-input input');
                    if (inputEl) {
                        inputEl.value = decodedText;
                        inputEl.dispatchEvent(new Event('input', { bubbles: true }));
                        const submitBtn = document.querySelector('#attendance-submit-btn');
                        if (submitBtn) submitBtn.click();
                    }
                };
                const config = { fps: 12, qrbox: { width: 240, height: 240 } };
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
                    ui.run_javascript('setTimeout(function(){ window.startLibreScanner(); }, 150);')
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

        # 3. Live Status Confirmation Banner Card
        feedback_banner_holder['banner'] = ui.element('div').classes('w-full')

        # 4. Rapid ID / Barcode Input Bar
        with ui.row().classes('w-full items-center justify-between mb-1.5 flex-wrap gap-1'):
            ui.label('RAPID ID / BARCODE INPUT:').classes('text-xs font-bold text-slate-500 uppercase tracking-wider')
            with ui.row().classes(
                'items-center gap-1 cursor-pointer px-2 py-0.5 rounded-md bg-indigo-50 border border-indigo-100 hover:bg-indigo-100 transition-colors'
            ).on('click', lambda: set_self_input()):
                ui.icon('flash_on', size='14px').classes('text-amber-500')
                ui.label(f'Fill My ID: {student_id}').classes('text-[11px] font-bold text-indigo-700')

        with ui.row().classes('w-full items-center gap-2.5 flex-wrap sm:flex-nowrap'):
            manual_input = ui.input(placeholder='Scan barcode gun or type Student ID (e.g. 2024-001)...') \
                .classes('flex-1 text-sm min-h-[44px]').props('id="attendance-manual-input" rounded-xl outlined dense autofocus')
            year_select = ui.select(["1st Year", "2nd Year", "3rd Year", "4th Year", "Graduate"], value="1st Year") \
                .classes('w-full sm:w-32 sm:shrink-0 text-sm').props('rounded-xl outlined dense options-dense')

            def set_self_input():
                manual_input.value = student_id

            async def do_submit():
                val = manual_input.value.strip()
                if not val:
                    ui.notify('Please enter or scan a Student ID', type='warning')
                    return
                await on_scan(val, active_purpose['val'], year_select.value)
                manual_input.value = ""

            manual_input.on('keydown.enter', do_submit)
            ui.button('Check In / Out', icon='login', on_click=do_submit) \
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
                            ui.label(f"ID: {r.get('student_id')}").classes('text-[10px] text-slate-400 font-mono')
                        ui.label(r.get('purpose', 'Study')).classes('text-[10px] text-slate-500 italic truncate')

                with ui.column().classes('items-end shrink-0 gap-1'):
                    with ui.element('div').classes(f'px-2 py-0.5 rounded-full text-[10px] font-black uppercase border {status_bg}'):
                        ui.label(r.get('status'))
                    ui.label(r.get('time_in_str', '')).classes('text-[10px] font-mono text-slate-400')

