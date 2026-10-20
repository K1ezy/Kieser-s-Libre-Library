from nicegui import ui, app
from components.sidebar import sidebar
from components.header import header
from components.book_card import book_card, has_disk_cover, get_format_color
from core.database.mongo_manager import mongo_db
from datetime import datetime
from typing import Any, Dict

def get_greeting() -> str:
    """Returns a time-based greeting."""
    h = datetime.now().hour
    return "Good morning" if h < 12 else "Good afternoon" if h < 18 else "Good evening"

def get_reading_cover_url(book_doc: Dict[str, Any]) -> str:
    """Safely retrieves the best cover image URL for active reading cards."""
    b_id = str(book_doc.get('id') or book_doc.get('book_id') or book_doc.get('_id') or '')
    if has_disk_cover(b_id):
        return f"/static_books/{b_id}/cover.jpg"
    elif book_doc.get('cover_image') and not str(book_doc.get('cover_image')).endswith(('default_cover.png', 'default_cover.svg')):
        return book_doc.get('cover_image')
    elif book_doc.get('cover_url') and not str(book_doc.get('cover_url')).endswith(('default_cover.png', 'default_cover.svg')):
        return book_doc.get('cover_url')
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
                        f'group-hover:bg-{color}-600 group-hover:text-white transition-colors duration-200 shadow-2xs shrink-0 border border-{color}-100 flex items-center justify-center'
                    ):
                        if icon.endswith('.svg') or '/' in icon:
                            ui.image(icon).classes('w-5 h-5 object-contain group-hover:brightness-0 group-hover:invert transition-all').props('no-spinner')
                        else:
                            ui.icon(icon, size='20px')
                    with ui.column().classes('gap-0 min-w-0 flex-1'):
                        ui.label(title).classes('text-xs sm:text-sm font-bold text-slate-900 leading-tight truncate w-full')
                        ui.label(subtitle).classes('text-[11px] text-slate-500 font-medium truncate w-full')
                ui.icon('arrow_forward', size='16px').classes(
                    f'text-slate-300 group-hover:text-{color}-600 group-hover:translate-x-0.5 transition-all duration-200 shrink-0'
                )

def continue_reading_card(book_prog: Dict[str, Any]):
    """Renders a high-scannability active reading card with prominent cover art and direct resume action."""
    b_id = str(book_prog.get('id') or book_prog.get('book_id') or book_prog.get('_id') or '')
    b_title = book_prog.get('title', 'Untitled')
    b_author = book_prog.get('display_author') or 'Unknown'
    b_pct = min(100, max(0, round(float(book_prog.get('progress_percent', 0)))))
    b_cur = book_prog.get('current_page', 1)
    b_tot = max(1, book_prog.get('total_pages', 1))
    cover_url = get_reading_cover_url(book_prog)
    file_type = str(book_prog.get('file_type', 'EPUB')).upper()
    txt_col, bg_col = get_format_color(file_type)

    with ui.card().classes(
        'p-4 sm:p-5 bg-white border border-slate-200/90 rounded-2xl shadow-xs '
        'hover:shadow-md hover:border-indigo-300 transition-all flex flex-col justify-between gap-3 sm:gap-4'
    ):
        with ui.row().classes('items-stretch gap-4 sm:gap-5 w-full'):
            # Book Cover Thumbnail (Enlarged 2:3 aspect ratio with format tag and hover zoom)
            with ui.element('div').classes(
                'w-24 sm:w-28 md:w-32 lg:w-36 xl:w-40 aspect-[2/3] rounded-xl overflow-hidden bg-slate-100 '
                'relative shrink-0 border border-slate-200/70 shadow-xs cursor-pointer group'
            ).style('aspect-ratio: 2/3;').on('click', lambda id=b_id: ui.navigate.to(f"/read/{id}")):
                ui.image(cover_url).classes('w-full h-full object-cover group-hover:scale-105 transition-transform duration-300')
                with ui.element('div').classes(
                    f'absolute bottom-1.5 left-1.5 sm:bottom-2 sm:left-2 px-1.5 sm:px-2 py-0.5 rounded text-[8px] sm:text-[9px] font-black border shadow-xs {txt_col} {bg_col}'
                ):
                    ui.label(file_type)

            # Metadata & Location Tracking
            with ui.column().classes('gap-2 flex-1 min-w-0 justify-between self-stretch py-0.5'):
                with ui.column().classes('gap-1 w-full'):
                    ui.label(b_title).classes('font-bold text-sm sm:text-base md:text-lg text-slate-900 leading-snug line-clamp-2')
                    ui.label(f"by {b_author}").classes('text-xs sm:text-sm text-slate-500 truncate')

                with ui.column().classes('gap-2 w-full mt-auto'):
                    # Progress indicator & Page count
                    with ui.row().classes('items-center justify-between gap-2 w-full'):
                        with ui.element('span').classes('text-xs font-bold text-indigo-700 bg-indigo-50 border border-indigo-200 px-2 sm:px-2.5 py-0.5 rounded-md'):
                            ui.label(f"{b_pct}% read")
                        ui.label(f"Page {b_cur} of {b_tot}").classes('text-xs text-slate-500 font-medium')

                    # Linear progress bar
                    with ui.element('div').classes('w-full bg-slate-100 h-2 rounded-full overflow-hidden border border-slate-200/60'):
                        ui.element('div').classes('bg-gradient-to-r from-indigo-500 to-indigo-600 h-full rounded-full transition-all duration-300').style(f'width: {b_pct}%')

        # Action Buttons
        with ui.row().classes('w-full justify-end items-center gap-2 pt-2.5 border-t border-slate-100'):
            ui.button('Details', icon='info', on_click=lambda id=b_id: ui.navigate.to(f"/book/{id}"))\
                .props('flat rounded-xl size=sm color=grey-8 font-bold').classes('text-xs')
            ui.button('Resume Reading', icon='play_arrow', on_click=lambda id=b_id: ui.navigate.to(f"/read/{id}"))\
                .props('unelevated rounded-xl size=sm color=indigo font-bold')\
                .classes('text-xs shadow-xs')

async def home_page():
    app.storage.client['page_path'] = '/'
    
    drawer = sidebar()
    header(drawer_reference=drawer)

    import asyncio
    uid = app.storage.user.get('user_id') or app.storage.user.get('token')
    user_name = app.storage.user.get('username') or app.storage.user.get('name') or ''
    total_books, recent_books = 0, []
    active_reading_items = []

    try:
        tasks = [
            mongo_db.get_total_book_count(),
            mongo_db.get_recent_books(limit=14)
        ]
        if uid:
            tasks.append(mongo_db.progress.get_reading_history(uid, limit=8))

        results = await asyncio.gather(*tasks, return_exceptions=True)
        total_books = results[0] if isinstance(results[0], int) else 0
        recent_books = results[1] if isinstance(results[1], list) else []
        raw_history = results[2] if len(results) > 2 and isinstance(results[2], list) else []

        if raw_history:
            b_ids = [item.get('book_id') for item in raw_history if item.get('book_id')]
            books_map = await mongo_db.get_books_by_ids(b_ids) if b_ids else {}

            for item in raw_history:
                b_id = item.get('book_id')
                b_doc = books_map.get(b_id)
                if b_doc:
                    b_copy = dict(b_doc)
                    b_copy['progress_percent'] = item.get('progress_percent', 0)
                    b_copy['current_page'] = item.get('current_page', 1)
                    b_copy['total_pages'] = item.get('total_pages', 1)
                    active_reading_items.append(b_copy)
                if len(active_reading_items) >= 2:
                    break
    except Exception:
        total_books, recent_books = 0, []
        active_reading_items = []

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

            # Catalog Stats
            with ui.element('div').classes('flex items-center gap-2 shrink-0'):
                ui.link(f"{total_books} Books Cataloged", '/books').classes(
                    'no-underline text-xs font-bold px-3 py-1.5 rounded-full bg-white/10 hover:bg-white/20 border border-white/20 text-white transition-colors'
                )

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
                with ui.card().classes('w-full p-4 sm:p-5 bg-white border border-slate-200/80 rounded-2xl flex-row items-center gap-3.5 shadow-2xs'):
                    with ui.element('div').classes('p-2.5 rounded-xl bg-indigo-50 text-indigo-600 shrink-0 border border-indigo-100'):
                        ui.icon('bookmark_border', size='22px')
                    with ui.column().classes('gap-0'):
                        ui.label("No active reading sessions in progress").classes('text-xs sm:text-sm font-bold text-slate-800')
                        ui.label("Choose a book from your library archive to pick up where you left off.").classes('text-xs text-slate-500')

        # 3. Quick Actions (The 4 Core Pillars)
        ui.label('QUICK ACTIONS').classes('text-[11px] sm:text-xs font-bold text-slate-400 uppercase tracking-widest mb-3 px-1')
        with ui.grid().classes('w-full grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4 mb-6 sm:mb-8'):
            action_card("Ask TARS AI", "Chat with AI librarian", "/static/tars_icon.svg", "cyan", "/chat")
            action_card("Study Planner", "Spaced repetition decks", "event_note", "purple", "/planner")
            action_card("Library Pass", "Digital QR entrance", "badge", "emerald", "/attendance")
            action_card("Library Archive", "Browse multi-format books", "/static/Libre-Library_icon.svg", "sky", "/books")

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
        else:
            with ui.element('div').classes('w-full fluid-book-grid grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-3 sm:gap-4 mb-8'):
                for book in recent_books:
                    book_card(book, action_target='book')