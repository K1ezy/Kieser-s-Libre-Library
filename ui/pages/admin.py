from nicegui import ui, app
from components.sidebar import sidebar
from components.header import header
from components.bottom_nav import bottom_nav
from core.database.mongo_manager import mongo_db

async def admin_dashboard():
    # Security Check
    if app.storage.user.get('role') != 'admin':
        ui.notify('Admins only.', type='negative')
        ui.navigate.to('/')
        return

    drawer = sidebar()
    header(drawer_reference=drawer)
    bottom_nav()

    users = await mongo_db.get_all_users()
    users = users or []
    
    with ui.column().classes('w-full min-h-screen pt-20 px-3 sm:px-4 md:pt-24 md:px-8 max-w-7xl mx-auto bg-slate-50/50 dark:bg-transparent pb-32 md:pb-24'):
        with ui.column().classes('gap-1 mb-6 sm:mb-8'):
            ui.label('Admin Console').classes('text-2xl sm:text-3xl font-black text-slate-800 dark:text-slate-100 tracking-tight')
            ui.label('System management and registered accounts.').classes('text-xs sm:text-sm text-slate-500 dark:text-slate-400')

        # User Table
        with ui.card().classes('w-full p-4 sm:p-6 rounded-2xl sm:rounded-3xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 shadow-sm'):
            ui.label('Registered Accounts').classes('text-[11px] sm:text-xs font-bold text-slate-400 uppercase tracking-widest mb-4')
            columns = [
                {'name': 'username', 'label': 'Username', 'field': 'username', 'align': 'left'},
                {'name': 'email', 'label': 'Email', 'field': 'email', 'align': 'left'},
                {'name': 'role', 'label': 'Role', 'field': 'role', 'align': 'left'},
            ]
            with ui.element('div').classes('w-full overflow-x-auto'):
                ui.table(columns=columns, rows=users, row_key='email').classes('w-full').props('flat bordered')