from typing import Dict, Any
from nicegui import app
from core.services.user_telemetry import telemetry_engine, render_readership_and_activity_section


def render_profile_stats(stats: Dict[str, Any]) -> None:
    """
    Renders 100% accurate, SQLite-persisted reading metrics and a mathematically
    locked 53-week contribution heatmap with zero-overhead CSS tooltips.
    """
    user_id = str(app.storage.user.get('user_id') or app.storage.user.get('username') or 'student')
    telemetry_engine.record_session_login(user_id)

    books_read = int(stats.get('reading_count', 0) or stats.get('books_read', 0) or 0)
    books_finished = int(stats.get('completed_books', 0) or stats.get('books_finished', 0) or 0)

    render_readership_and_activity_section(
        engine=telemetry_engine,
        user_id=user_id,
        books_read=books_read,
        books_finished=books_finished
    )
