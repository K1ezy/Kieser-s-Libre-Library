import asyncio
import threading
from datetime import datetime
import uuid
import random
from typing import Dict, List, Optional, Any
from pathlib import Path
from nicegui import ui, app, events

# --- IMPORTS ---
try:
    from components.sidebar import sidebar
    from components.header import header
    from core.database.mongo_manager import mongo_db
    from core.services.planner_service import planner_service
except ImportError:
    pass


# ==============================================================================
# 1. OPTIMIZED 3D FLASHCARD CAROUSEL COMPONENT
# ==============================================================================
class FlashcardCarousel(ui.element):
    """
    State-of-the-art 3D interactive flashcard carousel:
    - True 3D perspective flip with cubic-bezier easing
    - Responsive centered layout with adaptive typography
    - Keyboard shortcut support (Space: Flip, Left/Right: Navigate)
    - Deck shuffle, progress tracking, and restart capabilities
    """
    def __init__(self, cards: List[Dict]):
        super().__init__('div')
        self.original_cards = list(cards) if cards else []
        self.cards = list(self.original_cards)
        self.current_index = 0
        self._is_flipped = False
        self.classes('w-full flex flex-col items-center justify-center')
        self.render()

    def get_text(self, side: str) -> str:
        if not self.cards or self.current_index >= len(self.cards):
            return "No Data"
        c = self.cards[self.current_index]
        if side == 'q':
            return c.get('q') or c.get('question') or c.get('front') or "No Question"
        return c.get('a') or c.get('answer') or c.get('back') or "No Answer"

    def render(self):
        self.clear()

        if not self.cards:
            with self:
                ui.icon('school', size='3.5rem').classes('text-slate-300 mb-2')
                ui.label("No flashcards found in this study deck.").classes('text-slate-400 text-sm')
            return

        with self:
            total_cards = len(self.cards)
            current_num = self.current_index + 1
            pct = round((current_num / max(total_cards, 1)) * 100)

            # --- PROGRESS INDICATOR (Zeigarnik Effect) ---
            with ui.column().classes('items-center gap-1.5 mb-4 sm:mb-6 w-full max-w-xl px-2'):
                with ui.row().classes('w-full justify-between items-center text-xs font-bold text-slate-500 px-1'):
                    with ui.row().classes('items-center gap-1.5'):
                        ui.icon('style', size='xs').classes('text-indigo-600')
                        ui.label(f"Card {current_num} of {total_cards}").classes('tracking-wide text-slate-700')
                    ui.label(f"{pct}% Complete").classes('text-indigo-600 font-extrabold')

                ui.linear_progress(value=current_num / max(total_cards, 1))\
                    .props('rounded color=indigo size=6px track-color=grey-3').classes('w-full shadow-xs')

            # --- 3D PERSPECTIVE CARD CONTAINER ---
            card_container = ui.card().classes(
                'w-full max-w-xl h-72 sm:h-80 md:h-[350px] relative cursor-pointer no-shadow border-0 bg-transparent select-none'
            ).on('click', self.flip)
            card_container.style('perspective: 1200px;')

            with card_container:
                # --- FRONT FACE (Question) ---
                self.front = ui.column().classes(
                    'absolute inset-0 w-full h-full bg-white border border-slate-200/90 shadow-lg hover:shadow-xl '
                    'rounded-3xl items-center justify-between p-6 sm:p-8 text-center transition-shadow duration-300'
                )
                self.front.style('backface-visibility: hidden; transition: transform 0.55s cubic-bezier(0.4, 0, 0.2, 1); transform-style: preserve-3d;')

                with self.front:
                    with ui.row().classes('w-full justify-between items-center mb-2'):
                        ui.label("QUESTION").classes('text-[11px] font-extrabold tracking-widest text-indigo-600 bg-indigo-50 px-2.5 py-0.5 rounded-full border border-indigo-100')
                        ui.label(f"#{current_num}").classes('text-xs font-bold text-slate-300')

                    # Question Content
                    with ui.column().classes('w-full flex-grow items-center justify-center overflow-y-auto my-auto px-2 max-h-[190px]'):
                        ui.label(self.get_text('q')).classes('text-base sm:text-xl font-semibold text-slate-800 leading-snug break-words')

                    with ui.row().classes('items-center gap-1 text-[11px] text-slate-400 mt-2'):
                        ui.icon('touch_app', size='xs').classes('text-slate-400')
                        ui.label("Click card or press Spacebar to flip").classes('font-medium')

                # --- BACK FACE (Answer) ---
                self.back = ui.column().classes(
                    'absolute inset-0 w-full h-full bg-gradient-to-br from-indigo-600 via-indigo-700 to-indigo-800 '
                    'shadow-xl rounded-3xl items-center justify-between p-6 sm:p-8 text-center'
                )
                self.back.style('backface-visibility: hidden; transition: transform 0.55s cubic-bezier(0.4, 0, 0.2, 1); transform: rotateY(180deg); transform-style: preserve-3d;')

                with self.back:
                    with ui.row().classes('w-full justify-between items-center mb-2'):
                        ui.label("EXPLANATION & ANSWER").classes('text-[11px] font-extrabold tracking-widest text-white bg-white/20 px-2.5 py-0.5 rounded-full')
                        ui.label(f"#{current_num}").classes('text-xs font-bold text-indigo-200')

                    # Answer Content
                    with ui.column().classes('w-full flex-grow items-center justify-center overflow-y-auto my-auto px-2 max-h-[190px]'):
                        ui.label(self.get_text('a')).classes('text-sm sm:text-lg font-medium text-white leading-relaxed break-words')

                    with ui.row().classes('items-center gap-1 text-[11px] text-indigo-200 mt-2'):
                        ui.icon('sync', size='xs').classes('text-indigo-200')
                        ui.label("Click card or press Spacebar to flip back").classes('font-medium')

            # --- CONTROLS BAR (Fitts's Law touch targets) ---
            with ui.row().classes('mt-4 sm:mt-6 gap-2 sm:gap-4 items-center justify-center flex-wrap w-full max-w-xl'):
                # Previous Button
                ui.button(icon='arrow_back', on_click=self.prev_card)\
                    .props('round flat color=indigo size=md')\
                    .tooltip('Previous Card (Left Arrow)')\
                    .classes('bg-white border border-slate-200 shadow-xs hover:bg-slate-50')

                # Flip Card Action
                ui.button('Flip Card', icon='sync', on_click=self.flip)\
                    .props('unelevated rounded-xl color=indigo size=md')\
                    .classes('px-6 sm:px-8 font-bold shadow-sm hover:shadow-md transition-all')\
                    .tooltip('Flip Card (Spacebar)')

                # Next Button
                ui.button(icon='arrow_forward', on_click=self.next_card)\
                    .props('round flat color=indigo size=md')\
                    .tooltip('Next Card (Right Arrow)')\
                    .classes('bg-white border border-slate-200 shadow-xs hover:bg-slate-50')

                # Shuffle Button
                ui.button(icon='shuffle', on_click=self.shuffle_cards)\
                    .props('round flat color=grey-7 size=sm')\
                    .tooltip('Shuffle Deck')\
                    .classes('ml-2 bg-white border border-slate-200 shadow-xs hover:bg-slate-50')

                # Reset to Card 1
                ui.button(icon='replay', on_click=self.reset_deck)\
                    .props('round flat color=grey-7 size=sm')\
                    .tooltip('Restart from Card 1')\
                    .classes('bg-white border border-slate-200 shadow-xs hover:bg-slate-50')

            # Keyboard listener
            ui.keyboard(on_key=self._handle_key)

        self._apply_rotation()

    def _handle_key(self, e):
        try:
            if not e.action.keydown or e.action.repeat:
                return
            key = e.key.name if hasattr(e.key, 'name') else str(e.key)
            if key in ('Space', ' '):
                self.flip()
            elif key in ('ArrowRight', 'Right'):
                self.next_card()
            elif key in ('ArrowLeft', 'Left'):
                self.prev_card()
        except Exception:
            pass

    def flip(self):
        self._is_flipped = not self._is_flipped
        self._apply_rotation()

    def _apply_rotation(self):
        if hasattr(self, 'front') and hasattr(self, 'back'):
            if self._is_flipped:
                self.front.style('backface-visibility: hidden; transition: transform 0.55s cubic-bezier(0.4, 0, 0.2, 1); transform: rotateY(180deg);')
                self.back.style('backface-visibility: hidden; transition: transform 0.55s cubic-bezier(0.4, 0, 0.2, 1); transform: rotateY(0deg);')
            else:
                self.front.style('backface-visibility: hidden; transition: transform 0.55s cubic-bezier(0.4, 0, 0.2, 1); transform: rotateY(0deg);')
                self.back.style('backface-visibility: hidden; transition: transform 0.55s cubic-bezier(0.4, 0, 0.2, 1); transform: rotateY(180deg);')

    def next_card(self):
        if not self.cards: return
        self.current_index = (self.current_index + 1) % len(self.cards)
        self._is_flipped = False
        self.render()

    def prev_card(self):
        if not self.cards: return
        self.current_index = (self.current_index - 1) % len(self.cards)
        self._is_flipped = False
        self.render()

    def shuffle_cards(self):
        if len(self.cards) > 1:
            random.shuffle(self.cards)
            self.current_index = 0
            self._is_flipped = False
            ui.notify("Deck shuffled!", type='info', duration=2)
            self.render()

    def reset_deck(self):
        self.cards = list(self.original_cards)
        self.current_index = 0
        self._is_flipped = False
        self.render()


# ==============================================================================
# 2. STUDY PLANNER PAGE & STUDY DECK WORKFLOW
# ==============================================================================
class StudyPlannerPage:
    """
    Unified Study Planner & Flashcard Management:
    - Lightning-fast flashcard creation (<5-8s) via optimized TARS AI pipeline
    - Coherent, centered, and modern modal layout for deck generation and study
    - Robust library document selector with instant button activation & real-time tooltips
    - Seamless file upload handling (PDF, DOCX, PPTX, EPUB, TXT)
    """
    def __init__(self):
        self.tasks: List[Dict[str, Any]] = []
        self.container = None
        self.add_dialog = None
        self.library_options: Dict[str, str] = {}
        self.library_select = None
        self.quantity_select = None
        self.generate_btn = None
        self.generate_btn_tooltip = None
        self.selected_doc_badge = None
        self.client = None
        self.bg_status_container = None
        self.active_generations: Dict[str, Dict[str, Any]] = {}

    def safe_notify(self, message: str, type: str = 'info', **kwargs):
        """Dispatches notification safely within client context even if slot elements were deleted."""
        try:
            client = self.client or ui.context.client
            if client and getattr(client, 'has_socket_connection', False):
                with client:
                    ui.notify(message, type=type, **kwargs)
            else:
                ui.notify(message, type=type, **kwargs)
        except Exception:
            pass

    async def init(self):
        try:
            if mongo_db.db is None:
                await mongo_db.initialize()
            uid = app.storage.user.get('user_id')
            if uid:
                self.tasks = await mongo_db.get_tasks(user_id=uid)
                self.render_dashboard()
            else:
                ui.navigate.to('/login')
        except Exception as e:
            print(f"Error initializing planner: {e}")
            if self.container:
                self.container.clear()
                with self.container:
                    ui.label("Error loading planner tasks. Please refresh.").classes('text-red-500 font-semibold')

    async def add_task(self, title: str, date: str):
        if not title or not title.strip():
            self.safe_notify("Topic name cannot be empty.", type='warning')
            return
        try:
            uid = app.storage.user.get('user_id')
            if not uid:
                self.safe_notify("Authentication required.", type='warning')
                return
            created = await mongo_db.add_task(title=title.strip(), due_date=date or "", user_id=uid)
            if self.add_dialog:
                self.add_dialog.close()
            if created:
                self.safe_notify("Topic added successfully!", type='positive')
                await self.init()
            else:
                self.safe_notify("Could not add topic.", type='negative')
        except Exception as e:
            self.safe_notify(f"Could not add topic: {e}", type='negative')

    async def delete_task(self, task_id: str):
        try:
            success = await mongo_db.delete_task(task_id)
            if success:
                self.safe_notify("Topic and associated deck deleted.", type='info')
                await self.init()
            else:
                self.safe_notify("Failed to delete topic.", type='negative')
        except Exception as e:
            self.safe_notify(f"Error deleting topic: {e}", type='negative')

    async def open_study_modal(self, task: Dict[str, Any]):
        """Opens study modal with existing deck, generation progress, or creation screen."""
        task_id = task['id']
        active_gen = self.active_generations.get(task_id)
        is_generating = bool(active_gen and active_gen.get('status') == 'generating')

        deck = None
        if not is_generating:
            deck = await planner_service.get_deck(task_id)

        target_client = self.client or ui.context.client
        with target_client:
            with ui.dialog() as dialog, ui.card().classes(
                'w-[calc(100vw-1.5rem)] sm:w-full max-w-4xl h-[92vh] sm:h-[86vh] flex flex-col p-0 overflow-hidden '
                'rounded-3xl bg-white border border-slate-200/90 shadow-2xl transition-all'
            ):
                # --- MODAL HEADER ---
                with ui.row().classes('w-full border-b border-slate-200/80 px-4 sm:px-6 py-3.5 justify-between items-center bg-white z-10 shrink-0'):
                    with ui.row().classes('items-center gap-2.5 min-w-0'):
                        with ui.element('div').classes('p-2 rounded-xl bg-indigo-50 border border-indigo-100 flex items-center justify-center shrink-0'):
                            ui.icon('school', size='sm').classes('text-indigo-600')
                        with ui.column().classes('gap-0 min-w-0'):
                            ui.label(task['title']).classes('text-base sm:text-lg font-bold text-slate-800 truncate max-w-[220px] sm:max-w-md')
                            card_count = len(deck['cards']) if (deck and 'cards' in deck) else 0
                            status_sub = (
                                f"{card_count} Interactive Flashcards" if card_count > 0 else (
                                    "⚡ Synthesizing Study Cards..." if is_generating else "Study Deck Generator"
                                )
                            )
                            ui.label(status_sub).classes('text-[11px] text-slate-400 font-medium')

                    with ui.row().classes('items-center gap-1.5'):
                        # Regenerate / replace button (only visible if deck exists and not generating)
                        self.modal_refresh_btn = ui.button(icon='refresh', on_click=lambda: self._show_upload_screen(content_area, task, dialog))\
                            .props('flat round color=grey-7 size=sm')\
                            .tooltip('Regenerate or change source document')
                        self.modal_refresh_btn.set_visibility(bool(deck and deck.get('cards')) and not is_generating)

                        # Close / Minimize button
                        def handle_close_click():
                            if task_id in self.active_generations and self.active_generations[task_id].get('status') == 'generating':
                                self._minimize_generation(task_id, dialog)
                            else:
                                dialog.close()

                        ui.button(icon='close', on_click=handle_close_click).props('flat round color=grey-7 size=sm')

                # --- MODAL CONTENT AREA (Perfect Centering) ---
                content_area = ui.column().classes(
                    'w-full flex-grow flex flex-col items-center justify-center bg-slate-50/70 p-4 sm:p-8 overflow-y-auto'
                )

                # Clean backdrop close / escape handling: minimize if generating
                def on_dialog_close():
                    if task_id in self.active_generations and self.active_generations[task_id].get('status') == 'generating':
                        if not self.active_generations[task_id].get('minimized', False):
                            self.active_generations[task_id]['minimized'] = True
                            self._render_floating_widget()

                dialog.on('close', on_dialog_close)

                with content_area:
                    if is_generating and active_gen:
                        active_gen['minimized'] = False
                        active_gen['dialog'] = dialog
                        active_gen['container'] = content_area
                        self._render_generation_loading_screen(content_area, task, dialog, task_id)
                        self._render_floating_widget()
                    elif deck and 'cards' in deck and len(deck['cards']) > 0:
                        self._render_carousel_view(content_area, task, dialog, deck)
                    else:
                        self._show_upload_screen(content_area, task, dialog)

            dialog.open()

    def _render_carousel_view(self, container, task, dialog, deck):
        """Renders flashcards inside the centered container."""
        container.clear()
        if hasattr(self, 'modal_refresh_btn') and self.modal_refresh_btn:
            self.modal_refresh_btn.set_visibility(True)
        with container:
            FlashcardCarousel(deck['cards'])

    def _show_upload_screen(self, container, task, dialog):
        """Renders the optimized study deck generator screen with 2 side-by-side options."""
        container.clear()
        if hasattr(self, 'modal_refresh_btn') and self.modal_refresh_btn:
            self.modal_refresh_btn.set_visibility(False)

        with container:
            # Top Banner
            with ui.column().classes('items-center text-center mb-6 max-w-lg mx-auto gap-1'):
                with ui.element('div').classes('p-3 rounded-2xl bg-indigo-50 border border-indigo-100 mb-1'):
                    ui.icon('auto_awesome', size='2.5rem').classes('text-indigo-600')
                ui.label("Generate AI Study Flashcards").classes('text-xl sm:text-2xl font-black text-slate-900 tracking-tight')
                ui.label(
                    "Choose an existing textbook from your library or upload new lecture notes to automatically synthesize 3D flashcards."
                ).classes('text-xs sm:text-sm text-slate-500 leading-relaxed max-w-md')

            # --- DECK CONFIGURATION (Quantity Dropdown: Max 30) ---
            with ui.row().classes(
                'w-full max-w-3xl items-center justify-between bg-white border border-slate-200/90 '
                'rounded-2xl p-3.5 sm:p-4 shadow-xs mb-5 flex-wrap gap-3'
            ):
                with ui.row().classes('items-center gap-3 min-w-0'):
                    with ui.element('div').classes('p-2 sm:p-2.5 rounded-xl bg-indigo-50 border border-indigo-100 flex items-center justify-center shrink-0'):
                        ui.icon('tune', size='sm').classes('text-indigo-600')
                    with ui.column().classes('gap-0 min-w-0'):
                        ui.label("Flashcard Quantity").classes('font-bold text-slate-800 text-xs sm:text-sm')
                        ui.label("Set target deck size (up to 30 flashcards maximum)").classes('text-[11px] text-slate-400')

                self.quantity_select = ui.select(
                    options={
                        5: "5 Flashcards (Quick)",
                        10: "10 Flashcards (Standard)",
                        15: "15 Flashcards (Recommended)",
                        20: "20 Flashcards (In-depth)",
                        25: "25 Flashcards (Comprehensive)",
                        30: "30 Flashcards (Maximum)",
                    },
                    value=15,
                    label="Deck Size"
                ).props('outlined dense options-dense bg-color=white rounded').classes('w-48 sm:w-56 text-xs sm:text-sm font-semibold')

            def get_target_quantity() -> int:
                try:
                    if self.quantity_select and self.quantity_select.value:
                        return min(30, max(1, int(self.quantity_select.value)))
                except Exception:
                    pass
                return 15

            def on_quantity_change(e):
                val = self.library_select.value if self.library_select else None
                if val and str(val) not in ('loading', 'none', 'error', ''):
                    doc_title = self.library_options.get(str(val), 'Selected Document')
                    if self.generate_btn_tooltip:
                        self.generate_btn_tooltip.text = f"Generate {get_target_quantity()} flashcards from: {doc_title}"

            self.quantity_select.on_value_change(on_quantity_change)

            # Options Grid (Side-by-side on desktop, stacked on mobile)
            with ui.row().classes('w-full max-w-3xl justify-center gap-5 sm:gap-6 items-stretch flex-col md:flex-row'):

                # ==============================================================
                # OPTION 1: SELECT FROM LIBRARY (Primary Recommended Flow)
                # ==============================================================
                with ui.card().classes(
                    'flex-1 flex flex-col justify-between p-5 sm:p-6 rounded-2xl bg-white border border-slate-200/90 shadow-sm hover:shadow-md transition-shadow'
                ):
                    with ui.column().classes('w-full gap-2'):
                        with ui.row().classes('items-center gap-2 mb-1'):
                            with ui.element('div').classes('p-2 rounded-xl bg-purple-50 border border-purple-100'):
                                ui.icon('library_books', size='sm').classes('text-purple-600')
                            with ui.column().classes('gap-0'):
                                ui.label("From Library").classes('font-bold text-slate-800 text-sm sm:text-base')
                                ui.label("Select an existing catalog document").classes('text-[11px] text-slate-400')

                        # Searchable library dropdown
                        self.library_select = ui.select(
                            {'loading': 'Loading library catalog...'},
                            label="Choose Document",
                            with_input=True
                        ).props('outlined dense options-dense bg-color=white rounded').classes('w-full mt-2 text-sm')

                        # Selected Document Pill Indicator
                        self.selected_doc_badge = ui.label("").classes(
                            'text-[11px] font-semibold text-emerald-700 bg-emerald-50 border border-emerald-200/60 '
                            'px-2.5 py-1 rounded-lg w-full truncate'
                        )
                        self.selected_doc_badge.set_visibility(False)

                    # Reactive button state controller
                    def on_select_change(e):
                        val = e.value if hasattr(e, 'value') else self.library_select.value
                        if val and str(val) not in ('loading', 'none', 'error', ''):
                            doc_title = self.library_options.get(str(val), 'Selected Document')
                            if self.generate_btn:
                                self.generate_btn.enable()
                                self.generate_btn.props('unelevated color=indigo')
                                self.generate_btn.classes(remove='opacity-50 cursor-not-allowed')
                            if self.generate_btn_tooltip:
                                self.generate_btn_tooltip.text = f"Generate {get_target_quantity()} flashcards from: {doc_title}"
                            if self.selected_doc_badge:
                                self.selected_doc_badge.text = f"✓ Ready: {doc_title}"
                                self.selected_doc_badge.set_visibility(True)
                        else:
                            if self.generate_btn:
                                self.generate_btn.disable()
                                self.generate_btn.props('outline color=grey')
                                self.generate_btn.classes(add='opacity-50 cursor-not-allowed')
                            if self.generate_btn_tooltip:
                                self.generate_btn_tooltip.text = "Please choose a document from the dropdown above"
                            if self.selected_doc_badge:
                                self.selected_doc_badge.set_visibility(False)

                    self.library_select.on_value_change(on_select_change)

                    # Generate Button (Assign variable FIRST, then disable safely!)
                    with ui.column().classes('w-full mt-4'):
                        self.generate_btn = ui.button(
                            'Generate Flashcards',
                            icon='auto_awesome',
                            on_click=lambda: self._start_deck_generation(
                                self.library_select.value,
                                task,
                                container,
                                dialog,
                                is_upload=False,
                                quantity=get_target_quantity()
                            )
                        ).props('outline color=grey rounded-xl size=md').classes('w-full font-bold opacity-50 cursor-not-allowed py-2.5 transition-all')
                        self.generate_btn.disable()

                        with self.generate_btn:
                            self.generate_btn_tooltip = ui.tooltip("Please select a document from the library above")

                # ==============================================================
                # OPTION 2: UPLOAD NEW FILE
                # ==============================================================
                with ui.card().classes(
                    'flex-1 flex flex-col justify-between p-5 sm:p-6 rounded-2xl bg-white border border-slate-200/90 shadow-sm hover:shadow-md transition-shadow'
                ):
                    with ui.column().classes('w-full gap-2'):
                        with ui.row().classes('items-center gap-2 mb-1'):
                            with ui.element('div').classes('p-2 rounded-xl bg-indigo-50 border border-indigo-100'):
                                ui.icon('cloud_upload', size='sm').classes('text-indigo-600')
                            with ui.column().classes('gap-0'):
                                ui.label("Upload File").classes('font-bold text-slate-800 text-sm sm:text-base')
                                ui.label("PDF, DOCX, PPTX, EPUB, TXT").classes('text-[11px] text-slate-400')

                        async def handle_upload(e: events.UploadEventArguments):
                            await self._start_deck_generation(
                                e,
                                task,
                                container,
                                dialog,
                                is_upload=True,
                                quantity=get_target_quantity()
                            )

                        ui.upload(
                            label="Drop file here or browse",
                            auto_upload=True,
                            on_upload=handle_upload,
                            max_file_size=200_000_000
                        ).props('color=indigo accept=.pdf,.txt,.docx,.pptx,.epub flat bordered rounded').classes('w-full rounded-xl')

                    # Formats indicator chips
                    with ui.row().classes('w-full gap-1.5 justify-center mt-3 pt-2 border-t border-slate-100 flex-wrap'):
                        for fmt in ['PDF', 'DOCX', 'PPTX', 'EPUB', 'TXT']:
                            ui.label(fmt).classes('text-[10px] font-bold text-slate-400 bg-slate-100 px-2 py-0.5 rounded-md')

            # Fetch and populate library items asynchronously
            ui.timer(0.05, self._populate_library_dropdown, once=True)

    async def _populate_library_dropdown(self):
        """Fetches all valid library documents and binds to selection dropdown."""
        try:
            all_books = await mongo_db.get_all_books(limit=1000)
            options: Dict[str, str] = {}

            for b in all_books:
                b_id = b.get('id') or (str(b.get('_id')) if b.get('_id') else None)
                if not b_id:
                    continue

                title = (b.get('title') or 'Untitled Document').strip()
                ftype = (b.get('file_type') or '').upper()

                if not ftype:
                    formats = b.get('formats') or {}
                    if isinstance(formats, dict):
                        for k, v in formats.items():
                            val_str = str(v).lower()
                            if 'pdf' in k.lower() or 'pdf' in val_str: ftype = 'PDF'; break
                            elif 'epub' in k.lower() or 'epub' in val_str: ftype = 'EPUB'; break
                            elif 'docx' in k.lower() or 'docx' in val_str: ftype = 'DOCX'; break
                            elif 'pptx' in k.lower() or 'pptx' in val_str: ftype = 'PPTX'; break
                            elif 'txt' in k.lower() or 'txt' in val_str: ftype = 'TXT'; break

                type_label = f" [{ftype}]" if ftype else ""
                options[str(b_id)] = f"{title}{type_label}"

            # Sort alphabetically by title
            sorted_options = dict(sorted(options.items(), key=lambda item: item[1].lower()))
            self.library_options = sorted_options

            if self.library_select:
                if sorted_options:
                    self.library_select.options = sorted_options
                    self.library_select.update()

                    # Check for pre-selection from user storage (e.g. from Summarizer page)
                    pre_book_id = None
                    try:
                        pre_book_id = app.storage.user.pop('planner_book_id', None)
                    except Exception:
                        pass

                    if pre_book_id and str(pre_book_id) in sorted_options:
                        self.library_select.value = str(pre_book_id)
                        self.library_select.update()
                else:
                    self.library_select.options = {'none': 'No library documents found'}
                    self.library_select.value = 'none'
                    self.library_select.disable()
                    self.library_select.update()

        except Exception as e:
            print(f"Error loading library items: {e}")
            if self.library_select:
                self.library_select.options = {'error': 'Error loading documents'}
                self.library_select.value = 'error'
                self.library_select.disable()
                self.library_select.update()

    def _render_generation_loading_screen(self, container, task: Dict[str, Any], dialog, task_id: str):
        """Renders live generation status with Cancel and Minimize action controls."""
        container.clear()
        if hasattr(self, 'modal_refresh_btn') and self.modal_refresh_btn:
            self.modal_refresh_btn.set_visibility(False)

        info = self.active_generations.get(task_id, {})
        curr_msg = info.get('status_msg', 'Analyzing content and extracting concepts with TARS AI...')
        target_qty = info.get('quantity', 15)

        with container:
            with ui.column().classes('items-center justify-center p-6 sm:p-10 text-center max-w-lg mx-auto w-full'):
                with ui.element('div').classes('p-4 rounded-2xl bg-indigo-50 border border-indigo-100 mb-4 animate-pulse'):
                    ui.spinner('dots', size='3.5em', color='indigo')

                ui.label(f"Synthesizing {target_qty} Study Flashcards").classes('text-xl sm:text-2xl font-black text-slate-800 tracking-tight')
                ui.label(f"Topic: {task['title']} • Target: {target_qty} Cards (Max 30)").classes('text-xs font-semibold text-slate-400 mt-0.5 truncate max-w-md')

                status_label = ui.label(curr_msg).classes(
                    'text-xs sm:text-sm font-semibold text-indigo-600 mt-3 px-3 py-1.5 bg-indigo-50/70 border border-indigo-100 rounded-xl max-w-sm truncate'
                )
                info['status_label'] = status_label

                ui.label("⚡ Fast AI generation takes ~4–8 seconds. You can minimize this window to keep browsing your library or working in the background.").classes(
                    'text-xs text-slate-400 mt-3 font-normal max-w-sm leading-relaxed'
                )

                # Action Buttons: Minimize & Cancel
                with ui.row().classes('items-center justify-center gap-3 mt-6 flex-wrap'):
                    ui.button(
                        "Minimize to Background",
                        icon='unfold_less',
                        on_click=lambda: self._minimize_generation(task_id, dialog)
                    ).props('outline color=indigo rounded-xl size=md').classes('font-bold px-4 py-2 hover:bg-indigo-50 transition-all')

                    ui.button(
                        "Cancel Generation",
                        icon='close',
                        on_click=lambda: self._cancel_generation(task_id, container, task, dialog)
                    ).props('flat color=negative rounded-xl size=md').classes('font-bold px-4 py-2 hover:bg-rose-50 text-rose-600 transition-all')

    def _minimize_generation(self, task_id: str, dialog):
        """Minimizes the active generation modal to a sleek floating background status widget."""
        if task_id in self.active_generations:
            self.active_generations[task_id]['minimized'] = True
        try:
            dialog.close()
        except Exception:
            pass
        self._render_floating_widget()
        task_title = self.active_generations.get(task_id, {}).get('task_title', 'Study Topic')
        self.safe_notify(
            f"⚡ Generating flashcards for '{task_title}' in background.",
            type='info',
            duration=3
        )

    def _cancel_generation(self, task_id: str, container=None, task=None, dialog=None):
        """Cancels active generation immediately, stops background tasks, and cleans up."""
        gen_info = self.active_generations.pop(task_id, None)
        if gen_info:
            cancel_event = gen_info.get('cancel_event')
            if cancel_event:
                cancel_event.set()
            async_task = gen_info.get('async_task')
            if async_task and not async_task.done():
                async_task.cancel()
            if not container:
                container = gen_info.get('container')
            if not task:
                task = gen_info.get('task')
            if not dialog:
                dialog = gen_info.get('dialog')

        self._render_floating_widget()
        self.safe_notify("Generation cancelled.", type='info')

        # If dialog is still open, restore upload/selection screen
        if dialog and getattr(dialog, 'value', False) and container and task:
            try:
                client = self.client or ui.context.client
                if client and getattr(client, 'has_socket_connection', False):
                    with client:
                        self._show_upload_screen(container, task, dialog)
                else:
                    self._show_upload_screen(container, task, dialog)
            except Exception as e:
                print(f"Error resetting to upload screen: {e}")

    def _render_floating_widget(self):
        """Renders responsive floating progress pills for background generation tasks."""
        if not self.bg_status_container:
            return

        client = self.client or ui.context.client
        if not client or not getattr(client, 'has_socket_connection', False):
            return

        try:
            with client:
                self.bg_status_container.clear()
                if not self.active_generations:
                    return

                with self.bg_status_container:
                    for task_id, info in list(self.active_generations.items()):
                        # Only show if minimized or ready
                        if not info.get('minimized') and info.get('status') != 'ready':
                            continue

                        status = info.get('status')
                        task = info.get('task', {})
                        task_title = info.get('task_title', 'Study Topic')

                        with ui.card().classes(
                            'bg-white/95 backdrop-blur-md border border-indigo-200/90 shadow-2xl rounded-2xl '
                            'p-3.5 sm:p-4 flex flex-row items-center gap-3 w-80 sm:w-96 transition-all duration-300'
                        ):
                            if status == 'generating':
                                with ui.element('div').classes('p-2 rounded-xl bg-indigo-50 border border-indigo-100 shrink-0'):
                                    ui.spinner('dots', size='1.6em', color='indigo')

                                with ui.column().classes('gap-0 flex-1 min-w-0'):
                                    target_qty = info.get('quantity', 15)
                                    ui.label(f"{task_title} ({target_qty} cards)").classes('text-xs sm:text-sm font-bold text-slate-800 truncate')
                                    ui.label(info.get('status_msg', 'Generating flashcards...')).classes(
                                        'text-[11px] text-indigo-600 font-semibold truncate animate-pulse'
                                    )

                                with ui.row().classes('items-center gap-1 shrink-0'):
                                    ui.button(icon='open_in_full', on_click=lambda t=task: self.open_study_modal(t))\
                                        .props('flat round color=indigo size=sm')\
                                        .tooltip('Open Generation Window')

                                    ui.button(icon='close', on_click=lambda t_id=task_id: self._cancel_generation(t_id))\
                                        .props('flat round color=grey-7 size=sm')\
                                        .tooltip('Cancel Generation')

                            elif status == 'ready':
                                with ui.element('div').classes('p-2 rounded-xl bg-emerald-50 border border-emerald-100 shrink-0'):
                                    ui.icon('check_circle', size='sm').classes('text-emerald-600')

                                with ui.column().classes('gap-0 flex-1 min-w-0'):
                                    ui.label(task_title).classes('text-xs sm:text-sm font-bold text-slate-800 truncate')
                                    card_ct = info.get('card_ct', 0)
                                    ui.label(f"🎉 {card_ct} Flashcards Ready!").classes('text-[11px] text-emerald-600 font-bold truncate')

                                with ui.row().classes('items-center gap-1.5 shrink-0'):
                                    ui.button(
                                        'Study',
                                        icon='school',
                                        on_click=lambda t=task, t_id=task_id: self._open_completed_deck(t, t_id)
                                    ).props('unelevated rounded-lg size=sm color=indigo font-bold')

                                    ui.button(icon='close', on_click=lambda t_id=task_id: self._dismiss_generation(t_id))\
                                        .props('flat round color=grey-6 size=xs')\
                                        .tooltip('Dismiss')

        except Exception as ex:
            print(f"Error rendering floating widget: {ex}")

    async def _open_completed_deck(self, task: Dict[str, Any], task_id: str):
        """Opens study modal with ready flashcards and clears background status entry."""
        try:
            await self.open_study_modal(task)
        finally:
            self.active_generations.pop(task_id, None)
            self._render_floating_widget()

    def _dismiss_generation(self, task_id: str):
        """Dismisses the background task notification pill."""
        self.active_generations.pop(task_id, None)
        self._render_floating_widget()

    async def _start_deck_generation(
        self,
        source_data,
        task: Dict[str, Any],
        container,
        dialog,
        is_upload: bool,
        quantity: int = 15
    ):
        """Initializes and kicks off flashcard generation as a resilient background task."""
        task_id = task['id']

        if task_id in self.active_generations and self.active_generations[task_id].get('status') == 'generating':
            self.safe_notify("Flashcard generation is already in progress for this topic.", type='warning')
            return

        cancel_event = threading.Event()
        target_qty = min(30, max(1, int(quantity or 15)))

        self.active_generations[task_id] = {
            'task': task,
            'task_id': task_id,
            'task_title': task.get('title', 'Study Topic'),
            'cancel_event': cancel_event,
            'quantity': target_qty,
            'status': 'generating',
            'status_msg': 'Analyzing content and extracting concepts with TARS AI...',
            'dialog': dialog,
            'container': container,
            'minimized': False,
            'async_task': None,
        }

        # Show live generation view inside dialog
        self._render_generation_loading_screen(container, task, dialog, task_id)

        # Launch background generation task
        async_task = asyncio.create_task(
            self._run_deck_generation(
                task_id,
                source_data,
                task,
                container,
                dialog,
                is_upload,
                cancel_event,
                quantity=target_qty
            )
        )
        self.active_generations[task_id]['async_task'] = async_task

    async def _run_deck_generation(
        self,
        task_id: str,
        source_data: Any,
        task: Dict[str, Any],
        container,
        dialog,
        is_upload: bool,
        cancel_event: threading.Event,
        quantity: int = 15
    ):
        """Background worker executing document resolution, fast extraction, LLM synthesis, and persistence."""
        client = self.client or ui.context.client
        target_qty = min(30, max(1, int(quantity or 15)))

        def update_status(msg: str):
            info = self.active_generations.get(task_id)
            if info:
                info['status_msg'] = msg
                status_lbl = info.get('status_label')
                if status_lbl:
                    try:
                        status_lbl.text = msg
                    except Exception:
                        pass
                if info.get('minimized'):
                    try:
                        self._render_floating_widget()
                    except Exception:
                        pass

        file_obj = source_data

        if not is_upload:
            book_id = str(source_data).strip() if source_data else None
            if not book_id or book_id in ('none', 'error', 'loading'):
                self.safe_notify("Please select a valid document from the list.", type='warning')
                self.active_generations.pop(task_id, None)
                self._render_floating_widget()
                if getattr(dialog, 'value', False):
                    try:
                        self._show_upload_screen(container, task, dialog)
                    except Exception:
                        pass
                return

            try:
                book_doc = await mongo_db.get_book_details(book_id)
                resolved_path = mongo_db.books.resolve_document_path(book_id, book_doc)

                if not resolved_path or not Path(resolved_path).exists():
                    self.safe_notify("Could not locate the physical file for this document.", type='negative')
                    self.active_generations.pop(task_id, None)
                    self._render_floating_widget()
                    if getattr(dialog, 'value', False):
                        try:
                            self._show_upload_screen(container, task, dialog)
                        except Exception:
                            pass
                    return

                file_obj = resolved_path
            except Exception as ex:
                self.safe_notify(f"Error resolving document: {ex}", type='negative')
                self.active_generations.pop(task_id, None)
                self._render_floating_widget()
                if getattr(dialog, 'value', False):
                    try:
                        self._show_upload_screen(container, task, dialog)
                    except Exception:
                        pass
                return

        if cancel_event.is_set():
            return

        # Execute Fast Deck Generation
        try:
            success, message = await planner_service.generate_deck(
                task_id,
                file_obj,
                on_status=update_status,
                cancel_event=cancel_event,
                quantity=target_qty
            )
        except asyncio.CancelledError:
            success = False
            message = "Generation cancelled."
        except Exception as gen_err:
            success = False
            message = str(gen_err)

        if cancel_event.is_set():
            return

        info = self.active_generations.get(task_id)
        if not info:
            return

        if success:
            found_deck = await planner_service.get_deck(task_id)
            if found_deck and found_deck.get('cards'):
                card_ct = len(found_deck['cards'])
                info['status'] = 'ready'
                info['card_ct'] = card_ct
                info['deck'] = found_deck

                is_dialog_open = getattr(dialog, 'value', False) and not info.get('minimized', False)

                if is_dialog_open:
                    # User stayed in the dialog: render cards immediately in modal
                    try:
                        if client and getattr(client, 'has_socket_connection', False):
                            with client:
                                ui.notify(f"🎉 Study deck ready: {card_ct} flashcards generated!", type='positive')
                                self._render_carousel_view(container, task, dialog, found_deck)
                    except Exception as render_ex:
                        print(f"Error updating modal carousel: {render_ex}")

                    self.active_generations.pop(task_id, None)
                    self._render_floating_widget()
                else:
                    # Minimized / closed dialog: notify user safely and update floating badge
                    self.safe_notify(
                        f"🎉 Flashcards ready for '{task['title']}'! Click to study.",
                        type='positive',
                        duration=8
                    )
                    self._render_floating_widget()

                # Refresh dashboard cards so topic badge reflects the new deck
                try:
                    await self.init()
                except Exception:
                    pass
                return

        # Failure State
        if not cancel_event.is_set():
            is_dialog_open = getattr(dialog, 'value', False) and not info.get('minimized', False)
            if is_dialog_open:
                try:
                    if client and getattr(client, 'has_socket_connection', False):
                        with client:
                            container.clear()
                            with container:
                                with ui.column().classes('items-center justify-center p-6 sm:p-10 text-center max-w-md mx-auto'):
                                    with ui.element('div').classes('p-3 rounded-full bg-red-50 border border-red-100 mb-2'):
                                        ui.icon('error_outline', size='3em').classes('text-red-500')
                                    ui.label("Generation Incomplete").classes('text-lg sm:text-xl font-bold text-slate-800')
                                    ui.label(message or "Could not extract sufficient study cards from this document.").classes(
                                        'text-xs sm:text-sm text-red-500 my-3 text-center leading-relaxed'
                                    )
                                    ui.button("Try Another Document", icon='refresh', on_click=lambda: self._show_upload_screen(container, task, dialog))\
                                        .props('unelevated rounded-xl color=indigo size=md font-bold').classes('shadow-sm')
                except Exception as render_err:
                    print(f"Error showing failure screen: {render_err}")
                self.active_generations.pop(task_id, None)
                self._render_floating_widget()
            else:
                self.safe_notify(
                    f"❌ Could not generate flashcards for '{task['title']}': {message}",
                    type='negative',
                    duration=6
                )
                self.active_generations.pop(task_id, None)
                self._render_floating_widget()

    def render_dashboard(self):
        """Renders the Study Planner topic cards and action buttons safely within client context."""
        if not self.container:
            return
        client = self.client or ui.context.client
        if client and getattr(client, 'has_socket_connection', False):
            with client:
                self._do_render_dashboard()
        else:
            self._do_render_dashboard()

    def _do_render_dashboard(self):
        self.container.clear()
        with self.container:
            with ui.row().classes('w-full justify-between items-center mb-6 sm:mb-8 flex-wrap gap-4'):
                with ui.column().classes('gap-1'):
                    ui.label('Study Planner').classes('text-2xl sm:text-3xl md:text-4xl font-black text-slate-900 tracking-tight')
                    ui.label('Organize your curriculum topics and practice with AI-generated 3D flashcards.').classes('text-xs sm:text-sm text-slate-500')

                ui.button('New Topic', icon='add', on_click=self.open_add_dialog)\
                    .props('unelevated rounded-xl color=indigo size=md')\
                    .classes('font-bold shadow-sm hover:shadow-md transition-shadow')

            if not self.tasks:
                with ui.column().classes('w-full items-center py-16 sm:py-20 text-center bg-white border-2 border-dashed border-slate-200 rounded-3xl p-6 sm:p-8 shadow-xs'):
                    with ui.element('div').classes('p-5 rounded-full bg-indigo-50 border border-indigo-100 mb-3'):
                        ui.icon('school', size='3em').classes('text-indigo-600')
                    ui.label("No Study Topics Created Yet").classes('text-slate-800 text-lg sm:text-xl font-bold mb-1')
                    ui.label("Add your curriculum subjects or textbook chapters to generate automated 3D flashcards.").classes('text-slate-500 text-xs sm:text-sm max-w-sm mb-4')

                    # Quick topic starter suggestions
                    with ui.row().classes('items-center justify-center gap-2 mb-6 flex-wrap'):
                        ui.label('Try:').classes('text-xs font-bold text-slate-400')
                        for sample in ["CS 413 Software Engineering", "Data Structures & Algorithms", "Database Systems (SQL)"]:
                            def make_sample_click(t_name=sample):
                                async def fill_sample():
                                    await self.add_task(t_name, datetime.now().strftime("%Y-%m-%d"))
                                return fill_sample
                            ui.button(sample, on_click=make_sample_click(sample)).props('flat dense rounded-xl size=xs color=indigo').classes('bg-indigo-50 border border-indigo-100 font-bold')

                    ui.button('Create Custom Study Topic', icon='add', on_click=self.open_add_dialog)\
                        .props('unelevated rounded-xl color=indigo size=md font-bold').classes('shadow-md')

            with ui.grid().classes('w-full grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4 sm:gap-6'):
                for task in self.tasks:
                    self.render_task_card(task)

    def render_task_card(self, task: Dict[str, Any]):
        """Renders individual topic card with flashcard status badge and live background generation indicator."""
        task_id = task['id']
        is_generating = bool(
            task_id in self.active_generations and
            self.active_generations[task_id].get('status') == 'generating'
        )

        with ui.card().classes('p-5 sm:p-6 flex flex-col justify-between rounded-2xl sm:rounded-3xl bg-white border border-slate-200/90 hover:shadow-lg transition-all gap-4'):
            with ui.column().classes('w-full gap-2'):
                with ui.row().classes('w-full justify-between items-start gap-2'):
                    with ui.column().classes('gap-0.5 flex-1 min-w-0'):
                        ui.label(task['title']).classes('text-base sm:text-lg font-bold text-slate-800 leading-snug break-words')
                        date_str = task.get('due_date') or "No target date"
                        ui.label(f"Target: {date_str}").classes('text-xs text-slate-400 font-medium')

                    ui.button(icon='delete', on_click=lambda t_id=task['id']: self.delete_task(t_id))\
                        .props('flat dense round color=grey size=sm')\
                        .tooltip('Delete topic and flashcards')

            with ui.column().classes('w-full gap-2 pt-2 border-t border-slate-100'):
                if is_generating:
                    with ui.button(
                        on_click=lambda t=task: self.open_study_modal(t)
                    ).props('outline rounded-xl color=indigo size=md').classes('w-full font-bold shadow-xs transition-all border-indigo-200 bg-indigo-50/50'):
                        with ui.row().classes('items-center gap-2 justify-center w-full'):
                            ui.spinner('dots', size='sm', color='indigo')
                            ui.label("Generating Cards...").classes('text-xs font-bold text-indigo-700')
                else:
                    ui.button("Open Flashcards", icon='school', on_click=lambda t=task: self.open_study_modal(t))\
                        .props('unelevated rounded-xl color=indigo size=md')\
                        .classes('w-full font-bold shadow-xs hover:shadow-md transition-shadow')

    def open_add_dialog(self):
        with ui.dialog() as self.add_dialog, ui.card().classes('w-full max-w-md p-5 sm:p-6 rounded-t-3xl sm:rounded-3xl bg-white border border-slate-200 shadow-2xl'):
            ui.label("New Study Topic").classes('text-xl font-bold mb-4 text-slate-800')
            name = ui.input("Topic Name (e.g. Chapter 4 Data Modeling)").classes('w-full mb-3 text-sm').props('outlined rounded autofocus')
            date = ui.input("Target Date").props('outlined rounded type=date').classes('w-full mb-6 text-sm')
            with ui.row().classes('w-full justify-end gap-2'):
                ui.button("Cancel", on_click=self.add_dialog.close).props('flat color=grey')
                ui.button("Create Topic", on_click=lambda: self.add_task(name.value, date.value)).props('unelevated rounded-xl color=indigo font-bold')
        self.add_dialog.open()

    def build_ui(self):
        self.client = ui.context.client
        drawer = sidebar()
        header(drawer_reference=drawer)
        with ui.column().classes('w-full min-h-fit pt-[calc(4.5rem+env(safe-area-inset-top,0px))] px-3 sm:px-6 md:pt-24 md:px-10 max-w-[1600px] mx-auto pb-16 safe-pb-mobile-nav'):
            self.container = ui.column().classes('w-full')

        # Floating Background Generation Indicator
        self.bg_status_container = ui.element('div').classes(
            'fixed bottom-6 right-4 sm:bottom-6 sm:right-6 z-50 flex flex-col gap-2.5 pointer-events-auto max-w-sm'
        )


async def planner_page():
    app.storage.client['page_path'] = '/planner'
    page = StudyPlannerPage()
    page.build_ui()
    await page.init()