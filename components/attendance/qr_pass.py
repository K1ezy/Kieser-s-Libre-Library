import io
import base64
from typing import Callable, Any
from nicegui import ui


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
        return f"https://api.qrserver.com/v1/create-qr-code/?size=250x250&data={clean_text}"


def render_digital_pass_card(
    user_name: str,
    student_id: str,
    user_program: str,
    user_role: str,
    on_self_checkin: Callable[[], Any]
) -> None:
    """Renders the official digital ID card with contactless QR pass."""
    with ui.column().classes('w-full items-center justify-center py-4'):
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
                ui.label(user_role.upper()).classes('text-[10px] font-black text-purple-700 bg-purple-50 px-2.5 py-0.5 rounded-full')

            ui.label('Scan this QR code at the library entrance door scanner for automatic contactless check-in/out.').classes('text-xs text-slate-500 mb-4 px-4 leading-relaxed')

            with ui.row().classes('w-full justify-center gap-3'):
                ui.button('Self Check-In / Out Now', icon='how_to_reg', on_click=on_self_checkin) \
                    .props('unelevated rounded-xl color=indigo size=sm font-bold shadow-md')
