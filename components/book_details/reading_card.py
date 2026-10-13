from nicegui import ui
from typing import Dict, Any, Optional, Callable


def render_reading_card(
    container: ui.column,
    book: Dict[str, Any],
    reading_progress: Optional[Dict[str, Any]],
    total_pages: int,
    on_status_change: Callable[[str], Any],
    on_page_change: Callable[[int], Any],
) -> None:
    """
    Renders an isolated, responsive Reading Status and Progress card.
    Updates in-place without triggering full page re-renders.
    """
    if container is None or not book:
        return

    container.clear()

    # 1. Normalize status
    raw_status = book.get('reading_status', 'want_to_read')
    if reading_progress and reading_progress.get('status'):
        raw_status = reading_progress.get('status')

    if raw_status in ('to_read', 'want_to_read'):
        normalized_status = 'want_to_read'
    elif raw_status in ('reading', 'currently_reading', 'in_progress'):
        normalized_status = 'reading'
    elif raw_status in ('completed', 'done', 'finished'):
        normalized_status = 'completed'
    else:
        normalized_status = 'want_to_read'

    # 2. Pages and progress percentage calculation
    current_page = 0
    progress_percent = 0.0

    if reading_progress:
        current_page = int(reading_progress.get('current_page', 0))
        progress_percent = float(reading_progress.get('progress_percent', 0.0))

    if normalized_status == 'completed':
        current_page = total_pages
        progress_percent = 100.0
    elif normalized_status == 'want_to_read':
        current_page = 0
        progress_percent = 0.0
    elif normalized_status == 'reading':
        if current_page <= 0:
            current_page = 1
        elif current_page > total_pages:
            current_page = total_pages
        progress_percent = round((current_page / max(total_pages, 1)) * 100.0, 1)

    # 3. Visual configuration
    status_configs = {
        'completed': {
            'badge_bg': 'bg-emerald-50',
            'badge_text': 'text-emerald-700',
            'badge_border': 'border-emerald-200',
            'badge_label': 'Completed',
            'badge_icon': 'check_circle',
            'bar_color': 'emerald',
            'subtext': f"Finished • {total_pages} pages (100%)",
        },
        'reading': {
            'badge_bg': 'bg-indigo-50',
            'badge_text': 'text-indigo-700',
            'badge_border': 'border-indigo-200',
            'badge_label': 'Currently Reading',
            'badge_icon': 'auto_stories',
            'bar_color': 'indigo',
            'subtext': f"Page {current_page} of {total_pages} ({progress_percent:.0f}%)",
        },
        'want_to_read': {
            'badge_bg': 'bg-amber-50',
            'badge_text': 'text-amber-700',
            'badge_border': 'border-amber-200',
            'badge_label': 'Want to Read',
            'badge_icon': 'bookmark',
            'bar_color': 'amber',
            'subtext': "Not started yet (0%)",
        },
    }
    cfg = status_configs[normalized_status]

    with container:
        with ui.card().classes(
            'w-full p-4 bg-slate-50/90 rounded-2xl border border-slate-200 shadow-xs flex flex-col gap-3 transition-all duration-300'
        ):
            # Header row: Title & Active Badge
            with ui.row().classes('w-full justify-between items-center'):
                with ui.row().classes('items-center gap-1.5'):
                    ui.icon('auto_stories', size='18px').classes('text-indigo-600')
                    ui.label('Reading Status').classes('text-xs font-black text-slate-800 uppercase tracking-wider')

                with ui.element('div').classes(
                    f'px-2.5 py-0.5 rounded-lg text-xs font-bold border flex items-center gap-1 {cfg["badge_bg"]} {cfg["badge_text"]} {cfg["badge_border"]}'
                ):
                    ui.icon(cfg['badge_icon'], size='13px')
                    ui.label(cfg['badge_label'])

            # Linear Progress Bar
            progress_fraction = min(max(progress_percent / 100.0, 0.0), 1.0)
            ui.linear_progress(value=progress_fraction, show_value=False)\
                .props(f'rounded color={cfg["bar_color"]} size=6px track-color=grey-3')

            # Subtext & Percentage Info
            with ui.row().classes('w-full justify-between items-center text-[11px] text-slate-500 font-medium'):
                ui.label(cfg['subtext'])
                ui.label(f"{progress_percent:.0f}%").classes('font-bold text-slate-700')

            # The 3 Status Selector Buttons
            with ui.row().classes('w-full grid grid-cols-3 gap-1.5 pt-1'):
                # 1. Want to Read
                wtr_active = (normalized_status == 'want_to_read')
                wtr_cls = (
                    'bg-amber-500 text-white shadow-sm ring-2 ring-amber-300/60 font-bold'
                    if wtr_active else
                    'bg-white text-slate-700 hover:bg-amber-50/70 hover:text-amber-700 border border-slate-200 font-semibold'
                )
                with ui.button(on_click=lambda: on_status_change('want_to_read'))\
                    .props('flat dense size=sm')\
                    .classes(f'flex flex-col items-center justify-center py-2 px-1 rounded-xl transition-all duration-200 {wtr_cls}'):
                    ui.icon('bookmark', size='16px').classes('shrink-0')
                    ui.label('Want to read').classes('text-[10px] sm:text-[11px] leading-tight text-center mt-0.5 truncate w-full')

                # 2. Currently Reading
                cr_active = (normalized_status == 'reading')
                cr_cls = (
                    'bg-indigo-600 text-white shadow-sm ring-2 ring-indigo-300/60 font-bold'
                    if cr_active else
                    'bg-white text-slate-700 hover:bg-indigo-50/70 hover:text-indigo-700 border border-slate-200 font-semibold'
                )
                with ui.button(on_click=lambda: on_status_change('reading'))\
                    .props('flat dense size=sm')\
                    .classes(f'flex flex-col items-center justify-center py-2 px-1 rounded-xl transition-all duration-200 {cr_cls}'):
                    ui.icon('auto_stories', size='16px').classes('shrink-0')
                    ui.label('Currently reading').classes('text-[10px] sm:text-[11px] leading-tight text-center mt-0.5 truncate w-full')

                # 3. Completed
                done_active = (normalized_status == 'completed')
                done_cls = (
                    'bg-emerald-600 text-white shadow-sm ring-2 ring-emerald-300/60 font-bold'
                    if done_active else
                    'bg-white text-slate-700 hover:bg-emerald-50/70 hover:text-emerald-700 border border-slate-200 font-semibold'
                )
                with ui.button(on_click=lambda: on_status_change('completed'))\
                    .props('flat dense size=sm')\
                    .classes(f'flex flex-col items-center justify-center py-2 px-1 rounded-xl transition-all duration-200 {done_cls}'):
                    ui.icon('check_circle', size='16px').classes('shrink-0')
                    ui.label('Completed').classes('text-[10px] sm:text-[11px] leading-tight text-center mt-0.5 truncate w-full')

            # Active page quick updater (appears when Currently Reading)
            if normalized_status == 'reading':
                with ui.row().classes('w-full items-center justify-between gap-2 pt-2 mt-1 border-t border-slate-200/60 flex-wrap'):
                    ui.label('Active page:').classes('text-[11px] text-slate-500 font-semibold')
                    with ui.row().classes('items-center gap-1.5'):
                        page_num = ui.number(value=current_page, min=1, step=1)\
                            .props('outlined dense size=xs').classes('w-20 text-xs bg-white rounded-lg')
                        ui.label(f"of {total_pages}").classes('text-xs text-slate-400 font-medium')
                        with ui.button(
                            icon='check',
                            on_click=lambda: on_page_change(int(page_num.value or 1))
                        ).props('flat round dense size=xs color=indigo').classes('bg-indigo-50 hover:bg-indigo-100 p-1'):
                            ui.tooltip('Save page progress')
