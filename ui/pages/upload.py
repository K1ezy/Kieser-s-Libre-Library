from nicegui import ui, app
from components.sidebar import sidebar
from components.header import header
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
                with ui.column().classes('w-full h-full justify-center items-center opacity-30'):
                    ui.icon('history', size='3em')
                    ui.label("System Ready. Waiting for files...").classes('italic text-sm')
            
            for log in self.logs:
                with ui.row().classes('items-start gap-3 w-full p-3 bg-gray-800/50 rounded-lg mb-2 border border-gray-700'):
                    ui.icon(log['icon']).classes(f"{log['color']} text-xl mt-0.5")
                    ui.label(log['msg']).classes(f"text-gray-200 text-sm font-medium leading-tight flex-1")

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
            # We pass the adapter which behaves like a file object
            result = await ingestion_service.process_upload(adapter, filename)
            
            # 4. Handle Response
            if result['success']:
                self.add_log(result['message'], "success")
                ui.notify(f"Completed: {filename}", type='positive', position='bottom-right')
                
                # Signal the Home Page to refresh the library view next time it loads
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

        with ui.column().classes('w-full min-h-screen pt-20 px-4 md:pt-24 md:px-8 max-w-6xl mx-auto bg-slate-50'):
            
            # Page Title
            with ui.row().classes('w-full justify-between items-end mb-8'):
                with ui.column().classes('gap-1'):
                    ui.label('Ingestion Hub').classes('text-4xl font-black text-slate-800 tracking-tighter')
                    ui.label('Unified Input Stream: Library & AI Memory').classes('text-lg text-slate-500 font-medium')
                ui.icon('cloud_upload', size='4em').classes('text-indigo-100 hidden md:block')

            # Main Grid
            with ui.grid(columns=2).classes('w-full gap-8 items-start lt-md:grid-cols-1'):
                
                # LEFT: Upload Zone
                with ui.card().classes('w-full p-8 shadow-xl shadow-indigo-100 border border-indigo-50 rounded-3xl bg-white'):
                    ui.row().classes('items-center gap-2 mb-6').style('color: #6366f1')
                    with ui.row().classes('items-center gap-2'):
                         ui.icon('upload_file').classes('text-2xl text-indigo-500')
                         ui.label('File Drop').classes('text-sm font-bold text-gray-400 uppercase tracking-widest')
                    
                    # The Upload Widget (Max size set to 200MB)
                    ui.upload(
                        on_upload=self.handle_upload, 
                        multiple=True, 
                        auto_upload=True,
                        max_file_size=200_000_000
                    ).props(
                        'accept=".pdf,.epub,.docx,.pptx,.txt,.md" color=indigo flat bordered text-color=indigo-10'
                    ).classes('w-full h-64 border-2 border-dashed border-indigo-200 rounded-xl bg-indigo-50/30 hover:bg-indigo-50 transition-colors')
                    
                    # Supported Formats Badges
                    with ui.row().classes('mt-6 gap-2 flex-wrap'):
                        for fmt, color, icon in [
                            ('PDF', 'red', 'picture_as_pdf'),
                            ('EPUB', 'orange', 'book'),
                            ('DOCX', 'blue', 'description'),
                            ('PPTX', 'amber', 'slideshow'),
                            ('TXT', 'gray', 'article')
                        ]:
                            ui.chip(fmt, icon=icon).props(f'dense outline square').classes(f'text-{color}-500 border-{color}-200 bg-{color}-50')

                # RIGHT: Terminal / Logs
                with ui.card().classes('w-full p-0 shadow-2xl shadow-gray-200 border border-gray-800 rounded-3xl overflow-hidden bg-gray-900'):
                    # Terminal Header
                    with ui.row().classes('p-4 bg-gray-800 items-center justify-between border-b border-gray-700'):
                        with ui.row().classes('gap-2 items-center'):
                            ui.icon('terminal').classes('text-green-400')
                            ui.label('System Logs').classes('text-gray-200 font-mono font-bold')
                        with ui.row().classes('gap-1.5'):
                            ui.element('div').classes('w-3 h-3 rounded-full bg-red-500/80')
                            ui.element('div').classes('w-3 h-3 rounded-full bg-yellow-500/80')
                            ui.element('div').classes('w-3 h-3 rounded-full bg-green-500/80')
                    
                    # Log Container
                    with ui.column().classes('p-4 w-full h-80 overflow-y-auto custom-scrollbar font-mono') as self.log_container:
                        self.refresh_logs()

async def upload_page():
    # Helper to mark current page for sidebar
    app.storage.client['page_path'] = '/upload'
    hub = IngestionHub()
    hub.build_ui()