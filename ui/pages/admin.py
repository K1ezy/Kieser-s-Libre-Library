from nicegui import ui, app
from components.sidebar import sidebar
from components.header import header
from components.bottom_nav import bottom_nav
from core.database.mongo_manager import mongo_db
from core.ai_engine.llm_engine import tars_engine
from core.config import settings

async def admin_dashboard():
    app.storage.client['page_path'] = '/admin'
    if app.storage.user.get('role') != 'admin':
        ui.notify('Admins only.', type='negative')
        ui.navigate.to('/')
        return

    drawer = sidebar()
    header(drawer_reference=drawer)
    bottom_nav()

    users = await mongo_db.get_all_users()
    users = users or []
    
    with ui.column().classes('w-full min-h-[100dvh] pt-[calc(4.5rem+env(safe-area-inset-top,0px))] px-3 sm:px-4 md:pt-24 md:px-8 max-w-7xl mx-auto pb-[calc(5rem+env(safe-area-inset-bottom,0px))] md:pb-16'):
        with ui.column().classes('gap-1 mb-6 sm:mb-8'):
            ui.label('Admin Console').classes('text-2xl sm:text-3xl font-black text-slate-900 tracking-tight')
            ui.label('System management, AI engine configuration, and registered accounts.').classes('text-xs sm:text-sm text-slate-500')

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

        # User Table
        with ui.card().classes('w-full p-4 sm:p-6 rounded-2xl sm:rounded-3xl bg-white border border-slate-200 shadow-sm'):
            ui.label('Registered Accounts').classes('text-[11px] sm:text-xs font-bold text-slate-400 uppercase tracking-widest mb-4')
            columns = [
                {'name': 'username', 'label': 'Username', 'field': 'username', 'align': 'left'},
                {'name': 'email', 'label': 'Email', 'field': 'email', 'align': 'left'},
                {'name': 'role', 'label': 'Role', 'field': 'role', 'align': 'left'},
            ]
            with ui.element('div').classes('w-full overflow-x-auto'):
                ui.table(columns=columns, rows=users, row_key='email').classes('w-full').props('flat bordered')