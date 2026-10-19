import io
import base64
from typing import Callable, Any, Optional
from nicegui import ui


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
    return bool(re.match(r"^\d{2}-\d{5}$", str(val).strip()))


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
    on_self_checkin: Optional[Callable[[], Any]] = None,
) -> None:
    """
    Renders a responsive, mobile-safe Digital PVC ID & Library QR Pass.
    Guarantees zero overlap with fluid flexbox and bounded max-width.
    """
    qr_data_url = generate_qr_base64(student_id)
    norm_role = str(user_role or 'student').upper()
    norm_prog = str(user_program or 'GENERAL').upper()

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
            with ui.column().classes('w-full items-center gap-0.5 mb-4 mt-2'):
                ui.label('NORTH EASTERN MINDANAO STATE UNIVERSITY').classes('text-[10px] sm:text-xs font-black text-slate-800 tracking-wider')
                ui.label('Tandag Campus • Libre-Library Digital Pass • FM-LIBS-009').classes('text-[9px] sm:text-[10px] text-slate-400 font-bold uppercase tracking-widest')

            # QR Code Display Frame
            with ui.element('div').classes(
                'p-3.5 bg-slate-50 border-2 border-dashed border-indigo-200 rounded-3xl inline-block mx-auto mb-4 shadow-xs '
                'w-48 h-48 sm:w-56 sm:h-56 flex items-center justify-center overflow-hidden'
            ):
                ui.image(qr_data_url).classes('w-full h-full object-contain rounded-2xl')

            # Student Details & Metadata
            ui.label(user_name).classes('text-lg sm:text-2xl font-black text-slate-900 leading-tight mb-2 break-words')

            with ui.row().classes('items-center justify-center gap-1.5 mb-3 flex-wrap'):
                ui.label(norm_role).classes('text-[10px] font-black text-purple-700 bg-purple-50 border border-purple-200 px-2.5 py-0.5 rounded-full')
                ui.label(norm_prog).classes('text-[10px] font-black text-indigo-700 bg-indigo-50 border border-indigo-200 px-2.5 py-0.5 rounded-full')

            # Prominent Institutional ID Box
            with ui.element('div').classes(
                'w-full p-2.5 rounded-2xl bg-slate-900 border border-slate-800 text-white flex flex-col items-center justify-center gap-0.5 mb-3'
            ):
                ui.label('INSTITUTIONAL ID').classes('text-[9px] font-bold text-slate-400 tracking-widest uppercase')
                ui.label(student_id).classes('text-lg sm:text-xl font-black font-mono tracking-wider text-emerald-400')

            ui.label('Hold this QR pass in front of the doorway terminal upon Arrival (Time-In) and Departure (Time-Out).').classes('text-[11px] sm:text-xs text-slate-500 mb-5 px-2 leading-relaxed')

            # Action Buttons Row
            with ui.row().classes('w-full justify-center gap-2 flex-wrap sm:flex-nowrap pt-2 border-t border-slate-100'):
                def download_qr():
                    raw_bytes = generate_qr_png_bytes(student_id)
                    b64 = base64.b64encode(raw_bytes).decode('utf-8')
                    ui.run_javascript(f'''
                        const a = document.createElement('a');
                        a.href = 'data:image/png;base64,{b64}';
                        a.download = 'NEMSU_Library_QR_Pass_{student_id}.png';
                        a.click();
                    ''')
                    ui.notify('QR Pass downloaded!', type='positive')

                ui.button('Download PNG', icon='download', on_click=download_qr)\
                    .props('outline rounded-xl color=indigo size=sm font-bold').classes('flex-1 min-h-[40px] text-xs')

                ui.button('Print Pass', icon='print', on_click=lambda: ui.run_javascript('window.print();'))\
                    .props('flat rounded-xl color=slate size=sm font-bold').classes('min-h-[40px] text-xs')

                if on_self_checkin:
                    ui.button('Self Scan', icon='how_to_reg', on_click=on_self_checkin)\
                        .props('unelevated rounded-xl color=indigo size=sm font-bold shadow-xs').classes('flex-1 min-h-[40px] text-xs')
