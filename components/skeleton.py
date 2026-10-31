"""
Skeleton loading placeholders for the book grid.

Renders shimmer cards that match the real `book_card` footprint (2:3 cover plus
two text lines) so the grid shows structured placeholders while data loads
instead of a blank gap, then gets replaced by real cards. The shimmer animation
and `.skeleton-shimmer` class live in `ui/theme.py`.
"""
from nicegui import ui


def skeleton_book_card() -> None:
    """A single shimmer placeholder shaped like a book card."""
    with ui.element('div').classes('relative w-full book-card-item'):
        with ui.element('div').classes(
            'w-full border border-slate-200 rounded-2xl overflow-hidden bg-white flex flex-col'
        ):
            # Cover placeholder (same 2:3 aspect ratio as a real cover)
            ui.element('div').classes('w-full aspect-[2/3] skeleton-shimmer')
            # Title + author line placeholders
            with ui.element('div').classes('p-2.5 sm:p-3.5 flex flex-col gap-2 w-full'):
                ui.element('div').classes('h-3 w-5/6 rounded skeleton-shimmer')
                ui.element('div').classes('h-2.5 w-2/3 rounded skeleton-shimmer')


def skeleton_book_grid(count: int = 12) -> None:
    """Renders `count` skeleton cards into the current container context."""
    for _ in range(max(0, count)):
        skeleton_book_card()
