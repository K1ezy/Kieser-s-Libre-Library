from nicegui import ui, app
import bcrypt
import re
import logging

from core.database.mongo_manager import mongo_db
from core.database.repositories.user_repository import (
    validate_user_id,
    is_attempted_institutional_id,
    format_and_clean_user_id
)
from core.auth.jwt_handler import (
    create_access_token,
    is_user_authenticated,
    set_user_session,
    clear_user_session,
    get_current_user_info
)

logger = logging.getLogger("AUTH_PAGE")

# Premium Button & Input Styles
BTN_STYLE = 'w-full py-3 rounded-xl bg-indigo-600 hover:bg-indigo-700 text-white font-bold text-base shadow-lg shadow-indigo-500/20 active:scale-[0.99] transition-all'
INPUT_CLASSES = 'w-full mb-3 sm:mb-4 text-base'

def create_password_toggle(input_field):
    """Adds a modern eye icon toggle to show/hide password."""
    with input_field.add_slot('append'):
        toggle_icon = ui.icon('visibility_off').classes('cursor-pointer text-slate-400 hover:text-indigo-600 transition-colors')
        def toggle():
            current_type = input_field._props.get('type', 'password')
            if current_type == 'password':
                input_field._props['type'] = 'text'
                toggle_icon._props['name'] = 'visibility'
            else:
                input_field._props['type'] = 'password'
                toggle_icon._props['name'] = 'visibility_off'
            input_field.update()
            toggle_icon.update()
        toggle_icon.on('click', toggle)

async def login_page():
    # If already logged in, show active session with option to continue or switch
    if is_user_authenticated():
        user_info = get_current_user_info()
        user_name = user_info.get('username') or 'User'
        with ui.row().classes('w-full min-h-[100dvh] h-[100dvh] m-0 p-0 items-center justify-center bg-slate-50'):
            with ui.card().classes('w-full max-w-md p-6 sm:p-8 bg-white border border-slate-200 shadow-xl rounded-3xl text-center'):
                ui.icon('verified_user', size='3.5em').classes('text-indigo-600 mx-auto mb-2')
                ui.label('Active Session Found').classes('text-2xl font-black text-slate-900 mb-1')
                ui.label(f'You are currently signed in as {user_name}.').classes('text-xs text-slate-500 mb-6')
                
                ui.button('Continue to Library', icon='arrow_forward', on_click=lambda: ui.navigate.to('/')) \
                    .props('unelevated rounded-xl color=indigo size=md font-bold').classes('w-full mb-3')
                
                def switch_account():
                    clear_user_session()
                    ui.notify('Signed out. Please sign in or create an account.', type='info')
                    ui.navigate.to('/login')
                    
                ui.button('Sign Out / Switch Account', icon='logout', on_click=switch_account) \
                    .props('flat rounded-xl color=grey-7 size=sm font-bold').classes('w-full')
        return

    # Check for registration success flash data
    prefill_val = app.storage.user.pop('prefill_identifier', '')
    just_registered = app.storage.user.pop('signup_success', False)
    registered_role = app.storage.user.pop('signup_role', '')
    assigned_id_display = app.storage.user.pop('just_registered_id', '')

    with ui.column().classes('w-full min-h-[100dvh] items-center justify-center bg-slate-50 p-4 sm:p-8 overflow-y-auto'):
        with ui.card().classes('w-full max-w-[560px] p-6 sm:p-10 shadow-2xl border border-slate-200/90 bg-white rounded-3xl'):
            with ui.row().classes('w-full items-center gap-4 sm:gap-6 mb-6 flex-col sm:flex-row text-center sm:text-left'):
                ui.image('/static/Libre-Library_logo.svg').classes('w-32 sm:w-44 h-auto object-contain shrink-0').props('no-spinner')
                with ui.column().classes('gap-0.5 min-w-0 flex-1 justify-center items-center sm:items-start'):
                    ui.label('Welcome Back').classes('text-2xl sm:text-3xl font-extrabold text-slate-900 tracking-tight leading-tight')
                    ui.label('Sign in with your Institutional ID (YY-NNNNN), Username, or Email').classes('text-xs sm:text-sm text-slate-500 leading-snug')

                # Post-registration Success Notification Banner
                if just_registered:
                    with ui.column().classes('w-full p-4 mb-5 rounded-2xl bg-emerald-50/95 border border-emerald-200 shadow-sm gap-1.5'):
                        with ui.row().classes('items-center gap-2'):
                            ui.icon('celebration', size='24px').classes('text-emerald-600')
                            ui.label('Account Created Successfully!').classes('text-sm font-black text-emerald-950')
                        if assigned_id_display:
                            with ui.row().classes('items-center gap-2 py-1 px-3 rounded-xl bg-white border border-emerald-300 w-fit'):
                                ui.icon('badge', size='18px').classes('text-emerald-700')
                                ui.label('Your Registered Institutional ID:').classes('text-xs text-slate-600 font-semibold')
                                ui.label(assigned_id_display).classes('text-sm font-black text-emerald-700 tracking-wider font-mono')
                            ui.label('Your ID has been pre-filled below. Please enter your password to sign in.').classes('text-xs text-emerald-800')
                        else:
                            role_text = f"Your {registered_role.capitalize()} account" if registered_role else "Your account"
                            ui.label(f'{role_text} has been registered. Please sign in below with your password to continue.').classes('text-xs text-emerald-700 leading-snug')

                # Identifier Field (Institutional ID YY-NNNNN, Username, or Email)
                identifier = ui.input(placeholder='Institutional ID (e.g., 23-00125), Username, or Email', value=prefill_val) \
                    .classes(INPUT_CLASSES) \
                    .props('rounded outlined dense autocomplete="username" autocapitalize="none" spellcheck="false"')
                with identifier.add_slot('prepend'):
                    ui.icon('badge').classes('text-indigo-500 opacity-70')

                # Password Field
                pwd = ui.input(placeholder='Password', password=True) \
                    .classes('w-full mb-6') \
                    .props('rounded outlined dense autocomplete="current-password"')
                with pwd.add_slot('prepend'):
                    ui.icon('lock').classes('text-indigo-500 opacity-70')
                create_password_toggle(pwd)

                if prefill_val:
                    # Frictionless UX: auto-focus password when identifier is pre-filled from registration
                    ui.timer(0.1, lambda: pwd.run_method('focus'), once=True)

                login_btn = None

                async def try_login():
                    clean_id = (identifier.value or '').strip()
                    clean_pwd = (pwd.value or '').strip()

                    if not clean_id or not clean_pwd:
                        ui.notify('Please fill in both identifier (ID/username/email) and password.', type='warning')
                        return

                    # Enforce strict ID format validation if identifier is an attempted Institutional ID
                    if is_attempted_institutional_id(clean_id) and not validate_user_id(clean_id):
                        ui.notify(
                            'Invalid ID format. Institutional IDs must be in YY-NNNNN format with numbers only.',
                            type='negative',
                            duration=5.0
                        )
                        return

                    if login_btn:
                        login_btn.props('loading')

                    try:
                        matched_user = await mongo_db.authenticate_user(clean_id, clean_pwd)
                        token = create_access_token({"sub": matched_user['id'], "role": matched_user.get('role', 'user')})
                        set_user_session(matched_user, token)
                        await mongo_db.update_user_last_login(matched_user['id'])
                        ui.notify(f"Welcome back, {matched_user.get('name') or matched_user.get('username', 'User')}!", type='positive')
                        ui.navigate.to('/')
                    except ValueError as val_err:
                        ui.notify(str(val_err), type='negative', duration=4.0)
                    except Exception as err:
                        logger.error(f"Sign in error: {err}")
                        ui.notify('Invalid credentials. Please verify your password.', type='negative')
                    finally:
                        if login_btn:
                            login_btn.props(remove='loading')

                # Bind Enter Key to Submit
                identifier.on('keydown.enter', try_login)
                pwd.on('keydown.enter', try_login)

                login_btn = ui.button('Sign In', on_click=try_login).classes(BTN_STYLE)

                with ui.row().classes('w-full justify-center items-center mt-6 gap-1 text-sm'):
                    ui.label("Don't have an account?").classes('text-slate-500')
                    ui.link('Create Account', '/signup').classes('text-indigo-600 font-bold hover:underline')


async def signup_page():
    # If already logged in, show active session with option to continue or switch
    if is_user_authenticated():
        user_info = get_current_user_info()
        user_name = user_info.get('username') or 'User'
        with ui.row().classes('w-full min-h-[100dvh] h-[100dvh] m-0 p-0 items-center justify-center bg-slate-50'):
            with ui.card().classes('w-full max-w-md p-6 sm:p-8 bg-white border border-slate-200 shadow-xl rounded-3xl text-center'):
                ui.icon('verified_user', size='3.5em').classes('text-indigo-600 mx-auto mb-2')
                ui.label('Already Logged In').classes('text-2xl font-black text-slate-900 mb-1')
                ui.label(f'You are currently signed in as {user_name}.').classes('text-xs text-slate-500 mb-6')
                
                ui.button('Continue to Library', icon='arrow_forward', on_click=lambda: ui.navigate.to('/')) \
                    .props('unelevated rounded-xl color=indigo size=md font-bold').classes('w-full mb-3')
                
                def switch_account_signup():
                    clear_user_session()
                    ui.notify('Signed out. You can now register a new account.', type='info')
                    ui.navigate.to('/signup')
                    
                ui.button('Create a Different Account', icon='person_add', on_click=switch_account_signup) \
                    .props('flat rounded-xl color=grey-7 size=sm font-bold').classes('w-full')
        return

    with ui.column().classes('w-full min-h-[100dvh] items-center justify-center bg-slate-50 p-4 sm:p-8 py-8 sm:py-12 overflow-y-auto'):
        with ui.card().classes('w-full max-w-[620px] p-6 sm:p-10 shadow-2xl border border-slate-200/90 bg-white rounded-3xl'):
            with ui.row().classes('w-full items-center gap-4 sm:gap-6 mb-6 flex-col sm:flex-row text-center sm:text-left'):
                ui.image('/static/Libre-Library_logo.svg').classes('w-32 sm:w-44 h-auto object-contain shrink-0').props('no-spinner')
                with ui.column().classes('gap-0.5 min-w-0 flex-1 justify-center items-center sm:items-start'):
                    ui.label('Create Account').classes('text-2xl sm:text-3xl font-extrabold text-slate-900 tracking-tight leading-tight')
                    ui.label('Institutional registration across academic roles').classes('text-xs sm:text-sm text-slate-500 leading-snug')

                # Full Legal Name Field
                fullname = ui.input(placeholder='Full Legal Name *') \
                    .classes(INPUT_CLASSES) \
                    .props('rounded outlined dense autocomplete="name"')
                with fullname.add_slot('prepend'):
                    ui.icon('person').classes('text-indigo-500 opacity-70')

                # Institutional ID Input Bar (Only accepts 7 integer numbers: YY-NNNNN)
                with ui.column().classes('w-full gap-1 mb-3 sm:mb-4'):
                    institutional_id_input = ui.input(
                        placeholder='Input registered ID e.g, : (23-00125) *'
                    ).classes('w-full text-base').props(
                        'rounded outlined dense mask="##-#####" unmasked-value=false inputmode="numeric" autocomplete="off"'
                    )
                    with institutional_id_input.add_slot('prepend'):
                        ui.icon('badge').classes('text-indigo-500 opacity-70')
                    with ui.row().classes('w-full items-center justify-between px-2 text-[11px] text-slate-500 leading-tight'):
                        ui.label('7 integer numbers: 2 digits for year + 5 digits for student number (e.g. 23-00125).')
                        ui.label('Capacity: Max 5 digits (00001–99999)').classes('font-semibold text-indigo-600')

                # Username Field
                username = ui.input(placeholder='Username *') \
                    .classes(INPUT_CLASSES) \
                    .props('rounded outlined dense autocomplete="username" autocapitalize="none" spellcheck="false"')
                with username.add_slot('prepend'):
                    ui.icon('person_outline').classes('text-indigo-500 opacity-70')

                # Email Field
                email = ui.input(placeholder='Institutional Email Address *') \
                    .classes(INPUT_CLASSES) \
                    .props('rounded outlined dense autocomplete="email" autocapitalize="none" spellcheck="false"')
                with email.add_slot('prepend'):
                    ui.icon('alternate_email').classes('text-indigo-500 opacity-70')

                # Password Field
                pwd = ui.input(placeholder='Password (min 6 characters) *', password=True) \
                    .classes(INPUT_CLASSES) \
                    .props('rounded outlined dense autocomplete="new-password"')
                with pwd.add_slot('prepend'):
                    ui.icon('lock_outline').classes('text-indigo-500 opacity-70')
                create_password_toggle(pwd)

                # Confirm Password Field
                confirm_pwd = ui.input(placeholder='Confirm Password *', password=True) \
                    .classes(INPUT_CLASSES) \
                    .props('rounded outlined dense autocomplete="new-password"')
                with confirm_pwd.add_slot('prepend'):
                    ui.icon('lock_reset').classes('text-indigo-500 opacity-70')
                create_password_toggle(confirm_pwd)

                # 4-Tier Institutional Role Selection
                role_select = ui.select(
                    {
                        'student': 'Student (Undergraduate / Graduate)',
                        'faculty': 'Faculty Member / Professor',
                        'librarian': 'Librarian / Library Staff',
                        'admin': 'System Administrator',
                    },
                    value='student',
                    label='Institutional Role *'
                ).props('rounded outlined dense bg-color=white options-dense').classes(INPUT_CLASSES)

                # Dynamic Role Elements Container
                dynamic_container = ui.column().classes('w-full gap-0 mb-3')
                role_inputs = {}

                def render_role_fields():
                    dynamic_container.clear()
                    role_inputs.clear()
                    current_role = role_select.value or 'student'
                    with dynamic_container:
                        if current_role == 'student':
                            with ui.row().classes('w-full gap-2 mb-2'):
                                role_inputs['program'] = ui.select(
                                    ["BSCS", "BSIT", "BSED", "BEED", "BSBA", "BSHM", "Crim", "Nursing", "GENERAL"],
                                    value='BSCS', label='Program / Course *'
                                ).props('rounded outlined dense options-dense').classes('flex-1')

                                role_inputs['year_level'] = ui.select(
                                    ["1st Year", "2nd Year", "3rd Year", "4th Year", "Graduate"],
                                    value='1st Year', label='Year Level *'
                                ).props('rounded outlined dense options-dense').classes('w-32')

                        elif current_role == 'faculty':
                            role_inputs['department'] = ui.input(placeholder='Department * (e.g., College of Computer Studies)') \
                                .classes(INPUT_CLASSES).props('rounded outlined dense')
                            with role_inputs['department'].add_slot('prepend'):
                                ui.icon('business').classes('text-emerald-500 opacity-70')

                        elif current_role == 'librarian':
                            role_inputs['branch'] = ui.input(placeholder='Library Branch / Section * (e.g., Main Campus / Circulation)') \
                                .classes(INPUT_CLASSES).props('rounded outlined dense')
                            with role_inputs['branch'].add_slot('prepend'):
                                ui.icon('location_on').classes('text-blue-500 opacity-70')

                        elif current_role == 'admin':
                            role_inputs['admin_code'] = ui.input(placeholder='Optional Admin Security Code (if provided by IT)') \
                                .classes(INPUT_CLASSES).props('rounded outlined dense')
                            with role_inputs['admin_code'].add_slot('prepend'):
                                ui.icon('security').classes('text-purple-500 opacity-70')

                role_select.on_value_change(render_role_fields)
                render_role_fields()

                signup_btn = None

                async def try_signup():
                    clean_fullname = (fullname.value or '').strip()
                    raw_inst_id = (institutional_id_input.value or '').strip()
                    clean_username = (username.value or '').strip()
                    clean_email = (email.value or '').strip().lower()
                    clean_pwd = (pwd.value or '').strip()
                    clean_confirm = (confirm_pwd.value or '').strip()
                    chosen_role = (role_select.value or 'student').strip().lower()

                    # Validations
                    if not clean_fullname or not raw_inst_id or not clean_username or not clean_email or not clean_pwd or not clean_confirm:
                        ui.notify("All core account fields are required (*).", type='warning')
                        return

                    # Strict Institutional ID validation & formatting
                    try:
                        clean_inst_id = format_and_clean_user_id(raw_inst_id)
                    except ValueError as id_err:
                        ui.notify(str(id_err), type='warning', duration=5.0)
                        return

                    if len(clean_username) < 3:
                        ui.notify("Username must be at least 3 characters long.", type='warning')
                        return

                    if "-" in clean_username or clean_username.isdigit():
                        ui.notify(
                            "Usernames cannot contain hyphens or consist solely of numbers (reserved for Institutional IDs).",
                            type='warning'
                        )
                        return

                    if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", clean_email):
                        ui.notify("Please enter a valid email address.", type='warning')
                        return

                    if len(clean_pwd) < 6:
                        ui.notify("Password must be at least 6 characters long.", type='warning')
                        return

                    if clean_pwd != clean_confirm:
                        ui.notify("Passwords do not match.", type='warning')
                        return

                    # Role-specific validations
                    prog_val = role_inputs.get('program').value if 'program' in role_inputs else None
                    year_val = role_inputs.get('year_level').value if 'year_level' in role_inputs else None
                    dept_val = (role_inputs.get('department').value or '').strip() if 'department' in role_inputs else None
                    branch_val = (role_inputs.get('branch').value or '').strip() if 'branch' in role_inputs else None
                    admin_val = (role_inputs.get('admin_code').value or '').strip() if 'admin_code' in role_inputs else None

                    if chosen_role == 'faculty' and not dept_val:
                        ui.notify("Faculty department is required.", type='warning')
                        return
                    if chosen_role == 'librarian' and not branch_val:
                        ui.notify("Library branch / section is required.", type='warning')
                        return

                    if signup_btn:
                        signup_btn.props('loading')

                    try:
                        # Collision checks
                        if await mongo_db.get_user_by_identifier(clean_inst_id):
                            ui.notify(f"An account with Institutional ID '{clean_inst_id}' already exists. Please sign in or verify your ID.", type='negative')
                            return

                        if await mongo_db.get_user_by_email(clean_email):
                            ui.notify("An account with this email already exists.", type='negative')
                            return

                        if await mongo_db.get_user_by_identifier(clean_username):
                            ui.notify("This username is already taken. Please choose another.", type='negative')
                            return

                        hashed = bcrypt.hashpw(clean_pwd.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
                        user_count = await mongo_db.get_total_user_count()
                        role = "admin" if user_count == 0 else chosen_role

                        created = await mongo_db.create_user(
                            clean_username,
                            clean_email,
                            hashed,
                            role=role,
                            institutional_id=clean_inst_id,
                            name=clean_fullname,
                            program=prog_val,
                            year_level=year_val,
                            department=dept_val,
                            branch=branch_val,
                            admin_code=admin_val
                        )
                        if not created:
                            ui.notify("Registration failed. Please try again.", type='negative')
                            return

                        assigned_id = created.get('institutional_id') or clean_inst_id

                        # Safe & Explicit Auth: Prompt user to authenticate with their registered ID
                        clear_user_session()
                        app.storage.user['prefill_identifier'] = assigned_id
                        app.storage.user['just_registered_id'] = assigned_id
                        app.storage.user['signup_success'] = True
                        app.storage.user['signup_role'] = role
                        ui.notify(
                            f"Account created successfully! Your Institutional ID is {assigned_id}.",
                            type='positive',
                            duration=6.0
                        )
                        ui.navigate.to('/login')
                    except ValueError as val_err:
                        ui.notify(str(val_err), type='negative')
                    except Exception as exc:
                        logger.error(f"Sign up unexpected error: {exc}")
                        ui.notify("Registration failed. Please check your details and try again.", type='negative')
                    finally:
                        if signup_btn:
                            signup_btn.props(remove='loading')

                # Bind Enter Key
                username.on('keydown.enter', try_signup)
                email.on('keydown.enter', try_signup)
                pwd.on('keydown.enter', try_signup)
                confirm_pwd.on('keydown.enter', try_signup)

                signup_btn = ui.button('Create Account', on_click=try_signup).classes(BTN_STYLE)

                with ui.row().classes('w-full justify-center items-center mt-6 gap-1 text-sm'):
                    ui.label('Already have an account?').classes('text-slate-500')
                    ui.link('Sign In', '/login').classes('text-indigo-600 font-bold hover:underline')