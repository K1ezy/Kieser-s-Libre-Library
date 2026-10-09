from nicegui import ui, app
from pathlib import Path
import logging

from components.sidebar import sidebar
from components.header import header
from components.bottom_nav import bottom_nav
from core.database.mongo_manager import mongo_db
from core.ai_engine.llm_engine import tars_engine
from ui.pages.summarizer_service import summarizer_service, SUMMARY_MODES

logger = logging.getLogger("SUMMARIZER")


class SummarizerTool:
    """UI controller for the AI Document Summarizer tool."""

    def __init__(self):
        self.books = {}
        self.selected_book_id = None
        self.selected_mode = 'detailed'
        self.summary_output = None
        self.book_select = None
        self.mode_select = None
        self.doc_badge = None
        self.generate_btn = None
        self.copy_btn = None
        self.save_doc_btn = None
        self.view_book_btn = None
        self.current_summary_text = ""

    async def initialize(self):
        """Loads available library books into selection menu."""
        all_books = await mongo_db.get_all_books(limit=500)
        self.books = {}
        for b in all_books:
            b_id = b.get('id') or (str(b.get('_id')) if b.get('_id') else None)
            if b_id:
                title = b.get('title', 'Untitled')
                self.books[str(b_id)] = title

        # Pop pre-selection from user storage
        try:
            pre_book = app.storage.user.pop('summarize_book_id', None)
            if pre_book:
                self.selected_book_id = str(pre_book)
        except Exception:
            pass

        if self.book_select:
            self.book_select.options = self.books
            if self.selected_book_id and self.selected_book_id in self.books:
                self.book_select.value = self.selected_book_id
            self.book_select.update()

    async def generate_summary(self):
        """Generates structured summary using SummarizerService and LLM engine streaming."""
        if not self.selected_book_id:
            ui.notify('Please select a document first', type='warning')
            return

        title = self.books.get(self.selected_book_id, "Selected Document")

        if self.generate_btn:
            self.generate_btn.disable()
        if self.copy_btn:
            self.copy_btn.set_visibility(False)

        self.summary_output.content = f"🔍 **Locating and extracting text from *{title}*...**"

        book_doc = await mongo_db.get_book_details(self.selected_book_id)
        if not book_doc:
            self.summary_output.content = "⚠️ **Notice:** Document record not found in the library database."
            if self.generate_btn:
                self.generate_btn.enable()
            return

        local_path = await summarizer_service.resolve_document_file(self.selected_book_id, book_doc)
        context_text = ""

        if local_path and Path(local_path).exists():
            ext = Path(local_path).suffix.upper()
            size_mb = Path(local_path).stat().st_size / (1024 * 1024)
            self.summary_output.content = f"📖 **Reading *{title}* ({ext}, {size_mb:.1f} MB)...**"

            raw_text = await summarizer_service.extract_book_content(local_path)
            if raw_text and len(raw_text.strip()) > 30:
                context_text = summarizer_service.partition_document_text(raw_text)

        if not context_text:
            self.summary_output.content = (
                f"⚠️ **Could not extract readable text for *{title}*.**\n\n"
                "Please verify that the file exists on disk and contains readable text (PDF, PPTX, DOCX, EPUB, TXT)."
            )
            if self.generate_btn:
                self.generate_btn.enable()
            return

        messages = summarizer_service.build_summary_messages(self.selected_mode, title, context_text)

        self.summary_output.content = f"🧠 **TARS AI is analyzing and generating executive summary for *{title}*...**\n\n"
        buffer = f"## Summary: {title}\n\n"

        try:
            async for token in tars_engine.stream_response(messages):
                buffer += token
                self.summary_output.content = buffer

            self.current_summary_text = buffer
            if self.copy_btn:
                self.copy_btn.set_visibility(True)
            if self.save_doc_btn:
                self.save_doc_btn.text = 'Save to Book'
                self.save_doc_btn.enable()
                self.save_doc_btn.set_visibility(True)
        except Exception as e:
            logger.error(f"Summarizer generation error: {e}", exc_info=True)
            ui.notify(f"Generation Error: {e}", type='negative')
        finally:
            if self.generate_btn:
                self.generate_btn.enable()

    async def save_to_document(self):
        """Saves current summary directly to the book record in MongoDB."""
        if not self.selected_book_id or not self.current_summary_text:
            ui.notify("No summary text available to save.", type='warning')
            return
        try:
            success = await summarizer_service.save_summary_to_database(self.selected_book_id, self.current_summary_text)
            if success:
                if self.save_doc_btn:
                    self.save_doc_btn.text = 'Saved to Book ✓'
                    self.save_doc_btn.disable()
                if self.view_book_btn:
                    self.view_book_btn.set_visibility(True)
                ui.notify("Summary saved to Book record! Click 'View on Book Page ➔' to see it.", type='positive', duration=6)
            else:
                ui.notify("Failed to save summary to document.", type='negative')
        except Exception as ex:
            ui.notify(f"Error saving: {ex}", type='negative')

    def build_ui(self):
        """Constructs responsive Summarizer UI."""
        drawer = sidebar()
        header(drawer_reference=drawer)
        bottom_nav()

        with ui.column().classes('w-full min-h-[100dvh] pt-[calc(4.5rem+env(safe-area-inset-top,0px))] px-3 sm:px-4 md:pt-24 md:px-8 max-w-7xl mx-auto pb-[calc(5rem+env(safe-area-inset-bottom,0px))] md:pb-16'):
            with ui.column().classes('gap-1 mb-6 sm:mb-8'):
                ui.label('AI Document Summarizer').classes('text-2xl sm:text-3xl font-black text-slate-900 tracking-tight')
                ui.label('Extract authoritative insights, chapters, study guides, and executive summaries directly from your documents.').classes('text-xs sm:text-sm text-slate-500')

            with ui.row().classes('w-full gap-5 sm:gap-8 items-start flex-col lg:flex-row'):
                # Controls Card
                with ui.card().classes('w-full lg:w-1/3 p-4 sm:p-6 rounded-2xl sm:rounded-3xl bg-white border border-slate-200 shadow-sm'):
                    ui.label('Select Document').classes('font-bold text-xs sm:text-sm text-slate-800 uppercase tracking-wider mb-2')

                    try:
                        pre_book = app.storage.user.pop('summarize_book_id', None)
                        if pre_book:
                            self.selected_book_id = str(pre_book)
                    except Exception:
                        pass

                    init_val = self.selected_book_id if (self.selected_book_id and self.selected_book_id in self.books) else None

                    self.book_select = ui.select(
                        self.books, label='Choose from Library', with_input=True,
                        value=init_val,
                        on_change=lambda e: setattr(self, 'selected_book_id', e.value)
                    ).props('outlined rounded bg-color=white').classes('w-full mb-3 sm:mb-4 text-sm')

                    self.mode_select = ui.select(
                        SUMMARY_MODES,
                        value=self.selected_mode,
                        label='Study Guide Mode',
                        on_change=lambda e: setattr(self, 'selected_mode', e.value)
                    ).props('outlined rounded bg-color=white').classes('w-full mb-4 sm:mb-6 text-sm')

                    self.generate_btn = ui.button('Generate Summary', icon='bolt', on_click=self.generate_summary) \
                        .props('unelevated rounded-xl color=indigo size=md').classes('w-full py-2.5 sm:py-3 font-bold shadow-md')

                # Output Card
                with ui.card().classes('w-full lg:w-2/3 p-4 sm:p-6 md:p-8 min-h-[360px] sm:min-h-[460px] rounded-2xl sm:rounded-3xl bg-white border border-slate-200 shadow-sm'):
                    with ui.row().classes('w-full justify-between items-center mb-3 sm:mb-4 pb-3 border-b border-slate-100 flex-wrap gap-2'):
                        with ui.row().classes('items-center gap-2'):
                            ui.icon('summarize', size='sm').classes('text-indigo-600')
                            ui.label('Study Summary Output').classes('text-[10px] sm:text-xs font-bold text-slate-400 uppercase tracking-widest')

                        with ui.row().classes('items-center gap-2 flex-wrap'):
                            self.view_book_btn = ui.button(
                                'View on Book Page ➔', icon='open_in_new',
                                on_click=lambda: ui.navigate.to(f"/book/{self.selected_book_id}")
                            ).props('unelevated rounded-lg color=indigo size=sm').classes('text-xs font-bold')
                            self.view_book_btn.set_visibility(False)

                            self.save_doc_btn = ui.button(
                                'Save to Book', icon='save',
                                on_click=self.save_to_document
                            ).props('unelevated rounded-lg color=positive size=sm').classes('text-xs font-bold')
                            self.save_doc_btn.set_visibility(False)

                            self.copy_btn = ui.button(
                                'Copy', icon='content_copy',
                                on_click=lambda: (ui.run_javascript(f"navigator.clipboard.writeText({repr(self.current_summary_text)});"), ui.notify("Summary copied to clipboard!", type='positive'))
                            ).props('outline rounded-lg color=indigo size=sm').classes('text-xs font-bold')
                            self.copy_btn.set_visibility(False)

                    self.summary_output = ui.markdown('Select a document from the left and click **Generate Summary** to begin.') \
                        .classes('prose max-w-none text-slate-700 leading-relaxed text-sm md:text-base break-words overflow-x-auto')


async def summarizer_page():
    """Route handler for /summarizer."""
    app.storage.client['page_path'] = '/summarizer'
    tool = SummarizerTool()
    await tool.initialize()
    tool.build_ui()