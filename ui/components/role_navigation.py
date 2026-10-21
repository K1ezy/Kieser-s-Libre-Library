from typing import Any, Dict, Optional
from nicegui import ui, app

from core.security.rbac_policy import (
    Permission,
    UserRole,
    get_allowed_routes_for_role,
    get_circulation_policy,
    has_permission,
)


def inject_role_console_css() -> None:
    """
    Mobile-first, anti-overlap CSS styling for Role Consoles, Quota Badges,
    Circulation Desk cards, and Form FM-LIBS-002 queues.
    Can be used in NiceGUI via ui.add_head_html or standalone HTML injection.
    """
    css_content = """
    <style>
    *, *::before, *::after {
        box-sizing: border-box;
    }
    .role-header-card {
        background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%);
        border: 1px solid #334155;
        border-radius: 14px;
        padding: 1rem 1.25rem;
        margin-bottom: 1.15rem;
        color: #f8fafc;
        display: flex;
        flex-wrap: wrap;
        justify-content: space-between;
        align-items: center;
        gap: 0.75rem;
    }
    .console-kpi-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(175px, 1fr));
        gap: 0.85rem;
        margin: 0.85rem 0 1.25rem 0;
    }
    .console-kpi-box {
        background: #1e293b;
        border: 1px solid #334155;
        border-radius: 12px;
        padding: 0.9rem 1rem;
        color: #f8fafc;
    }
    @media (max-width: 640px) {
        .role-header-card {
            padding: 0.85rem 1rem;
        }
    }
    </style>
    """
    try:
        ui.add_head_html(css_content)
    except Exception:
        pass


def render_sidebar_role_router(user: Optional[Dict[str, Any]]) -> List[Dict[str, str]]:
    """
    Returns the allowed routes for the user's role and renders/stores active navigation.
    """
    if not user:
        return [{"path": "/login", "label": "Login", "group": "Auth"}]
    return get_allowed_routes_for_role(user)


def render_role_identity_banner(user: Dict[str, Any]) -> ui.element:
    """
    Renders the mobile-first, anti-overlap Role Identity & Borrowing Quota Banner:
    Displays User Full Name, Role Pill, Institutional ID (YY-NNNNN), Department,
    and role-specific circulation privileges (3 books / 7d vs. 10 books / 30d).
    Built natively with NiceGUI & Tailwind.
    """
    policy = get_circulation_policy(user)
    full_name = user.get("full_name") or user.get("name") or user.get("username") or "Library User"
    inst_id = user.get("institutional_id") or user.get("student_id") or "UNASSIGNED"
    dept = (user.get("department") or user.get("program") or "CAMPUS").upper()

    with ui.card().classes(
        'w-full p-4 sm:p-5 rounded-2xl sm:rounded-3xl bg-slate-900 border border-slate-800 '
        'text-white shadow-md mb-6 flex flex-col md:flex-row md:items-center md:justify-between gap-4'
    ) as banner:
        # Left side: Identity & Role Badge
        with ui.column().classes('gap-1 min-w-0 flex-1'):
            with ui.row().classes('items-center gap-2 flex-wrap'):
                ui.label(full_name).classes('text-lg sm:text-xl font-black text-white truncate max-w-full')
                ui.label(policy.display_label).classes(
                    'text-xs font-bold px-2.5 py-0.5 rounded-full bg-indigo-600 text-indigo-50 shrink-0'
                )
                ui.label(f"ID: {inst_id}").classes(
                    'text-xs font-mono font-bold px-2 py-0.5 rounded-md bg-slate-800 text-emerald-400 border border-slate-700 shrink-0'
                )
                if dept:
                    ui.label(dept).classes(
                        'text-xs font-semibold px-2 py-0.5 rounded-md bg-slate-800 text-slate-300 border border-slate-700 shrink-0'
                    )

        # Right side: Role Quota & Privileges Strip
        with ui.row().classes('items-center gap-2 flex-wrap'):
            if policy.is_staff:
                with ui.element('span').classes(
                    'text-xs font-semibold px-3 py-1.5 rounded-xl bg-slate-800 border border-slate-700 text-amber-300 flex items-center gap-1.5'
                ):
                    ui.icon('shield', size='16px')
                    ui.label('Staff Circulation & Override Authority')
                with ui.element('span').classes(
                    'text-xs font-semibold px-3 py-1.5 rounded-xl bg-slate-800 border border-slate-700 text-indigo-300 flex items-center gap-1.5'
                ):
                    ui.icon('assignment', size='16px')
                    ui.label('Form FM-LIBS-002 & 009 Reviewer')
            else:
                with ui.element('span').classes(
                    'text-xs font-semibold px-3 py-1.5 rounded-xl bg-slate-800 border border-slate-700 text-slate-200 flex items-center gap-1.5'
                ):
                    ui.icon('menu_book', size='16px').classes('text-indigo-400')
                    ui.label(f"Quota: {policy.max_active_loans} Books")

                with ui.element('span').classes(
                    'text-xs font-semibold px-3 py-1.5 rounded-xl bg-slate-800 border border-slate-700 text-slate-200 flex items-center gap-1.5'
                ):
                    ui.icon('schedule', size='16px').classes('text-emerald-400')
                    ui.label(f"Loan: {policy.loan_duration_days} Days")

                with ui.element('span').classes(
                    'text-xs font-semibold px-3 py-1.5 rounded-xl bg-slate-800 border border-slate-700 text-slate-200 flex items-center gap-1.5'
                ):
                    ui.icon('replay', size='16px').classes('text-sky-400')
                    ui.label(f"Renewal: +{policy.renewal_extension_days} Days")

    return banner
