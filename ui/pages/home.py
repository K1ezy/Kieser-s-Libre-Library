from nicegui import ui, app
from components.sidebar import sidebar
from components.header import header
from components.book_card import book_card
from core.database.mongo_manager import mongo_db
from core.ai_engine.llm_engine import tars_engine
from datetime import datetime
from typing import Any

# --- UI HELPERS ---

def get_greeting():
    """Returns a time-based greeting."""
    h = datetime.now().hour
    return "Good morning" if h < 12 else "Good afternoon" if h < 18 else "Good evening"

def stat_card(icon: str, label: str, value: Any, color: str, subtext: str = ""):
    """Displays an activity statistic in a sleek card."""
    with ui.card().classes(
        f'relative overflow-hidden group p-6 border border-slate-100 dark:border-slate-800 '
        f'shadow-sm hover:shadow-lg hover:border-{color}-300 transition-all duration-300 '
        f'bg-white dark:bg-slate-900 rounded-3xl flex-1'
    ):
        # Decorative faded background icon
        ui.icon(icon).classes(
            f'absolute -right-4 -bottom-4 text-8xl text-{color}-500/10 '
            f'group-hover:scale-110 transition-transform duration-500 ease-out pointer-events-none'
        )
        
        with ui.row().classes('items-center gap-5 relative z-10 w-full'):
            with ui.element('div').classes(f'p-4 rounded-2xl bg-{color}-50 dark:bg-{color}-950/40 text-{color}-600 dark:text-{color}-400 shadow-inner'):
                ui.icon(icon, size='md')
            with ui.column().classes('gap-1'):
                ui.label(label).classes('text-xs font-bold text-slate-400 uppercase tracking-widest')
                ui.label(str(value)).classes('text-3xl font-black text-slate-800 dark:text-slate-100 leading-none')
                if subtext: 
                    ui.label(subtext).classes(f'text-[10px] font-bold text-{color}-600 dark:text-{color}-400 bg-{color}-50 dark:bg-{color}-950/40 px-2 py-0.5 rounded-md w-max mt-1')

def action_card(title: str, subtitle: str, icon: str, color: str, target: str):
    """Large clickable action banner."""
    with ui.link(target=target).classes('w-full no-underline block'):
        with ui.card().classes(
            f'group w-full h-full p-6 border border-slate-100 dark:border-slate-800 shadow-sm '
            f'hover:shadow-xl hover:border-{color}-300 hover:-translate-y-1 transition-all duration-300 '
            f'bg-white dark:bg-slate-900 rounded-3xl cursor-pointer relative overflow-hidden'
        ):
            ui.element('div').classes(
                f'absolute top-0 right-0 w-32 h-32 bg-gradient-to-br from-{color}-100/40 to-transparent '
                f'dark:from-{color}-900/20 opacity-60 rounded-bl-full -z-0 group-hover:scale-110 transition-transform duration-500'
            )
            
            with ui.row().classes('items-center justify-between w-full relative z-10'):
                with ui.row().classes('items-center gap-5'):
                    with ui.element('div').classes(
                        f'p-4 rounded-2xl bg-{color}-50 dark:bg-{color}-950/40 text-{color}-600 dark:text-{color}-400 '
                        f'group-hover:bg-{color}-600 group-hover:text-white transition-colors duration-300 shadow-sm'
                    ):
                        ui.icon(icon, size='md')
                    with ui.column().classes('gap-1'):
                        ui.label(title).classes('text-lg font-bold text-slate-800 dark:text-slate-100 leading-tight')
                        ui.label(subtitle).classes('text-sm text-slate-500 dark:text-slate-400 font-medium')
                ui.icon('arrow_forward', size='sm').classes(
                    f'text-slate-300 dark:text-slate-600 group-hover:text-{color}-500 group-hover:translate-x-1 transition-all duration-300'
                )

# --- MAIN DASHBOARD PAGE ---
async def home_page():
    app.storage.client['page_path'] = '/'
    
    # 1. Setup Layout
    drawer = sidebar()
    header(drawer_reference=drawer)

    # 2. Load Data Safely
    try:
        total_books = await mongo_db.get_total_book_count()
        recent_books = await mongo_db.get_recent_books(limit=10)
    except Exception:
        total_books, recent_books = 0, []

    # 3. Content Container
    with ui.column().classes('w-full min-h-screen pt-20 px-4 md:pt-24 md:px-8 max-w-7xl mx-auto bg-slate-50/50 dark:bg-transparent'):
        
        # Hero Welcome Banner
        with ui.row().classes(
            'w-full justify-between items-center mb-8 gap-6 p-8 bg-gradient-to-r '
            'from-indigo-600 via-indigo-700 to-purple-700 rounded-3xl shadow-xl relative overflow-hidden'
        ):
            ui.icon('menu_book', size='12em').classes('absolute -right-8 -bottom-8 text-white opacity-10 rotate-12 pointer-events-none')
            
            with ui.column().classes('gap-2 z-10'):
                ui.label(f"{get_greeting()}! Welcome to Libre-Library").classes('text-3xl md:text-5xl font-black text-white tracking-tight leading-tight')
                ui.label('Your intelligent personal digital archive for learning, discovery, and research.').classes('text-base md:text-lg text-indigo-100 font-medium')

        # Statistics Grid
        is_tars_online = tars_engine.is_available
        tars_status = "Online" if is_tars_online else "Offline"
        tars_color = "emerald" if is_tars_online else "rose"
        tars_sub = "Llama 3.2 3B Active (Local)" if is_tars_online else "Model missing in models/"

        with ui.grid().classes('w-full grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6 mb-10'):
            stat_card('library_books', 'Library Size', total_books, 'indigo', 'Books indexed')
            stat_card('dns', 'System Status', 'Online', 'emerald', 'All engines active')
            stat_card('smart_toy', 'AI Assistant', f'TARS {tars_status}', tars_color, tars_sub)

        # Quick Actions
        ui.label('QUICK ACTIONS').classes('text-xs font-bold text-slate-400 uppercase tracking-widest mb-4 px-2')
        with ui.grid().classes('w-full grid-cols-1 md:grid-cols-2 gap-6 mb-12'):
            action_card("Ask TARS AI", "Chat with your private local AI librarian.", "smart_toy", "indigo", "/chat")
            action_card("Ingest Material", "Upload PDF, EPUB, DOCX, or PPTX.", "cloud_upload", "purple", "/upload")

        # Recent Books Section
        with ui.row().classes('w-full justify-between items-end mb-6 px-2'):
            with ui.column().classes('gap-1'):
                ui.label('Recent Additions').classes('text-2xl font-bold text-slate-800 dark:text-slate-100 tracking-tight')
                ui.label('Latest documents and books in your archive.').classes('text-sm text-slate-500 dark:text-slate-400')
            if recent_books:
                ui.link('View All Books', '/books').classes(
                    'text-sm font-bold text-indigo-600 dark:text-indigo-400 no-underline '
                    'hover:text-indigo-800 bg-indigo-50 dark:bg-indigo-950/50 px-4 py-2 rounded-full transition-colors'
                )

        if not recent_books:
            with ui.column().classes('w-full items-center justify-center py-20 bg-white dark:bg-slate-900 rounded-3xl border-2 border-dashed border-slate-200 dark:border-slate-800 shadow-sm'):
                with ui.element('div').classes('p-6 bg-slate-50 dark:bg-slate-800 rounded-full mb-4'):
                    ui.icon('library_add', size='4em').classes('text-slate-300 dark:text-slate-600')
                ui.label("Your library is empty").classes('text-slate-700 dark:text-slate-300 text-xl font-bold mb-2')
                ui.label("Start by uploading some books or documents to begin reading.").classes('text-slate-500 text-sm mb-6')
                ui.button('Upload First Book', icon='cloud_upload', on_click=lambda: ui.navigate.to('/upload')) \
                    .props('unelevated rounded color=indigo padding="12px 24px"').classes('shadow-md hover:shadow-lg transition-all font-bold')
        else:
            # Unified Book Cards Grid
            with ui.grid().classes('w-full grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-4 md:gap-6 pb-24'):
                for book in recent_books:
                    book_card(book, action_target='book')