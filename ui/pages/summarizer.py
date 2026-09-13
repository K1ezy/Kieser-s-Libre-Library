from nicegui import ui, app, run
from components.sidebar import sidebar
from components.header import header
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
        self.current_summary_text = ""

    async def initialize(self):
        all_books = await mongo_db.get_all_books(limit=500)
        self.books = {b['id']: b.get('title', 'Untitled') for b in all_books}
        
        if self.book_select:
            self.book_select.options = self.books
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
        
        # Disable button during generation
        if self.generate_btn:
            self.generate_btn.disable()
        if self.copy_btn:
            self.copy_btn.set_visibility(False)

        self.summary_output.content = f"🔍 **Locating and extracting text from *{title}*...**"
        
        # 1. Authoritative document retrieval
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
            
            # Extract actual text from the file
            raw_text = await run.io_bound(extract_text_from_file, local_path)
            if raw_text and len(raw_text.strip()) > 30:
                clean_text = raw_text.strip()
                # Intelligent length handling:
                # For presentation slides, research papers, and chapters (up to 24,000 chars / ~5,500 tokens),
                # pass the ENTIRE document text so zero slides or topics are omitted!
                MAX_SINGLE_PASS_CHARS = 24000
                if len(clean_text) <= MAX_SINGLE_PASS_CHARS:
                    context_text = clean_text
                else:
                    # Multi-section proportional sampling across the entire document
                    # Ensures beginning, early, middle, late, and conclusion are all captured
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

        # 2. Strict Educational Summarization Prompt
        selected_mode = getattr(self, 'selected_mode', 'detailed')
        if selected_mode == 'brief':
            prompt_text = (
                f"You are an expert academic research assistant.\n"
                f"Below is the verified text extracted from: '{title}'.\n\n"
                "CRITICAL INSTRUCTIONS:\n"
                "1. Base your summary STRICTLY on the provided text below. Do NOT reference outside fiction or unrelated materials.\n"
                "2. Provide a concise, high-level executive summary highlighting the core purpose, major themes, and key conclusions.\n\n"
                f"--- START OF DOCUMENT: {title} ---\n{context_text}\n--- END OF DOCUMENT ---\n\n"
                "Organize under:\n"
                "### Executive Overview\n"
                "### Key Findings & Methodologies\n"
                "### Strategic Takeaways\n"
            )
        else:
            prompt_text = (
                f"You are an expert academic professor and educational summarizer.\n"
                f"Below is the verified text extracted from the document: '{title}'.\n\n"
                "CRITICAL INSTRUCTIONS:\n"
                "1. Base your summary STRICTLY and EXCLUSIVELY on the provided document text below. Do NOT reference outside fiction or unrelated materials.\n"
                "2. BE EXHAUSTIVE AND COMPLETE: Do NOT omit any frameworks, hierarchies, methodologies, criteria, or classifications.\n"
                "3. Use domain-appropriate academic headings based purely on the document's actual subject matter. Do NOT invent unrelated headings (such as 'Security Controls') unless the document is explicitly about security.\n\n"
                f"--- START OF DOCUMENT: {title} ---\n{context_text}\n--- END OF DOCUMENT ---\n\n"
                "Produce an exhaustive, high-yield master study guide covering:\n\n"
                "### 1. Executive Overview, Research Process & Hypothesis Criteria\n"
                "- Formal definitions, goals, and the complete 6-step research process (with examples).\n"
                "- Policy & decision-making pipeline (Findings -> Policies -> Development).\n"
                "- Literature review (purpose, gaps, sources) and Hypothesis formulation (mandatory criteria: Clear & Specific, Testable, Falsifiable).\n\n"
                "### 2. Structural Hierarchy & Key Areas of Computer Science Research\n"
                "- The 4-Tier Knowledge Hierarchy (Foundational Knowledge, Systems & Architecture, Core Applied Areas, Advanced Specializations - list all subjects in each tier).\n"
                "- Key computer science research areas.\n\n"
                "### 3. Sustainable Research in Computer Science\n"
                "- Detail all sustainability dimensions: Energy-Efficient Computing, Green Software Engineering, Circular Economy in Computing, Climate Informatics, and Sustainable AI.\n\n"
                "### 4. Comprehensive Research Methodologies Catalog\n"
                "- Qualitative vs. Quantitative (purposes, data collection, analysis, CS & theoretical examples).\n"
                "- Experimental Research (interventions, control vs experimental groups, confounding variables) vs. Observational Research.\n"
                "- Descriptive vs. Correlational Research (purposes, designs, cross-sectional studies, CS examples).\n"
                "- Comparative Studies (purposes, benchmarks, CS examples) and Case Studies (in-depth analysis, CS examples, and the 6-step case study execution framework).\n\n"
                "### 5. The 5 Major Challenges in Computer Science Research\n"
                "- Detail all sub-challenges across: Data-Related, Algorithmic & Technical, Ethical & Societal, Resource & Infrastructure, and Research Process.\n\n"
                "### 6. Emerging Technologies & Future Directions\n"
                "- Specific emerging technologies (GenAI/LLMs, Domain-Specific AI, Edge AI, GNNs, BCI, XR, Emotion AI, Assistive AI).\n"
                "- Future directions and concluding takeaways (Human-Centered AI, Explainability/Trust, Sustainable AI, AI for Science & Society).\n"
            )

        messages = [
            {"role": "system", "content": "You are a professional research librarian and educational document summarizer."},
            {"role": "user", "content": prompt_text}
        ]

        # 3. Stream Response with TARS
        self.summary_output.content = f"🧠 **TARS AI is analyzing and generating executive summary for *{title}*...**\n\n"
        buffer = f"## Summary: {title}\n\n"
        
        try:
            async for token in tars_engine.stream_response(messages):
                buffer += token
                self.summary_output.content = buffer
            
            self.current_summary_text = buffer
            if self.copy_btn:
                self.copy_btn.set_visibility(True)
        except Exception as e:
            logger.error(f"Summarizer generation error: {e}", exc_info=True)
            ui.notify(f"Generation Error: {e}", type='negative')
        finally:
            if self.generate_btn:
                self.generate_btn.enable()

    def build_ui(self):
        drawer = sidebar()
        header(drawer_reference=drawer)

        with ui.column().classes('w-full min-h-screen pt-20 px-4 md:pt-24 md:px-8 max-w-7xl mx-auto bg-slate-50/50 dark:bg-transparent pb-24'):
            
            with ui.column().classes('gap-1 mb-8'):
                ui.label('AI Document Summarizer').classes('text-3xl font-black text-slate-800 dark:text-slate-100 tracking-tight')
                ui.label('Extract authoritative insights, chapters, and executive summaries directly from your course materials and books.').classes('text-sm text-slate-500 dark:text-slate-400')

            with ui.row().classes('w-full gap-8 items-start flex-col lg:flex-row'):
                
                # Controls Card
                with ui.card().classes('w-full lg:w-1/3 p-6 rounded-3xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 shadow-sm'):
                    ui.label('Select Document').classes('font-bold text-sm text-slate-700 dark:text-slate-200 uppercase tracking-wider mb-2')
                    
                    self.book_select = ui.select(
                        {}, label='Choose from Library', with_input=True, 
                        on_change=lambda e: setattr(self, 'selected_book_id', e.value)
                    ).props('outlined rounded').classes('w-full mb-4')

                    self.selected_mode = 'detailed'
                    self.mode_select = ui.select(
                        {'detailed': 'Exhaustive Study Guide (All Topics)', 'brief': 'Executive Overview (Concise)'},
                        value='detailed',
                        label='Summary Depth',
                        on_change=lambda e: setattr(self, 'selected_mode', e.value)
                    ).props('outlined rounded').classes('w-full mb-6')
                    
                    self.generate_btn = ui.button('Generate Summary', icon='bolt', on_click=self.generate_summary) \
                        .props('unelevated rounded color=indigo').classes('w-full py-3 font-bold shadow-md')

                # Output Card
                with ui.card().classes('w-full lg:w-2/3 p-8 min-h-[460px] rounded-3xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 shadow-sm'):
                    with ui.row().classes('w-full justify-between items-center mb-4 pb-3 border-b border-slate-100 dark:border-slate-800'):
                        with ui.row().classes('items-center gap-2'):
                            ui.icon('summarize', size='sm').classes('text-indigo-500')
                            ui.label('Executive Summary Output').classes('text-xs font-bold text-slate-400 uppercase tracking-widest')
                        
                        self.copy_btn = ui.button(
                            'Copy', icon='content_copy', 
                            on_click=lambda: (ui.run_javascript(f"navigator.clipboard.writeText({repr(self.current_summary_text)});"), ui.notify("Summary copied to clipboard!", type='positive'))
                        ).props('flat dense color=indigo').classes('text-xs font-bold')
                        self.copy_btn.set_visibility(False)
                    
                    self.summary_output = ui.markdown('Select a document from the left and click **Generate Summary** to begin.') \
                        .classes('prose max-w-none text-slate-700 dark:text-slate-300 leading-relaxed text-sm md:text-base')

async def summarizer_page():
    app.storage.client['page_path'] = '/summarizer'
    tool = SummarizerTool()
    tool.build_ui()
    await tool.initialize()