import time
from datetime import datetime
from typing import Optional, Dict, Any, List
from nicegui import ui, app

from components.sidebar import sidebar
from components.header import header
from components.bottom_nav import bottom_nav
from core.database.mongo_manager import mongo_db

STATUS_BADGES = {
    "Pending Review": ("bg-amber-50 text-amber-700 border-amber-200", "hourglass_empty"),
    "Approved": ("bg-blue-50 text-blue-700 border-blue-200", "verified"),
    "In Procurement": ("bg-purple-50 text-purple-700 border-purple-200", "shopping_cart"),
    "Available in Library": ("bg-emerald-50 text-emerald-700 border-emerald-200", "check_circle"),
    "Declined": ("bg-rose-50 text-rose-700 border-rose-200", "cancel"),
}

DEPARTMENTS = ["BSCS", "BSIT", "BSED", "BEED", "BSBA", "BSHM", "Crim", "Nursing", "GENERAL"]
URGENCY_LEVELS = ["Normal", "Urgent", "Critical for Accreditation"]


async def requisitions_page():
    """
    Faculty Book Requisition & Curriculum Acquisition Portal.
    Complies with SRS Chapter 1 (Specific Objective 4), Chapter 2 (FR 4),
    and Section 2.3 ("Faculty Book Requisition Form").
    """
    app.storage.client['page_path'] = '/requisitions'

    drawer = sidebar()
    header(drawer_reference=drawer)
    bottom_nav()

    # User context
    user_id = app.storage.user.get('user_id') or "guest"
    user_name = app.storage.user.get('username') or 'Faculty Member'
    user_role = app.storage.user.get('role', 'student').lower()
    can_manage = user_role in ['librarian', 'admin']

    user_profile = await mongo_db.get_user_profile(user_id)
    user_email = user_profile.get('email') or f"{user_name.lower()}@nemsu.edu.ph"
    user_department = user_profile.get('program') or "BSCS"

    # Filter State
    current_status_filter = {'val': 'All'}

    with ui.column().classes(
        'w-full min-h-[100dvh] pt-[calc(4.5rem+env(safe-area-inset-top,0px))] '
        'px-3 sm:px-6 md:pt-24 md:px-8 max-w-7xl mx-auto pb-[calc(5rem+env(safe-area-inset-bottom,0px))] md:pb-16'
    ):
        # Header Banner
        with ui.row().classes('w-full items-center justify-between gap-4 mb-6 flex-wrap'):
            with ui.column().classes('gap-1'):
                with ui.row().classes('items-center gap-2.5'):
                    with ui.element('div').classes('p-2.5 rounded-2xl bg-indigo-50 text-indigo-600 border border-indigo-100 shadow-sm'):
                        ui.icon('post_add', size='28px')
                    with ui.column().classes('gap-0'):
                        ui.label('Faculty Book Requisition Portal').classes('text-2xl sm:text-3xl font-black text-slate-900 tracking-tight')
                        ui.label('Curriculum-aligned textbook requests & real-time procurement tracking (NEMSU Tandag Campus)').classes('text-xs sm:text-sm text-slate-500')

            # Submit New Requisition CTA
            ui.button('Submit Book Requisition', icon='add', on_click=lambda: open_requisition_dialog()) \
                .props('unelevated rounded-xl color=indigo size=md font-bold shadow-md')

        # Status Summary Metrics Bar
        summary_container = ui.row().classes('w-full grid grid-cols-2 sm:grid-cols-4 gap-3 sm:gap-4 mb-6')

        async def refresh_summary():
            summary_container.clear()
            counts = await mongo_db.get_requisition_status_counts()
            all_reqs = await mongo_db.get_requisitions(limit=500)
            with summary_container:
                metric_cards = [
                    ("receipt", "Total Requisitions", str(len(all_reqs)), "text-slate-700", "bg-slate-100"),
                    ("pending_actions", "Pending Review", str(counts.get("Pending Review", 0)), "text-amber-600", "bg-amber-50"),
                    ("local_shipping", "In Procurement", str(counts.get("In Procurement", 0)), "text-purple-600", "bg-purple-50"),
                    ("library_add_check", "Available in Library", str(counts.get("Available in Library", 0)), "text-emerald-600", "bg-emerald-50"),
                ]
                for icon_name, label_text, val_text, text_col, bg_col in metric_cards:
                    with ui.card().classes('p-3.5 sm:p-4 rounded-2xl bg-white border border-slate-200 shadow-sm'):
                        with ui.row().classes('items-center gap-2 mb-1'):
                            with ui.element('div').classes(f'p-1.5 rounded-xl {bg_col} {text_col}'):
                                ui.icon(icon_name, size='18px')
                            ui.label(label_text).classes('text-[11px] font-bold text-slate-400 uppercase tracking-wider')
                        ui.label(val_text).classes('text-xl sm:text-2xl font-black text-slate-900')

        await refresh_summary()

        # Filter Tabs Row (Rendered above list container, calling load_requisitions_list)
        with ui.row().classes('w-full items-center justify-between gap-3 mb-4 flex-wrap'):
            with ui.row().classes('gap-1 bg-slate-100 p-1 rounded-2xl flex-wrap'):
                filter_tabs = ["All", "Pending Review", "Approved", "In Procurement", "Available in Library", "Declined"]
                tab_btns = {}
                for st in filter_tabs:
                    def make_tab_click(selected_status=st):
                        async def on_tab_click():
                            current_status_filter['val'] = selected_status
                            for k, b in tab_btns.items():
                                if k == selected_status:
                                    b.props('unelevated color=white text-color=indigo shadow-sm')
                                else:
                                    b.props('flat color=grey-7')
                            await load_requisitions_list()
                        return on_tab_click

                    b_el = ui.button(st, on_click=make_tab_click(st)).props(
                        'rounded-xl size=xs font-bold ' + ('unelevated color=white text-color=indigo shadow-sm' if st == 'All' else 'flat color=grey-7')
                    )
                    tab_btns[st] = b_el

            if can_manage:
                ui.label('🛡️ Librarian Review Mode Active').classes('text-xs font-bold text-indigo-700 bg-indigo-50 border border-indigo-200 px-3 py-1 rounded-full')

        # Requisitions List Container
        reqs_list_container = ui.column().classes('w-full gap-4')

        async def load_requisitions_list():
            reqs_list_container.clear()
            st_filter = current_status_filter['val']
            reqs = await mongo_db.get_requisitions(status=st_filter if st_filter != 'All' else None, limit=100)

            with reqs_list_container:
                if not reqs:
                    with ui.card().classes('w-full p-8 text-center bg-white border border-slate-200 rounded-3xl shadow-sm'):
                        ui.icon('menu_book', size='3em').classes('text-slate-300 mx-auto mb-2')
                        ui.label('No requisitions found in this category.').classes('text-base font-bold text-slate-700')
                        ui.label('Faculty members can click "Submit Book Requisition" above to request instructional textbooks.').classes('text-xs text-slate-400')
                    return

                for r in reqs:
                    st = r.get('status', 'Pending Review')
                    badge_style, badge_icon = STATUS_BADGES.get(st, ("bg-slate-100 text-slate-700", "info"))
                    req_id = r.get('id')

                    with ui.card().classes('w-full p-4 sm:p-6 rounded-3xl bg-white border border-slate-200 shadow-sm hover:shadow-md transition-shadow'):
                        with ui.row().classes('w-full items-start justify-between gap-3 mb-3 flex-wrap'):
                            # Left Title & Details
                            with ui.column().classes('gap-1 flex-1 min-w-[260px]'):
                                with ui.row().classes('items-center gap-2 flex-wrap'):
                                    ui.label(r.get('book_title', 'Untitled')).classes('text-lg sm:text-xl font-black text-slate-900')
                                    with ui.element('div').classes(f'px-2.5 py-0.5 rounded-full text-xs font-black uppercase border flex items-center gap-1 {badge_style}'):
                                        ui.icon(badge_icon, size='14px')
                                        ui.label(st)

                                ui.label(f"By {r.get('author', 'Unknown Author')} • {r.get('edition_year', 'Current Edition')}").classes('text-xs font-medium text-slate-600')

                            # Right Urgency & Program Pill
                            with ui.column().classes('items-end shrink-0 gap-1'):
                                with ui.row().classes('items-center gap-1.5'):
                                    ui.label(r.get('department', 'BSCS')).classes('text-xs font-black text-indigo-700 bg-indigo-50 border border-indigo-100 px-2 py-0.5 rounded-lg')
                                    urgency_col = 'text-rose-700 bg-rose-50 border-rose-200' if r.get('urgency') == 'Critical for Accreditation' else 'text-slate-600 bg-slate-100 border-slate-200'
                                    ui.label(r.get('urgency', 'Normal')).classes(f'text-[10px] font-bold uppercase px-2 py-0.5 rounded-lg border {urgency_col}')
                                date_str = datetime.fromtimestamp(r.get('created_at', time.time())).strftime("%b %d, %Y")
                                ui.label(f"Submitted: {date_str}").classes('text-[10px] font-mono text-slate-400')

                        # Course & Justification Box
                        with ui.row().classes('w-full p-3 bg-slate-50 rounded-2xl border border-slate-100 items-center justify-between gap-3 flex-wrap text-xs mb-3'):
                            with ui.row().classes('items-center gap-2'):
                                ui.icon('school', size='sm').classes('text-indigo-600')
                                ui.label(f"Course: {r.get('course_code', '')} - {r.get('course_title', '')}").classes('font-bold text-slate-800')
                            with ui.row().classes('items-center gap-1'):
                                ui.icon('person', size='sm').classes('text-slate-400')
                                ui.label(f"Requested by: {r.get('faculty_name', 'Faculty')} ({r.get('email', '')})").classes('text-slate-600 font-medium')

                        if r.get('justification'):
                            ui.label(f"Syllabus Justification: \"{r.get('justification')}\"").classes('text-xs text-slate-600 italic px-1 mb-2')

                        if r.get('admin_notes'):
                            with ui.row().classes('w-full p-2.5 bg-amber-50/70 border border-amber-200/60 rounded-xl items-center gap-2 mb-2'):
                                ui.icon('assignment', size='16px').classes('text-amber-700')
                                ui.label(f"Librarian Note: {r.get('admin_notes')}").classes('text-xs font-medium text-amber-900')

                        # Actions: Librarian Management Controls
                        if can_manage:
                            ui.separator().classes('my-2')
                            with ui.row().classes('w-full items-center justify-between gap-2 pt-1 flex-wrap'):
                                ui.label('Update Procurement Pipeline:').classes('text-[11px] font-bold text-slate-400 uppercase tracking-wider')
                                with ui.row().classes('gap-1.5 flex-wrap'):
                                    def make_status_updater(target_id=req_id, new_st="Approved"):
                                        async def update_click():
                                            await mongo_db.update_requisition_status(target_id, new_st, admin_notes=f"Updated by {user_name}")
                                            ui.notify(f"Requisition marked as '{new_st}'", type='positive')
                                            await refresh_summary()
                                            await load_requisitions_list()
                                        return update_click

                                    if st != "Approved":
                                        ui.button('Approve', icon='check', on_click=make_status_updater(req_id, "Approved")) \
                                            .props('unelevated rounded-xl color=blue size=xs font-bold')
                                    if st != "In Procurement":
                                        ui.button('Order / Procure', icon='shopping_bag', on_click=make_status_updater(req_id, "In Procurement")) \
                                            .props('unelevated rounded-xl color=purple size=xs font-bold')
                                    if st != "Available in Library":
                                        ui.button('Mark Available', icon='library_add_check', on_click=make_status_updater(req_id, "Available in Library")) \
                                            .props('unelevated rounded-xl color=emerald size=xs font-bold')
                                    if st != "Declined":
                                        ui.button('Decline', icon='close', on_click=make_status_updater(req_id, "Declined")) \
                                            .props('flat rounded-xl color=rose size=xs font-bold')

        # Initial data load
        await load_requisitions_list()


    # Submission Dialog
    def open_requisition_dialog():
        with ui.dialog() as req_dialog, ui.card().classes('w-[calc(100vw-2rem)] max-w-xl p-6 sm:p-8 rounded-3xl bg-white border border-slate-200 shadow-2xl'):
            with ui.row().classes('w-full justify-between items-center mb-2'):
                with ui.row().classes('items-center gap-2'):
                    ui.icon('post_add', size='md').classes('text-indigo-600')
                    ui.label('Faculty Book Requisition Form').classes('text-lg sm:text-xl font-black text-slate-900')
                ui.button(icon='close', on_click=req_dialog.close).props('flat round dense size=sm color=grey')

            ui.label('Submit textbook titles or reference materials to the library collection committee (CS 413 / Section 2.3).').classes('text-xs text-slate-500 mb-4')

            b_title = ui.input(label='Book / Resource Title *', placeholder='e.g., Software Engineering: A Practitioner\'s Approach') \
                .classes('w-full mb-2').props('rounded outlined dense autofocus')

            with ui.row().classes('w-full gap-2 mb-2'):
                b_author = ui.input(label='Author / Publisher *', placeholder='e.g., Roger S. Pressman') \
                    .classes('flex-1').props('rounded outlined dense')
                b_edition = ui.input(label='Edition / Year', placeholder='e.g., 9th Edition, 2020') \
                    .classes('w-36').props('rounded outlined dense')

            with ui.row().classes('w-full gap-2 mb-2'):
                b_course_code = ui.input(label='Course Code *', placeholder='e.g., CS 413') \
                    .classes('w-28').props('rounded outlined dense')
                b_course_title = ui.input(label='Course Title *', placeholder='e.g., Software Engineering 2') \
                    .classes('flex-1').props('rounded outlined dense')

            with ui.row().classes('w-full gap-2 mb-2'):
                b_dept = ui.select(DEPARTMENTS, value=user_department, label='Department / Program') \
                    .classes('flex-1').props('rounded outlined dense options-dense')
                b_urgency = ui.select(URGENCY_LEVELS, value='Normal', label='Urgency Level') \
                    .classes('flex-1').props('rounded outlined dense options-dense')

            b_justification = ui.textarea(label='Syllabus Justification / Reason for Acquisition', placeholder='Required for updated CS 413 syllabus reference and student laboratory projects.') \
                .classes('w-full mb-4').props('rounded outlined dense rows=2')

            with ui.row().classes('w-full justify-end gap-2'):
                ui.button('Cancel', on_click=req_dialog.close).props('flat rounded-xl color=grey size=sm font-bold')
                
                async def submit_form():
                    if not b_title.value.strip() or not b_author.value.strip() or not b_course_code.value.strip():
                        ui.notify('Please fill out all required fields (*)', type='warning')
                        return
                    res = await mongo_db.create_requisition(
                        faculty_id=user_id,
                        faculty_name=user_name,
                        email=user_email,
                        department=b_dept.value,
                        book_title=b_title.value,
                        author=b_author.value,
                        course_code=b_course_code.value,
                        course_title=b_course_title.value,
                        edition_year=b_edition.value,
                        urgency=b_urgency.value,
                        justification=b_justification.value
                    )
                    if res.get('success'):
                        ui.notify('Requisition submitted to library committee!', type='positive')
                        req_dialog.close()
                        await refresh_summary()
                        await load_requisitions_list()
                    else:
                        ui.notify(res.get('error', 'Submission failed'), type='negative')

                ui.button('Submit Requisition', icon='send', on_click=submit_form) \
                    .props('unelevated rounded-xl color=indigo size=sm font-bold shadow-md')

        req_dialog.open()
