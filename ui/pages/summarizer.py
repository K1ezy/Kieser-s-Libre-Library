from nicegui import ui, app, run
from components.sidebar import sidebar
from components.header import header
from components.bottom_nav import bottom_nav
from core.database.mongo_manager import mongo_db
from core.ai_engine.llm_engine import tars_engine
from core.utils.text_extractor import extract_text_from_file
from core.config import settings
import asyncio
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger("SUMMARIZER")

class SummarizerTool:
    def __init__(self):
        self.books = {}
        self.selected_book_id = None
        self.summary_output = None
        self.book_select = None
        self.doc_badge = None
        self.generate_btn = None
        self.copy_btn = None
        self.save_doc_btn = None
        self.view_book_btn = None
        self.current_summary_text = ""

    async def initialize(self):
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

    async def resolve_document_path(self, book_id: str, book_doc: dict) -> Optional[str]:
        """
        Authoritatively locates the physical file on disk for the selected document.
        Searches organized books, formats dictionary, and storage directories.
        """
        # 1. Direct local_path from database record
        lp = book_doc.get('local_path')
        if lp and Path(lp).exists():
            return lp

        # 2. Parse from static_books formats dictionary
        formats = book_doc.get('formats') or {}
        for fmt, url_path in formats.items():
            if url_path and '/static_books/' in url_path:
                rel_part = url_path.split('/static_books/', 1)[1]
                candidate = settings.BASE_DIR / 'data' / 'books' / rel_part
                if candidate.exists():
                    return str(candidate)

        # 3. Check data/books/{book_id} folder
        book_dir = settings.BASE_DIR / 'data' / 'books' / book_id
        if book_dir.exists() and book_dir.is_dir():
            valid_exts = {'.pdf', '.epub', '.docx', '.pptx', '.txt'}
            files = [f for f in book_dir.iterdir() if f.is_file() and f.suffix.lower() in valid_exts]
            if files:
                return str(files[0])

        # 4. Check global BOOKS_DIR (E-Books directory)
        if settings.BOOKS_DIR.exists():
            for p in settings.BOOKS_DIR.rglob('*'):
                if p.is_file() and (p.stem.lower() == book_id.lower() or book_id.lower() in p.stem.lower()):
                    return str(p)

        # 5. Check uploads directory
        uploads_dir = settings.BASE_DIR / 'uploads'
        if uploads_dir.exists():
            for p in uploads_dir.iterdir():
                if p.is_file() and (p.stem.lower() == book_id.lower() or book_id.lower() in p.stem.lower()):
                    return str(p)

        return None

    async def generate_summary(self):
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
            self.summary_output.content = f"⚠️ **Notice:** Document record not found in the library database."
            if self.generate_btn: self.generate_btn.enable()
            return

        local_path = await self.resolve_document_path(self.selected_book_id, book_doc)
        context_text = ""

        if local_path and Path(local_path).exists():
            ext = Path(local_path).suffix.upper()
            size_mb = Path(local_path).stat().st_size / (1024 * 1024)
            self.summary_output.content = f"📖 **Reading *{title}* ({ext}, {size_mb:.1f} MB)...**"
            
            raw_text = await run.io_bound(extract_text_from_file, local_path)
            if raw_text and len(raw_text.strip()) > 30:
                clean_text = raw_text.strip()
                MAX_SINGLE_PASS_CHARS = 24000
                if len(clean_text) <= MAX_SINGLE_PASS_CHARS:
                    context_text = clean_text
                else:
                    chunk = 4500
                    total = len(clean_text)
                    p1 = clean_text[:chunk]
                    p2 = clean_text[total//4 : total//4 + chunk]
                    p3 = clean_text[total//2 : total//2 + chunk]
                    p4 = clean_text[3*total//4 : 3*total//4 + chunk]
                    p5 = clean_text[-chunk:]
                    context_text = (
                        f"=== PART 1: INTRODUCTION & BEGINNING ===\n{p1}\n\n"
                        f"=== PART 2: EARLY SECTIONS ===\n{p2}\n\n"
                        f"=== PART 3: CORE MIDDLE SECTIONS ===\n{p3}\n\n"
                        f"=== PART 4: ADVANCED / LATER TOPICS ===\n{p4}\n\n"
                        f"=== PART 5: CONCLUSION & TAKEAWAYS ===\n{p5}"
                    )

        if not context_text:
            self.summary_output.content = (
                f"⚠️ **Could not extract readable text for *{title}*.**\n\n"
                "Please verify that the file exists on disk and contains readable text (PDF, PPTX, DOCX, EPUB, TXT)."
            )
            if self.generate_btn: self.generate_btn.enable()
            return

        selected_mode = getattr(self, 'selected_mode', 'detailed')
        
        if selected_mode == 'brief':
            prompt_text = (
                f"You are an expert research librarian and academic analyst.\n"
                f"Below is the verified text extracted from the document: '{title}'.\n\n"
                "CRITICAL INSTRUCTIONS:\n"
                "1. Base your summary STRICTLY and EXCLUSIVELY on the provided text below. Do NOT hallucinate outside materials.\n"
                "2. Provide an authoritative Executive Overview highlighting the central thesis, primary objectives, key findings, and strategic takeaways.\n"
                "3. Structure your response clearly using markdown headings:\n"
                "### 🎯 Executive Summary & Core Objective\n"
                "### 🔍 Key Findings & Main Themes\n"
                "### 💡 Major Takeaways & Practical Applications\n\n"
                f"--- START OF DOCUMENT: {title} ---\n{context_text}\n--- END OF DOCUMENT ---"
            )
        elif selected_mode == 'concepts':
            prompt_text = (
                f"You are a master educator and subject matter expert.\n"
                f"Below is the verified text extracted from the document: '{title}'.\n\n"
                "CRITICAL INSTRUCTIONS:\n"
                "1. Extract and explain all CORE CONCEPTS, TERMINOLOGY, FRAMEWORKS, and PRINCIPLES found in this document.\n"
                "2. Base explanations purely on the text provided.\n"
                "3. Structure your response under:\n"
                "### 📚 Foundational Terminology & Definitions\n"
                "### ⚙️ Core Principles, Frameworks & Methodologies\n"
                "### ⚠️ Critical Distinctions & Rules to Remember\n\n"
                f"--- START OF DOCUMENT: {title} ---\n{context_text}\n--- END OF DOCUMENT ---"
            )
        elif selected_mode == 'qa':
            prompt_text = (
                f"You are a university professor creating an active recall exam review guide.\n"
                f"Below is the verified text extracted from the document: '{title}'.\n\n"
                "CRITICAL INSTRUCTIONS:\n"
                "1. Generate 8-12 high-yield study questions and in-depth answers covering the most vital topics of this document.\n"
                "2. Include both conceptual understanding and applied analysis questions.\n"
                "3. Format each item clearly with:\n"
                "**Q[N]: [Clear, testable question]**\n"
                "**Answer:** [Accurate explanation referencing the document]\n\n"
                f"--- START OF DOCUMENT: {title} ---\n{context_text}\n--- END OF DOCUMENT ---"
            )
        else:
            prompt_text = (
                f"You are an expert academic professor and educational summarizer.\n"
                f"Below is the verified text extracted from the document: '{title}'.\n\n"
                "CRITICAL INSTRUCTIONS:\n"
                "1. Base your summary STRICTLY and EXCLUSIVELY on the provided document text below. Do NOT invent outside topics or reference unrelated domains.\n"
                "2. BE EXHAUSTIVE AND THOROUGH: Ensure all major sections, arguments, methodologies, criteria, and classifications present in the text are comprehensively covered.\n"
                "3. Derive section headings DYNAMICALLY based directly on the actual subject matter and themes of the document.\n"
                "4. Structure your response with the following format:\n"
                "### 1. Document Overview & Primary Goals\n"
                "- Context, purpose, scope, and target audience.\n\n"
                "### 2. Comprehensive Section & Topic Breakdown\n"
                "- In-depth explanation of each key topic, model, or narrative progression presented in the text.\n\n"
                "### 3. Key Methodologies, Evidence & Analysis\n"
                "- Specific data, procedures, qualitative/quantitative points, or arguments made.\n\n"
                "### 4. Critical Insights & Key Implications\n"
                "- High-yield conclusions, lessons learned, and future directions.\n\n"
                f"--- START OF DOCUMENT: {title} ---\n{context_text}\n--- END OF DOCUMENT ---"
            )

        messages = [
            {"role": "system", "content": "You are a professional research librarian and educational document summarizer."},
            {"role": "user", "content": prompt_text}
        ]

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
            success = await mongo_db.save_book_summary(self.selected_book_id, self.current_summary_text)
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

                    self.selected_mode = 'detailed'
                    self.mode_select = ui.select(
                        {
                            'detailed': 'Exhaustive Study Guide (Full Depth)',
                            'brief': 'Executive Overview (Concise)',
                            'concepts': 'Key Concepts & Definitions',
                            'qa': 'Q&A Active Recall Prep'
                        },
                        value='detailed',
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
    app.storage.client['page_path'] = '/summarizer'
    tool = SummarizerTool()
    await tool.initialize()
    tool.build_ui()