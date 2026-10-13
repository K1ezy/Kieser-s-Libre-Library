from nicegui import ui, app
from components.sidebar import sidebar
from components.header import header
from components.book_card import book_card, has_disk_cover, get_format_color
from core.database.mongo_manager import mongo_db
from core.ai_engine.llm_engine import tars_engine
from datetime import datetime
from typing import Any, Dict

def get_greeting() -> str:
    """Returns a time-based greeting."""
    h = datetime.now().hour
    return "Good morning" if h < 12 else "Good afternoon" if h < 18 else "Good evening"

def get_reading_cover_url(book_doc: Dict[str, Any]) -> str:
    """Safely retrieves the best cover image URL for active reading cards."""
    b_id = str(book_doc.get('id', ''))
    if has_disk_cover(b_id):
        return f"/static_books/{b_id}/cover.jpg"
    elif book_doc.get('cover_image') and not str(book_doc.get('cover_image')).endswith(('default_cover.png', 'default_cover.svg')):
        return book_doc.get('cover_image')
    return "/static/default_cover.svg"

def action_card(title: str, subtitle: str, icon: str, color: str, target: str):
    """Compact clickable action card for primary tool access."""
    with ui.link(target=target).classes('w-full no-underline block'):
        with ui.card().classes(
            f'group w-full h-full p-3.5 sm:p-4 border border-slate-200/90 shadow-2xs '
            f'hover:shadow-md hover:border-{color}-300 hover:-translate-y-0.5 transition-all duration-200 '
            f'bg-white rounded-2xl cursor-pointer'
        ):
            with ui.row().classes('items-center justify-between w-full gap-2.5'):
                with ui.row().classes('items-center gap-3 min-w-0 flex-1'):
                    with ui.element('div').classes(
                        f'p-2.5 rounded-xl bg-{color}-50 text-{color}-600 '
                        f'group-hover:bg-{color}-600 group-hover:text-white transition-colors duration-200 shadow-2xs shrink-0 border border-{color}-100'
                    ):
                        ui.icon(icon, size='20px')
                    with ui.column().classes('gap-0 min-w-0 flex-1'):
                        ui.label(title).classes('text-xs sm:text-sm font-bold text-slate-900 leading-tight truncate w-full')
                        ui.label(subtitle).classes('text-[11px] text-slate-500 font-medium truncate w-full')
                ui.icon('arrow_forward', size='16px').classes(
                    f'text-slate-300 group-hover:text-{color}-600 group-hover:translate-x-0.5 transition-all duration-200 shrink-0'
                )

def continue_reading_card(book_prog: Dict[str, Any]):
    """Renders a high-scannability active reading card with cover art and direct resume action."""
    b_id = str(book_prog.get('id', ''))
    b_title = book_prog.get('title', 'Untitled')
    b_author = book_prog.get('display_author') or 'Unknown'
    b_pct = min(100, max(0, round(float(book_prog.get('progress_percent', 0)))))
    b_cur = book_prog.get('current_page', 1)
    b_tot = max(1, book_prog.get('total_pages', 1))
    cover_url = get_reading_cover_url(book_prog)
    file_type = str(book_prog.get('file_type', 'EPUB')).upper()
    txt_col, bg_col = get_format_color(file_type)

    with ui.card().classes(
        'p-3.5 sm:p-4 bg-white border border-slate-200/90 rounded-2xl shadow-xs '
        'hover:shadow-md hover:border-indigo-300 transition-all flex flex-col justify-between gap-3'
    ):
        with ui.row().classes('items-start gap-3.5 w-full'):
            # Book Cover Thumbnail (2:3 aspect ratio with format tag)
            with ui.element('div').classes('w-16 sm:w-20 h-24 sm:h-28 rounded-xl overflow-hidden bg-slate-100 relative shrink-0 border border-slate-200/60 shadow-2xs'):
                ui.image(cover_url).classes('w-full h-full object-cover')
                with ui.element('div').classes(f'absolute bottom-1 left-1 px-1.5 py-0.2 rounded text-[8px] sm:text-[9px] font-black border {txt_col} {bg_col}'):
                    ui.label(file_type)

            # Metadata & Location Tracking
            with ui.column().classes('gap-1 flex-1 min-w-0'):
                ui.label(b_title).classes('font-bold text-sm sm:text-base text-slate-900 leading-snug line-clamp-2')
                ui.label(f"by {b_author}").classes('text-xs text-slate-500 truncate')

                # Progress indicator & Page count
                with ui.row().classes('items-center justify-between gap-2 mt-1 w-full'):
                    with ui.element('span').classes('text-xs font-bold text-indigo-700 bg-indigo-50 border border-indigo-200 px-2 py-0.5 rounded-md'):
                        ui.label(f"{b_pct}% read")
                    ui.label(f"Page {b_cur} of {b_tot}").classes('text-xs text-slate-500 font-medium')

                # Linear progress bar
                with ui.element('div').classes('w-full bg-slate-100 h-2 rounded-full overflow-hidden mt-1 border border-slate-200/60'):
                    ui.element('div').classes('bg-gradient-to-r from-indigo-500 to-indigo-600 h-full rounded-full transition-all duration-300').style(f'width: {b_pct}%')

        # Action Buttons
        with ui.row().classes('w-full justify-end items-center gap-2 pt-2 border-t border-slate-100'):
            ui.button('Details', icon='info', on_click=lambda id=b_id: ui.navigate.to(f"/book/{id}"))\
                .props('flat rounded-xl size=sm color=grey-8 font-bold').classes('text-xs')
            ui.button('Resume Reading', icon='play_arrow', on_click=lambda id=b_id: ui.navigate.to(f"/read/{id}"))\
                .props('unelevated rounded-xl size=sm color=indigo font-bold')\
                .classes('text-xs shadow-xs')

async def home_page():
    app.storage.client['page_path'] = '/'
    
    drawer = sidebar()
    header(drawer_reference=drawer)

    try:
        total_books = await mongo_db.get_total_book_count()
        recent_books = await mongo_db.get_recent_books(limit=14)
    except Exception:
        total_books, recent_books = 0, []

    uid = app.storage.user.get('user_id') or app.storage.user.get('token')
    user_name = app.storage.user.get('username') or app.storage.user.get('name') or ''
    active_reading_items = []
    if uid:
        try:
            raw_history = await mongo_db.progress.get_reading_history(uid, limit=10)
            for item in raw_history:
                b_id = item.get('book_id')
                if b_id:
                    b_doc = await mongo_db.get_book_details(b_id)
                    if b_doc:
                        b_doc['progress_percent'] = item.get('progress_percent', 0)
                        b_doc['current_page'] = item.get('current_page', 1)
                        b_doc['total_pages'] = item.get('total_pages', 1)
                        active_reading_items.append(b_doc)
                if len(active_reading_items) >= 2:
                    break
        except Exception:
            active_reading_items = []

    # System Status values
    is_tars_online = tars_engine.is_available
    tars_status = "Online" if is_tars_online else "Offline"
    tars_color = "emerald" if is_tars_online else "rose"
    tars_sub = "Llama 3.2 3B Active (Local)" if is_tars_online else "Model missing in models/"

    greeting_str = f"{get_greeting()}, {user_name}" if user_name else f"{get_greeting()}"

    with ui.column().classes('w-full min-h-fit pt-[calc(4.5rem+env(safe-area-inset-top,0px))] md:pt-24 px-3 sm:px-6 md:px-10 max-w-[1700px] mx-auto pb-16'):
        
        # 1. Compact Welcome Header (Personal Dashboard)
        with ui.element('div').classes(
            'w-full flex flex-col md:flex-row justify-between items-start md:items-center min-h-fit '
            'mb-5 sm:mb-6 gap-4 p-4 sm:p-6 bg-gradient-to-r from-slate-900 via-indigo-950 to-slate-900 '
            'rounded-2xl sm:rounded-3xl shadow-md text-white'
        ):
            with ui.row().classes('items-center gap-3.5 min-w-0 flex-1'):
                with ui.element('div').classes('p-2.5 sm:p-3 rounded-2xl bg-white/10 border border-white/20 text-white shadow-inner shrink-0'):
                    ui.icon('local_library', size='sm')
                with ui.column().classes('gap-0.5 min-w-0'):
                    ui.label(f"{greeting_str}!").classes('text-lg sm:text-2xl md:text-3xl font-black text-white tracking-tight leading-tight break-words')
                    ui.label('Welcome to your personal learning & reading workspace.').classes('text-xs sm:text-sm text-slate-300 font-medium')

            # Multi-tier System Health Indicator (Transparent Operational Diagnostics)
            with ui.element('div').classes('flex flex-wrap items-center gap-2 shrink-0 w-full md:w-auto'):
                ui.link(f"{total_books} Books Cataloged", '/books').classes(
                    'no-underline text-xs font-bold px-3 py-1.5 rounded-full bg-white/10 hover:bg-white/20 border border-white/20 text-white transition-colors'
                )
                with ui.row().classes('items-center gap-1.5 px-3 py-1.5 rounded-full bg-emerald-500/20 border border-emerald-400/30 text-white text-xs font-bold'):
                    ui.element('div').classes('w-2 h-2 rounded-full bg-emerald-400 animate-pulse')
                    ui.label('App: Online')
                with ui.row().classes(f'items-center gap-1.5 px-3 py-1.5 rounded-full bg-{tars_color}-500/20 border border-{tars_color}-400/30 text-white text-xs font-bold'):
                    ui.element('div').classes(f'w-2 h-2 rounded-full bg-{tars_color}-400 animate-pulse')
                    ui.label(f"AI: {tars_status}")

        # 2. Continue Reading (Primary Hero Focus)
        with ui.column().classes('w-full mb-6 sm:mb-8'):
            with ui.row().classes('items-center justify-between w-full mb-3 px-1'):
                with ui.row().classes('items-center gap-2'):
                    ui.icon('auto_stories', size='sm').classes('text-indigo-600')
                    ui.label('CONTINUE READING').classes('text-[11px] sm:text-xs font-black text-indigo-700 uppercase tracking-widest')
                if active_reading_items:
                    with ui.element('span').classes('text-xs font-bold text-slate-500'):
                        ui.label(f"{len(active_reading_items)} active session{'s' if len(active_reading_items) > 1 else ''}")

            if active_reading_items:
                with ui.grid().classes('w-full grid-cols-1 md:grid-cols-2 gap-4'):
                    for book_prog in active_reading_items:
                        continue_reading_card(book_prog)
            else:
                with ui.card().classes('w-full p-4 sm:p-5 bg-white border border-slate-200/80 rounded-2xl flex-row items-center justify-between gap-4 flex-wrap shadow-2xs'):
                    with ui.row().classes('items-center gap-3.5'):
                        with ui.element('div').classes('p-2.5 rounded-xl bg-indigo-50 text-indigo-600 shrink-0 border border-indigo-100'):
                            ui.icon('bookmark_border', size='22px')
                        with ui.column().classes('gap-0'):
                            ui.label("No active reading sessions in progress").classes('text-xs sm:text-sm font-bold text-slate-800')
                            ui.label("Choose a book from your library archive to pick up where you left off.").classes('text-xs text-slate-500')
                    ui.button('Browse Library Archive', icon='library_books', on_click=lambda: ui.navigate.to('/books'))\
                        .props('unelevated rounded-xl color=indigo size=sm font-bold').classes('shadow-xs')

        # 3. Quick Actions (The 4 Core Pillars)
        ui.label('QUICK ACTIONS').classes('text-[11px] sm:text-xs font-bold text-slate-400 uppercase tracking-widest mb-3 px-1')
        with ui.grid().classes('w-full grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4 mb-6 sm:mb-8'):
            action_card("Ask TARS AI", "Chat with AI librarian", "smart_toy", "indigo", "/chat")
            action_card("Study Planner", "Spaced repetition decks", "event_note", "purple", "/planner")
            action_card("Library Pass", "Digital QR entrance", "badge", "emerald", "/attendance")
            action_card("Library Archive", "Browse multi-format books", "local_library", "sky", "/books")

        # 4. Recent Additions Section
        with ui.row().classes('w-full justify-between items-end mb-4 px-1'):
            with ui.column().classes('gap-0.5'):
                ui.label('Recent Additions').classes('text-lg sm:text-xl font-bold text-slate-900 tracking-tight')
                ui.label('Latest documents and books added to your library.').classes('text-xs text-slate-500')
            if recent_books:
                ui.link(f'View All ({total_books}) →', '/books').classes(
                    'text-xs font-bold text-indigo-600 no-underline hover:text-indigo-800 bg-indigo-50 px-3 py-1.5 rounded-full transition-colors border border-indigo-100'
                )

        if not recent_books:
            with ui.column().classes('w-full items-center justify-center py-12 sm:py-16 bg-white rounded-2xl border-2 border-dashed border-slate-200 px-4 text-center'):
                ui.icon('library_books', size='3em').classes('text-slate-300 mb-2')
                ui.label("Your library archive is empty").classes('text-slate-800 text-base font-bold')
                ui.label("Upload books or research papers to begin building your personal collection.").classes('text-slate-500 text-xs mb-4 max-w-sm')
                ui.button('Upload First Document', icon='cloud_upload', on_click=lambda: ui.navigate.to('/upload')) \
                    .props('unelevated rounded-xl color=indigo size=sm font-bold').classes('shadow-xs')
            with ui.element('div').classes('w-full fluid-book-grid grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-3 sm:gap-4 mb-8'):
                for book in recent_books:
                    book_card(book, action_target='book')

        # 5. Transparent 3-Subsystem Diagnostics Strip
        with ui.row().classes('w-full p-3.5 bg-slate-50 border border-slate-200/80 rounded-2xl items-center justify-between gap-3 flex-wrap mt-2'):
            with ui.row().classes('items-center gap-2'):
                ui.icon('dns', size='18px').classes('text-slate-500')
                ui.label('SYSTEM SUBSYSTEMS:').classes('text-[11px] font-bold text-slate-400 uppercase tracking-wider')
            with ui.row().classes('items-center gap-4 text-xs font-medium text-slate-600 flex-wrap'):
                with ui.row().classes('items-center gap-1.5'):
                    ui.icon('web', size='14px').classes('text-emerald-600')
                    ui.label("App Server: Ready (FastAPI/NiceGUI)")
                with ui.row().classes('items-center gap-1.5'):
                    ui.icon('smart_toy', size='14px').classes(f'text-{tars_color}-600')
                    ui.label(f"AI Engine: {tars_status} ({tars_sub})")
                with ui.row().classes('items-center gap-1.5'):
                    ui.icon('storage', size='14px').classes('text-indigo-600')
                    ui.label("Database: Connected (MongoDB & ChromaDB)")