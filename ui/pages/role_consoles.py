from datetime import datetime
from typing import Any, Dict, List, Optional
from nicegui import ui, app

from core.database.mongo_manager import mongo_db
from core.database.repositories.operations_repository import (
    VALID_PRIORITIES,
    VALID_REQUISITION_STATUSES,
)
from core.security.rbac_policy import (
    Permission,
    UserRole,
    get_circulation_policy,
    has_permission,
)


# =============================================================================
# 1. PROFILE BORROWING QUOTA & 1-CLICK RENEWAL WIDGET (/profile)
# =============================================================================
async def render_profile_loans_and_quota_widget(current_user: Dict[str, Any]) -> None:
    """
    Renders active loans and quota stats in NiceGUI:
    - Quota KPIs (3 books / 7d for Student vs 10 books / 30d for Faculty)
    - Active loan cards with 1-click renewal (+7d for Student, +15d for Faculty)
    """
    policy = get_circulation_policy(current_user)
    user_id = str(current_user.get("_id") or current_user.get("id"))
    active_loans = await mongo_db.operations.list_active_loans(user_id=user_id)

    with ui.column().classes('w-full gap-4'):
        # Quota KPI Grid
        with ui.grid().classes('w-full grid-cols-1 sm:grid-cols-3 gap-3 sm:gap-4 mb-2'):
            with ui.card().classes('p-4 rounded-2xl bg-white border border-slate-200 shadow-xs'):
                ui.label('Active Borrowed Books').classes('text-xs font-bold text-slate-400 uppercase tracking-wider')
                ui.label(f"{len(active_loans)} / {policy.max_active_loans}").classes('text-2xl font-black text-indigo-700')
                ui.label(f"Role: {policy.display_label}").classes('text-[11px] text-slate-500')

            with ui.card().classes('p-4 rounded-2xl bg-white border border-slate-200 shadow-xs'):
                ui.label('Standard Loan Term').classes('text-xs font-bold text-slate-400 uppercase tracking-wider')
                ui.label(f"{policy.loan_duration_days} Days").classes('text-2xl font-black text-slate-900')
                ui.label('Per physical book volume').classes('text-[11px] text-slate-500')

            with ui.card().classes('p-4 rounded-2xl bg-white border border-slate-200 shadow-xs'):
                ui.label('Self-Renewal Extension').classes('text-xs font-bold text-slate-400 uppercase tracking-wider')
                ui.label(f"+{policy.renewal_extension_days} Days").classes('text-2xl font-black text-emerald-600')
                ui.label(f"Max renewals: {policy.max_renewals_per_loan}").classes('text-[11px] text-slate-500')

        if not active_loans:
            with ui.card().classes('w-full p-6 bg-slate-50 border border-slate-200/80 rounded-2xl items-center text-center gap-1'):
                ui.icon('menu_book', size='32px').classes('text-slate-400 mb-1')
                ui.label('You currently have no active physical book loans.').classes('text-sm font-bold text-slate-700')
                ui.label('Browse the library archive to borrow physical catalog volumes.').classes('text-xs text-slate-500')
        else:
            with ui.column().classes('w-full gap-3'):
                for loan in active_loans:
                    lid = str(loan.get("_id") or loan.get("id"))
                    title = loan.get("book_title", "Untitled Book")
                    author = loan.get("book_author", "Unknown Author")
                    due_at = loan.get("due_at")
                    due_str = due_at.strftime("%b %d, %Y") if isinstance(due_at, datetime) else "N/A"
                    status = loan.get("status", "Active")
                    renewals_used = int(loan.get("renewal_count", 0))
                    max_renewals = int(loan.get("max_renewals", policy.max_renewals_per_loan))
                    is_overdue = status == "Overdue"
                    can_renew = (not is_overdue and renewals_used < max_renewals) or policy.can_override_loans

                    with ui.card().classes('w-full p-4 rounded-2xl bg-white border border-slate-200 shadow-xs'):
                        with ui.row().classes('w-full items-start justify-between gap-3 flex-wrap'):
                            with ui.column().classes('gap-0.5 min-w-0 flex-1'):
                                ui.label(title).classes('text-base font-black text-slate-900 truncate')
                                ui.label(f"By {author}").classes('text-xs text-slate-500')
                                with ui.row().classes('items-center gap-2 mt-1 flex-wrap text-xs'):
                                    status_cls = 'bg-rose-50 text-rose-700 border-rose-200' if is_overdue else 'bg-emerald-50 text-emerald-700 border-emerald-200'
                                    ui.label(f"Status: {status}").classes(f'font-bold px-2 py-0.5 rounded border {status_cls}')
                                    ui.label(f"Due: {due_str}").classes('font-bold text-slate-700')
                                    ui.label(f"Renewals used: {renewals_used}/{max_renewals}").classes('text-slate-500')

                            async def do_renew(loan_id=lid):
                                try:
                                    updated = await mongo_db.operations.renew_loan(current_user, loan_id)
                                    new_due = updated["due_at"].strftime("%b %d, %Y")
                                    ui.notify(f"Loan extended! New due date is {new_due}.", type='positive')
                                    ui.navigate.to('/profile')
                                except Exception as err:
                                    ui.notify(str(err), type='negative')

                            ui.button(
                                f"Renew (+{policy.renewal_extension_days}d)",
                                icon='replay',
                                on_click=lambda l_id=lid: do_renew(l_id)
                            ).props(f'unelevated rounded-xl size=sm {"color=indigo" if can_renew else "disable color=grey-4 text-color=grey-7"}')


# =============================================================================
# 2. FACULTY BOOK REQUISITION PORTAL (/requisitions — Form FM-LIBS-002)
# =============================================================================
async def render_faculty_requisition_portal(current_user: Dict[str, Any]) -> None:
    """
    Renders the Faculty Book Requisition Portal (Form FM-LIBS-002) in NiceGUI.
    Enforces submission for Faculty & Admin, and displays committee review notes.
    """
    if not has_permission(current_user, Permission.SUBMIT_REQUISITION_FM_LIBS_002):
        ui.label('Access Restricted: Only Faculty Members and Administrators may submit Form FM-LIBS-002.').classes(
            'p-4 bg-rose-50 text-rose-700 border border-rose-200 rounded-2xl font-bold'
        )
        return

    user_id = str(current_user.get("_id") or current_user.get("id"))
    my_reqs = await mongo_db.operations.list_requisitions(requester_id=user_id)

    with ui.column().classes('w-full gap-6'):
        with ui.card().classes('w-full p-5 sm:p-7 rounded-3xl bg-white border border-slate-200 shadow-sm'):
            with ui.row().classes('items-center gap-2 mb-2'):
                ui.icon('post_add', size='24px').classes('text-indigo-600')
                ui.label('Submit Curricular Book Requisition (Form FM-LIBS-002)').classes('text-lg font-black text-slate-900')
            ui.label('Recommend essential textbooks and reference materials aligned with your course syllabus.').classes('text-xs text-slate-500 mb-4')

            with ui.row().classes('w-full gap-3 mb-3'):
                c_code = ui.input(placeholder='Course Code * (e.g. CS 401)').classes('flex-1 text-sm').props('rounded outlined dense')
                c_prio = ui.select(list(VALID_PRIORITIES), value=VALID_PRIORITIES[0], label='Priority *').classes('flex-1 text-sm').props('rounded outlined dense options-dense')
                c_copies = ui.number(label='Copies *', value=3, min=1, max=30).classes('w-28 text-sm').props('rounded outlined dense')

            with ui.row().classes('w-full gap-3 mb-3'):
                c_title = ui.input(placeholder='Book Title *').classes('flex-1 text-sm').props('rounded outlined dense')
                c_author = ui.input(placeholder='Author(s) *').classes('flex-1 text-sm').props('rounded outlined dense')

            with ui.row().classes('w-full gap-3 mb-3'):
                c_edition = ui.input(placeholder='Edition / Year (e.g. 4th Edition, 2024)').classes('flex-1 text-sm').props('rounded outlined dense')
                c_isbn = ui.input(placeholder='ISBN-13 (Optional)').classes('flex-1 text-sm').props('rounded outlined dense')

            c_just = ui.textarea(
                placeholder='Academic & Syllabus Justification * (Explain how this volume supports course learning outcomes, laboratory experiments, or accreditation requirements...)'
            ).classes('w-full text-sm mb-4').props('rounded outlined dense rows=3')

            async def submit_form():
                try:
                    res = await mongo_db.operations.submit_requisition(
                        faculty_doc=current_user,
                        course_code=(c_code.value or '').strip(),
                        title=(c_title.value or '').strip(),
                        author=(c_author.value or '').strip(),
                        edition=(c_edition.value or 'Latest').strip(),
                        isbn=(c_isbn.value or '').strip(),
                        priority=c_prio.value or 'Standard',
                        justification=(c_just.value or '').strip(),
                        copies_requested=int(c_copies.value or 3),
                    )
                    ui.notify(f"Requisition {res['requisition_code']} submitted successfully for Librarian committee review!", type='positive')
                    ui.navigate.to('/requisitions')
                except Exception as err:
                    ui.notify(str(err), type='negative')

            ui.button('Submit Requisition (FM-LIBS-002)', icon='send', on_click=submit_form) \
                .props('unelevated rounded-xl color=indigo size=sm font-bold shadow-xs')

        # My Requisitions List
        with ui.column().classes('w-full gap-3'):
            ui.label('My Submitted Curricular Requisitions').classes('text-base font-black text-slate-900')
            if not my_reqs:
                ui.label('No requisitions submitted yet.').classes('text-xs text-slate-400 italic')
            else:
                for r in my_reqs:
                    st = r.get("status", "Pending Review")
                    st_cls = 'bg-emerald-50 text-emerald-700 border-emerald-200' if st == 'Approved / In Acquisition' else (
                        'bg-rose-50 text-rose-700 border-rose-200' if st == 'Rejected' else 'bg-amber-50 text-amber-700 border-amber-200'
                    )
                    with ui.card().classes('w-full p-4 rounded-2xl bg-white border border-slate-200 shadow-xs'):
                        with ui.row().classes('w-full items-start justify-between gap-3 flex-wrap'):
                            with ui.column().classes('gap-0.5 min-w-0 flex-1'):
                                with ui.row().classes('items-center gap-2 flex-wrap'):
                                    ui.label(r.get('requisition_code', 'REQ')).classes('text-xs font-mono font-bold text-indigo-700')
                                    ui.label(r.get('title', 'Untitled')).classes('text-sm font-black text-slate-900')
                                ui.label(f"Course: {r.get('course_code')} | Author: {r.get('author')} | Copies: {r.get('copies_requested')}").classes('text-xs text-slate-500')
                                ui.label(f"Justification: {r.get('justification')}").classes('text-xs text-slate-700 mt-1 italic')
                            ui.label(st).classes(f'text-xs font-bold px-2.5 py-0.5 rounded-full border {st_cls}')
                        if r.get('review_notes'):
                            with ui.row().classes('w-full mt-2 p-2.5 rounded-xl bg-slate-50 border border-slate-200 text-xs items-center gap-1.5'):
                                ui.icon('rate_review', size='16px').classes('text-indigo-600')
                                ui.label(f"Committee Note ({r.get('reviewed_by', 'Librarian')}): {r.get('review_notes')}").classes('text-slate-700')


# =============================================================================
# 3. LIBRARIAN OPERATIONS CONSOLE (/librarian)
# =============================================================================
async def render_librarian_operations_console(*args, **kwargs) -> None:
    """
    Renders the Librarian Operations Console (/librarian):
    - Circulation Desk Widget (Active loans + 1-click Check-In Return + Staff Override)
    - Faculty Requisition Approval Queue (Form FM-LIBS-002)
    - OPDS E-Reader Feed Hub (Apple Books, KOReader, Moon+ Reader XML feed)
    - Collection Format Analytics (EPUB Reflowable vs. Fixed PDF)
    """
    current_user = None
    for arg in args:
        if isinstance(arg, dict) and ("role" in arg or "institutional_id" in arg or "username" in arg):
            current_user = arg
            break
    if not current_user:
        current_user = kwargs.get("current_user", {})

    if not has_permission(current_user, Permission.OPERATE_CIRCULATION_DESK):
        ui.label('Access Restricted: Only University Librarians and Administrators can access the Librarian Operations Console.').classes(
            'p-4 bg-rose-50 text-rose-700 border border-rose-200 rounded-2xl font-bold'
        )
        return

    active_loans = await mongo_db.operations.list_active_loans()
    overdue_loans = [l for l in active_loans if l.get("status") == "Overdue"]
    pending_reqs = await mongo_db.operations.list_requisitions(status_filter="Pending Review")
    fmt_stats = await mongo_db.operations.get_collection_format_analytics()

    with ui.column().classes('w-full gap-6'):
        # Header banner
        with ui.row().classes('w-full items-start justify-between gap-4 flex-wrap'):
            with ui.column().classes('gap-1'):
                with ui.row().classes('items-center gap-2.5'):
                    with ui.element('div').classes('p-2.5 rounded-2xl bg-indigo-50 text-indigo-600 border border-indigo-100 shadow-sm'):
                        ui.icon('local_library', size='28px')
                    with ui.column().classes('gap-0'):
                        ui.label('Librarian Operations Console').classes('text-2xl sm:text-3xl font-black text-slate-900 tracking-tight')
                        ui.label('Physical Circulation Desk • Curricular Requisition Queue (FM-LIBS-002) • OPDS Feed Hub • Format Analytics').classes('text-xs sm:text-sm text-slate-500')

        # Top Operational KPIs
        with ui.grid().classes('w-full grid-cols-2 md:grid-cols-4 gap-3 sm:gap-4 mb-2'):
            with ui.card().classes('p-4 rounded-2xl bg-white border border-slate-200 shadow-xs'):
                ui.label('Active Loans').classes('text-xs font-bold text-slate-400 uppercase tracking-wider')
                ui.label(str(len(active_loans))).classes('text-2xl font-black text-indigo-700')
                ui.label('Physical volumes out').classes('text-[11px] text-slate-500')

            with ui.card().classes('p-4 rounded-2xl bg-white border border-slate-200 shadow-xs'):
                ui.label('Overdue Volumes').classes('text-xs font-bold text-slate-400 uppercase tracking-wider')
                ui.label(str(len(overdue_loans))).classes('text-2xl font-black text-rose-600')
                ui.label('Past loan due date').classes('text-[11px] text-slate-500')

            with ui.card().classes('p-4 rounded-2xl bg-white border border-slate-200 shadow-xs'):
                ui.label('FM-LIBS-002 Queue').classes('text-xs font-bold text-slate-400 uppercase tracking-wider')
                ui.label(str(len(pending_reqs))).classes('text-2xl font-black text-amber-600')
                ui.label('Pending requisition review').classes('text-[11px] text-slate-500')

            with ui.card().classes('p-4 rounded-2xl bg-white border border-slate-200 shadow-xs'):
                ui.label('Collection (EPUB/PDF)').classes('text-xs font-bold text-slate-400 uppercase tracking-wider')
                ui.label(f"{fmt_stats['epub_reflowable']} / {fmt_stats['pdf_fixed']}").classes('text-2xl font-black text-slate-900')
                ui.label('Reflowable vs Fixed').classes('text-[11px] text-slate-500')

        # Tabs for operational consoles
        with ui.tabs().classes('w-full') as tabs:
            tab_circ = ui.tab('Circulation Desk')
            tab_reqs = ui.tab('Requisitions Queue (FM-LIBS-002)')
            tab_opds = ui.tab('OPDS Feed Hub')
            tab_fmt = ui.tab('Format Analytics')

        with ui.tab_panels(tabs, value=tab_circ).classes('w-full bg-transparent'):
            with ui.tab_panel(tab_circ).classes('p-0 pt-4'):
                with ui.column().classes('w-full gap-3'):
                    if not active_loans:
                        ui.label('All borrowed physical books are currently checked in!').classes('text-sm text-slate-500 italic p-4 bg-slate-50 rounded-2xl border border-slate-200')
                    else:
                        for loan in active_loans:
                            lid = str(loan.get("_id") or loan.get("id"))
                            status = loan.get("status", "Active")
                            due_at = loan.get("due_at")
                            due_str = due_at.strftime("%b %d, %Y") if isinstance(due_at, datetime) else "N/A"
                            is_overdue = status == "Overdue"

                            with ui.card().classes('w-full p-4 rounded-2xl bg-white border border-slate-200 shadow-xs'):
                                with ui.row().classes('w-full items-start justify-between gap-3 flex-wrap'):
                                    with ui.column().classes('gap-0.5 min-w-0 flex-1'):
                                        ui.label(loan.get('book_title', 'Untitled')).classes('text-sm font-black text-slate-900')
                                        ui.label(f"Borrower: {loan.get('borrower_name')} ({loan.get('institutional_id')}) • Role: {loan.get('borrower_role', 'student').capitalize()}").classes('text-xs text-slate-500')
                                        ui.label(f"Due: {due_str}").classes('text-xs font-bold ' + ('text-rose-600' if is_overdue else 'text-slate-700'))

                                    with ui.row().classes('items-center gap-2'):
                                        async def do_checkin(loan_id=lid):
                                            try:
                                                await mongo_db.operations.checkin_return_loan(current_user, loan_id)
                                                ui.notify('Book successfully checked in and returned to catalog!', type='positive')
                                                ui.navigate.to('/librarian')
                                            except Exception as err:
                                                ui.notify(str(err), type='negative')

                                        async def do_override_renew(loan_id=lid):
                                            try:
                                                await mongo_db.operations.renew_loan(current_user, loan_id)
                                                ui.notify('Loan extended via Staff Override!', type='positive')
                                                ui.navigate.to('/librarian')
                                            except Exception as err:
                                                ui.notify(str(err), type='negative')

                                        ui.button('Check-In Return', icon='check_circle', on_click=lambda l_id=lid: do_checkin(l_id)) \
                                            .props('unelevated rounded-xl color=emerald size=sm font-bold shadow-xs')
                                        ui.button('Override Renew', icon='replay', on_click=lambda l_id=lid: do_override_renew(l_id)) \
                                            .props('outline rounded-xl color=indigo size=sm font-bold')

            with ui.tab_panel(tab_reqs).classes('p-0 pt-4'):
                all_queue_reqs = await mongo_db.operations.list_requisitions()
                with ui.column().classes('w-full gap-3'):
                    if not all_queue_reqs:
                        ui.label('No requisitions in queue.').classes('text-sm text-slate-500 italic p-4 bg-slate-50 rounded-2xl border border-slate-200')
                    else:
                        for req in all_queue_reqs:
                            req_id = str(req.get("_id") or req.get("id"))
                            r_status = req.get("status", "Pending Review")

                            with ui.card().classes('w-full p-4 rounded-2xl bg-white border border-slate-200 shadow-xs'):
                                with ui.row().classes('w-full items-start justify-between gap-3 flex-wrap'):
                                    with ui.column().classes('gap-0.5 min-w-0 flex-1'):
                                        with ui.row().classes('items-center gap-2 flex-wrap'):
                                            ui.label(req.get('requisition_code', 'REQ')).classes('text-xs font-mono font-bold text-indigo-700')
                                            ui.label(req.get('title', 'Untitled')).classes('text-sm font-black text-slate-900')
                                        ui.label(f"Requester: {req.get('requester_name')} ({req.get('requester_inst_id')}) | Dept: {req.get('department')} | Course: {req.get('course_code')}").classes('text-xs text-slate-500')
                                        ui.label(f"Syllabus Justification: {req.get('justification')}").classes('text-xs text-slate-700 mt-1')

                                note_input = ui.input(placeholder='Official Committee Review Note...', value=req.get('review_notes', '')).classes('w-full text-xs mt-2').props('rounded outlined dense')

                                async def do_review(status_to_set, r_id=req_id, n_inp=note_input):
                                    try:
                                        await mongo_db.operations.review_requisition(
                                            reviewer_doc=current_user,
                                            requisition_id=r_id,
                                            new_status=status_to_set,
                                            review_notes=n_inp.value or '',
                                        )
                                        ui.notify(f"Requisition set to '{status_to_set}'.", type='positive')
                                        ui.navigate.to('/librarian')
                                    except Exception as err:
                                        ui.notify(str(err), type='negative')

                                with ui.row().classes('items-center gap-2 mt-2'):
                                    ui.button('Approve / In Acquisition', icon='check', on_click=lambda r_id=req_id: do_review('Approved / In Acquisition', r_id)) \
                                        .props('unelevated rounded-xl color=emerald size=xs font-bold')
                                    ui.button('Reject', icon='close', on_click=lambda r_id=req_id: do_review('Rejected', r_id)) \
                                        .props('unelevated rounded-xl color=rose size=xs font-bold')
                                    ui.button('Keep Pending', icon='schedule', on_click=lambda r_id=req_id: do_review('Pending Review', r_id)) \
                                        .props('flat rounded-xl color=amber size=xs font-bold')

            with ui.tab_panel(tab_opds).classes('p-0 pt-4'):
                with ui.card().classes('w-full p-5 rounded-2xl bg-white border border-slate-200 shadow-xs'):
                    ui.label('OPDS 1.2 Catalog Feed Hub').classes('text-base font-black text-slate-900')
                    ui.label('Broadcast the digital catalog over Wi-Fi directly to dedicated e-readers and mobile reading apps (Apple Books, KOReader, Moon+ Reader, Calibre).').classes('text-xs text-slate-500 mb-3')
                    with ui.row().classes('w-full p-3 bg-slate-50 rounded-xl border border-slate-200 items-center justify-between gap-2'):
                        ui.label('/api/opds/v1.2/catalog.xml').classes('text-xs font-mono font-bold text-indigo-700')
                        ui.button('Copy Feed URL', icon='content_copy', on_click=lambda: ui.notify('Feed URL copied: /api/opds/v1.2/catalog.xml', type='info')).props('flat rounded-lg size=xs')

            with ui.tab_panel(tab_fmt).classes('p-0 pt-4'):
                with ui.card().classes('w-full p-5 rounded-2xl bg-white border border-slate-200 shadow-xs'):
                    ui.label('Multi-Format Digital Catalog Analytics').classes('text-base font-black text-slate-900')
                    ui.label(f"Total Volumes: {fmt_stats['total_volumes']} | EPUB (Reflowable): {fmt_stats['epub_reflowable']} | PDF (Fixed Layout): {fmt_stats['pdf_fixed']} | Other: {fmt_stats['other_formats']}").classes('text-xs text-slate-600')


# =============================================================================
# 4. ADMIN IT GOVERNANCE CONSOLE (/admin)
# =============================================================================
async def render_admin_governance_console(*args, **kwargs) -> None:
    """
    Renders the Admin IT Governance Console (/admin):
    - Quick Role Switcher Bar (/admin, /librarian, /attendance, /requisitions)
    - RBAC User Administration Table (Search, filter, promote/demote roles)
    - Infrastructure Diagnostic Cards
    - TARS AI Vector Store Health & 1-Click Re-Indexing
    """
    current_user = None
    for arg in args:
        if isinstance(arg, dict) and ("role" in arg or "institutional_id" in arg or "username" in arg):
            current_user = arg
            break
    if not current_user:
        current_user = kwargs.get("current_user", {})

    if not has_permission(current_user, Permission.MANAGE_RBAC_USERS):
        ui.label('Root Authority Required: Only System Administrators may access the IT Governance Console.').classes(
            'p-4 bg-rose-50 text-rose-700 border border-rose-200 rounded-2xl font-bold'
        )
        return

    # Quick Role Switcher Bar
    with ui.row().classes('w-full items-center gap-2 mb-4 flex-wrap'):
        ui.button('Librarian Console', icon='local_library', on_click=lambda: ui.navigate.to('/librarian')) \
            .props('unelevated rounded-xl color=indigo size=sm font-bold shadow-xs')
        ui.button('Gate Attendance', icon='qr_code_scanner', on_click=lambda: ui.navigate.to('/attendance')) \
            .props('unelevated rounded-xl color=emerald size=sm font-bold shadow-xs')
        ui.button('Book Requisitions', icon='post_add', on_click=lambda: ui.navigate.to('/requisitions')) \
            .props('unelevated rounded-xl color=amber size=sm font-bold shadow-xs')

    all_users = await mongo_db.get_all_users()
    with ui.card().classes('w-full p-5 rounded-2xl bg-white border border-slate-200 shadow-sm'):
        ui.label('RBAC User Role Administration').classes('text-base font-black text-slate-900 mb-1')
        ui.label('Manage institutional roles across Student, Faculty, Librarian, and Admin.').classes('text-xs text-slate-500 mb-4')

        role_options = [r.value for r in UserRole]
        for u in (all_users or [])[:30]:
            uid = str(u.get("_id") or u.get("id"))
            curr_role = UserRole.normalize(u.get("role")).value
            inst_id = u.get("institutional_id") or u.get("student_id") or "N/A"

            with ui.row().classes('w-full items-center justify-between p-3 rounded-xl border border-slate-100 bg-slate-50/60 mb-2 gap-2 flex-wrap'):
                with ui.column().classes('gap-0 flex-1 min-w-[200px]'):
                    ui.label(f"{u.get('full_name') or u.get('username', 'User')} ({inst_id})").classes('text-xs font-bold text-slate-900')
                    ui.label(f"Email: {u.get('email', 'N/A')} | Dept: {u.get('department') or u.get('program', 'N/A')}").classes('text-[11px] text-slate-500')

                role_sel = ui.select(role_options, value=curr_role).props('dense rounded outlined').classes('w-32 text-xs')

                async def do_save_role(target_id=uid, r_sel=role_sel):
                    try:
                        await mongo_db.operations.update_user_role(current_user, target_id, r_sel.value)
                        ui.notify(f"Role updated to '{r_sel.value}'!", type='positive')
                        ui.navigate.to('/admin')
                    except Exception as err:
                        ui.notify(str(err), type='negative')

                ui.button('Save Role', icon='badge', on_click=lambda tid=uid, rs=role_sel: do_save_role(tid, rs)) \
                    .props('unelevated rounded-xl color=indigo size=xs font-bold')

