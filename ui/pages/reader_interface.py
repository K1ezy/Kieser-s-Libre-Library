from nicegui import ui, app
from pathlib import Path
import urllib.parse
import re
from core.config import settings

class BookReader:
    def __init__(self, book_id: str):
        self.book_id = str(book_id).strip()
        self.books_root = (settings.BASE_DIR / 'data' / 'books').resolve()
        self.book_path = None
        self.file_url = None
        self.file_type = None
        self.file_name = None
        self.error_msg = None

    def find_content_file(self):
        # Security: Prevent path traversal attacks
        if not re.match(r'^[a-zA-Z0-9_-]+$', self.book_id):
            self.error_msg = "Invalid book identifier."
            return False

        candidate_path = (self.books_root / self.book_id).resolve()
        if candidate_path == self.books_root or not candidate_path.is_relative_to(self.books_root):
            self.error_msg = "Unauthorized document path."
            return False

        self.book_path = candidate_path
        if not self.book_path.exists():
            self.error_msg = f"Book folder not found on disk: {self.book_id}"
            return False

        files = sorted([f for f in self.book_path.iterdir() if f.is_file()])

        
        # 1. PDF
        for f in files:
            if f.suffix.lower() == '.pdf':
                self.file_name = f.name
                safe_name = urllib.parse.quote(f.name)
                self.file_url = f'/static_books/{self.book_id}/{safe_name}'
                self.file_type = 'pdf'
                return True
        
        # 2. EPUB
        for f in files:
            if f.suffix.lower() == '.epub':
                self.file_name = f.name
                safe_name = urllib.parse.quote(f.name)
                self.file_url = f'/static_books/{self.book_id}/{safe_name}'
                self.file_type = 'epub'
                return True

        # 3. DOCX
        for f in files:
            if f.suffix.lower() == '.docx':
                self.file_name = f.name
                safe_name = urllib.parse.quote(f.name)
                self.file_url = f'/static_books/{self.book_id}/{safe_name}'
                self.file_type = 'docx'
                return True

        # 4. PPTX
        for f in files:
            if f.suffix.lower() in ('.pptx', '.ppt'):
                self.file_name = f.name
                safe_name = urllib.parse.quote(f.name)
                self.file_url = f'/static_books/{self.book_id}/{safe_name}'
                self.file_type = 'pptx'
                return True
        
        # 5. TXT / MD
        for f in files:
            if f.suffix.lower() in ['.txt', '.md']:
                self.file_name = f.name
                safe_name = urllib.parse.quote(f.name)
                self.file_url = f'/static_books/{self.book_id}/{safe_name}'
                self.file_type = 'text'
                return True
        
        self.error_msg = "No readable file format found in book folder."
        return False

    def build_ui(self):
        # Fluid Non-Overlapping Header
        with ui.header().classes('bg-white/95 backdrop-blur-md border-b border-slate-200 text-slate-800 h-14 pt-[env(safe-area-inset-top,0px)] items-center px-2.5 sm:px-4 z-50 shadow-sm'):
            with ui.row().classes('w-full items-center justify-between flex-nowrap gap-1.5 sm:gap-2'):
                # Left: Back button & Title (Title uses flex-1 min-w-0 truncate to never overlap)
                with ui.row().classes('items-center gap-1.5 flex-1 min-w-0'):
                    ui.button(icon='arrow_back', on_click=lambda: ui.navigate.to('/books')) \
                        .props('flat round dense color=indigo size=md').tooltip('Back to Library').classes('shrink-0')
                    ui.label(self.file_name or 'Reading Mode').classes('font-bold text-xs sm:text-sm text-slate-900 truncate flex-1 min-w-0')

                # Right: Actions grouped and fixed
                with ui.row().classes('items-center gap-1 shrink-0'):
                    if self.file_url:
                        ui.button(icon='download', on_click=lambda: ui.download(self.file_url)) \
                            .props('flat round dense color=indigo size=md').tooltip('Download File')
                    ui.button(icon='fullscreen', on_click=lambda: ui.run_javascript('if(document.fullscreenElement){document.exitFullscreen()}else{document.documentElement.requestFullscreen()}')) \
                        .props('flat round dense color=grey-7 size=md').tooltip('Toggle Fullscreen')

        with ui.column().classes('w-full h-[calc(100dvh-3.5rem)] pt-[env(safe-area-inset-top,0px)] pb-[env(safe-area-inset-bottom,0px)] p-0 m-0 bg-slate-50 items-center justify-center overflow-hidden'):
            found = self.find_content_file()
            
            if not found:
                with ui.card().classes('items-center text-center p-6 sm:p-8 bg-white shadow-xl rounded-2xl sm:rounded-3xl border-l-4 border-rose-500 w-[calc(100vw-2rem)] max-w-md mx-4'):
                    ui.icon('error_outline', size='3.5em').classes('text-rose-500 mb-2')
                    ui.label("Document Unavailable").classes('text-base sm:text-lg font-bold text-slate-900')
                    ui.label(self.error_msg).classes('text-xs text-rose-500 font-mono mt-1 break-words')
                    ui.button('Back to Collection', on_click=lambda: ui.navigate.to('/books')).props('unelevated rounded color=indigo size=sm font-bold').classes('mt-4')
            
            elif self.file_type == 'pdf':
                ui.element('iframe').props(f'src="{self.file_url}" type="application/pdf"').classes('w-full h-full border-none bg-white')

            elif self.file_type == 'epub':
                viewer_path = f"/static/epub-viewer/index.html?file={self.file_url}"
                ui.element('iframe').props(f'src="{viewer_path}" frameborder="0"').classes('w-full h-full border-none bg-white')

            elif self.file_type == 'docx':
                try:
                    import docx
                    file_path = self.book_path / self.file_name
                    doc = docx.Document(file_path)
                    with ui.scroll_area().classes('w-full h-full p-4 sm:p-8 md:p-16 bg-white max-w-4xl shadow-sm sm:rounded-2xl sm:my-4 border border-slate-200'):
                        ui.label(f"Document: {self.file_name}").classes('text-xl sm:text-2xl font-bold mb-4 sm:mb-6 text-slate-900 break-words')
                        for para in doc.paragraphs:
                            if para.text.strip():
                                ui.label(para.text).classes('text-slate-800 font-serif text-sm sm:text-base mb-3 leading-relaxed break-words')
                except Exception as e:
                    ui.notify(f"Error reading DOCX: {e}", type='negative')

            elif self.file_type == 'pptx':
                try:
                    from pptx import Presentation
                    file_path = self.book_path / self.file_name
                    prs = Presentation(file_path)
                    with ui.scroll_area().classes('w-full h-full p-3 sm:p-8 md:p-16 bg-white max-w-5xl shadow-sm sm:rounded-2xl sm:my-4 border border-slate-200'):
                        for i, slide in enumerate(prs.slides):
                            with ui.card().classes('w-full mb-4 sm:mb-6 p-4 sm:p-6 bg-slate-50 border border-slate-200 rounded-xl sm:rounded-2xl shadow-sm'):
                                ui.label(f"Slide {i+1}").classes('text-xs font-bold text-indigo-600 uppercase mb-2')
                                txts = [s.text for s in slide.shapes if hasattr(s, "text") and s.text.strip()]
                                if txts:
                                    ui.label(txts[0]).classes('text-base sm:text-lg font-bold text-slate-900 mb-2 sm:mb-3 break-words')
                                    for t in txts[1:]: ui.markdown(f"• {t}").classes('ml-2 sm:ml-4 text-slate-700 text-xs sm:text-sm break-words')
                except Exception as e:
                    ui.notify(f"Error reading PPTX: {e}", type='negative')

            elif self.file_type == 'text':
                try:
                    file_path = self.book_path / self.file_name
                    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                        ui.markdown(f.read()).classes('prose max-w-none lg:prose-xl mx-auto font-serif p-4 sm:p-8 break-words text-slate-800')
                except Exception as e:
                    ui.notify(f"Error reading text: {e}", type='negative')

async def reader_page(book_id: str):
    app.storage.client['page_path'] = '/read'
    reader = BookReader(book_id)
    reader.build_ui()