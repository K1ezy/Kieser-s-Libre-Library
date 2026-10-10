from nicegui import ui, app
from datetime import datetime
import logging

from components.sidebar import sidebar
from components.header import header
from components.bottom_nav import bottom_nav
from core.database.mongo_manager import mongo_db
from core.config import settings

logger = logging.getLogger("ADMIN_UI")


async def admin_dashboard():
    """Admin Console Dashboard for Libre-Library."""
    app.storage.client['page_path'] = '/admin'
    if app.storage.user.get('role') != 'admin':
        ui.notify('Admins only.', type='negative')
        ui.navigate.to('/')
        return

    drawer = sidebar()
    header(drawer_reference=drawer)
    bottom_nav()

    # Fetch system diagnostics
    stats = await mongo_db.get_system_diagnostics()
    raw_users = await mongo_db.get_all_users()

    # Sanitize user rows to ensure strict JSON serializability (no BSON ObjectId)
    def format_users(user_list):
        formatted = []
        for u in (user_list or []):
            created_val = u.get("joined_at") or u.get("created_at")
            joined_str = "Recently"
            if isinstance(created_val, (int, float)):
                try:
                    joined_str = datetime.fromtimestamp(created_val).strftime("%b %d, %Y")
                except Exception:
                    joined_str = "Recently"
            elif isinstance(created_val, str) and created_val.strip():
                joined_str = created_val.strip()[:10]

            formatted.append({
                'id': str(u.get('id') or u.get('_id') or ''),
                'username': str(u.get('username') or 'User'),
                'email': str(u.get('email') or 'No email'),
                'role': str(u.get('role') or 'user').upper(),
                'joined_at': joined_str,
            })
        return formatted

    clean_users = format_users(raw_users)

    with ui.column().classes(
        'w-full min-h-[100dvh] pt-[calc(4.5rem+env(safe-area-inset-top,0px))] '
        'px-3 sm:px-4 md:pt-24 md:px-8 max-w-7xl mx-auto pb-[calc(5rem+env(safe-area-inset-bottom,0px))] md:pb-16'
    ):
        # Page Title Banner
        with ui.column().classes('gap-1 mb-6 sm:mb-8'):
            ui.label('Admin Console').classes('text-2xl sm:text-3xl font-black text-slate-900 tracking-tight')
            ui.label('System metrics, OPDS catalog connectivity, and registered accounts management.').classes('text-xs sm:text-sm text-slate-500')

        # Real-time Metrics Grid
        with ui.grid().classes('w-full grid-cols-2 md:grid-cols-4 gap-3 sm:gap-4 mb-6'):
            metric_cards = [
                ("menu_book", "Total Books", str(stats.get("books", 0)), "text-indigo-600", "bg-indigo-50"),
                ("people", "User Accounts", str(stats.get("users", len(clean_users))), "text-blue-600", "bg-blue-50"),
                ("check_circle", "Study Tasks", str(stats.get("tasks", 0)), "text-emerald-600", "bg-emerald-50"),
                ("style", "Flashcard Decks", str(stats.get("decks", 0)), "text-amber-600", "bg-amber-50"),
            ]
            for icon_name, label_text, val_text, text_color, bg_color in metric_cards:
                with ui.card().classes('p-3.5 sm:p-5 rounded-2xl bg-white border border-slate-200 shadow-sm'):
                    with ui.row().classes('items-center gap-2 mb-1.5'):
                        with ui.element('div').classes(f'p-1.5 rounded-xl {bg_color} {text_color}'):
                            ui.icon(icon_name, size='18px')
                        ui.label(label_text).classes('text-[11px] font-bold text-slate-400 uppercase tracking-wider')
                    ui.label(val_text).classes('text-xl sm:text-2xl font-black text-slate-900')

        # Institutional Core Services Hub (SRS Chapter 1 & 2 Modules)
        with ui.card().classes('w-full p-4 sm:p-6 rounded-2xl sm:rounded-3xl bg-white border border-slate-200 shadow-sm mb-6'):
            with ui.row().classes('items-center gap-2 mb-3'):
                ui.icon('hub', size='sm').classes('text-indigo-600')
                ui.label('INSTITUTIONAL CORE SERVICES').classes('text-xs sm:text-sm font-black text-slate-900 uppercase tracking-widest')
            with ui.grid().classes('w-full grid-cols-1 sm:grid-cols-3 gap-3'):
                # Attendance
                with ui.card().classes('p-4 rounded-xl border border-slate-200 bg-slate-50 hover:bg-slate-100/80 cursor-pointer transition-all').on('click', lambda: ui.navigate.to('/attendance')):
                    with ui.row().classes('items-center gap-2 mb-1'):
                        ui.icon('qr_code_scanner', size='20px').classes('text-indigo-600')
                        ui.label('Attendance Terminal').classes('text-sm font-bold text-slate-900')
                    ui.label('Automated QR check-ins and daily visitor log summaries.').classes('text-[11px] text-slate-500')

                # Requisitions
                with ui.card().classes('p-4 rounded-xl border border-slate-200 bg-slate-50 hover:bg-slate-100/80 cursor-pointer transition-all').on('click', lambda: ui.navigate.to('/requisitions')):
                    with ui.row().classes('items-center gap-2 mb-1'):
                        ui.icon('post_add', size='20px').classes('text-purple-600')
                        ui.label('Faculty Requisitions').classes('text-sm font-bold text-slate-900')
                    ui.label('Curriculum textbook requests & procurement status tracker.').classes('text-[11px] text-slate-500')

                # Analytics
                with ui.card().classes('p-4 rounded-xl border border-slate-200 bg-slate-50 hover:bg-slate-100/80 cursor-pointer transition-all').on('click', lambda: ui.navigate.to('/analytics')):
                    with ui.row().classes('items-center gap-2 mb-1'):
                        ui.icon('insights', size='20px').classes('text-emerald-600')
                        ui.label('Program Analytics').classes('text-sm font-bold text-slate-900')
                    ui.label('Program utilization charts & AI accreditation reports.').classes('text-[11px] text-slate-500')

        # OPDS E-Reader Catalog Link Card
        with ui.card().classes('w-full p-4 sm:p-6 rounded-2xl sm:rounded-3xl bg-white border border-slate-200 shadow-sm mb-6'):
            with ui.row().classes('items-center gap-2 mb-2'):
                ui.icon('wifi_tethering', size='sm').classes('text-indigo-600')
                ui.label('OPDS E-READER CATALOG FEED').classes('text-sm sm:text-base font-black text-slate-900')
            ui.label('Connect e-readers (Kobo, Kindle via KOReader) or mobile apps (Moon+ Reader, Apple Books) over Wi-Fi.').classes('text-xs text-slate-500 mb-3')
            with ui.row().classes('w-full p-3 bg-slate-50 rounded-xl border border-slate-200 items-center justify-between gap-3 flex-wrap'):
                opds_url_label = ui.label("http://<your-ip-or-ngrok>:8080/opds").classes('font-mono text-xs sm:text-sm font-bold text-slate-800 truncate flex-1 min-w-0')
                ui.run_javascript(f'const el = document.getElementById("{opds_url_label.id}"); if(el) el.innerText = window.location.origin + "/opds";')
                ui.button('Copy Catalog Feed URL', icon='content_copy', on_click=lambda: ui.run_javascript("""
                    navigator.clipboard.writeText(window.location.origin + '/opds');
                    alert('OPDS Catalog Feed URL copied! Enter this in your e-reader app.');
                """)).props('unelevated rounded-xl color=indigo size=sm font-bold')

        # Registered Accounts Management Table (Role-Based Access Control)
        with ui.card().classes('w-full p-4 sm:p-6 rounded-2xl sm:rounded-3xl bg-white border border-slate-200 shadow-sm'):
            with ui.row().classes('w-full items-center justify-between mb-4'):
                with ui.row().classes('items-center gap-2'):
                    ui.icon('manage_accounts', size='sm').classes('text-indigo-600')
                    ui.label('Registered Accounts & Roles (RBAC)').classes('text-xs sm:text-sm font-black text-slate-900 uppercase tracking-widest')
                ui.label(f"{len(clean_users)} users").classes('text-[10px] font-bold text-slate-500 bg-slate-100 px-2 py-0.5 rounded-full')

            user_table_container = ui.element('div').classes('w-full overflow-x-auto')

            def render_user_table():
                user_table_container.clear()
                with user_table_container:
                    columns = [
                        {'name': 'username', 'label': 'Username', 'field': 'username', 'align': 'left', 'sortable': True},
                        {'name': 'email', 'label': 'Email', 'field': 'email', 'align': 'left', 'sortable': True},
                        {'name': 'role', 'label': 'Role (RBAC)', 'field': 'role', 'align': 'center', 'sortable': True},
                        {'name': 'joined_at', 'label': 'Joined Date', 'field': 'joined_at', 'align': 'right', 'sortable': True},
                    ]
                    t = ui.table(columns=columns, rows=clean_users, row_key='email').classes('w-full').props('flat bordered')

            render_user_table()

            # Dynamic Role Change Helper
            ui.separator().classes('my-4')
            with ui.row().classes('w-full items-center justify-between gap-3 flex-wrap'):
                ui.label('Assign Role to User Account:').classes('text-xs font-bold text-slate-600')
                user_options = {u['id']: f"{u['username']} ({u['email']})" for u in clean_users if u['id']}
                if user_options:
                    with ui.row().classes('items-center gap-2 flex-wrap'):
                        selected_user_id = list(user_options.keys())[0]
                        u_select = ui.select(user_options, value=selected_user_id, label='Select Account').props('dense rounded outlined').classes('w-60 text-xs')
                        r_select = ui.select(['student', 'faculty', 'librarian', 'admin'], value='faculty', label='New Role').props('dense rounded outlined').classes('w-32 text-xs')
                        
                        async def apply_role():
                            uid = u_select.value
                            nrole = r_select.value
                            if uid and nrole:
                                await mongo_db.users.update_user_role(uid, nrole)
                                ui.notify(f"Account updated to role '{nrole.upper()}'", type='positive')
                                updated_users = await mongo_db.get_all_users()
                                clean_users.clear()
                                clean_users.extend(format_users(updated_users))
                                render_user_table()

                        ui.button('Update Role', icon='badge', on_click=apply_role).props('unelevated rounded-xl color=indigo size=sm font-bold')