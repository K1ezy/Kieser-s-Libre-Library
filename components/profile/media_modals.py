from typing import Callable, Any, Optional
from nicegui import ui
from core.database.mongo_manager import mongo_db
from core.utils.media_handler import save_user_media, extract_upload_file


def open_avatar_modal(
    user_id: str,
    current_avatar: Optional[str],
    initials: str,
    on_uploaded: Callable[[str], Any]
) -> None:
    """Interactive modal for uploading/previewing circular avatar with 2MB validation."""
    with ui.dialog() as avatar_dialog, ui.card().classes(
        'w-[calc(100vw-2rem)] max-w-md p-5 rounded-3xl bg-white border border-slate-200 shadow-2xl'
    ):
        with ui.row().classes('w-full justify-between items-center mb-2'):
            with ui.row().classes('items-center gap-2'):
                ui.icon('photo_camera', size='sm').classes('text-indigo-600')
                ui.label('Update Profile Photo').classes('text-base font-bold text-slate-800')
            ui.button(icon='close', on_click=avatar_dialog.close).props('flat round dense size=sm color=grey')

        ui.label('Upload a square photo in JPEG, PNG, or WebP format (Max 2MB).').classes('text-xs text-slate-500 mb-4')

        with ui.row().classes('w-full justify-center mb-4'):
            if current_avatar:
                ui.image(current_avatar).classes('w-24 h-24 rounded-full object-cover border-2 border-indigo-200 shadow-sm')
            else:
                with ui.element('div').classes('w-24 h-24 rounded-full bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center text-white font-black text-2xl shadow-sm'):
                    ui.label(initials)

        async def handle_avatar_upload(e):
            try:
                file_name, raw_bytes = await extract_upload_file(e)
                if not raw_bytes:
                    ui.notify('No file data received. Please select an image.', type='warning')
                    return
                success, msg, url = save_user_media(user_id, raw_bytes, file_name, "avatar")
                if not success:
                    ui.notify(msg, type='negative')
                    return
                await mongo_db.update_user_media(user_id, avatar_url=url)
                ui.notify('Avatar updated successfully!', type='positive')
                avatar_dialog.close()
                await on_uploaded(url)
            except Exception as err:
                ui.notify(f'Upload failed: {err}', type='negative')

        ui.upload(
            label="Select or drop photo here",
            auto_upload=True,
            on_upload=handle_avatar_upload,
            max_file_size=2_097_152
        ).props('accept=".jpg,.jpeg,.png,.webp" flat bordered color=indigo').classes('w-full rounded-2xl')

        with ui.row().classes('w-full justify-end mt-4'):
            ui.button('Cancel', on_click=avatar_dialog.close).props('flat rounded-xl color=grey size=sm font-bold')

    avatar_dialog.open()


def open_cover_modal(
    user_id: str,
    current_cover: Optional[str],
    on_uploaded: Callable[[str], Any]
) -> None:
    """Interactive modal for uploading/previewing cover banner with 5MB validation."""
    with ui.dialog() as cover_dialog, ui.card().classes(
        'w-[calc(100vw-2rem)] max-w-lg p-5 rounded-3xl bg-white border border-slate-200 shadow-2xl'
    ):
        with ui.row().classes('w-full justify-between items-center mb-2'):
            with ui.row().classes('items-center gap-2'):
                ui.icon('image', size='sm').classes('text-indigo-600')
                ui.label('Update Cover Photo').classes('text-base font-bold text-slate-800')
            ui.button(icon='close', on_click=cover_dialog.close).props('flat round dense size=sm color=grey')

        ui.label('Upload a banner image in JPEG, PNG, or WebP format (Max 5MB, ~3:1 ratio recommended).').classes('text-xs text-slate-500 mb-4')

        with ui.row().classes('w-full justify-center mb-4'):
            if current_cover:
                ui.image(current_cover).classes('w-full h-28 rounded-xl object-cover border border-slate-200 shadow-sm')
            else:
                with ui.element('div').classes('w-full h-28 rounded-xl bg-gradient-to-r from-indigo-700 via-purple-700 to-slate-900 flex items-center justify-center text-white/80 text-xs font-bold'):
                    ui.label('Default Gradient Banner Active')

        async def handle_cover_upload(e):
            try:
                file_name, raw_bytes = await extract_upload_file(e)
                if not raw_bytes:
                    ui.notify('No file data received. Please select an image.', type='warning')
                    return
                success, msg, url = save_user_media(user_id, raw_bytes, file_name, "cover")
                if not success:
                    ui.notify(msg, type='negative')
                    return
                await mongo_db.update_user_media(user_id, cover_url=url)
                ui.notify('Cover photo updated successfully!', type='positive')
                cover_dialog.close()
                await on_uploaded(url)
            except Exception as err:
                ui.notify(f'Upload failed: {err}', type='negative')

        ui.upload(
            label="Select or drop cover banner here",
            auto_upload=True,
            on_upload=handle_cover_upload,
            max_file_size=5_242_880
        ).props('accept=".jpg,.jpeg,.png,.webp" flat bordered color=indigo').classes('w-full rounded-2xl')

        with ui.row().classes('w-full justify-end mt-4'):
            ui.button('Cancel', on_click=cover_dialog.close).props('flat rounded-xl color=grey size=sm font-bold')

    cover_dialog.open()
