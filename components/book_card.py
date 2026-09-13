from nicegui import ui, app
from pathlib import Path
from typing import Dict, Any, Optional, Callable
from core.config import settings

def format_author(authors_val: Any) -> str:
    """Safely normalizes author metadata into a clean display string."""
    if not authors_val:
        return "Unknown"
    if isinstance(authors_val, list):
        if not authors_val:
            return "Unknown"
        first = authors_val[0]
        if isinstance(first, dict):
            return first.get('name', 'Unknown')
        return str(first)
    if isinstance(authors_val, str):
        return authors_val.strip()
    return str(authors_val)

def get_format_color(fmt: str) -> tuple:
    """Returns (text_color, bg_color) for format chips."""
    fmt = fmt.upper()
    if fmt == 'PDF':
        return ('text-rose-700', 'bg-rose-50 border-rose-200')
    elif fmt == 'EPUB':
        return ('text-amber-700', 'bg-amber-50 border-amber-200')
    elif fmt == 'DOCX':
        return ('text-sky-700', 'bg-sky-50 border-sky-200')
    elif fmt in ('PPTX', 'PPT'):
        return ('text-indigo-700', 'bg-indigo-50 border-indigo-200')
    return ('text-slate-600', 'bg-slate-100 border-slate-200')

def book_card(
    book: Dict[str, Any],
    action_target: str = 'book',
    on_delete: Optional[Callable[[str, str], Any]] = None
):
    """
    Unified high-performance Book Card component.
    Used across Home Dashboard, Library Collection, and Search results.
    
    Args:
        book: Book dictionary from MongoDB
        action_target: 'book' for book details page, 'read' for direct reader
        on_delete: Optional async/sync callback when delete button is pressed
    """
    book_id = str(book.get('id', ''))
    title = book.get('title', 'Untitled')
    author_display = book.get('display_author') or format_author(book.get('authors', []))
    
    # Safe Cover Detection
    books_data_dir = settings.BASE_DIR / 'data' / 'books'
    disk_cover = books_data_dir / book_id / 'cover.jpg'
    
    if disk_cover.exists():
        cover_url = f"/static_books/{book_id}/cover.jpg"
    elif book.get('cover_image') and not str(book.get('cover_image')).endswith('default_cover.png'):
        cover_url = book.get('cover_image')
    else:
        cover_url = "/static/default_cover.svg"

    target_url = f"/read/{book_id}" if action_target == 'read' else f"/book/{book_id}"
    
    # File Type Badge
    file_type = str(book.get('file_type', 'E-BOOK')).upper()
    if file_type == 'E-BOOK' and book.get('formats'):
        formats_keys = list(book.get('formats', {}).keys())
        if formats_keys:
            file_type = formats_keys[0].upper()
    txt_col, bg_col = get_format_color(file_type)

    # Card Wrapper with hover lift & shadow
    with ui.element('div').classes('relative group w-full'):
        with ui.card().classes(
            'w-full p-0 gap-0 border border-slate-200 dark:border-slate-800 shadow-sm '
            'hover:shadow-xl hover:-translate-y-1 transition-all duration-300 '
            'rounded-2xl overflow-hidden bg-white dark:bg-slate-900 cursor-pointer flex flex-col'
        ).on('click', lambda: ui.navigate.to(target_url)):
            
            # Cover Container (Fixed 2:3 aspect ratio adapted for mobile)
            with ui.element('div').classes('w-full h-44 xs:h-48 sm:h-52 md:h-56 relative overflow-hidden bg-slate-100 dark:bg-slate-800 flex items-center justify-center'):
                ui.image(cover_url).classes('w-full h-full object-cover transition-transform duration-500 group-hover:scale-105') \
                    .props('loading=lazy')
                
                # Format Badge overlay
                with ui.element('div').classes(f'absolute bottom-1.5 left-1.5 sm:bottom-2 sm:left-2 px-1.5 sm:px-2 py-0.5 rounded-md text-[9px] sm:text-[10px] font-black tracking-wider border shadow-sm backdrop-blur-md {txt_col} {bg_col}'):
                    ui.label(file_type)
                
                # Hover "Read" indicator overlay
                with ui.row().classes('absolute inset-0 bg-indigo-900/40 backdrop-blur-[2px] opacity-0 group-hover:opacity-100 transition-opacity duration-300 items-center justify-center gap-2'):
                    ui.button(
                        'Read' if action_target == 'read' else 'Details',
                        icon='menu_book' if action_target == 'read' else 'info'
                    ).props('rounded unelevated color=indigo size=sm text-color=white')

            # Content Info
            with ui.column().classes('p-2.5 sm:p-3.5 gap-0.5 sm:gap-1 w-full flex-grow justify-between bg-white dark:bg-slate-900'):
                with ui.column().classes('gap-0.5 w-full'):
                    ui.label(title).classes('font-bold text-xs sm:text-sm text-slate-800 dark:text-slate-100 leading-snug line-clamp-2 min-h-[2rem] sm:min-h-[2.5rem]')
                    ui.label(author_display).classes('text-[11px] sm:text-xs text-slate-500 dark:text-slate-400 font-medium truncate w-full')

        # Admin / Quick Delete Action Overlay
        if on_delete:
            with ui.button(icon='delete', on_click=lambda b_id=book_id, t=title: on_delete(b_id, t)) \
                    .props('flat round dense color=red size=sm') \
                    .classes('absolute top-1.5 right-1.5 sm:top-2 sm:right-2 opacity-70 sm:opacity-0 sm:group-hover:opacity-100 transition-all duration-200 bg-white/90 dark:bg-slate-800/90 shadow-md z-20 hover:scale-110'):
                ui.tooltip('Delete Book')