from nicegui import ui
from typing import Optional, List, Any


def render_specs_grid(
    file_type: str,
    lang_str: str,
    pages_str: str,
    reading_time_str: str,
    file_size_str: str,
    formatted_date: str,
    publisher: Optional[str] = None,
    pub_year: Optional[Any] = None,
    shelves: Optional[List[str]] = None,
    genres: Optional[List[str]] = None,
) -> None:
    """
    Renders the responsive metadata pill grid, publisher info, and category/tag chips.
    """
    # 1. DOCUMENT SPECS PILL GRID
    with ui.row().classes('w-full gap-2 sm:gap-2.5 flex-wrap items-center'):
        # Format Pill
        with ui.row().classes('items-center gap-1.5 px-3 py-1.5 bg-indigo-50 text-indigo-700 border border-indigo-100 rounded-xl text-xs font-bold shadow-xs'):
            ui.icon('description', size='15px')
            ui.label(file_type)

        # Language Pill
        with ui.row().classes('items-center gap-1.5 px-3 py-1.5 bg-slate-100 text-slate-700 border border-slate-200 rounded-xl text-xs font-bold shadow-xs'):
            ui.icon('translate', size='15px')
            ui.label((lang_str or 'EN').upper())

        # Page Count Pill
        with ui.row().classes('items-center gap-1.5 px-3 py-1.5 bg-slate-100 text-slate-700 border border-slate-200 rounded-xl text-xs font-bold shadow-xs'):
            ui.icon('auto_stories', size='15px')
            ui.label(pages_str)

        # Reading Time Estimate Pill
        with ui.row().classes('items-center gap-1.5 px-3 py-1.5 bg-slate-100 text-slate-700 border border-slate-200 rounded-xl text-xs font-bold shadow-xs'):
            ui.icon('schedule', size='15px')
            ui.label(reading_time_str)

        # File Size Pill
        with ui.row().classes('items-center gap-1.5 px-3 py-1.5 bg-slate-100 text-slate-700 border border-slate-200 rounded-xl text-xs font-bold shadow-xs'):
            ui.icon('save', size='15px')
            ui.label(file_size_str)

        # Added Date Pill
        with ui.row().classes('items-center gap-1.5 px-3 py-1.5 bg-slate-100 text-slate-700 border border-slate-200 rounded-xl text-xs font-bold shadow-xs'):
            ui.icon('calendar_today', size='15px')
            ui.label(f"Added {formatted_date}")

    # 2. Publisher & Year Sub-row (if available)
    if publisher or pub_year:
        with ui.row().classes('items-center gap-2 text-xs font-semibold text-slate-500 mt-0.5'):
            ui.icon('business', size='15px').classes('text-slate-400')
            meta_parts = []
            if publisher:
                meta_parts.append(str(publisher))
            if pub_year:
                meta_parts.append(str(pub_year))
            ui.label(" • ".join(meta_parts))

    # 3. Tags & Categories Chips
    combined_tags: List[str] = []
    shelves_list = shelves if isinstance(shelves, list) else ([shelves] if shelves else [])
    genres_list = genres if isinstance(genres, list) else ([genres] if genres else [])
    
    for t in shelves_list + genres_list:
        if t and str(t).strip() and str(t).strip() not in combined_tags:
            combined_tags.append(str(t).strip())

    if combined_tags:
        with ui.row().classes('gap-1.5 flex-wrap items-center mt-1'):
            ui.label('Tags:').classes('text-[11px] font-black text-slate-400 uppercase tracking-widest mr-1')
            for tag in combined_tags[:8]:
                with ui.row().classes('items-center gap-1 bg-purple-50 text-purple-700 border border-purple-200 px-2.5 py-0.5 rounded-lg text-xs font-bold shadow-xs'):
                    ui.icon('tag', size='12px').classes('text-purple-500')
                    ui.label(tag)
