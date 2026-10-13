from nicegui import ui, app
from datetime import datetime
import logging

from components.sidebar import sidebar
from components.header import header
from core.database.mongo_manager import mongo_db
from core.config import settings
from core.auth.jwt_handler import get_current_user_role

logger = logging.getLogger("ADMIN_UI")


async def admin_dashboard():
    """Admin Console Dashboard for Libre-Library."""
    app.storage.client['page_path'] = '/admin'
    if get_current_user_role() != 'admin':
        ui.notify('System Administrator privileges required.', type='negative')
        ui.navigate.to('/')
        return

    drawer = sidebar()
    header(drawer_reference=drawer)

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
        'w-full min-h-fit pt-[calc(4.5rem+env(safe-area-inset-top,0px))] '
        'px-3 sm:px-6 md:pt-24 md:px-10 max-w-[1600px] mx-auto pb-16'
    ):
        # Page Title Banner
        with ui.row().classes('w-full items-start justify-between gap-4 mb-6 sm:mb-8 flex-wrap'):
            with ui.column().classes('gap-1'):
                with ui.row().classes('items-center gap-2.5'):
                    with ui.element('div').classes('p-2.5 rounded-2xl bg-rose-50 text-rose-600 border border-rose-100 shadow-sm'):
                        ui.icon('admin_panel_settings', size='28px')
                    with ui.column().classes('gap-0'):
                        ui.label('Admin IT Governance Console').classes('text-2xl sm:text-3xl font-black text-slate-900 tracking-tight')
                        ui.label('System security, database diagnostics, and Role-Based Access Control (RBAC) user administration.').classes('text-xs sm:text-sm text-slate-500')
            with ui.row().classes('items-center gap-2'):
                ui.element('span').classes('text-xs font-black uppercase tracking-wider bg-rose-50 text-rose-700 px-3 py-1 rounded-full border border-rose-200') \
                    .text = '🛡️ Root Administrator'
                ui.button('Open Librarian Hub', icon='local_library', on_click=lambda: ui.navigate.to('/librarian')) \
                    .props('unelevated rounded-xl color=indigo size=sm font-bold shadow-xs')

        # Real-time IT & Infrastructure Metrics Grid
        with ui.grid().classes('w-full grid-cols-2 md:grid-cols-4 gap-3 sm:gap-4 mb-6'):
            metric_cards = [
                ("people", "Registered Accounts", str(stats.get("users", len(clean_users))), "Active RBAC Accounts", "text-blue-600", "bg-blue-50"),
                ("menu_book", "Catalog Volumes", str(stats.get("books", 0)), "Synchronized Documents", "text-indigo-600", "bg-indigo-50"),
                ("security", "Security Architecture", "Active", "256-Bit Cryptographic Guard", "text-emerald-600", "bg-emerald-50"),
                ("dns", "Database Cluster", "Connected", "MongoDB Replicated Store", "text-purple-600", "bg-purple-50"),
            ]
            for icon_name, label_text, val_text, sub_text, text_color, bg_color in metric_cards:
                with ui.card().classes('p-3.5 sm:p-5 rounded-2xl bg-white border border-slate-200 shadow-sm'):
                    with ui.row().classes('items-center gap-2 mb-1.5'):
                        with ui.element('div').classes(f'p-1.5 rounded-xl {bg_color} {text_color}'):
                            ui.icon(icon_name, size='18px')
                        ui.label(label_text).classes('text-[11px] font-bold text-slate-400 uppercase tracking-wider truncate')
                    ui.label(val_text).classes('text-xl sm:text-2xl font-black text-slate-900')
                    ui.label(sub_text).classes('text-[10px] sm:text-[11px] text-slate-500 font-medium')

        # Cross-Link Banner to Dedicated Librarian Operations Console
        with ui.card().classes('w-full p-4 sm:p-5 rounded-2xl sm:rounded-3xl bg-gradient-to-r from-indigo-50 to-slate-50 border border-indigo-100 shadow-xs mb-6'):
            with ui.row().classes('w-full items-center justify-between gap-3 flex-wrap'):
                with ui.row().classes('items-center gap-3 min-w-0 flex-1'):
                    with ui.element('div').classes('p-2.5 rounded-2xl bg-indigo-600 text-white shrink-0'):
                        ui.icon('local_library', size='22px')
                    with ui.column().classes('gap-0.5 min-w-0 flex-1'):
                        ui.label('Looking for Library Circulation & Collection Management?').classes('text-sm font-black text-slate-900')
                        ui.label('Curricular requisitions (FM-LIBS-002), entrance attendance logs (FM-LIBS-009), and OPDS e-reader feeds are centralized in the Librarian Console.').classes('text-xs text-slate-500 leading-snug')
                ui.button('Switch to Librarian Operations Console', icon='arrow_forward', on_click=lambda: ui.navigate.to('/librarian')) \
                    .props('unelevated rounded-xl color=indigo size=sm font-bold shadow-sm')


        # Registered Accounts Management Table (Role-Based Access Control)
        with ui.card().classes('w-full p-4 sm:p-6 rounded-2xl sm:rounded-3xl bg-white border border-slate-200 shadow-sm'):
            with ui.row().classes('w-full items-center justify-between mb-4'):
                with ui.row().classes('items-center gap-2'):
                    ui.icon('manage_accounts', size='sm').classes('text-indigo-600')
                    ui.label('Registered Accounts & Roles (RBAC)').classes('text-xs sm:text-sm font-black text-slate-900 uppercase tracking-widest')
                ui.label(f"{len(clean_users)} users").classes('text-[10px] font-bold text-slate-500 bg-slate-100 px-2 py-0.5 rounded-full')

            ROLE_STYLES = {
                'admin': ('bg-rose-50 text-rose-700 border-rose-200', 'security'),
                'librarian': ('bg-indigo-50 text-indigo-700 border-indigo-200', 'local_library'),
                'faculty': ('bg-emerald-50 text-emerald-700 border-emerald-200', 'school'),
                'student': ('bg-slate-100 text-slate-700 border-slate-200', 'person'),
            }

            user_table_container = ui.element('div').classes('w-full')

            def open_role_dialog(target_user):
                with ui.dialog() as role_dialog, ui.card().classes('w-[calc(100vw-2rem)] max-w-sm p-5 sm:p-6 rounded-3xl bg-white border border-slate-200 shadow-2xl'):
                    with ui.row().classes('w-full items-center justify-between mb-2'):
                        with ui.row().classes('items-center gap-2'):
                            ui.icon('badge', size='sm').classes('text-indigo-600')
                            ui.label('Change Account Role').classes('text-base font-black text-slate-900')
                        ui.button(icon='close', on_click=role_dialog.close).props('flat round dense size=sm color=grey')

                    with ui.column().classes('w-full gap-1 mb-4 p-3 bg-slate-50 rounded-2xl border border-slate-100'):
                        ui.label(target_user.get('username', 'User')).classes('text-sm font-bold text-slate-900')
                        ui.label(target_user.get('email', '')).classes('text-xs text-slate-500 font-mono truncate')
                        curr_role = target_user.get('role', 'student')
                        ui.label(f"Current Role: {curr_role.upper()}").classes('text-[11px] font-bold text-indigo-600 mt-1')

                    role_sel = ui.select(
                        ['student', 'faculty', 'librarian', 'admin'],
                        value=target_user.get('role', 'student'),
                        label='Assign New Role'
                    ).props('rounded outlined dense options-dense').classes('w-full mb-4')

                    with ui.row().classes('w-full justify-end gap-2'):
                        ui.button('Cancel', on_click=role_dialog.close).props('flat rounded-xl color=grey size=sm font-bold')
                        
                        async def save_role_change():
                            uid = target_user.get('id')
                            nrole = role_sel.value
                            if uid and nrole:
                                await mongo_db.users.update_user_role(uid, nrole)
                                ui.notify(f"Role updated to '{nrole.upper()}' for {target_user.get('username')}", type='positive')
                                role_dialog.close()
                                updated_users = await mongo_db.get_all_users()
                                clean_users.clear()
                                clean_users.extend(format_users(updated_users))
                                render_user_table()

                        ui.button('Save Role', icon='check', on_click=save_role_change) \
                            .props('unelevated rounded-xl color=indigo size=sm font-bold shadow-md')

                role_dialog.open()

            def render_user_table():
                user_table_container.clear()
                with user_table_container:
                    # 1. Desktop High-Density Table (>=768px)
                    with ui.element('div').classes('hidden md:block w-full overflow-x-auto'):
                        columns = [
                            {'name': 'username', 'label': 'Username', 'field': 'username', 'align': 'left', 'sortable': True},
                            {'name': 'email', 'label': 'Email', 'field': 'email', 'align': 'left', 'sortable': True},
                            {'name': 'role', 'label': 'Role (RBAC)', 'field': 'role', 'align': 'center', 'sortable': True},
                            {'name': 'joined_at', 'label': 'Joined Date', 'field': 'joined_at', 'align': 'right', 'sortable': True},
                        ]
                        ui.table(columns=columns, rows=clean_users, row_key='email').classes('w-full mobile-card-table').props('flat bordered')

                    # 2. Mobile Touch-Optimized Cards (<768px)
                    with ui.element('div').classes('block md:hidden w-full flex flex-col gap-3'):
                        if not clean_users:
                            ui.label('No registered user accounts found.').classes('text-xs text-slate-400 italic py-4 text-center')
                        for u in clean_users:
                            u_role = u.get('role', 'student')
                            badge_cls, badge_ic = ROLE_STYLES.get(u_role, ('bg-slate-100 text-slate-700 border-slate-200', 'person'))
                            
                            with ui.card().classes('w-full p-4 rounded-2xl bg-white border border-slate-200 shadow-xs hover:border-indigo-200 transition-all'):
                                with ui.row().classes('w-full items-start justify-between gap-2 mb-2'):
                                    with ui.row().classes('items-center gap-2.5 min-w-0 flex-1'):
                                        ui.avatar(icon=badge_ic, color='indigo-50', text_color='indigo-700', size='36px') \
                                            .classes('border border-indigo-100 shrink-0 font-bold')
                                        with ui.column().classes('gap-0 min-w-0 flex-1'):
                                            ui.label(u.get('username', 'User')).classes('text-sm font-black text-slate-900 truncate')
                                            ui.label(u.get('email', '')).classes('text-xs text-slate-500 font-mono truncate')
                                    with ui.element('div').classes(f'px-2.5 py-0.5 rounded-full text-[10px] font-black uppercase border shrink-0 flex items-center gap-1 {badge_cls}'):
                                        ui.icon(badge_ic, size='12px')
                                        ui.label(u_role)

                                with ui.row().classes('w-full items-center justify-between text-[11px] text-slate-400 pt-2 border-t border-slate-100 mt-1'):
                                    ui.label(f"Joined: {u.get('joined_at', 'N/A')}")
                                    ui.button('Manage Role', icon='edit', on_click=lambda usr=u: open_role_dialog(usr)) \
                                        .props('flat rounded-xl color=indigo size=xs font-bold')

            render_user_table()

            # Dynamic Role Change Helper (Desktop Quick Bar)
            ui.separator().classes('my-4')
            with ui.row().classes('w-full items-center justify-between gap-3 flex-wrap'):
                ui.label('Assign Role to User Account:').classes('text-xs font-bold text-slate-600')
                user_options = {u['id']: f"{u['username']} ({u['email']})" for u in clean_users if u['id']}
                if user_options:
                    with ui.row().classes('items-center gap-2 flex-wrap'):
                        selected_user_id = list(user_options.keys())[0]
                        u_select = ui.select(user_options, value=selected_user_id, label='Select Account').props('dense rounded outlined').classes('w-full sm:w-60 text-xs')
                        r_select = ui.select(['student', 'faculty', 'librarian', 'admin'], value='faculty', label='New Role').props('dense rounded outlined').classes('w-full sm:w-32 text-xs')
                        
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