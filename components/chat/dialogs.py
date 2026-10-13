from nicegui import ui
from typing import Dict, Any, List, Callable, Optional


class BookPickerDialog:
    """Modal dialog for choosing or changing the scoped book filter."""

    def __init__(
        self,
        on_select_book: Callable[[Dict[str, Any]], Any],
        on_clear_focus: Callable[[], Any],
    ):
        self.on_select_book = on_select_book
        self.on_clear_focus = on_clear_focus

        self.dialog = None
        self.list_container = None
        self.cached_books: List[Dict[str, Any]] = []
        self.active_focus_book_id: Optional[str] = None

    def build(self) -> ui.dialog:
        with ui.dialog() as self.dialog, ui.card().classes(
            'w-[calc(100vw-2rem)] max-w-xl p-5 sm:p-6 rounded-3xl bg-white border border-slate-200 shadow-2xl'
        ):
            with ui.row().classes('w-full justify-between items-center mb-1'):
                with ui.row().classes('items-center gap-2'):
                    with ui.element('div').classes('p-2 rounded-xl bg-indigo-50 text-indigo-600 border border-indigo-100'):
                        ui.icon('menu_book', size='20px')
                    ui.label("Focus on a Library Document").classes('text-base sm:text-lg font-black text-slate-900')
                ui.button(icon='close', on_click=self.dialog.close).props('flat round dense size=sm color=grey')

            ui.label("Constrain TARS AI answers and RAG retrieval exclusively to a single book or paper.").classes('text-xs text-slate-500 mb-3')

            with ui.row().classes('w-full gap-2 items-center mb-3'):
                search_inp = ui.input(placeholder='Search by book title or author...').props('outlined rounded-xl dense clearable').classes('flex-grow text-xs')
                search_inp.on('update:model-value', lambda e: self.populate(e.args if hasattr(e, 'args') and e.args else search_inp.value or ""))
                ui.button('Entire Library', icon='public', on_click=lambda: (self.on_clear_focus(), self.dialog.close())) \
                    .props('flat dense rounded-xl size=sm color=indigo font-bold').tooltip('Remove focus constraint and search all books')

            with ui.column().classes('w-full max-h-80 overflow-y-auto gap-2 pr-1 no-scrollbar') as self.list_container:
                pass

        return self.dialog

    def open(self, books: List[Dict[str, Any]], active_focus_book_id: Optional[str] = None):
        self.cached_books = books or []
        self.active_focus_book_id = active_focus_book_id
        if self.dialog:
            self.dialog.open()
        self.populate("")

    def close(self):
        if self.dialog:
            self.dialog.close()

    def populate(self, query: str = ""):
        if not self.list_container:
            return
        self.list_container.clear()

        books = self.cached_books
        if query:
            q = query.lower().strip()
            books = [
                b for b in books
                if q in b.get('title', '').lower()
                or q in str(b.get('display_author', '')).lower()
                or q in str(b.get('authors', '')).lower()
            ]

        with self.list_container:
            if not books:
                with ui.column().classes('w-full items-center py-8 text-center text-slate-400'):
                    ui.icon('search_off', size='2.5em').classes('mb-1')
                    ui.label("No documents matching filter.").classes('text-xs font-semibold')
                return

            for b in books:
                self._render_book_item(b)

    def _render_book_item(self, book: dict):
        title = book.get('title', 'Untitled')
        author = book.get('display_author') or book.get('authors') or 'Unknown'
        if isinstance(author, list) and author:
            author = str(author[0])
        ftype = book.get('file_type', 'PDF').upper()
        is_active = (book.get('id') == self.active_focus_book_id)

        card_border = (
            'border-indigo-400 bg-indigo-50/50'
            if is_active else
            'border-slate-200 bg-white'
        )

        with ui.card().classes(f'w-full p-2.5 sm:p-3 rounded-2xl border {card_border} transition-all hover:border-indigo-400 cursor-pointer shadow-none'):
            with ui.row().classes('w-full items-center justify-between no-wrap gap-2'):
                with ui.row().classes('items-center gap-2.5 flex-grow min-w-0'):
                    with ui.element('div').classes('p-2 rounded-xl bg-indigo-50 text-indigo-600 shrink-0 border border-indigo-100'):
                        ui.icon('menu_book', size='18px')
                    with ui.column().classes('gap-0 flex-grow min-w-0'):
                        ui.label(title).classes('text-xs font-bold text-slate-900 truncate w-full')
                        ui.label(f"{author} • {ftype}").classes('text-[10px] text-slate-400 truncate')

                if is_active:
                    ui.label('Current Focus').classes('text-[10px] font-bold text-indigo-700 bg-indigo-100 px-2.5 py-1 rounded-full shrink-0')
                else:
                    ui.button('Focus', on_click=lambda b=book: (self.on_select_book(b), self.dialog.close())) \
                        .props('unelevated rounded-xl dense size=xs color=indigo').classes('font-bold shrink-0')


def open_upload_dialog(on_upload: Callable[[Any], Any]) -> ui.dialog:
    """Constructs and opens modal for file uploads and knowledge base ingestion."""
    with ui.dialog() as upload_dialog, ui.card().classes(
        'w-[calc(100vw-2rem)] max-w-md p-5 sm:p-6 rounded-3xl bg-white border border-slate-200 shadow-2xl'
    ):
        ui.label("Ingest Document to TARS").classes('text-lg font-black text-slate-900')
        ui.label("Upload PDF, EPUB, DOCX, PPTX, or TXT into your library & knowledge base.").classes('text-xs text-slate-500 mb-4')
        ui.upload(on_upload=on_upload, auto_upload=True).props(
            'accept=".pdf,.epub,.docx,.pptx,.txt" color=indigo flat bordered'
        ).classes('w-full border-2 border-dashed border-indigo-200 rounded-2xl')
        ui.button('Close', on_click=upload_dialog.close).props('flat rounded-xl color=grey size=md font-bold').classes('w-full mt-3')

    upload_dialog.open()
    return upload_dialog


def show_architecture_dialog() -> None:
    """Displays dialog explaining local AI architecture."""
    with ui.dialog() as d, ui.card().classes('max-w-md p-6 rounded-3xl bg-white border border-slate-200 shadow-2xl'):
        with ui.row().classes('items-center gap-2 mb-2'):
            ui.icon('memory', size='24px').classes('text-indigo-600')
            ui.label("TARS AI Architecture").classes('text-base font-bold text-slate-900')
        ui.label("• Engine: Multi-provider Local GGUF, Ollama, & OpenAI endpoints").classes('text-xs text-slate-600')
        ui.label("• Vector DB: ChromaDB with all-MiniLM-L6-v2 embeddings").classes('text-xs text-slate-600')
        ui.label("• Scoped RAG: Document-level & Library-wide semantic retrieval").classes('text-xs text-slate-600')
        ui.label("• Citations: Clickable document page references").classes('text-xs text-slate-600')
        ui.button("Close", on_click=d.close).props('unelevated rounded-xl color=indigo size=sm font-bold').classes('mt-4 w-full shadow-md')
    d.open()
