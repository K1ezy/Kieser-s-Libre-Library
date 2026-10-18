from typing import Dict, Any, Optional
from nicegui import ui
from components.attendance.qr_pass import generate_qr_base64


ROLE_CONFIGS = {
    "STUDENT": {
        "title": "STUDENT",
        "badge_color": "emerald",
        "badge_bg": "bg-emerald-50 text-emerald-700 border-emerald-200",
        "card_gradient": "from-emerald-700 via-teal-800 to-slate-900",
        "accent_hex": "#10b981",
        "icon": "school",
        "id_name": "Student ID Number",
        "unit_name": "Academic Program",
    },
    "FACULTY": {
        "title": "FACULTY",
        "badge_color": "blue",
        "badge_bg": "bg-blue-50 text-blue-700 border-blue-200",
        "card_gradient": "from-blue-700 via-indigo-800 to-slate-900",
        "accent_hex": "#3b82f6",
        "icon": "cast_for_education",
        "id_name": "Faculty / Employee ID",
        "unit_name": "Department",
    },
    "LIBRARIAN": {
        "title": "LIBRARIAN",
        "badge_color": "purple",
        "badge_bg": "bg-purple-50 text-purple-700 border-purple-200",
        "card_gradient": "from-purple-700 via-indigo-900 to-slate-900",
        "accent_hex": "#a855f7",
        "icon": "local_library",
        "id_name": "Staff ID Number",
        "unit_name": "Library Branch / Section",
    },
    "ADMIN": {
        "title": "ADMINISTRATOR",
        "badge_color": "amber",
        "badge_bg": "bg-amber-50 text-amber-800 border-amber-200",
        "card_gradient": "from-amber-600 via-slate-800 to-slate-950",
        "accent_hex": "#f59e0b",
        "icon": "admin_panel_settings",
        "id_name": "Admin ID / Employee Code",
        "unit_name": "Governance Unit",
    },
}


def get_user_initials(name: str = "", username: str = "") -> str:
    """Generates two-letter uppercase fallback initials."""
    raw = (name or username or "U").strip()
    parts = [p for p in raw.split() if p]
    if len(parts) >= 2:
        return (parts[0][0] + parts[-1][0]).upper()
    elif parts and len(parts[0]) >= 2:
        return parts[0][:2].upper()
    elif parts:
        return parts[0][0].upper()
    return "LU"


def render_pvc_id_card(
    user_name: str,
    norm_role: str,
    role_cfg: Dict[str, Any],
    inst_id: str,
    program: str,
    year_level: str,
    dept: str,
    branch: str,
    admin_code: str,
    avatar_url: Optional[str],
    initials: str
) -> None:
    """Renders official institutional digital PVC ID badge with QR attendance pass."""
    qr_code_b64 = generate_qr_base64(inst_id)

    with ui.element('div').classes(
        'w-full p-4 sm:p-6 rounded-2xl sm:rounded-3xl bg-gradient-to-br from-slate-900 via-indigo-950 to-slate-900 '
        'border border-indigo-500/30 text-white shadow-xl relative overflow-hidden mb-5'
    ):
        with ui.element('div').classes('absolute right-[-20px] bottom-[-20px] opacity-10 pointer-events-none'):
            ui.icon('local_library', size='12rem')

        with ui.row().classes('w-full justify-between items-center mb-4 pb-3 border-b border-white/10 gap-2 flex-wrap'):
            with ui.row().classes('items-center gap-2.5'):
                with ui.element('div').classes('p-1.5 rounded-lg bg-white/10 border border-white/20 text-white'):
                    ui.icon('local_library', size='18px')
                with ui.column().classes('gap-0'):
                    ui.label('LIBRE ACADEMIC ECOSYSTEM').classes('text-[10px] font-black tracking-widest text-indigo-300 uppercase')
                    ui.label('OFFICIAL INSTITUTIONAL SMART PASS').classes('text-xs font-bold text-white')

            with ui.row().classes('items-center gap-2'):
                with ui.row().classes('items-center gap-1.5 px-2.5 py-1 rounded-full bg-emerald-500/20 border border-emerald-400/30 text-emerald-300 text-[10px] font-black uppercase tracking-wider'):
                    ui.element('div').classes('w-2 h-2 rounded-full bg-emerald-400 animate-pulse')
                    ui.label('ACTIVE • VERIFIED')
                ui.icon('contactless', size='20px').classes('text-indigo-300')

        with ui.row().classes('w-full items-center justify-between gap-4 flex-col md:flex-row'):
            with ui.row().classes('items-center gap-4 flex-1 min-w-0 w-full md:w-auto'):
                with ui.element('div').classes('w-16 h-16 sm:w-20 sm:h-20 rounded-2xl border-2 border-indigo-400/50 overflow-hidden bg-slate-800 shrink-0 shadow-md'):
                    if avatar_url:
                        ui.image(avatar_url).classes('w-full h-full object-cover')
                    else:
                        with ui.element('div').classes('w-full h-full flex items-center justify-center bg-indigo-700 text-white font-black text-xl'):
                            ui.label(initials)

                with ui.column().classes('gap-1 min-w-0 flex-1'):
                    ui.label(user_name).classes('text-lg sm:text-xl font-black text-white truncate w-full')
                    with ui.row().classes('items-center gap-2 flex-wrap'):
                        with ui.element('div').classes(f'text-[9px] font-black px-2 py-0.5 rounded-md uppercase tracking-wider {role_cfg["badge_bg"]}'):
                            ui.label(norm_role)
                        ui.label(f"ID: {inst_id}").classes('text-xs font-mono font-bold text-indigo-200 bg-white/10 px-2 py-0.5 rounded-md')

                    if norm_role == 'STUDENT':
                        ui.label(f"Program: {program} ({year_level})").classes('text-xs text-slate-300 font-medium')
                    elif norm_role == 'FACULTY':
                        ui.label(f"Department: {dept}").classes('text-xs text-slate-300 font-medium')
                    elif norm_role == 'LIBRARIAN':
                        ui.label(f"Branch: {branch}").classes('text-xs text-slate-300 font-medium')
                    elif norm_role == 'ADMIN':
                        ui.label(f"Access Code: {admin_code}").classes('text-xs text-slate-300 font-medium')

            with ui.row().classes('items-center gap-3 shrink-0 self-center md:self-auto'):
                with ui.element('div').classes('p-2 bg-white rounded-xl shadow-md border border-white/20 shrink-0'):
                    ui.image(qr_code_b64).classes('w-16 h-16 sm:w-20 sm:h-20 rounded-lg')
                with ui.column().classes('gap-1'):
                    ui.label('DOOR ACCESS').classes('text-[9px] font-black text-indigo-300 uppercase tracking-widest')
                    ui.button('Attendance Pass', icon='qr_code_scanner', on_click=lambda: ui.navigate.to('/attendance')).props(
                        'unelevated rounded-xl color=indigo size=sm font-bold'
                    ).classes('shadow-md text-xs')
