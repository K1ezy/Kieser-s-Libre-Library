from nicegui import ui, app
from typing import Dict, Any, Callable
from datetime import datetime, timedelta
from core.auth.jwt_handler import get_current_user_role
from core.services.book_details_service import book_details_service
from core.database.mongo_manager import mongo_db


def open_cover_dialog(title: str, cover_url: str):
    """Cover zoom lightbox preview modal."""
    with ui.dialog() as cover_dialog, ui.card().classes(
        'p-4 sm:p-5 bg-white/95 backdrop-blur-md rounded-3xl max-w-lg w-full items-center shadow-2xl border border-slate-200'
    ):
        with ui.row().classes('w-full justify-between items-center px-1 pb-3 border-b border-slate-100'):
            with ui.column().classes('gap-0 max-w-[80%]'):
                ui.label(title).classes('font-bold text-slate-800 text-sm sm:text-base truncate')
                ui.label('Front Page Cover Preview').classes('text-xs text-indigo-600 font-semibold')
            ui.button(icon='close', on_click=cover_dialog.close).props('flat round dense size=sm color=grey')
        with ui.element('div').classes('w-full max-h-[72vh] flex items-center justify-center overflow-hidden rounded-2xl my-3 bg-slate-50 border border-slate-100 shadow-inner'):
            ui.image(cover_url).classes('max-h-[70vh] object-contain rounded-xl shadow-md')
        with ui.row().classes('w-full justify-end pt-1'):
            ui.button('Close', on_click=cover_dialog.close).props('unelevated rounded-xl size=sm color=indigo font-bold')
    cover_dialog.open()


def open_edit_metadata_dialog(book_id: str, book: Dict[str, Any], on_saved: Callable[[Dict[str, Any]], None]):
    """Edit Book Metadata Dialog (Librarian & Admin Restricted)."""
    if get_current_user_role() not in ('admin', 'librarian'):
        ui.notify("Librarian or Administrator privileges required to edit book metadata.", type='warning')
        return

    title = book.get('title', 'Untitled')
    author_name = book.get('display_author') or (book.get('authors', ['Unknown'])[0] if book.get('authors') else 'Unknown')
    shelves = book.get('shelves', []) or []
    genres = book.get('genres', []) or book.get('subjects', []) or []
    publisher = book.get('publisher') or ""
    pub_year = book.get('publication_year') or ""
    synopsis_text = book.get('description') or ""

    with ui.dialog() as edit_dialog, ui.card().classes(
        'w-[calc(100vw-2rem)] max-w-2xl p-5 sm:p-6 bg-white rounded-3xl shadow-2xl border border-slate-200 max-h-[90vh] flex flex-col'
    ):
        with ui.row().classes('w-full justify-between items-center pb-3 border-b border-slate-100'):
            with ui.row().classes('items-center gap-2'):
                with ui.element('div').classes('p-2 rounded-xl bg-indigo-50 text-indigo-600'):
                    ui.icon('edit_note', size='20px')
                ui.label('Edit Book Metadata').classes('text-lg font-black text-slate-900')
            ui.button(icon='close', on_click=edit_dialog.close).props('flat round dense size=sm color=grey')

        with ui.column().classes('w-full gap-3.5 py-4 overflow-y-auto flex-grow no-scrollbar'):
            title_input = ui.input(label='Title', value=title).props('outlined dense rounded').classes('w-full')
            author_input = ui.input(label='Author(s)', value=author_name if author_name != 'Unknown' else '').props('outlined dense rounded').classes('w-full')
            
            with ui.row().classes('w-full gap-3 flex-col sm:flex-row'):
                shelves_val = ", ".join(shelves) if isinstance(shelves, list) else str(shelves)
                shelves_input = ui.input(label='Shelf / Category', value=shelves_val).props('outlined dense rounded').classes('flex-1')
                
                tags_val = ", ".join(genres) if isinstance(genres, list) else str(genres)
                tags_input = ui.input(label='Tags / Genres (comma-separated)', value=tags_val).props('outlined dense rounded').classes('flex-1')

            with ui.row().classes('w-full gap-3 flex-col sm:flex-row'):
                pub_input = ui.input(label='Publisher', value=str(publisher)).props('outlined dense rounded').classes('flex-1')
                year_input = ui.input(label='Publication Year', value=str(pub_year)).props('outlined dense rounded').classes('flex-1')

            desc_input = ui.textarea(label='Synopsis / Description', value=synopsis_text).props('outlined rounded rows=5').classes('w-full text-sm')

        with ui.row().classes('w-full justify-end gap-2.5 pt-3 border-t border-slate-100'):
            ui.button('Cancel', on_click=edit_dialog.close).props('flat rounded-xl color=grey font-bold size=sm')
            
            async def save_metadata():
                new_title = title_input.value.strip() or title
                new_author = author_input.value.strip() or 'Unknown'
                new_pub = pub_input.value.strip()
                new_year = year_input.value.strip()
                new_desc = book_details_service.format_synopsis_text(desc_input.value.strip())

                clean_shelves = [s.strip() for s in shelves_input.value.split(',') if s.strip()]
                clean_genres = [g.strip() for g in tags_input.value.split(',') if g.strip()]

                updates = {
                    'title': new_title,
                    'display_author': new_author,
                    'authors': [new_author],
                    'publisher': new_pub,
                    'publication_year': new_year,
                    'description': new_desc,
                    'shelves': clean_shelves,
                    'genres': clean_genres,
                }

                success, msg = await book_details_service.update_metadata(book_id, updates)
                if success:
                    edit_dialog.close()
                    ui.notify('Book metadata updated successfully!', type='positive')
                    if on_saved:
                        on_saved(updates)
                else:
                    ui.notify(msg, type='negative')

            ui.button('Save Changes', icon='save', on_click=save_metadata)\
                .props('unelevated rounded-xl color=indigo font-bold size=sm shadow-md')

    edit_dialog.open()


def open_delete_dialog(book_id: str, title: str, on_deleted: Callable[[], None]):
    """Delete Confirmation Dialog (Librarian & Admin Restricted)."""
    if get_current_user_role() not in ('admin', 'librarian'):
        ui.notify("Librarian or Administrator privileges required to delete books.", type='warning')
        return

    with ui.dialog() as del_dialog, ui.card().classes('p-5 sm:p-6 bg-white rounded-3xl max-w-md w-full shadow-2xl border border-slate-200'):
        with ui.row().classes('items-center gap-3 text-red-600 mb-2'):
            with ui.element('div').classes('p-2.5 rounded-2xl bg-red-50 text-red-600 border border-red-100'):
                ui.icon('warning', size='24px')
            ui.label('Delete Document').classes('text-lg font-black text-slate-900')
        
        ui.label(
            f"Are you sure you want to permanently remove '{title}' from your library? "
            "This action cannot be undone."
        ).classes('text-sm text-slate-600 leading-relaxed mb-4')
        
        with ui.row().classes('w-full justify-end gap-2'):
            ui.button('Cancel', on_click=del_dialog.close).props('flat rounded-xl color=grey font-bold size=sm')
            
            async def do_delete():
                delete_btn.props('loading')
                success, msg = await book_details_service.delete_book(book_id)
                del_dialog.close()
                if success:
                    ui.notify(f"'{title}' has been deleted.", type='positive')
                    if on_deleted:
                        on_deleted()
                else:
                    ui.notify(msg, type='negative')
                    delete_btn.props(remove='loading')

            delete_btn = ui.button('Delete Permanently', icon='delete_forever', on_click=do_delete)\
                .props('unelevated rounded-xl color=red font-bold size=sm shadow-md')

    del_dialog.open()


async def open_borrow_dialog(book_id: str, book: Dict[str, Any]):
    """Opens a circulation modal for borrowing a physical copy of a book."""
    user_id = app.storage.user.get('user_id') or app.storage.user.get('token')
    if not user_id:
        ui.notify("Please log in to borrow physical library books.", type='warning')
        ui.navigate.to('/login')
        return

    user = await mongo_db.users.get_user(user_id)
    if not user:
        user = await mongo_db.users.get_user_by_username(user_id)
    if not user:
        ui.notify("Unable to locate your user account profile.", type='negative')
        return

    role = str(user.get("role", "student")).lower().strip()
    is_faculty = role == "faculty"
    loan_days = 30 if is_faculty else 7
    due_date = datetime.now() + timedelta(days=loan_days)
    formatted_due = due_date.strftime("%B %d, %Y")

    title = book.get("title", "Untitled Book")
    author_name = book.get("display_author") or (book.get("authors", ["Unknown"])[0] if book.get("authors") else "Unknown")
    inst_id = user.get("institutional_id") or user.get("student_id") or "N/A"
    user_display = user.get("name") or user.get("username", "User")

    with ui.dialog() as borrow_dialog, ui.card().classes(
        'w-[calc(100vw-2rem)] max-w-lg p-5 sm:p-6 bg-white rounded-3xl shadow-2xl border border-slate-200'
    ):
        with ui.row().classes('w-full justify-between items-center pb-3 border-b border-slate-100'):
            with ui.row().classes('items-center gap-2.5'):
                with ui.element('div').classes('p-2.5 rounded-2xl bg-indigo-50 text-indigo-600 border border-indigo-100'):
                    ui.icon('local_library', size='22px')
                with ui.column().classes('gap-0'):
                    ui.label('Circulation Borrowing').classes('text-base sm:text-lg font-black text-slate-900')
                    ui.label('Borrow Physical Book Copy').classes('text-xs text-slate-500 font-medium')
            ui.button(icon='close', on_click=borrow_dialog.close).props('flat round dense size=sm color=grey')

        with ui.column().classes('w-full gap-4 py-2'):
            # Privilege Notice Card
            if is_faculty:
                with ui.element('div').classes(
                    'w-full p-3.5 rounded-2xl bg-emerald-50 border border-emerald-200/80 flex items-start gap-3'
                ):
                    ui.icon('verified', size='22px').classes('text-emerald-600 shrink-0 mt-0.5')
                    with ui.column().classes('gap-0.5'):
                        ui.label('Faculty Privilege Active').classes('text-xs font-black text-emerald-800 uppercase tracking-wide')
                        ui.label(
                            'You receive an extended 30-day loan duration with up to 10 simultaneous books and 2 renewal cycles.'
                        ).classes('text-xs text-emerald-700 leading-snug')
            else:
                with ui.element('div').classes(
                    'w-full p-3.5 rounded-2xl bg-indigo-50/70 border border-indigo-100 flex items-start gap-3'
                ):
                    ui.icon('info', size='20px').classes('text-indigo-600 shrink-0 mt-0.5')
                    with ui.column().classes('gap-0.5'):
                        ui.label('Student Circulation Policy').classes('text-xs font-black text-indigo-900 uppercase tracking-wide')
                        ui.label(
                            'Standard 7-day borrowing period. Up to 3 simultaneous book loans allowed with 2 renewal extensions.'
                        ).classes('text-xs text-indigo-700 leading-snug')

            # Book Summary Pill
            with ui.element('div').classes('w-full p-3 bg-slate-50 border border-slate-200 rounded-2xl flex items-center gap-3'):
                ui.icon('book', size='24px').classes('text-slate-400')
                with ui.column().classes('gap-0 overflow-hidden'):
                    ui.label(title).classes('text-sm font-bold text-slate-800 truncate')
                    ui.label(f"by {author_name}").classes('text-xs text-slate-500 truncate')

            # Circulation Details Grid
            with ui.element('div').classes('w-full grid grid-cols-2 gap-3 p-3 bg-slate-50/60 rounded-2xl border border-slate-100 text-xs'):
                with ui.column().classes('gap-0.5'):
                    ui.label('Borrower Name').classes('text-[11px] font-semibold text-slate-400')
                    ui.label(user_display).classes('font-bold text-slate-800 truncate')
                with ui.column().classes('gap-0.5'):
                    ui.label('Institutional ID').classes('text-[11px] font-semibold text-slate-400')
                    ui.label(inst_id).classes('font-bold font-mono text-indigo-600')
                with ui.column().classes('gap-0.5'):
                    ui.label('Loan Duration').classes('text-[11px] font-semibold text-slate-400')
                    ui.label(f"{loan_days} Days").classes('font-bold text-slate-800')
                with ui.column().classes('gap-0.5'):
                    ui.label('Due Date').classes('text-[11px] font-semibold text-slate-400')
                    ui.label(formatted_due).classes('font-bold text-emerald-600')

            notes_input = ui.input(
                label='Course / Reference Notes (Optional)',
                placeholder='e.g., Thesis research, CS-301 curriculum'
            ).props('outlined dense rounded').classes('w-full text-xs')

        with ui.row().classes('w-full justify-end gap-2 pt-2 border-t border-slate-100'):
            ui.button('Cancel', on_click=borrow_dialog.close).props('flat rounded-xl color=grey font-bold size=sm')

            async def do_borrow():
                borrow_btn.props('loading')
                res = await mongo_db.borrow_book(
                    user_id=user.get("id", user_id),
                    book_id=book_id,
                    notes=notes_input.value or ""
                )
                borrow_btn.props(remove='loading')
                if res.get("success"):
                    borrow_dialog.close()
                    loan = res.get("loan", {})
                    loan_code = loan.get("loan_id", "N/A")
                    ui.notify(f"Book borrowed successfully! Loan Voucher: {loan_code}", type='positive')
                else:
                    ui.notify(res.get("error", "Failed to borrow book."), type='negative')

            borrow_btn = ui.button(
                'Confirm Borrowing',
                icon='check_circle',
                on_click=do_borrow
            ).props('unelevated rounded-xl color=indigo font-bold size=sm shadow-md')

    borrow_dialog.open()
