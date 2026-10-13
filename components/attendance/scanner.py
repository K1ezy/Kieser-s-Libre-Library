from nicegui import ui
from typing import Dict, Any, List, Callable, Optional


PURPOSE_OPTIONS = [
    "📚 Study / Review",
    "🔬 Research / Thesis",
    "📖 Book Borrow / Return",
    "💻 E-Library / Digital OPAC",
    "👥 Group Discussion"
]


def render_scanner_station(
    student_id: str,
    active_purpose: Dict[str, str],
    on_scan: Callable[[str, str, str], Any],
    feedback_banner_holder: Dict[str, Any]
) -> None:
    """Renders the entrance scanner card with camera runner, purpose selector, and barcode field."""
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
            ui.html('<div id="reader" style="width: 100%; max-width: 480px; min-height: 240px; margin: auto;"></div>', sanitize=False, tag='div').classes('w-full')

        with ui.row().classes('w-full justify-between items-center gap-2 mt-3 flex-wrap'):
            ui.button('Activate Camera Scanner', icon='videocam', on_click=lambda: ui.run_javascript('window.startLibreScanner();')) \
                .props('unelevated rounded-xl color=indigo size=sm font-bold min-height=40px')
            ui.label('⚡ Response Time: < 0.2s').classes('text-xs font-mono text-emerald-600 font-bold')

        ui.separator().classes('my-4')

        # Live Status Confirmation Banner Card
        feedback_banner_holder['banner'] = ui.element('div').classes('w-full')

        # Manual ID Input / Barcode Scanner Gun Field
        with ui.row().classes('w-full items-center justify-between mb-1 flex-wrap gap-1'):
            ui.label('Rapid ID / Barcode Input:').classes('text-xs font-bold text-slate-500 uppercase tracking-wider')
            with ui.row().classes('items-center gap-1 cursor-pointer hover:opacity-80').on('click', lambda: set_self_input()):
                ui.icon('flash_on', size='14px').classes('text-amber-500')
                ui.label(f'Fill My ID: {student_id}').classes('text-[11px] font-bold text-indigo-600')

        with ui.row().classes('w-full items-center gap-2 flex-wrap sm:flex-nowrap'):
            manual_input = ui.input(placeholder='Scan barcode gun or type Student ID (e.g. 2024-001)...') \
                .classes('flex-1 text-base min-h-[44px]').props('id="attendance-manual-input" rounded outlined dense autofocus')
            year_select = ui.select(["1st Year", "2nd Year", "3rd Year", "4th Year", "Graduate"], value="1st Year") \
                .classes('w-full sm:w-28 sm:shrink-0').props('rounded outlined dense options-dense')

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
                .classes('w-full sm:w-auto min-h-[44px] px-5 shrink-0 shadow-sm hover:brightness-110 active:scale-95 transition-all')


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
