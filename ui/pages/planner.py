import asyncio
from datetime import datetime
import uuid
from typing import Dict, List, Optional
from nicegui import ui, app, events

# --- IMPORTS ---
try:
    from components.sidebar import sidebar
    from components.header import header
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
            # 2. h-96: FIXED HEIGHT (384px). 'h-100' is not standard tailwind, h-96 prevents layout shift.
            # 3. relative perspective: Essential for 3D effect
            container = ui.card().classes('w-full max-w-xl h-96 relative perspective cursor-pointer no-shadow border-0 bg-transparent') \
                .on('click', self.flip)
            
            # 3D Depth style
            container.style('perspective: 1000px;')

            with container:
                # --- FRONT FACE ---
                # absolute inset-0: Ensures it fills the h-96 container exactly
                self.front = ui.column().classes(
                    'absolute inset-0 w-full h-full bg-white border border-gray-200 shadow-lg rounded-2xl items-center justify-center p-8 text-center'
                )
                self.front.style('backface-visibility: hidden; transition: transform 0.6s; transform-style: preserve-3d;')
                
                with self.front:
                    ui.label("QUESTION").classes('text-xs font-bold tracking-widest text-indigo-400 mb-4')
                    # overflow-y-auto ensures long text doesn't break the card
                    ui.label(self.get_text('q')).classes('text-2xl font-medium text-slate-800 overflow-y-auto max-h-full')
                    ui.label("Tap to reveal").classes('text-xs text-gray-300 mt-auto pt-4')

                # --- BACK FACE ---
                self.back = ui.column().classes(
                    'absolute inset-0 w-full h-full bg-indigo-600 shadow-lg rounded-2xl items-center justify-center p-8 text-center'
                )
                # Start rotated 180deg
                self.back.style('backface-visibility: hidden; transition: transform 0.6s; transform: rotateY(180deg); transform-style: preserve-3d;')
                
                with self.back:
                    ui.label("ANSWER").classes('text-xs font-bold tracking-widest text-indigo-200 mb-4')
                    ui.label(self.get_text('a')).classes('text-xl font-medium text-white overflow-y-auto max-h-full')

            # --- CONTROLS ---
            with ui.row().classes('mt-8 gap-6 items-center'):
                ui.button(icon='arrow_back', on_click=self.prev_card).props('round flat color=grey')
                
                # Main Flip Button (for those who don't want to click the card)
                ui.button('Flip Card', on_click=self.flip).props('rounded outline color=indigo').classes('px-8')
                
                ui.button(icon='arrow_forward', on_click=self.next_card).props('round flat color=grey')

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
        uid = app.storage.user.get('user_id') or app.storage.user.get('token')
        if uid:
            self.tasks = await mongo_db.db.tasks.find({'user_id': uid}).sort('created_at', -1).to_list(None)
            self.render_dashboard()
        else: ui.navigate.to('/login')

    async def add_task(self, title, date):
        if not title: return
        uid = app.storage.user.get('user_id') or app.storage.user.get('token')
        new_task = {'id': str(uuid.uuid4()), 'user_id': uid, 'title': title, 'due_date': date, 'completed': False, 'created_at': datetime.utcnow()}
        await mongo_db.db.tasks.insert_one(new_task)
        if self.add_dialog: self.add_dialog.close()
        await self.init()

    async def delete_task(self, task_id):
        await mongo_db.db.tasks.delete_one({'id': task_id})
        await planner_service.delete_deck_by_task(task_id)
        await self.init()

    async def open_study_modal(self, task):
        deck = await planner_service.get_deck(task['id'])

        with ui.dialog() as dialog, ui.card().classes('w-full max-w-4xl h-[85vh] flex flex-col p-0 overflow-hidden'):
            # Header
            with ui.row().classes('w-full border-b p-4 justify-between items-center bg-white z-10'):
                ui.label(task['title']).classes('text-xl font-bold text-slate-700')
                ui.button(icon='close', on_click=dialog.close).props('flat round color=grey')
            
            # Content
            content_area = ui.column().classes('w-full flex-grow items-center justify-center bg-slate-50 p-6 scroll-y-auto')
            
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
            with ui.button(on_click=lambda: self._show_upload_screen(container, task, dialog)).props('round flat color=grey icon=refresh').classes('absolute bottom-4 right-4 opacity-50 hover:opacity-100'):
                ui.tooltip('Regenerate Deck')

    def _show_upload_screen(self, container, task, dialog):
        container.clear()
        with container:
            ui.icon('school', size='4rem').classes('text-indigo-200 mb-4')
            ui.label("Create Your Study Deck").classes('text-xl font-bold text-slate-700 mb-2')
            ui.label("Select a document from your library or upload a new one.").classes('text-sm text-gray-400 mb-8')

            # Container for the two options
            with ui.row().classes('w-full max-w-2xl justify-center gap-8 items-start'):
                
                # --- OPTION 1: UPLOAD NEW FILE ---
                with ui.column().classes('items-center border border-gray-200 rounded-xl p-6 bg-white flex-1'):
                    ui.label("Upload File").classes('font-bold text-slate-600 mb-2')
                    ui.label("PDF, TXT, DOCX, PPTX").classes('text-xs text-gray-400 mb-4')
                    async def handle_upload(e: events.UploadEventArguments):
                        await self._process_deck_generation(e, task, container, dialog, is_upload=True)

                    ui.upload(label="Drop file here", auto_upload=True, on_upload=handle_upload)\
                        .props('color=indigo accept=.pdf,.txt,.docx,.pptx').classes('w-full')

                # --- OPTION 2: SELECT FROM LIBRARY ---
                with ui.column().classes('items-center border border-gray-200 rounded-xl p-6 bg-white flex-1'):
                    ui.label("Select from Library").classes('font-bold text-slate-600 mb-2')
                    ui.label("Excludes large books").classes('text-xs text-gray-400 mb-4')
                    
                    self.library_select = ui.select({'loading': 'Loading documents...'}, label="Choose Document", on_change=lambda e: self.generate_btn.enable() if e.value else self.generate_btn.disable())\
                        .props('outlined dense options-dense').classes('w-full mb-4')
                    
                    self.generate_btn = ui.button('Generate Flashcards', on_click=lambda: self._process_deck_generation(self.library_select.value, task, container, dialog, is_upload=False))\
                        .props('color=indigo outline').classes('w-full').disable()
                    
                    # Fetch valid library items asynchronously
                    ui.timer(0.1, self._populate_library_dropdown, once=True)

    async def _populate_library_dropdown(self):
        try:
            all_books = await mongo_db.get_all_books()
            options = {}
            for b in all_books:
                # Get extension from original filename if available, else derive from formats
                raw_name = b.get('filename')
                filename = str(raw_name).lower() if raw_name else ''
                ext = None
                if filename:
                    ext = '.' + filename.split('.')[-1]
                else:
                    formats = b.get('formats', {})
                    if 'pdf' in formats: ext = '.pdf'
                    elif 'txt' in formats: ext = '.txt'
                    elif 'docx' in formats: ext = '.docx'
                    elif 'pptx' in formats: ext = '.pptx'
                
                # Allow specific document formats, disallow epub/mobi
                allowed_exts = ['.pdf', '.txt', '.docx', '.pptx']
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
        # 1. Spinner
        with ui.dialog() as spinner, ui.card().classes('p-8 items-center'):
            ui.spinner('dots', size='3em', color='indigo')
            ui.label("Analyzing content...").classes('mt-2 text-indigo-500')
        spinner.open()
        
        # 2. Prepare file object
        file_obj = None
        if is_upload:
            file_obj = getattr(source_data, 'content', getattr(source_data, 'file', source_data))
        else:
            # `source_data` is the book ID from the library select
            book_id = source_data
            if book_id in ('none', 'error', 'loading'):
                spinner.close()
                return
                
            try:
                # Fetch book document to find the file path
                book_doc = await mongo_db.get_book_details(book_id)
                if book_doc:
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
                    
                    if found_path:
                        # Open the file and pass it as a file object
                        with open(found_path, 'rb') as f:
                            # Read into memory to pass to FlashcardService (which expects bytes or an object with .read())
                            file_bytes = f.read()
                            
                            # Create a dummy object that behaves like an upload event content
                            class MockFile:
                                def __init__(self, name, content):
                                    self.name = name
                                    self.content = content
                                def read(self):
                                    return self.content
                            
                            file_obj = MockFile(name=filename or "library_doc.pdf", content=file_bytes)
                    else:
                        ui.notify("Could not locate the physical file for this document.", type='negative')
                        spinner.close()
                        return
                else:
                    ui.notify("Document not found in database.", type='negative')
                    spinner.close()
                    return
            except Exception as e:
                print(f"Error fetching library file: {e}")
                ui.notify(f"Error accessing file: {e}", type='negative')
                spinner.close()
                return
        
        # 3. Process with FlashcardService
        success, message = await planner_service.generate_deck(task['id'], file_obj)
        
        # 4. Wait loop for background processing
        found_deck = None
        if success:
            for i in range(15): # Increased polling
                found_deck = await planner_service.get_deck(task['id'])
                if found_deck and found_deck.get('cards'):
                    break
                await asyncio.sleep(0.5)
        
        spinner.close()

        if found_deck and found_deck.get('cards'):
            ui.timer(0.1, lambda: self._render_carousel_view(container, task, dialog, found_deck), once=True)
        else:
            ui.notify(f"Failed: {message or 'Generation timed out'}", type='negative')

    def render_dashboard(self):
        if not self.container: return
        self.container.clear()
        with self.container:
            ui.label('Study Planner').classes('text-4xl font-bold mb-8 text-slate-800')
            
            with ui.row().classes('w-full justify-between items-center mb-8'):
                ui.label('Your Topics').classes('text-xl text-gray-500 font-medium')
                ui.button('New Topic', icon='add', on_click=self.open_add_dialog).props('color=indigo')

            if not self.tasks:
                with ui.column().classes('w-full items-center py-12'):
                    ui.icon('assignment', size='4rem').classes('text-gray-200 mb-4')
                    ui.label("No topics yet.").classes('text-gray-400 italic')
            
            with ui.grid().classes('w-full grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6'):
                for task in self.tasks: self.render_task_card(task)

    def render_task_card(self, task):
        with ui.card().classes('p-6 flex flex-col gap-4 hover:shadow-md transition-shadow'):
            with ui.row().classes('w-full justify-between items-start'):
                with ui.column().classes('gap-1'):
                    ui.label(task['title']).classes('text-lg font-bold text-slate-700')
                    date_str = task['due_date'] if task['due_date'] else "No date"
                    ui.label(f"Due: {date_str}").classes('text-xs text-gray-400')
                
                ui.button(icon='delete', on_click=lambda: self.delete_task(task['id'])).props('flat dense round color=grey')
            
            ui.separator().classes('my-2')
            ui.button("Open Flashcards", icon='school', on_click=lambda: self.open_study_modal(task)).props('flat color=indigo').classes('w-full')

    def open_add_dialog(self):
        with ui.dialog() as self.add_dialog, ui.card().classes('w-96 p-6'):
            ui.label("New Topic").classes('text-xl font-bold mb-4')
            name = ui.input("Topic Name").classes('w-full mb-4').props('autofocus')
            date = ui.input("Target Date").props('type=date').classes('w-full mb-8')
            with ui.row().classes('w-full justify-end'):
                ui.button("Cancel", on_click=self.add_dialog.close).props('flat color=grey')
                ui.button("Create", on_click=lambda: self.add_task(name.value, date.value)).props('color=indigo')
        self.add_dialog.open()

    def build_ui(self):
        if 'sidebar' in globals(): sidebar()
        if 'header' in globals(): header(drawer_reference=None)
        with ui.column().classes('w-full min-h-screen pt-24 px-8 bg-gray-50'):
            self.container = ui.column().classes('w-full max-w-7xl mx-auto')

@ui.page('/planner')
async def planner_page():
    page = StudyPlannerPage()
    page.build_ui()
    await page.init()