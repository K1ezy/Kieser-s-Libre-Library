from nicegui import ui, app
from components.sidebar import sidebar
from components.header import header
from core.services.ingestion_service import ingestion_service
import asyncio
from datetime import datetime

# -----------------------------------------------------------------------------
# Smart File Adapter (Robustness Layer)
# -----------------------------------------------------------------------------
class SmartFileAdapter:
    """
    Standardizes the NiceGUI upload event into a consistent object 
    for the backend, safely reading bytes from NiceGUI FileUpload.
    """
    def __init__(self, event):
        self.name = "unknown_file"
        self.event = event

        if hasattr(event, 'file') and hasattr(event.file, 'name'):
            self.name = event.file.name
        elif hasattr(event, 'name'):
            self.name = event.name
        elif hasattr(event, 'content') and hasattr(event.content, 'name'):
            self.name = event.content.name

    async def read(self) -> bytes:
        if hasattr(self.event, 'file'):
            f = self.event.file
            if hasattr(f, 'read'):
                res = f.read()
                return await res if asyncio.iscoroutine(res) else res
        if hasattr(self.event, 'content'):
            c = self.event.content
            if hasattr(c, 'read'):
                res = c.read()
                return await res if asyncio.iscoroutine(res) else res
            elif isinstance(c, bytes):
                return c
        return b""

# -----------------------------------------------------------------------------
# UI Logic (Ingestion Hub)
# -----------------------------------------------------------------------------
class IngestionHub:
    def __init__(self):
        self.logs = []
        self.log_container = None
        self.last_uploaded_doc = None
        self.pipeline_active = False
        
        # Real-time Ingestion State
        self.upload_state = {
            'is_active': False,
            'finished': False,
            'filename': '',
            'stage': 'Idle',
            'message': '',
            'percent': 0,
            'title': '',
            'book_id': None,
        }

    def add_log(self, message: str, type: str = "info", stage_tag: str = "PIPELINE"):
        """Adds a styled timestamped log message to the terminal window."""
        color = "text-emerald-400" if type == "success" else "text-rose-400" if type == "error" else "text-indigo-300"
        icon = "check_circle" if type == "success" else "error_outline" if type == "error" else "info"
        badge_color = "bg-emerald-500/20 text-emerald-300 border-emerald-500/40" if type == "success" \
            else "bg-rose-500/20 text-rose-300 border-rose-500/40" if type == "error" \
            else "bg-indigo-500/20 text-indigo-300 border-indigo-500/40"
        
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.logs.insert(0, {
            "time": timestamp,
            "tag": stage_tag,
            "badge_color": badge_color,
            "msg": message,
            "color": color,
            "icon": icon
        })
        self.refresh_logs.refresh()

    def clear_logs(self):
        """Clears the terminal log history."""
        self.logs.clear()
        self.refresh_logs.refresh()
        ui.notify("Pipeline console cleared.", type='info', position='bottom-right')

    def show_pipeline_modal(self):
        """Explains the purpose and mechanics of the System Ingestion Pipeline."""
        with ui.dialog() as dialog, ui.card().classes('w-[92vw] max-w-lg p-5 sm:p-6 rounded-3xl bg-slate-900 border border-slate-700 text-slate-200 shadow-2xl'):
            with ui.row().classes('w-full justify-between items-center mb-3'):
                with ui.row().classes('items-center gap-2'):
                    ui.icon('terminal').classes('text-emerald-400 text-xl')
                    ui.label('System Ingestion Pipeline').classes('font-black text-white text-base sm:text-lg font-mono')
                ui.button(icon='close', on_click=dialog.close).props('flat round dense text-color=slate-400 size=sm')

            ui.label('What is its main function?').classes('text-sm font-bold text-emerald-400 mb-1')
            ui.label(
                'The System Ingestion Pipeline is the automated backend execution and telemetry engine of Libre-Library. '
                'It transforms raw uploaded documents into searchable, cataloged, and AI-comprehended knowledge assets.'
            ).classes('text-xs sm:text-sm text-slate-300 leading-relaxed mb-4')

            ui.label('Automated 6-Stage Workflow:').classes('text-xs font-bold uppercase tracking-wider text-slate-400 mb-2')
            
            stages = [
                ('1. Format Validation', 'Verifies MIME types and sanitizes safe filesystem filenames.', 'verified_user', 'text-sky-400'),
                ('2. Secure Vault Storage', 'Persists the original book into the isolated /data/books/<uuid>/ repository.', 'folder_zip', 'text-indigo-400'),
                ('3. Metadata Scraping', 'Extracts embedded document titles, authors, publishers, and subjects.', 'description', 'text-amber-400'),
                ('4. Cover Art Synthesis', 'Renders PyMuPDF page rasters or extracts embedded EPUB cover artwork.', 'image', 'text-purple-400'),
                ('5. TARS AI Vector Memory', 'Chunks document text and creates ChromaDB semantic embeddings for instant RAG answers.', 'psychology', 'text-emerald-400'),
                ('6. Catalog Registration', 'Synchronizes records into MongoDB and publishes OPDS feeds for e-readers.', 'cloud_done', 'text-teal-400'),
            ]

            with ui.column().classes('gap-2 w-full mb-4'):
                for title, desc, icon_name, color_cls in stages:
                    with ui.row().classes('items-start gap-2.5 p-2 rounded-xl bg-slate-800/80 border border-slate-700/80 w-full'):
                        ui.icon(icon_name).classes(f'{color_cls} text-base mt-0.5 shrink-0')
                        with ui.column().classes('gap-0 flex-1 min-w-0'):
                            ui.label(title).classes('text-xs font-bold text-slate-100')
                            ui.label(desc).classes('text-[11px] text-slate-400 leading-tight')

            with ui.row().classes('w-full justify-end'):
                ui.button('Got it', on_click=dialog.close).props('unelevated rounded-xl color=indigo size=sm font-bold')
        dialog.open()

    @ui.refreshable
    def refresh_pipeline_header(self):
        """Renders live status indicator on top of the terminal card."""
        with ui.row().classes('w-full p-3.5 sm:p-4 bg-slate-800 items-center justify-between border-b border-slate-700'):
            with ui.row().classes('gap-2 items-center min-w-0'):
                ui.icon('terminal').classes('text-emerald-400 text-sm sm:text-base')
                ui.label('System Ingestion Pipeline').classes('text-slate-200 font-mono font-bold text-xs sm:text-sm truncate')
                
                # Live status pill
                if self.pipeline_active:
                    with ui.row().classes('items-center gap-1.5 px-2 py-0.5 rounded-full bg-emerald-500/20 border border-emerald-500/40 shrink-0'):
                        ui.icon('sync').classes('text-emerald-400 text-xs animate-spin')
                        ui.label('INGESTING').classes('text-[10px] font-mono font-bold text-emerald-400')
                else:
                    with ui.row().classes('items-center gap-1.5 px-2 py-0.5 rounded-full bg-slate-700 border border-slate-600 shrink-0'):
                        ui.element('div').classes('w-1.5 h-1.5 rounded-full bg-slate-400')
                        ui.label('IDLE').classes('text-[10px] font-mono font-medium text-slate-400')

            with ui.row().classes('gap-1 items-center shrink-0'):
                ui.button(icon='info_outline', on_click=self.show_pipeline_modal)\
                    .props('flat round dense text-color=slate-400 size=sm')\
                    .tooltip('Explain System Ingestion Pipeline')
                ui.button(icon='delete_sweep', on_click=self.clear_logs)\
                    .props('flat round dense text-color=slate-400 size=sm')\
                    .tooltip('Clear Console Logs')
                with ui.row().classes('gap-1.5 ml-1'):
                    ui.element('div').classes('w-2.5 h-2.5 rounded-full bg-rose-500/80')
                    ui.element('div').classes('w-2.5 h-2.5 rounded-full bg-amber-500/80')
                    ui.element('div').classes('w-2.5 h-2.5 rounded-full bg-emerald-500/80')

    @ui.refreshable
    def refresh_logs(self):
        """Renders the log list dynamically."""
        if not self.log_container: return
        self.log_container.clear()
        with self.log_container:
            if not self.logs:
                with ui.column().classes('w-full h-full justify-center items-center opacity-40 py-10 gap-2 text-center'):
                    ui.icon('history', size='2.8em').classes('text-slate-400')
                    ui.label("System Ready. Waiting for files...").classes('italic text-xs sm:text-sm text-slate-300 font-mono')
                    ui.label("Upload any document to observe real-time validation, metadata scraping, and ChromaDB vectorization.").classes('text-[11px] text-slate-400 max-w-xs')
            
            for log in self.logs:
                with ui.row().classes('items-start gap-2.5 w-full p-2.5 bg-slate-800/90 rounded-xl mb-2 border border-slate-700/80 font-mono'):
                    ui.icon(log['icon']).classes(f"{log['color']} text-base mt-0.5 shrink-0")
                    with ui.column().classes('gap-0.5 flex-1 min-w-0'):
                        with ui.row().classes('items-center gap-2 flex-wrap'):
                            ui.label(log['time']).classes('text-[10px] text-slate-500 font-mono')
                            ui.label(log['tag']).classes(f'text-[9px] font-bold px-1.5 py-0.2 rounded border font-mono {log["badge_color"]}')
                        ui.label(log['msg']).classes("text-slate-200 text-xs font-mono font-medium leading-relaxed break-words w-full")

    @ui.refreshable
    def render_upload_indicator(self):
        """
        Renders the active progress wheel/bar while processing,
        and transitions to a small completion bar upon finish that disappears.
        """
        if not self.upload_state['is_active']:
            return

        st = self.upload_state

        # STATE 1: Completed -> Small bar that will be gone automatically
        if st['finished']:
            with ui.card().classes('w-full p-3 sm:p-4 mb-4 bg-gradient-to-r from-emerald-50 via-white to-teal-50 border border-emerald-300 rounded-2xl shadow-sm transition-all animate-fade-in'):
                with ui.row().classes('w-full items-center justify-between gap-3'):
                    with ui.row().classes('items-center gap-2.5 flex-1 min-w-0'):
                        with ui.element('div').classes('w-7 h-7 rounded-xl bg-emerald-500 text-white flex items-center justify-center shrink-0 shadow-xs'):
                            ui.icon('check', size='18px')
                        with ui.column().classes('gap-0 flex-1 min-w-0'):
                            ui.label(f"Upload Complete: {st['title']}").classes('text-xs sm:text-sm font-bold text-emerald-950 truncate w-full')
                            ui.label("Indexed into Library Archive & AI Memory").classes('text-[11px] text-emerald-700')
                    with ui.element('span').classes('text-[10px] font-bold px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-800 border border-emerald-200 shrink-0'):
                        ui.label("100% DONE")
                
                # Small slim completion bar
                with ui.element('div').classes('w-full bg-emerald-100 h-1.5 rounded-full overflow-hidden mt-2.5'):
                    ui.element('div').classes('bg-emerald-500 h-full rounded-full transition-all duration-500 w-full')
            return

        # STATE 2: Active Upload / Ingestion in progress -> Indicator Screen / Wheel
        pct = max(5, min(100, int(st['percent'])))
        with ui.card().classes('w-full p-4 sm:p-5 mb-4 bg-gradient-to-br from-indigo-50/90 via-white to-purple-50/80 border-2 border-indigo-200 rounded-2xl sm:rounded-3xl shadow-md transition-all animate-fade-in'):
            with ui.row().classes('w-full items-center gap-4'):
                
                # Percentage Wheel Indicator
                with ui.element('div').classes('relative flex items-center justify-center shrink-0'):
                    ui.circular_progress(value=pct / 100.0, size='64px', show_value=False, color='indigo')\
                        .props('thickness=0.18 track-color=indigo-1')
                    with ui.column().classes('absolute inset-0 items-center justify-center pointer-events-none'):
                        ui.label(f"{pct}%").classes('text-xs font-black text-indigo-900 leading-none')

                # Step & Details Info
                with ui.column().classes('gap-1 flex-1 min-w-0'):
                    with ui.row().classes('items-center gap-2 flex-wrap'):
                        with ui.element('span').classes('text-[10px] font-bold px-2 py-0.5 rounded-full bg-indigo-100 text-indigo-700 border border-indigo-200'):
                            ui.label(st['stage'])
                        with ui.row().classes('items-center gap-1'):
                            ui.element('div').classes('w-1.5 h-1.5 rounded-full bg-indigo-600 animate-ping')
                            ui.label('Processing Pipeline...').classes('text-[11px] font-semibold text-indigo-600')

                    ui.label(st['filename']).classes('text-xs sm:text-sm font-black text-slate-900 truncate w-full')
                    ui.label(st['message']).classes('text-[11px] sm:text-xs text-slate-500 truncate w-full')

            # Linear progress bar beneath
            with ui.element('div').classes('w-full bg-slate-100 h-2 rounded-full overflow-hidden mt-3 border border-slate-200/60'):
                ui.element('div').classes('bg-gradient-to-r from-indigo-500 to-purple-600 h-full rounded-full transition-all duration-300').style(f'width: {pct}%')

    async def handle_upload(self, e):
        """Orchestrates the upload and ingestion telemetry stream."""
        adapter = SmartFileAdapter(e)
        filename = adapter.name

        # 1. Initialize Indicator Screen
        self.upload_state = {
            'is_active': True,
            'finished': False,
            'filename': filename,
            'stage': 'Starting Pipeline',
            'message': f'Receiving file stream for {filename}...',
            'percent': 10,
            'title': filename,
            'book_id': None
        }
        self.pipeline_active = True
        self.render_upload_indicator.refresh()
        self.refresh_pipeline_header.refresh()

        ui.notify(f"Receiving: {filename}...", type='info', position='bottom-right')
        self.add_log(f"Starting ingestion pipeline for: {filename}", "info", "STREAM")

        # 2. Callback for fine-grained real-time progress updates
        async def on_progress(step: int, total_steps: int, stage: str, message: str, percent: int, log_type: str = "info"):
            self.upload_state['stage'] = f"Stage {step}/{total_steps}: {stage}"
            self.upload_state['message'] = message
            self.upload_state['percent'] = percent
            self.render_upload_indicator.refresh()
            self.add_log(message, log_type, stage.upper()[:10])
            await asyncio.sleep(0.04)  # Brief UI frame yield

        try:
            result = await ingestion_service.process_upload(adapter, filename, progress_callback=on_progress)
            
            if result['success']:
                book_id = result.get('book_id')
                book_title = result.get('title') or filename

                # Transition to Small Finished Bar
                self.upload_state['percent'] = 100
                self.upload_state['stage'] = 'Ingestion Complete'
                self.upload_state['title'] = book_title
                self.upload_state['book_id'] = book_id
                self.upload_state['finished'] = True
                self.pipeline_active = False
                
                self.render_upload_indicator.refresh()
                self.refresh_pipeline_header.refresh()
                
                ui.notify(f"Completed: {book_title}", type='positive', position='bottom-right')
                app.storage.user['library_needs_refresh'] = True
                self.last_uploaded_doc = {
                    'id': book_id,
                    'title': book_title
                }
                self.render_action_banner.refresh()

                # User requirement: "and then after it finishes uploading there will be a small bar and if it finishes uploading it will be gone"
                # Display small completion bar for 3.5 seconds, then dismiss:
                await asyncio.sleep(3.5)
                self.upload_state['is_active'] = False
                self.upload_state['finished'] = False
                self.render_upload_indicator.refresh()
                
            else:
                err_msg = result.get('error', 'Unknown ingestion error')
                self.upload_state['is_active'] = False
                self.pipeline_active = False
                self.render_upload_indicator.refresh()
                self.refresh_pipeline_header.refresh()
                self.add_log(f"Error {filename}: {err_msg}", "error", "ERROR")
                ui.notify(f"Ingestion Failed: {err_msg}", type='negative', position='bottom-right')
                
        except Exception as ex:
            self.upload_state['is_active'] = False
            self.pipeline_active = False
            self.render_upload_indicator.refresh()
            self.refresh_pipeline_header.refresh()
            self.add_log(f"Critical System Error: {str(ex)}", "error", "PANIC")
            print(f"UPLOAD EXCEPTION: {ex}")

    def build_ui(self):
        """Constructs the NiceGUI Layout."""
        drawer = sidebar()
        header(drawer_reference=drawer)

        # Custom CSS for seamless dropzone styling & hiding Quasar's awkward 0.0B / 0.00% subtitle
        ui.add_head_html('''
            <style>
                .custom-file-drop {
                    border: 2px dashed #818cf8 !important;
                    border-radius: 1.25rem !important;
                    background: rgba(238, 242, 255, 0.4) !important;
                    transition: all 0.25s ease !important;
                }
                .custom-file-drop:hover {
                    border-color: #4f46e5 !important;
                    background: rgba(238, 242, 255, 0.75) !important;
                }
                .custom-file-drop .q-uploader__header {
                    background: transparent !important;
                    color: #4338ca !important;
                    border-bottom: 1px dashed rgba(129, 140, 248, 0.4) !important;
                }
                .custom-file-drop .q-uploader__subtitle {
                    display: none !important; /* Removes awkward 0.0B / 0.00% */
                }
                .custom-file-drop .q-uploader__title {
                    font-weight: 800 !important;
                    font-size: 0.875rem !important;
                    color: #312e81 !important;
                    letter-spacing: -0.01em !important;
                }
                .custom-file-drop .q-uploader__list {
                    min-height: 110px !important;
                }
            </style>
        ''')

        with ui.column().classes('w-full min-h-fit pt-[calc(4.5rem+env(safe-area-inset-top,0px))] px-3 sm:px-4 md:pt-24 md:px-8 max-w-7xl mx-auto pb-16 safe-pb-mobile-nav'):
            
            # Page Title
            with ui.row().classes('w-full justify-between items-end mb-6 sm:mb-8'):
                with ui.column().classes('gap-0.5 sm:gap-1'):
                    ui.label('Ingestion Hub').classes('text-2xl sm:text-3xl md:text-4xl font-black text-slate-900 tracking-tight')
                    ui.label('Unified Input Stream: Library & AI Memory').classes('text-xs sm:text-base text-slate-500 font-medium')
                ui.icon('cloud_upload', size='3.5em').classes('text-indigo-200 hidden md:block')

            # Main Grid
            with ui.grid().classes('w-full grid-cols-1 lg:grid-cols-2 gap-5 sm:gap-8 items-start'):
                
                # LEFT: Upload Zone & Active Progress Wheel
                with ui.card().classes('w-full p-4 sm:p-6 md:p-8 shadow-sm border border-slate-200 rounded-2xl sm:rounded-3xl bg-white'):
                    with ui.row().classes('items-center justify-between w-full mb-4 sm:mb-6'):
                        with ui.row().classes('items-center gap-2'):
                            ui.icon('upload_file').classes('text-xl sm:text-2xl text-indigo-600')
                            ui.label('File Drop').classes('text-xs sm:text-sm font-bold text-slate-400 uppercase tracking-widest')
                        with ui.element('span').classes('text-[11px] font-bold text-indigo-600 bg-indigo-50 border border-indigo-100 px-2.5 py-1 rounded-full'):
                            ui.label('Up to 200MB')
                    
                    # 1. Live Upload & Ingestion Indicator (Progress Wheel / Small disappearing bar)
                    self.render_upload_indicator()

                    # 2. The Upload Widget
                    ui.upload(
                        on_upload=self.handle_upload, 
                        multiple=True, 
                        auto_upload=True,
                        max_file_size=200_000_000
                    ).props(
                        'accept=".pdf,.epub,.docx,.pptx,.txt,.md" color=indigo flat bordered text-color=indigo-10'
                    ).classes('w-full h-48 sm:h-56 custom-file-drop')
                    
                    # Supported Formats Badges
                    with ui.row().classes('mt-4 sm:mt-6 gap-1.5 sm:gap-2 flex-wrap items-center justify-between'):
                        with ui.row().classes('gap-1.5 sm:gap-2 flex-wrap'):
                            for fmt, color, icon in [
                                ('PDF', 'red', 'picture_as_pdf'),
                                ('EPUB', 'orange', 'book'),
                                ('DOCX', 'blue', 'description'),
                                ('PPTX', 'amber', 'slideshow'),
                                ('TXT', 'gray', 'article'),
                                ('MD', 'purple', 'code')
                            ]:
                                ui.chip(fmt, icon=icon).props('dense outline square').classes(f'text-{color}-600 border-{color}-200 bg-{color}-50 text-xs font-semibold')

                        ui.button('Pipeline Info', icon='help_outline', on_click=self.show_pipeline_modal)\
                            .props('flat dense size=xs color=indigo').classes('text-xs font-bold')

                # RIGHT: System Ingestion Pipeline Console
                with ui.card().classes('w-full p-0 shadow-sm border border-slate-800 rounded-2xl sm:rounded-3xl overflow-hidden bg-slate-900'):
                    # Terminal Header with Live Status & Modal Help
                    self.refresh_pipeline_header()
                    
                    # Log Container
                    with ui.column().classes('p-3 sm:p-4 w-full h-64 sm:h-80 overflow-y-auto custom-scrollbar font-mono') as self.log_container:
                        self.refresh_logs()

            # Dynamic Contextual Next Actions (Peak-End Rule: renders only when a file was successfully uploaded)
            self.render_action_banner()

    @ui.refreshable
    def render_action_banner(self):
        """Renders contextual action cards linked directly to the newly ingested material."""
        if not self.last_uploaded_doc:
            return

        doc = self.last_uploaded_doc
        b_id = doc.get('id')
        b_title = doc.get('title') or "Uploaded Document"

        with ui.card().classes('w-full p-4 sm:p-6 mt-6 sm:mt-8 bg-gradient-to-r from-indigo-50 via-white to-purple-50/70 border border-indigo-200 rounded-2xl sm:rounded-3xl shadow-sm transition-all animate-fade-in'):
            with ui.row().classes('w-full items-center justify-between gap-4 flex-wrap'):
                with ui.row().classes('items-center gap-3 flex-1 min-w-[240px]'):
                    with ui.element('div').classes('p-2.5 rounded-xl bg-indigo-600 text-white shadow-sm shrink-0'):
                        ui.icon('check_circle', size='22px')
                    with ui.column().classes('gap-0.5 flex-1 min-w-0'):
                        ui.label(f'Ready for Action: {b_title}').classes('font-black text-slate-900 text-sm sm:text-base truncate w-full')
                        ui.label('Your document has been indexed into ChromaDB. Jump directly into reading or AI study.').classes('text-xs text-slate-500')

                with ui.row().classes('items-center gap-2 flex-wrap shrink-0'):
                    if b_id:
                        ui.button('Read Now', icon='auto_stories', on_click=lambda id=b_id: ui.navigate.to(f'/read/{id}'))\
                            .props('unelevated rounded-xl color=indigo size=sm font-bold').classes('shadow-xs')
                        ui.button('Ask TARS AI', icon='smart_toy', on_click=lambda: ui.navigate.to('/chat'))\
                            .props('outline rounded-xl color=indigo size=sm font-bold')
                        ui.button('Study Deck', icon='school', on_click=lambda: ui.navigate.to('/planner'))\
                            .props('outline rounded-xl color=purple size=sm font-bold')
                    ui.button('View Archive', icon='library_books', on_click=lambda: ui.navigate.to('/books'))\
                        .props('flat rounded-xl color=grey-8 size=sm font-bold')

async def upload_page():
    app.storage.client['page_path'] = '/upload'
    hub = IngestionHub()
    hub.build_ui()