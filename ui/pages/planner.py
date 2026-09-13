import asyncio
from datetime import datetime
import uuid
from typing import Dict, List, Optional
from nicegui import ui, app, events

# --- IMPORTS ---
try:
    from components.sidebar import sidebar
    from components.header import header
    from components.bottom_nav import bottom_nav
    from core.database.mongo_manager import mongo_db
    from .planner_service import planner_service
except ImportError:
    pass

# --- 1. RESTORED & FIXED FLASHCARD COMPONENT ---
class FlashcardCarousel(ui.element):
    def __init__(self, cards: List[Dict]):
        super().__init__('div')
        self.cards = cards if cards else []
        self.current_index = 0
        self._is_flipped = False
        
        # FIX: Removed the debug background (bg-gray-50) so it blends cleanly
        # FIX: W-full ensures it takes available width of the modal
        self.classes('w-full flex flex-col items-center justify-center') 
        self.render()

    def get_text(self, side: str) -> str:
        if not self.cards: return "No Data"
        c = self.cards[self.current_index]
        if side == 'q':
            return c.get('q') or c.get('question') or c.get('front') or "No Question"
        return c.get('a') or c.get('answer') or c.get('back') or "No Answer"

    def render(self):
        self.clear()
        
        if not self.cards:
            with self:
                ui.icon('sentiment_dissatisfied', size='3rem').classes('text-gray-300 mb-2')
                ui.label("No cards available").classes('text-gray-400')
            return

        with self:
            # --- PROGRESS INDICATOR (Restored to subtle style) ---
            ui.label(f"Card {self.current_index + 1} of {len(self.cards)}").classes('text-sm font-bold text-gray-400 mb-6 tracking-wide')
            
            # --- CARD CONTAINER (THE SIZE FIXES) ---
            # 1. w-full max-w-xl: Controls width responsiveness
            # 2. h-72 sm:h-80 md:h-96: Responsive height that fits mobile viewports
            # 3. relative perspective: Essential for 3D effect
            container = ui.card().classes('w-full max-w-xl h-72 sm:h-80 md:h-96 relative perspective cursor-pointer no-shadow border-0 bg-transparent') \
                .on('click', self.flip)
            
            # 3D Depth style
            container.style('perspective: 1000px;')

            with container:
                # --- FRONT FACE ---
                self.front = ui.column().classes(
                    'absolute inset-0 w-full h-full bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 shadow-lg rounded-2xl items-center justify-center p-5 sm:p-8 text-center'
                )
                self.front.style('backface-visibility: hidden; transition: transform 0.6s; transform-style: preserve-3d;')
                
                with self.front:
                    ui.label("QUESTION").classes('text-xs font-bold tracking-widest text-indigo-500 mb-2 sm:mb-4')
                    ui.label(self.get_text('q')).classes('text-lg sm:text-2xl font-medium text-slate-800 dark:text-slate-100 overflow-y-auto max-h-full break-words')
                    ui.label("Tap to reveal").classes('text-xs text-slate-400 mt-auto pt-2 sm:pt-4')

                # --- BACK FACE ---
                self.back = ui.column().classes(
                    'absolute inset-0 w-full h-full bg-indigo-600 shadow-lg rounded-2xl items-center justify-center p-5 sm:p-8 text-center'
                )
                # Start rotated 180deg
                self.back.style('backface-visibility: hidden; transition: transform 0.6s; transform: rotateY(180deg); transform-style: preserve-3d;')
                
                with self.back:
                    ui.label("ANSWER").classes('text-xs font-bold tracking-widest text-indigo-200 mb-2 sm:mb-4')
                    ui.label(self.get_text('a')).classes('text-base sm:text-xl font-medium text-white overflow-y-auto max-h-full break-words')

            # --- CONTROLS ---
            with ui.row().classes('mt-4 sm:mt-8 gap-3 sm:gap-6 items-center justify-center flex-wrap'):
                ui.button(icon='arrow_back', on_click=self.prev_card).props('round flat color=grey size=md')
                
                # Main Flip Button
                ui.button('Flip Card', on_click=self.flip).props('rounded outline color=indigo size=md').classes('px-5 sm:px-8 font-bold')
                
                ui.button(icon='arrow_forward', on_click=self.next_card).props('round flat color=grey size=md')

        # Apply state
        self._apply_rotation()

    def flip(self):
        self._is_flipped = not self._is_flipped
        self._apply_rotation()

    def _apply_rotation(self):
        if self._is_flipped:
            self.front.style('backface-visibility: hidden; transition: transform 0.6s; transform: rotateY(180deg);')
            self.back.style('backface-visibility: hidden; transition: transform 0.6s; transform: rotateY(0deg);')
        else:
            self.front.style('backface-visibility: hidden; transition: transform 0.6s; transform: rotateY(0deg);')
            self.back.style('backface-visibility: hidden; transition: transform 0.6s; transform: rotateY(180deg);')

    def next_card(self):
        self.current_index = (self.current_index + 1) % len(self.cards)
        self._is_flipped = False
        self.render()

    def prev_card(self):
        self.current_index = (self.current_index - 1) % len(self.cards)
        self._is_flipped = False
        self.render()


# --- PAGE LOGIC (UNCHANGED EXCEPT FOR CAROUSEL INTEGRATION) ---
class StudyPlannerPage:
    def __init__(self):
        self.tasks = []
        self.container = None
        self.add_dialog = None
        
    async def init(self):
        try:
            if mongo_db.db is None:
                await mongo_db.initialize()
            uid = app.storage.user.get('user_id') or app.storage.user.get('token')
            if uid:
                self.tasks = await mongo_db.db.tasks.find({'user_id': uid}).sort('created_at', -1).to_list(100)
                self.render_dashboard()
            else:
                ui.navigate.to('/login')
        except Exception as e:
            print(f"Error initializing planner: {e}")
            if self.container:
                self.container.clear()
                with self.container:
                    ui.label("Error loading planner tasks. Please refresh.").classes('text-red-500')

    async def add_task(self, title, date):
        if not title: return
        try:
            if mongo_db.db is None:
                await mongo_db.initialize()
            uid = app.storage.user.get('user_id') or app.storage.user.get('token')
            new_task = {
                'id': str(uuid.uuid4()),
                'user_id': uid,
                'title': title.strip(),
                'due_date': date,
                'completed': False,
                'created_at': datetime.utcnow()
            }
            await mongo_db.db.tasks.insert_one(new_task)
            if self.add_dialog: self.add_dialog.close()
            ui.notify("Topic added successfully!", type='positive')
            await self.init()
        except Exception as e:
            ui.notify(f"Could not add topic: {e}", type='negative')

    async def delete_task(self, task_id):
        try:
            if mongo_db.db is None:
                await mongo_db.initialize()
            await mongo_db.db.tasks.delete_one({'id': task_id})
            await planner_service.delete_deck(task_id)
            ui.notify("Topic deleted.", type='info')
            await self.init()
        except Exception as e:
            ui.notify(f"Error deleting topic: {e}", type='negative')

    async def open_study_modal(self, task):
        deck = await planner_service.get_deck(task['id'])

        with ui.dialog() as dialog, ui.card().classes('w-[calc(100vw-1.5rem)] sm:w-full max-w-4xl h-[90vh] sm:h-[85vh] flex flex-col p-0 overflow-hidden rounded-2xl sm:rounded-3xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 shadow-2xl'):
            # Header
            with ui.row().classes('w-full border-b border-slate-200 dark:border-slate-800 p-3.5 sm:p-4 justify-between items-center bg-white dark:bg-slate-900 z-10'):
                ui.label(task['title']).classes('text-base sm:text-xl font-bold text-slate-800 dark:text-slate-100 truncate max-w-[200px] sm:max-w-md')
                ui.button(icon='close', on_click=dialog.close).props('flat round color=grey size=md')
            
            # Content
            content_area = ui.column().classes('w-full flex-grow items-center justify-center bg-slate-50 dark:bg-slate-950 p-4 sm:p-6 overflow-y-auto')
            
            with content_area:
                if deck and 'cards' in deck and len(deck['cards']) > 0:
                    self._render_carousel_view(content_area, task, dialog, deck)
                else:
                    self._show_upload_screen(content_area, task, dialog)
        dialog.open()

    def _render_carousel_view(self, container, task, dialog, deck):
        container.clear()
        with container:
            FlashcardCarousel(deck['cards'])
            
            # Clean Refresh Button
            with ui.button(on_click=lambda: self._show_upload_screen(container, task, dialog)).props('round flat color=grey icon=refresh size=md').classes('absolute bottom-4 right-4 opacity-70 hover:opacity-100 bg-white/80 dark:bg-slate-800/80 shadow'):
                ui.tooltip('Regenerate Deck')

    def _show_upload_screen(self, container, task, dialog):
        container.clear()
        with container:
            ui.icon('school', size='3.5em').classes('text-indigo-400 mb-2')
            ui.label("Create Your Study Deck").classes('text-lg sm:text-xl font-bold text-slate-800 dark:text-slate-100 mb-1')
            ui.label("Select a document from your library or upload a new one.").classes('text-xs sm:text-sm text-slate-400 mb-6 text-center max-w-sm')

            # Container for the two options
            with ui.row().classes('w-full max-w-2xl justify-center gap-4 sm:gap-8 items-stretch flex-col md:flex-row'):
                
                # --- OPTION 1: UPLOAD NEW FILE ---
                with ui.column().classes('items-center border border-slate-200 dark:border-slate-800 rounded-2xl p-4 sm:p-6 bg-white dark:bg-slate-900 flex-1 w-full shadow-sm'):
                    ui.label("Upload File").classes('font-bold text-slate-700 dark:text-slate-200 mb-1 text-sm sm:text-base')
                    ui.label("PDF, TXT, DOCX, PPTX, EPUB").classes('text-xs text-slate-400 mb-4')
                    async def handle_upload(e: events.UploadEventArguments):
                        await self._process_deck_generation(e, task, container, dialog, is_upload=True)

                    ui.upload(label="Drop file here", auto_upload=True, on_upload=handle_upload, max_file_size=200_000_000)\
                        .props('color=indigo accept=.pdf,.txt,.docx,.pptx,.epub flat bordered').classes('w-full rounded-xl')

                # --- OPTION 2: SELECT FROM LIBRARY ---
                with ui.column().classes('items-center border border-slate-200 dark:border-slate-800 rounded-2xl p-4 sm:p-6 bg-white dark:bg-slate-900 flex-1 w-full shadow-sm'):
                    ui.label("Select from Library").classes('font-bold text-slate-700 dark:text-slate-200 mb-1 text-sm sm:text-base')
                    ui.label("Choose an existing book").classes('text-xs text-slate-400 mb-4')
                    
                    self.library_select = ui.select({'loading': 'Loading documents...'}, label="Choose Document", on_change=lambda e: self.generate_btn.enable() if e.value else self.generate_btn.disable())\
                        .props('outlined dense options-dense').classes('w-full mb-4 text-sm')
                    
                    self.generate_btn = ui.button('Generate Flashcards', on_click=lambda: self._process_deck_generation(self.library_select.value, task, container, dialog, is_upload=False))\
                        .props('color=indigo outline').classes('w-full font-bold').disable()
                    
                    # Fetch valid library items asynchronously
                    ui.timer(0.1, self._populate_library_dropdown, once=True)

    async def _populate_library_dropdown(self):
        try:
            all_books = await mongo_db.get_all_books()
            options = {}
            for b in all_books:
                raw_name = b.get('filename')
                filename = str(raw_name).lower() if raw_name else ''
                ext = None
                if filename:
                    ext = '.' + filename.split('.')[-1]
                else:
                    formats = b.get('formats', {})
                    if 'pdf' in formats: ext = '.pdf'
                    elif 'epub' in formats: ext = '.epub'
                    elif 'txt' in formats: ext = '.txt'
                    elif 'docx' in formats: ext = '.docx'
                    elif 'pptx' in formats: ext = '.pptx'
                
                allowed_exts = ['.pdf', '.epub', '.txt', '.docx', '.pptx']
                if ext in allowed_exts:
                    options[b['id']] = b.get('title', 'Unknown Document')
            
            if options:
                self.library_select.options = options
                self.library_select.update()
            else:
                self.library_select.options = {'none': 'No supported documents found'}
                self.library_select.value = 'none'
                self.library_select.disable()
                self.library_select.update()
        except Exception as e:
            print(f"Error loading library items: {e}")
            self.library_select.options = {'error': 'Error loading documents'}
            self.library_select.value = 'error'
            self.library_select.disable()
            self.library_select.update()

    async def _process_deck_generation(self, source_data, task, container, dialog, is_upload: bool):
        # In-place loading inside the modal container to prevent nested modal glitches
        container.clear()
        with container:
            with ui.column().classes('items-center justify-center p-6 sm:p-8 text-center max-w-md mx-auto'):
                ui.spinner('dots', size='3.5em', color='indigo')
                ui.label("Generating Study Deck").classes('mt-4 text-lg sm:text-xl font-bold text-slate-800 dark:text-slate-100')
                status_label = ui.label("Analyzing content and creating flashcards with TARS AI...").classes('text-xs sm:text-sm text-indigo-500 dark:text-indigo-400 mt-1.5')
                ui.label("This typically takes 10–25 seconds.").classes('text-xs text-slate-400 mt-2')

        def update_status(msg: str):
            status_label.text = msg

        file_obj = source_data

        if not is_upload:
            book_id = source_data
            if not book_id or book_id in ('none', 'error', 'loading'):
                ui.notify("Please select a valid document.", type='warning')
                self._show_upload_screen(container, task, dialog)
                return

            try:
                book_doc = await mongo_db.get_book_details(book_id)
                if not book_doc:
                    ui.notify("Document not found in database.", type='negative')
                    self._show_upload_screen(container, task, dialog)
                    return

                from pathlib import Path
                from core.config import settings

                found_path = None
                if book_doc.get('local_path') and Path(book_doc['local_path']).exists():
                    found_path = str(book_doc['local_path'])
                else:
                    book_folder = settings.BASE_DIR / 'data' / 'books' / book_id
                    if book_folder.exists():
                        candidates = [f for f in book_folder.iterdir() if f.is_file() and f.suffix.lower() in ('.pdf', '.epub', '.docx', '.pptx', '.txt')]
                        if candidates:
                            found_path = str(candidates[0])

                if not found_path:
                    ui.notify("Could not locate physical file for document.", type='negative')
                    self._show_upload_screen(container, task, dialog)
                    return

                file_obj = found_path
            except Exception as ex:
                ui.notify(f"Error loading book: {ex}", type='negative')
                self._show_upload_screen(container, task, dialog)
                return

        # Generate Deck with real-time status updates
        try:
            success, message = await planner_service.generate_deck(task['id'], file_obj, on_status=update_status)
        except Exception as gen_err:
            success = False
            message = str(gen_err)

        if success:
            found_deck = await planner_service.get_deck(task['id'])
            if found_deck and found_deck.get('cards'):
                ui.notify(f"Study deck ready: {len(found_deck['cards'])} cards generated!", type='positive')
                self._render_carousel_view(container, task, dialog, found_deck)
                return

        # On failure, render error state inside container with retry button
        container.clear()
        with container:
            with ui.column().classes('items-center justify-center p-6 sm:p-8 text-center max-w-md mx-auto'):
                ui.icon('error_outline', size='3.5em').classes('text-red-400 mb-2')
                ui.label("Generation Incomplete").classes('text-lg sm:text-xl font-bold text-slate-800 dark:text-slate-100')
                ui.label(message or "Could not extract sufficient cards from this document.").classes('text-xs sm:text-sm text-red-500 mb-6 text-center')
                ui.button("Try Another Document", icon='refresh', on_click=lambda: self._show_upload_screen(container, task, dialog))\
                    .props('color=indigo unelevated rounded')

    def render_dashboard(self):
        if not self.container: return
        self.container.clear()
        with self.container:
            ui.label('Study Planner').classes('text-2xl sm:text-3xl md:text-4xl font-black mb-4 sm:mb-8 text-slate-800 dark:text-slate-100 tracking-tight')
            
            with ui.row().classes('w-full justify-between items-center mb-6 gap-2'):
                ui.label('Your Topics').classes('text-lg sm:text-xl text-slate-500 dark:text-slate-400 font-semibold')
                ui.button('New Topic', icon='add', on_click=self.open_add_dialog).props('color=indigo unelevated rounded size=md').classes('font-bold shadow-sm')

            if not self.tasks:
                with ui.column().classes('w-full items-center py-12 sm:py-16 text-center'):
                    ui.icon('assignment', size='3.5em').classes('text-slate-300 dark:text-slate-600 mb-3')
                    ui.label("No topics yet.").classes('text-slate-400 text-sm italic')
            
            with ui.grid().classes('w-full grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 sm:gap-6'):
                for task in self.tasks: self.render_task_card(task)

    def render_task_card(self, task):
        with ui.card().classes('p-4 sm:p-6 flex flex-col gap-3 sm:gap-4 rounded-2xl sm:rounded-3xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 hover:shadow-lg transition-all'):
            with ui.row().classes('w-full justify-between items-start gap-2'):
                with ui.column().classes('gap-0.5 flex-1 min-w-0'):
                    ui.label(task['title']).classes('text-base sm:text-lg font-bold text-slate-800 dark:text-slate-100 leading-snug break-words')
                    date_str = task.get('due_date') or "No date"
                    ui.label(f"Due: {date_str}").classes('text-xs text-slate-400 font-medium')
                
                ui.button(icon='delete', on_click=lambda t_id=task['id']: self.delete_task(t_id)).props('flat dense round color=grey size=md')
            
            ui.separator().classes('my-1 opacity-50')
            ui.button("Open Flashcards", icon='school', on_click=lambda t=task: self.open_study_modal(t)).props('flat color=indigo size=md').classes('w-full font-bold')

    def open_add_dialog(self):
        with ui.dialog() as self.add_dialog, ui.card().classes('w-[calc(100vw-2rem)] max-w-md p-5 sm:p-6 rounded-2xl sm:rounded-3xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 shadow-2xl'):
            ui.label("New Topic").classes('text-xl font-bold mb-4 text-slate-800 dark:text-slate-100')
            name = ui.input("Topic Name").classes('w-full mb-3 text-sm').props('outlined rounded autofocus')
            date = ui.input("Target Date").props('outlined rounded type=date').classes('w-full mb-6 text-sm')
            with ui.row().classes('w-full justify-end gap-2'):
                ui.button("Cancel", on_click=self.add_dialog.close).props('flat color=grey')
                ui.button("Create", on_click=lambda: self.add_task(name.value, date.value)).props('unelevated rounded color=indigo font-bold')
        self.add_dialog.open()

    def build_ui(self):
        drawer = sidebar()
        header(drawer_reference=drawer)
        bottom_nav()
        with ui.column().classes('w-full min-h-screen pt-20 px-3 sm:px-4 md:pt-24 md:px-8 bg-slate-50/50 dark:bg-transparent pb-32 md:pb-24'):
            self.container = ui.column().classes('w-full max-w-7xl mx-auto')

@ui.page('/planner')
async def planner_page():
    page = StudyPlannerPage()
    page.build_ui()
    await page.init()