from nicegui import ui, app
from pathlib import Path
import urllib.parse
from core.config import settings

class BookReader:
    def __init__(self, book_id: str):
        self.book_id = book_id
        self.book_path = settings.BASE_DIR / 'data' / 'books' / book_id
        self.file_url = None
        self.file_type = None
        self.file_name = None
        self.error_msg = None

    def find_content_file(self):
        if not self.book_path.exists():
            legacy_path = settings.BASE_DIR / 'E-Books' / self.book_id
            if legacy_path.exists():
                self.error_msg = "File located in legacy E-Books folder."
                return False
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
        with ui.header().classes('bg-white/95 dark:bg-slate-900/95 backdrop-blur-md border-b border-slate-200 dark:border-slate-800 text-slate-800 dark:text-slate-100 h-14 items-center px-2.5 sm:px-4 z-50'):
            ui.button(icon='arrow_back', on_click=lambda: ui.navigate.to('/books')) \
                .props('flat round color=indigo size=md').tooltip('Back to Library')
            ui.label(self.file_name or 'Reading Mode').classes('font-bold text-xs uppercase tracking-wider text-slate-500 dark:text-slate-400 ml-1 sm:ml-2 truncate max-w-[130px] xs:max-w-[220px] sm:max-w-md')
            ui.space()
            if self.file_url:
                ui.button(icon='download', on_click=lambda: ui.download(self.file_url)).props('flat round color=indigo size=md').tooltip('Download File')
            ui.button(icon='fullscreen', on_click=lambda: ui.run_javascript('if(document.fullscreenElement){document.exitFullscreen()}else{document.documentElement.requestFullscreen()}')).props('flat round color=grey size=md').tooltip('Toggle Fullscreen')

        with ui.column().classes('w-full h-[calc(100vh-56px)] p-0 m-0 bg-slate-100 dark:bg-slate-950 items-center justify-center overflow-hidden'):
            found = self.find_content_file()
            
            if not found:
                with ui.card().classes('items-center text-center p-6 sm:p-8 bg-white dark:bg-slate-900 shadow-xl rounded-2xl sm:rounded-3xl border-l-4 border-red-500 w-[calc(100vw-2rem)] max-w-md mx-4'):
                    ui.icon('error_outline', size='3.5em').classes('text-red-400 mb-2')
                    ui.label("Document Unavailable").classes('text-base sm:text-lg font-bold text-slate-800 dark:text-slate-100')
                    ui.label(self.error_msg).classes('text-xs text-red-500 font-mono mt-1 break-words')
                    ui.button('Back to Collection', on_click=lambda: ui.navigate.to('/books')).props('unelevated rounded color=indigo size=sm').classes('mt-4')
            
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
                    with ui.scroll_area().classes('w-full h-full p-4 sm:p-8 md:p-16 bg-white dark:bg-slate-900 max-w-4xl shadow-xl sm:rounded-2xl sm:my-4'):
                        ui.label(f"Document: {self.file_name}").classes('text-xl sm:text-2xl font-bold mb-4 sm:mb-6 text-slate-800 dark:text-slate-100 break-words')
                        for para in doc.paragraphs:
                            if para.text.strip():
                                ui.label(para.text).classes('text-slate-700 dark:text-slate-300 font-serif text-sm sm:text-base mb-3 leading-relaxed break-words')
                except Exception as e:
                    ui.notify(f"Error reading DOCX: {e}", type='negative')

            elif self.file_type == 'pptx':
                try:
                    from pptx import Presentation
                    file_path = self.book_path / self.file_name
                    prs = Presentation(file_path)
                    with ui.scroll_area().classes('w-full h-full p-3 sm:p-8 md:p-16 bg-white dark:bg-slate-900 max-w-5xl shadow-xl sm:rounded-2xl sm:my-4'):
                        for i, slide in enumerate(prs.slides):
                            with ui.card().classes('w-full mb-4 sm:mb-6 p-4 sm:p-6 bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl sm:rounded-2xl shadow-sm'):
                                ui.label(f"Slide {i+1}").classes('text-xs font-bold text-indigo-500 uppercase mb-2')
                                txts = [s.text for s in slide.shapes if hasattr(s, "text") and s.text.strip()]
                                if txts:
                                    ui.label(txts[0]).classes('text-base sm:text-lg font-bold text-slate-900 dark:text-slate-100 mb-2 sm:mb-3 break-words')
                                    for t in txts[1:]: ui.markdown(f"• {t}").classes('ml-2 sm:ml-4 text-slate-700 dark:text-slate-300 text-xs sm:text-sm break-words')
                except Exception as e:
                    ui.notify(f"Error reading PPTX: {e}", type='negative')

            elif self.file_type == 'text':
                try:
                    file_path = self.book_path / self.file_name
                    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                        ui.markdown(f.read()).classes('prose dark:prose-invert lg:prose-xl mx-auto font-serif p-4 sm:p-8 break-words')
                except Exception as e:
                    ui.notify(f"Error reading text: {e}", type='negative')

async def reader_page(book_id: str):
    app.storage.client['page_path'] = '/read'
    reader = BookReader(book_id)
    reader.build_ui()