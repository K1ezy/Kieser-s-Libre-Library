from nicegui import ui, app
from components.sidebar import sidebar
from components.header import header
from components.bottom_nav import bottom_nav
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
        f'relative overflow-hidden group p-4 sm:p-6 border border-slate-100 dark:border-slate-800 '
        f'shadow-sm hover:shadow-lg hover:border-{color}-300 transition-all duration-300 '
        f'bg-white dark:bg-slate-900 rounded-2xl sm:rounded-3xl flex-1'
    ):
        # Decorative faded background icon
        ui.icon(icon).classes(
            f'absolute -right-3 -bottom-3 text-7xl sm:text-8xl text-{color}-500/10 '
            f'group-hover:scale-110 transition-transform duration-500 ease-out pointer-events-none'
        )
        
        with ui.row().classes('items-center gap-3.5 sm:gap-5 relative z-10 w-full'):
            with ui.element('div').classes(f'p-3 sm:p-4 rounded-xl sm:rounded-2xl bg-{color}-50 dark:bg-{color}-950/40 text-{color}-600 dark:text-{color}-400 shadow-inner shrink-0'):
                ui.icon(icon, size='md')
            with ui.column().classes('gap-0.5 sm:gap-1 flex-1 min-w-0'):
                ui.label(label).classes('text-[11px] sm:text-xs font-bold text-slate-400 uppercase tracking-widest')
                ui.label(str(value)).classes('text-2xl sm:text-3xl font-black text-slate-800 dark:text-slate-100 leading-none truncate')
                if subtext: 
                    ui.label(subtext).classes(f'text-[10px] font-bold text-{color}-600 dark:text-{color}-400 bg-{color}-50 dark:bg-{color}-950/40 px-2 py-0.5 rounded-md w-max mt-1 truncate max-w-full')

def action_card(title: str, subtitle: str, icon: str, color: str, target: str):
    """Large clickable action banner."""
    with ui.link(target=target).classes('w-full no-underline block'):
        with ui.card().classes(
            f'group w-full h-full p-4 sm:p-6 border border-slate-100 dark:border-slate-800 shadow-sm '
            f'hover:shadow-xl hover:border-{color}-300 hover:-translate-y-0.5 transition-all duration-300 '
            f'bg-white dark:bg-slate-900 rounded-2xl sm:rounded-3xl cursor-pointer relative overflow-hidden'
        ):
            ui.element('div').classes(
                f'absolute top-0 right-0 w-28 sm:w-32 h-28 sm:h-32 bg-gradient-to-br from-{color}-100/40 to-transparent '
                f'dark:from-{color}-900/20 opacity-60 rounded-bl-full -z-0 group-hover:scale-110 transition-transform duration-500'
            )
            
            with ui.row().classes('items-center justify-between w-full relative z-10 gap-3'):
                with ui.row().classes('items-center gap-3.5 sm:gap-5 flex-1 min-w-0'):
                    with ui.element('div').classes(
                        f'p-3 sm:p-4 rounded-xl sm:rounded-2xl bg-{color}-50 dark:bg-{color}-950/40 text-{color}-600 dark:text-{color}-400 '
                        f'group-hover:bg-{color}-600 group-hover:text-white transition-colors duration-300 shadow-sm shrink-0'
                    ):
                        ui.icon(icon, size='md')
                    with ui.column().classes('gap-0.5 flex-1 min-w-0'):
                        ui.label(title).classes('text-base sm:text-lg font-bold text-slate-800 dark:text-slate-100 leading-tight')
                        ui.label(subtitle).classes('text-xs sm:text-sm text-slate-500 dark:text-slate-400 font-medium truncate w-full')
                ui.icon('arrow_forward', size='sm').classes(
                    f'text-slate-300 dark:text-slate-600 group-hover:text-{color}-500 group-hover:translate-x-1 transition-all duration-300 shrink-0'
                )

# --- MAIN DASHBOARD PAGE ---
async def home_page():
    app.storage.client['page_path'] = '/'
    
    # 1. Setup Layout
    drawer = sidebar()
    header(drawer_reference=drawer)
    bottom_nav()

    # 2. Load Data Safely
    try:
        total_books = await mongo_db.get_total_book_count()
        recent_books = await mongo_db.get_recent_books(limit=10)
    except Exception:
        total_books, recent_books = 0, []

    # 3. Content Container
    with ui.column().classes('w-full min-h-screen pt-20 px-3 sm:px-4 md:pt-24 md:px-8 max-w-7xl mx-auto bg-slate-50/50 dark:bg-transparent pb-32 md:pb-24'):
        
        # Hero Welcome Banner
        with ui.row().classes(
            'w-full justify-between items-center mb-6 sm:mb-8 gap-4 sm:gap-6 p-5 sm:p-8 bg-gradient-to-r '
            'from-indigo-600 via-indigo-700 to-purple-700 rounded-2xl sm:rounded-3xl shadow-xl relative overflow-hidden'
        ):
            ui.icon('menu_book', size='9em').classes('absolute -right-6 -bottom-6 text-white opacity-10 rotate-12 pointer-events-none')
            
            with ui.column().classes('gap-1.5 sm:gap-2 z-10 w-full'):
                ui.label(f"{get_greeting()}! Welcome to Libre-Library").classes('text-2xl sm:text-3xl md:text-5xl font-black text-white tracking-tight leading-tight')
                ui.label('Your intelligent personal digital archive for learning, discovery, and research.').classes('text-xs sm:text-base md:text-lg text-indigo-100 font-medium')

        # Statistics Grid
        is_tars_online = tars_engine.is_available
        tars_status = "Online" if is_tars_online else "Offline"
        tars_color = "emerald" if is_tars_online else "rose"
        tars_sub = "Llama 3.2 3B Active (Local)" if is_tars_online else "Model missing in models/"

        with ui.grid().classes('w-full grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3 sm:gap-6 mb-6 sm:mb-10'):
            stat_card('library_books', 'Library Size', total_books, 'indigo', 'Books indexed')
            stat_card('dns', 'System Status', 'Online', 'emerald', 'All engines active')
            stat_card('smart_toy', 'AI Assistant', f'TARS {tars_status}', tars_color, tars_sub)

        # Quick Actions
        ui.label('QUICK ACTIONS').classes('text-[11px] sm:text-xs font-bold text-slate-400 uppercase tracking-widest mb-3 sm:mb-4 px-1')
        with ui.grid().classes('w-full grid-cols-1 md:grid-cols-2 gap-3 sm:gap-6 mb-8 sm:mb-12'):
            action_card("Ask TARS AI", "Chat with your private local AI librarian.", "smart_toy", "indigo", "/chat")
            action_card("Ingest Material", "Upload PDF, EPUB, DOCX, or PPTX.", "cloud_upload", "purple", "/upload")

        # Recent Books Section
        with ui.row().classes('w-full justify-between items-end mb-4 sm:mb-6 px-1'):
            with ui.column().classes('gap-0.5'):
                ui.label('Recent Additions').classes('text-xl sm:text-2xl font-bold text-slate-800 dark:text-slate-100 tracking-tight')
                ui.label('Latest documents and books in your archive.').classes('text-xs sm:text-sm text-slate-500 dark:text-slate-400')
            if recent_books:
                ui.link('View All Books', '/books').classes(
                    'text-xs sm:text-sm font-bold text-indigo-600 dark:text-indigo-400 no-underline '
                    'hover:text-indigo-800 bg-indigo-50 dark:bg-indigo-950/50 px-3 sm:px-4 py-1.5 sm:py-2 rounded-full transition-colors'
                )

        if not recent_books:
            with ui.column().classes('w-full items-center justify-center py-16 sm:py-20 bg-white dark:bg-slate-900 rounded-2xl sm:rounded-3xl border-2 border-dashed border-slate-200 dark:border-slate-800 shadow-sm px-4 text-center'):
                with ui.element('div').classes('p-5 sm:p-6 bg-slate-50 dark:bg-slate-800 rounded-full mb-4'):
                    ui.icon('library_add', size='3.5em').classes('text-slate-300 dark:text-slate-600')
                ui.label("Your library is empty").classes('text-slate-700 dark:text-slate-300 text-lg sm:text-xl font-bold mb-1')
                ui.label("Start by uploading some books or documents to begin reading.").classes('text-slate-500 text-xs sm:text-sm mb-5 max-w-sm')
                ui.button('Upload First Book', icon='cloud_upload', on_click=lambda: ui.navigate.to('/upload')) \
                    .props('unelevated rounded color=indigo padding="10px 20px"').classes('shadow-md hover:shadow-lg transition-all font-bold text-sm')
        else:
            # Unified Book Cards Grid
            with ui.grid().classes('w-full grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-3 sm:gap-4 md:gap-6'):
                for book in recent_books:
                    book_card(book, action_target='book')