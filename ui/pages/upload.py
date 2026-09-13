from nicegui import ui, app
from components.sidebar import sidebar
from components.header import header
from components.bottom_nav import bottom_nav
from core.services.ingestion_service import ingestion_service
import asyncio

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

    def add_log(self, message: str, type: str = "info"):
        """Adds a styled log message to the terminal window."""
        color = "text-green-400" if type == "success" else "text-red-400" if type == "error" else "text-indigo-300"
        icon = "check_circle" if type == "success" else "warning" if type == "error" else "info"
        
        self.logs.insert(0, {"msg": message, "color": color, "icon": icon})
        self.refresh_logs.refresh()

    @ui.refreshable
    def refresh_logs(self):
        """Renders the log list dynamically."""
        if not self.log_container: return
        self.log_container.clear()
        with self.log_container:
            if not self.logs:
                with ui.column().classes('w-full h-full justify-center items-center opacity-30 py-8'):
                    ui.icon('history', size='3em')
                    ui.label("System Ready. Waiting for files...").classes('italic text-xs sm:text-sm')
            
            for log in self.logs:
                with ui.row().classes('items-start gap-2.5 sm:gap-3 w-full p-2.5 sm:p-3 bg-gray-800/50 rounded-lg mb-2 border border-gray-700'):
                    ui.icon(log['icon']).classes(f"{log['color']} text-lg sm:text-xl mt-0.5 shrink-0")
                    ui.label(log['msg']).classes("text-gray-200 text-xs sm:text-sm font-medium leading-tight flex-1 break-words")

    async def handle_upload(self, e):
        """Orchestrates the upload process."""
        # 1. Adapt the input
        adapter = SmartFileAdapter(e)
        filename = adapter.name

        # 2. UI Feedback
        ui.notify(f"Receiving: {filename}...", type='info', position='bottom-right')
        self.add_log(f"Starting ingestion pipeline for: {filename}...", "info")
        
        try:
            # 3. Call Backend Service (Async)
            result = await ingestion_service.process_upload(adapter, filename)
            
            # 4. Handle Response
            if result['success']:
                self.add_log(result['message'], "success")
                ui.notify(f"Completed: {filename}", type='positive', position='bottom-right')
                app.storage.user['library_needs_refresh'] = True
            else:
                err_msg = result.get('error', 'Unknown ingestion error')
                self.add_log(f"Error {filename}: {err_msg}", "error")
                ui.notify(f"Ingestion Failed: {err_msg}", type='negative', position='bottom-right')
                
        except Exception as ex:
            self.add_log(f"Critical System Error: {str(ex)}", "error")
            print(f"UPLOAD EXCEPTION: {ex}")

    def build_ui(self):
        """Constructs the NiceGUI Layout."""
        drawer = sidebar()
        header(drawer_reference=drawer)
        bottom_nav()

        with ui.column().classes('w-full min-h-screen pt-20 px-3 sm:px-4 md:pt-24 md:px-8 max-w-6xl mx-auto bg-slate-50/50 dark:bg-transparent pb-32 md:pb-24'):
            
            # Page Title
            with ui.row().classes('w-full justify-between items-end mb-6 sm:mb-8'):
                with ui.column().classes('gap-0.5 sm:gap-1'):
                    ui.label('Ingestion Hub').classes('text-2xl sm:text-3xl md:text-4xl font-black text-slate-800 dark:text-slate-100 tracking-tight')
                    ui.label('Unified Input Stream: Library & AI Memory').classes('text-xs sm:text-base text-slate-500 dark:text-slate-400 font-medium')
                ui.icon('cloud_upload', size='3.5em').classes('text-indigo-200 dark:text-indigo-900/40 hidden md:block')

            # Main Grid
            with ui.grid().classes('w-full grid-cols-1 lg:grid-cols-2 gap-5 sm:gap-8 items-start'):
                
                # LEFT: Upload Zone
                with ui.card().classes('w-full p-4 sm:p-6 md:p-8 shadow-xl border border-slate-200 dark:border-slate-800 rounded-2xl sm:rounded-3xl bg-white dark:bg-slate-900'):
                    with ui.row().classes('items-center gap-2 mb-4 sm:mb-6'):
                         ui.icon('upload_file').classes('text-xl sm:text-2xl text-indigo-500')
                         ui.label('File Drop').classes('text-xs sm:text-sm font-bold text-slate-400 uppercase tracking-widest')
                    
                    # The Upload Widget (Max size set to 200MB)
                    ui.upload(
                        on_upload=self.handle_upload, 
                        multiple=True, 
                        auto_upload=True,
                        max_file_size=200_000_000
                    ).props(
                        'accept=".pdf,.epub,.docx,.pptx,.txt,.md" color=indigo flat bordered text-color=indigo-10'
                    ).classes('w-full h-48 sm:h-64 border-2 border-dashed border-indigo-200 dark:border-indigo-800 rounded-xl bg-indigo-50/30 dark:bg-indigo-950/20 hover:bg-indigo-50 dark:hover:bg-indigo-950/40 transition-colors')
                    
                    # Supported Formats Badges
                    with ui.row().classes('mt-4 sm:mt-6 gap-1.5 sm:gap-2 flex-wrap'):
                        for fmt, color, icon in [
                            ('PDF', 'red', 'picture_as_pdf'),
                            ('EPUB', 'orange', 'book'),
                            ('DOCX', 'blue', 'description'),
                            ('PPTX', 'amber', 'slideshow'),
                            ('TXT', 'gray', 'article')
                        ]:
                            ui.chip(fmt, icon=icon).props('dense outline square').classes(f'text-{color}-500 border-{color}-200 dark:border-{color}-900/40 bg-{color}-50 dark:bg-{color}-950/30 text-xs')

                # RIGHT: Terminal / Logs
                with ui.card().classes('w-full p-0 shadow-2xl border border-slate-800 rounded-2xl sm:rounded-3xl overflow-hidden bg-gray-900'):
                    # Terminal Header
                    with ui.row().classes('p-3.5 sm:p-4 bg-gray-800 items-center justify-between border-b border-gray-700'):
                        with ui.row().classes('gap-2 items-center'):
                            ui.icon('terminal').classes('text-green-400 text-sm sm:text-base')
                            ui.label('System Logs').classes('text-gray-200 font-mono font-bold text-xs sm:text-sm')
                        with ui.row().classes('gap-1.5'):
                            ui.element('div').classes('w-2.5 h-2.5 sm:w-3 sm:h-3 rounded-full bg-red-500/80')
                            ui.element('div').classes('w-2.5 h-2.5 sm:w-3 sm:h-3 rounded-full bg-yellow-500/80')
                            ui.element('div').classes('w-2.5 h-2.5 sm:w-3 sm:h-3 rounded-full bg-green-500/80')
                    
                    # Log Container
                    with ui.column().classes('p-3 sm:p-4 w-full h-64 sm:h-80 overflow-y-auto custom-scrollbar font-mono') as self.log_container:
                        self.refresh_logs()

async def upload_page():
    app.storage.client['page_path'] = '/upload'
    hub = IngestionHub()
    hub.build_ui()