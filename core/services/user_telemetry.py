import datetime
import math
import sqlite3
from pathlib import Path
from typing import Any, Optional, List, Dict
from nicegui import ui

# -------------------------------------------------------------------------
# 1. HIGH-PERFORMANCE SCOPED CSS (Zero-Overhead Tooltips & Exact Grid)
# -------------------------------------------------------------------------
TELEMETRY_CSS = """
/* Responsive 53-Week Grid that fits 100% of the card with NO scrollbar on desktop */
.libre-heatmap-grid {
    display: grid;
    grid-template-columns: 28px repeat(var(--weeks-count, 53), minmax(0, 1fr));
    gap: 3px;
    width: 100%;
    min-width: 620px;
    align-items: center;
}

/* Crisp GitHub-accurate Emerald & Indigo Color Scales */
.hm-cell {
    width: 100%;
    aspect-ratio: 1 / 1;
    border-radius: 3px;
    position: relative;
    transition: transform 0.12s ease, box-shadow 0.12s ease;
}
.hm-cell[data-active="true"]:hover {
    transform: scale(1.35);
    z-index: 30;
    box-shadow: 0 2px 6px rgba(15, 23, 42, 0.25);
}

/* Mobile Touch & Momentum Scrolling Optimization */
.heatmap-scroll {
    -webkit-overflow-scrolling: touch;
    scrollbar-width: thin;
    scrollbar-color: #CBD5E1 transparent;
}
.heatmap-scroll::-webkit-scrollbar {
    height: 5px;
}
.heatmap-scroll::-webkit-scrollbar-track {
    background: transparent;
}
.heatmap-scroll::-webkit-scrollbar-thumb {
    background: #CBD5E1;
    border-radius: 9999px;
}
.heatmap-scroll::-webkit-scrollbar-thumb:hover {
    background: #94A3B8;
}

/* Touchscreen tap optimizations: eliminate sticky hover on mobile */
@media (hover: none) and (pointer: coarse) {
    .hm-cell[data-active="true"]:hover {
        transform: none !important;
        box-shadow: none !important;
    }
}

/* Intensity Levels: Exact GitHub Contribution Palette */
.hm-lvl-0 { background-color: #F1F5F9; border: 1px solid #E2E8F0; }
.hm-lvl-1 { background-color: #A7F3D0; border: 1px solid #6EE7B7; }
.hm-lvl-2 { background-color: #34D399; border: 1px solid #10B981; }
.hm-lvl-3 { background-color: #059669; border: 1px solid #047857; }
.hm-lvl-4 { background-color: #064E3B; border: 1px solid #022C22; }
.hm-future { background-color: #F8FAFC; border: 1px dashed #E2E8F0; opacity: 0.55; }

/* Today Highlight Ring */
.hm-today {
    outline: 2px solid #4F46E5;
    outline-offset: 1px;
}

/* Zero-JS Instant CSS Tooltip (Replaces 365 heavy Vue QTooltip instances) */
.hm-cell[data-tip]:hover::after {
    content: attr(data-tip);
    position: absolute;
    bottom: calc(100% + 7px);
    left: 50%;
    transform: translateX(-50%);
    background: #0F172A;
    color: #F8FAFC;
    font-size: 11px;
    font-weight: 600;
    line-height: 1.25;
    padding: 5px 9px;
    border-radius: 6px;
    white-space: nowrap;
    pointer-events: none;
    box-shadow: 0 4px 12px rgba(15, 23, 42, 0.25);
    z-index: 50;
}
.hm-cell[data-tip]:hover::before {
    content: "";
    position: absolute;
    bottom: calc(100% + 2px);
    left: 50%;
    transform: translateX(-50%);
    border-width: 5px 5px 0 5px;
    border-style: solid;
    border-color: #0F172A transparent transparent transparent;
    pointer-events: none;
    z-index: 50;
}
"""


# -------------------------------------------------------------------------
# 2. REAL SQLITE TELEMETRY ENGINE (Accurate DB Tracking & Aggregation)
# -------------------------------------------------------------------------
class UserTelemetryEngine:
    """
    Lightweight, thread-safe SQLite telemetry store & aggregator.
    Automatically creates `user_daily_telemetry` if missing and syncs with
    existing reading progress / attendance tables when present.
    """

    def __init__(self, db_path: Optional[str | Path] = None):
        if db_path is None:
            base_dir = Path(__file__).resolve().parent.parent.parent
            self.db_path = str(base_dir / 'libre_library.db')
        else:
            self.db_path = str(db_path)
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=5.0)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS user_daily_telemetry (
                    user_id TEXT NOT NULL,
                    activity_date TEXT NOT NULL,
                    login_count INTEGER NOT NULL DEFAULT 0,
                    pages_read INTEGER NOT NULL DEFAULT 0,
                    books_touched INTEGER NOT NULL DEFAULT 0,
                    last_seen_at TEXT,
                    PRIMARY KEY (user_id, activity_date)
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS user_book_progress (
                    user_id TEXT NOT NULL,
                    book_id TEXT NOT NULL,
                    current_page INTEGER NOT NULL DEFAULT 1,
                    total_pages INTEGER NOT NULL DEFAULT 100,
                    is_finished INTEGER NOT NULL DEFAULT 0,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (user_id, book_id)
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_telemetry_user_date
                ON user_daily_telemetry (user_id, activity_date)
            """)

    @staticmethod
    def _local_today() -> datetime.date:
        """Returns current date in Philippine Standard Time (UTC+8)."""
        tz_ph = datetime.timezone(datetime.timedelta(hours=8))
        return datetime.datetime.now(tz_ph).date()

    def record_session_login(self, user_id: str, debounce_minutes: int = 15) -> None:
        """
        Records a real web app session for `user_id` today.
        Uses a debounce window so rapid F5 page refreshes don't artificially inflate login counts.
        """
        if not user_id:
            return
        tz_ph = datetime.timezone(datetime.timedelta(hours=8))
        now = datetime.datetime.now(tz_ph)
        today_str = now.date().isoformat()
        now_iso = now.isoformat(timespec='seconds')

        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT login_count, last_seen_at
                FROM user_daily_telemetry
                WHERE user_id = ? AND activity_date = ?
                """,
                (str(user_id), today_str),
            ).fetchone()

            if row is None:
                conn.execute(
                    """
                    INSERT INTO user_daily_telemetry (user_id, activity_date, login_count, last_seen_at)
                    VALUES (?, ?, 1, ?)
                    """,
                    (str(user_id), today_str, now_iso),
                )
            else:
                should_increment = True
                if row['last_seen_at'] and debounce_minutes > 0:
                    try:
                        prev_dt = datetime.datetime.fromisoformat(row['last_seen_at'])
                        if (now - prev_dt).total_seconds() < (debounce_minutes * 60):
                            should_increment = False
                    except ValueError:
                        pass

                if should_increment:
                    conn.execute(
                        """
                        UPDATE user_daily_telemetry
                        SET login_count = login_count + 1, last_seen_at = ?
                        WHERE user_id = ? AND activity_date = ?
                        """,
                        (now_iso, str(user_id), today_str),
                    )

    def record_reading_activity(
        self,
        user_id: str,
        book_id: str,
        current_page: int,
        total_pages: int,
        pages_delta: int = 1,
    ) -> None:
        """Records real book reading progress and automatically marks books finished at >=100%."""
        if not user_id or not book_id:
            return
        tz_ph = datetime.timezone(datetime.timedelta(hours=8))
        now = datetime.datetime.now(tz_ph)
        today_str = now.date().isoformat()
        total_pages = max(1, int(total_pages))
        current_page = max(0, min(int(current_page), total_pages))
        is_finished = 1 if current_page >= total_pages else 0

        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO user_book_progress (user_id, book_id, current_page, total_pages, is_finished, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id, book_id) DO UPDATE SET
                    current_page = MAX(user_book_progress.current_page, excluded.current_page),
                    total_pages = excluded.total_pages,
                    is_finished = MAX(user_book_progress.is_finished, excluded.is_finished),
                    updated_at = excluded.updated_at
                """,
                (str(user_id), str(book_id), current_page, total_pages, is_finished, now.isoformat()),
            )
            conn.execute(
                """
                INSERT INTO user_daily_telemetry (user_id, activity_date, login_count, pages_read, books_touched, last_seen_at)
                VALUES (?, ?, 1, ?, 1, ?)
                ON CONFLICT(user_id, activity_date) DO UPDATE SET
                    pages_read = user_daily_telemetry.pages_read + ?,
                    books_touched = user_daily_telemetry.books_touched + 1,
                    last_seen_at = excluded.last_seen_at
                """,
                (str(user_id), today_str, max(0, pages_delta), now.isoformat(), max(0, pages_delta)),
            )

    def sync_from_mongo_progress(self, user_id: str, progress_docs: List[Dict[str, Any]]) -> None:
        """
        Synchronizes existing MongoDB reading progress records into SQLite
        telemetry so historical reading activity appears in the heatmap.
        """
        if not user_id or not progress_docs:
            return
        tz_ph = datetime.timezone(datetime.timedelta(hours=8))
        with self._connect() as conn:
            for doc in progress_docs:
                book_id = str(doc.get('book_id', ''))
                if not book_id:
                    continue
                current_page = int(doc.get('current_page', 1) or 1)
                total_pages = int(doc.get('total_pages', 100) or 100)
                is_finished = 1 if (doc.get('status') == 'completed' or (total_pages > 0 and current_page >= total_pages)) else 0
                ts = doc.get('last_read_at')
                if ts:
                    try:
                        dt = datetime.datetime.fromtimestamp(float(ts), tz=tz_ph)
                        date_str = dt.date().isoformat()
                        iso_str = dt.isoformat(timespec='seconds')
                    except Exception:
                        dt = datetime.datetime.now(tz_ph)
                        date_str = dt.date().isoformat()
                        iso_str = dt.isoformat(timespec='seconds')
                else:
                    dt = datetime.datetime.now(tz_ph)
                    date_str = dt.date().isoformat()
                    iso_str = dt.isoformat(timespec='seconds')

                conn.execute(
                    """
                    INSERT INTO user_book_progress (user_id, book_id, current_page, total_pages, is_finished, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(user_id, book_id) DO UPDATE SET
                        current_page = MAX(user_book_progress.current_page, excluded.current_page),
                        total_pages = excluded.total_pages,
                        is_finished = MAX(user_book_progress.is_finished, excluded.is_finished),
                        updated_at = excluded.updated_at
                    """,
                    (str(user_id), book_id, current_page, total_pages, is_finished, iso_str)
                )
                conn.execute(
                    """
                    INSERT INTO user_daily_telemetry (user_id, activity_date, login_count, pages_read, books_touched, last_seen_at)
                    VALUES (?, ?, 1, ?, 1, ?)
                    ON CONFLICT(user_id, activity_date) DO UPDATE SET
                        pages_read = MAX(user_daily_telemetry.pages_read, excluded.pages_read),
                        books_touched = MAX(user_daily_telemetry.books_touched, 1),
                        last_seen_at = excluded.last_seen_at
                    """,
                    (str(user_id), date_str, max(1, current_page), iso_str)
                )

    @staticmethod
    def _compute_quartile_thresholds(non_zero_values: list[int]) -> tuple[int, int, int]:
        """
        Computes exact dynamic quartile thresholds (Q1, Q2, Q3) from actual non-zero daily counts,
        matching GitHub's contribution graph calibration algorithm.
        """
        if not non_zero_values:
            return (1, 2, 4)
        sorted_vals = sorted(non_zero_values)
        max_val = sorted_vals[-1]
        if max_val <= 4:
            return (1, 2, 3)

        def percentile(p: float) -> int:
            idx = (len(sorted_vals) - 1) * p
            lo = math.floor(idx)
            hi = math.ceil(idx)
            val = sorted_vals[lo] if lo == hi else (sorted_vals[lo] + sorted_vals[hi]) / 2.0
            return max(1, int(round(val)))

        q1 = max(1, percentile(0.25))
        q2 = max(q1 + 1, percentile(0.50))
        q3 = max(q2 + 1, percentile(0.75))
        return (q1, q2, q3)

    def get_accurate_profile_analytics(
        self,
        user_id: str,
        year: int | None = None,
        override_books_read: int | None = None,
        override_books_finished: int | None = None,
    ) -> dict[str, Any]:
        """
        Computes 100% accurate, database-backed reading and login analytics for `user_id`.
        """
        today = self._local_today()
        target_year = year or today.year

        # 1. Fetch daily activity rows for target year + trailing days for streak calculation
        daily_map: dict[datetime.date, dict[str, int]] = {}
        books_read_db = 0
        books_finished_db = 0

        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT activity_date, login_count, pages_read, books_touched
                FROM user_daily_telemetry
                WHERE user_id = ?
                  AND activity_date BETWEEN ? AND ?
                """,
                (str(user_id), f'{target_year - 1}-01-01', f'{target_year}-12-31'),
            ).fetchall()

            for r in rows:
                try:
                    dt = datetime.date.fromisoformat(r['activity_date'])
                    daily_map[dt] = {
                        'logins': int(r['login_count'] or 0),
                        'pages': int(r['pages_read'] or 0),
                        'books': int(r['books_touched'] or 0),
                    }
                except ValueError:
                    continue

            # Query book completion counts
            bk_row = conn.execute(
                """
                SELECT
                    COUNT(*) AS total_read,
                    SUM(CASE WHEN is_finished = 1 OR (total_pages > 0 AND current_page >= total_pages) THEN 1 ELSE 0 END) AS total_finished
                FROM user_book_progress
                WHERE user_id = ?
                """,
                (str(user_id),),
            ).fetchone()
            if bk_row:
                books_read_db = int(bk_row['total_read'] or 0)
                books_finished_db = int(bk_row['total_finished'] or 0)

        books_read = override_books_read if override_books_read is not None else books_read_db
        books_finished = (
            override_books_finished if override_books_finished is not None else books_finished_db
        )
        books_finished = min(books_read, max(0, books_finished))
        books_in_progress = max(0, books_read - books_finished)
        completion_rate = int(round((books_finished / books_read) * 100)) if books_read > 0 else 0

        # 2. Exact Cadence Aggregations (Today, ISO Week, Month, Year)
        iso_year, iso_week, _ = today.isocalendar()
        logins_today = daily_map.get(today, {}).get('logins', 0)
        logins_this_week = 0
        logins_this_month = 0
        total_logins_year = 0
        total_pages_year = 0
        active_days_year = 0

        weekday_totals = [0] * 7  # 0=Mon .. 6=Sun
        month_totals = [0] * 13   # 1=Jan .. 12=Dec
        non_zero_scores: list[int] = []

        start_of_year = datetime.date(target_year, 1, 1)
        end_of_year = datetime.date(target_year, 12, 31)

        curr = start_of_year
        while curr <= end_of_year:
            entry = daily_map.get(curr, {'logins': 0, 'pages': 0, 'books': 0})
            l_cnt = entry['logins']
            p_cnt = entry['pages']
            # Unified activity intensity score (1 login = 1 pt, every 15 pages read = 1 pt)
            score = l_cnt + (1 if p_cnt > 0 else 0) + (p_cnt // 15)

            if curr <= today:
                total_logins_year += l_cnt
                total_pages_year += p_cnt
                if score > 0:
                    active_days_year += 1
                    non_zero_scores.append(score)
                weekday_totals[curr.weekday()] += l_cnt
                month_totals[curr.month] += l_cnt

                c_iso_y, c_iso_w, _ = curr.isocalendar()
                if (c_iso_y, c_iso_w) == (iso_year, iso_week):
                    logins_this_week += l_cnt
                if curr.year == today.year and curr.month == today.month:
                    logins_this_month += l_cnt

            curr += datetime.timedelta(days=1)

        # 3. Exact Consecutive Day Streak Calculation (walks backward from Today / Yesterday)
        current_streak = 0
        cursor = today
        if daily_map.get(cursor, {}).get('logins', 0) == 0 and daily_map.get(cursor, {}).get('pages', 0) == 0:
            # If user hasn't logged in yet today, check if streak was alive yesterday
            yesterday = today - datetime.timedelta(days=1)
            if daily_map.get(yesterday, {}).get('logins', 0) > 0 or daily_map.get(yesterday, {}).get('pages', 0) > 0:
                cursor = yesterday
            else:
                cursor = None

        while cursor is not None:
            e = daily_map.get(cursor)
            if e and (e['logins'] > 0 or e['pages'] > 0):
                current_streak += 1
                cursor -= datetime.timedelta(days=1)
            else:
                break

        # 4. Exact Peak Day of Week & Peak Month Detection
        weekday_names = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
        if sum(weekday_totals) > 0:
            best_wd = max(range(7), key=lambda i: weekday_totals[i])
            peak_weekday = weekday_names[best_wd]
        else:
            peak_weekday = 'No data yet'

        if sum(month_totals) > 0:
            best_m = max(range(1, 13), key=lambda m: month_totals[m])
            peak_month = datetime.date(target_year, best_m, 1).strftime('%B')
        else:
            peak_month = 'No data yet'

        # 5. Dynamic Quartile Calibration (L0-L4) & Exact 53-Column Calendar Matrix
        q1, q2, q3 = self._compute_quartile_thresholds(non_zero_scores)

        # Align grid start to the Monday of the week containing Jan 1
        grid_start = start_of_year - datetime.timedelta(days=start_of_year.weekday())
        # Align grid end to the Sunday of the week containing Dec 31
        grid_end = end_of_year + datetime.timedelta(days=(6 - end_of_year.weekday()))
        total_weeks = ((grid_end - grid_start).days + 1) // 7

        weeks_matrix: list[dict[str, Any]] = []
        seen_months: set[int] = set()

        for wk_idx in range(total_weeks):
            week_start = grid_start + datetime.timedelta(days=wk_idx * 7)
            month_header = ''
            days_col: list[dict[str, Any]] = []

            for day_idx in range(7):
                cell_date = week_start + datetime.timedelta(days=day_idx)
                in_year = cell_date.year == target_year
                is_future = cell_date > today

                # Bind month label directly to the exact week column where the 1st..7th of that month falls
                if in_year and cell_date.month not in seen_months and cell_date.day <= 7:
                    month_header = cell_date.strftime('%b')
                    seen_months.add(cell_date.month)

                entry = daily_map.get(cell_date, {'logins': 0, 'pages': 0, 'books': 0})
                l_cnt = entry['logins'] if (in_year and not is_future) else 0
                p_cnt = entry['pages'] if (in_year and not is_future) else 0
                score = l_cnt + (1 if p_cnt > 0 else 0) + (p_cnt // 15)

                if not in_year or is_future or score == 0:
                    level = 0
                elif score <= q1:
                    level = 1
                elif score <= q2:
                    level = 2
                elif score <= q3:
                    level = 3
                else:
                    level = 4

                days_col.append({
                    'date': cell_date,
                    'in_year': in_year,
                    'is_future': is_future,
                    'is_today': cell_date == today,
                    'logins': l_cnt,
                    'pages': p_cnt,
                    'level': level,
                })

            weeks_matrix.append({
                'month_header': month_header,
                'days': days_col,
            })

        return {
            'year': target_year,
            'books_read': books_read,
            'books_in_progress': books_in_progress,
            'books_finished': books_finished,
            'completion_rate': completion_rate,
            'total_logins_year': total_logins_year,
            'total_pages_year': total_pages_year,
            'active_days_year': active_days_year,
            'logins_today': logins_today,
            'logins_this_week': logins_this_week,
            'logins_this_month': logins_this_month,
            'current_streak': current_streak,
            'peak_weekday': peak_weekday,
            'peak_month': peak_month,
            'quartiles': (q1, q2, q3),
            'total_weeks': total_weeks,
            'weeks_matrix': weeks_matrix,
        }


# Singleton engine instance
telemetry_engine = UserTelemetryEngine()


# -------------------------------------------------------------------------
# 3. MODULAR UI RENDERER (Column-Locked Months & Instant CSS Tooltips)
# -------------------------------------------------------------------------
def render_readership_and_activity_section(
    engine: UserTelemetryEngine,
    user_id: str,
    books_read: int | None = None,
    books_finished: int | None = None,
) -> None:
    """
    Renders the complete Readership KPI Cards + Precision 53-Week Heatmap.
    Drop this directly inside your `/profile` container.
    """
    ui.add_css(TELEMETRY_CSS)
    today_year = UserTelemetryEngine._local_today().year
    state = {'selected_year': today_year}

    section_wrapper = ui.column().classes('mt-6 gap-4 w-full')

    def draw_content() -> None:
        section_wrapper.clear()
        data = engine.get_accurate_profile_analytics(
            user_id=user_id,
            year=state['selected_year'],
            override_books_read=books_read,
            override_books_finished=books_finished,
        )
        q1, q2, q3 = data['quartiles']

        with section_wrapper:
            # Section Header
            with ui.column().classes('gap-0.5'):
                ui.label('READERSHIP & WEB APP ACTIVITY').classes(
                    'text-xs font-bold uppercase tracking-wider text-slate-400'
                )
                ui.label(
                    'Personal reading milestones, study cadence, and verified activity intensity across the academic year'
                ).classes('text-xs text-slate-500')

            # -----------------------------------------------------------------
            # ROW 1: 4 ACCURATE KPI CARDS
            # -----------------------------------------------------------------
            with ui.element('div').classes(
                'grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 w-full'
            ):
                # Card 1: Books Read
                with ui.element('div').classes(
                    'p-4 rounded-xl bg-slate-50/70 border border-slate-200/90 flex flex-col justify-between gap-2'
                ):
                    with ui.row().classes('items-center justify-between'):
                        ui.label('BOOKS READ').classes(
                            'text-[11px] font-bold uppercase tracking-wider text-slate-500'
                        )
                        with ui.element('div').classes(
                            'w-7 h-7 rounded-lg bg-indigo-100 text-indigo-600 flex items-center justify-center'
                        ):
                            ui.icon('menu_book').classes('text-sm')
                    ui.label(f"{data['books_read']}").classes(
                        'text-3xl font-extrabold text-slate-900 tabular-nums'
                    )
                    with ui.row().classes('items-center gap-1.5'):
                        ui.element('span').classes('w-2 h-2 rounded-full bg-indigo-500')
                        ui.label(f"{data['books_in_progress']} currently in progress").classes(
                            'text-xs font-medium text-slate-600'
                        )

                # Card 2: Books Finished + True Completion Bar
                with ui.element('div').classes(
                    'p-4 rounded-xl bg-slate-50/70 border border-slate-200/90 flex flex-col justify-between gap-2'
                ):
                    with ui.row().classes('items-center justify-between'):
                        ui.label('BOOKS FINISHED').classes(
                            'text-[11px] font-bold uppercase tracking-wider text-slate-500'
                        )
                        with ui.element('div').classes(
                            'w-7 h-7 rounded-lg bg-emerald-100 text-emerald-600 flex items-center justify-center'
                        ):
                            ui.icon('task_alt').classes('text-sm')
                    with ui.row().classes('items-baseline gap-2'):
                        ui.label(f"{data['books_finished']}").classes(
                            'text-3xl font-extrabold text-slate-900 tabular-nums'
                        )
                        ui.label(f"{data['completion_rate']}% rate").classes(
                            'px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-800 text-[11px] font-bold'
                        )
                    with ui.element('div').classes(
                        'w-full h-1.5 rounded-full bg-slate-200 overflow-hidden'
                    ):
                        ui.element('div').classes(
                            'h-full bg-emerald-500 rounded-full transition-all duration-300'
                        ).style(f"width: {data['completion_rate']}%;")

                # Card 3: Web App Logins (Exact Today / Week / Month / Year)
                with ui.element('div').classes(
                    'p-4 rounded-xl bg-slate-50/70 border border-slate-200/90 flex flex-col justify-between gap-2'
                ):
                    with ui.row().classes('items-center justify-between'):
                        ui.label('WEB APP LOGINS').classes(
                            'text-[11px] font-bold uppercase tracking-wider text-slate-500'
                        )
                        with ui.element('div').classes(
                            'w-7 h-7 rounded-lg bg-sky-100 text-sky-600 flex items-center justify-center'
                        ):
                            ui.icon('login').classes('text-sm')
                    with ui.row().classes('items-baseline gap-1.5'):
                        ui.label(f"{data['total_logins_year']}").classes(
                            'text-3xl font-extrabold text-slate-900 tabular-nums'
                        )
                        ui.label(f"in {data['year']}").classes('text-xs font-medium text-slate-500')
                    with ui.row().classes('items-center gap-1.5 flex-wrap'):
                        for badge_txt in [
                            f"Today: {data['logins_today']}",
                            f"Week: {data['logins_this_week']}",
                            f"Month: {data['logins_this_month']}",
                        ]:
                            ui.label(badge_txt).classes(
                                'px-1.5 py-0.5 rounded bg-white border border-slate-200 text-[11px] font-semibold text-slate-700 tabular-nums'
                            )

                # Card 4: Verified Streak & Peak Habit
                with ui.element('div').classes(
                    'p-4 rounded-xl bg-slate-50/70 border border-slate-200/90 flex flex-col justify-between gap-2'
                ):
                    with ui.row().classes('items-center justify-between'):
                        ui.label('PEAK HABIT').classes(
                            'text-[11px] font-bold uppercase tracking-wider text-slate-500'
                        )
                        with ui.element('div').classes(
                            'w-7 h-7 rounded-lg bg-amber-100 text-amber-600 flex items-center justify-center'
                        ):
                            ui.icon('local_fire_department').classes('text-sm')
                    streak_label = (
                        f"{data['current_streak']}-Day Streak"
                        if data['current_streak'] > 0
                        else '0-Day Streak'
                    )
                    ui.label(streak_label).classes('text-2xl font-extrabold text-slate-900')
                    peak_sub = (
                        f"Peak: {data['peak_weekday']}s • {data['peak_month']}"
                        if data['peak_weekday'] != 'No data yet'
                        else 'Log in & read to build habit insights'
                    )
                    ui.label(peak_sub).classes('text-xs font-semibold text-amber-700')

            # -----------------------------------------------------------------
            # ROW 2: PRECISION COLUMN-LOCKED 53-WEEK HEATMAP
            # -----------------------------------------------------------------
            with ui.element('div').classes(
                'w-full p-5 rounded-xl bg-white border border-slate-200 shadow-2xs flex flex-col gap-3.5'
            ):
                # Top Header + Year Switcher
                with ui.row().classes('w-full items-center justify-between flex-wrap gap-2'):
                    with ui.row().classes('items-center gap-2'):
                        ui.icon('grid_on').classes('text-emerald-600 text-base')
                        ui.label(
                            f"{data['total_logins_year']} web app sessions across {data['active_days_year']} active days in {data['year']}"
                        ).classes('text-sm font-bold text-slate-800')

                    with ui.row().classes('items-center gap-1.5'):
                        for yr in [today_year, today_year - 1]:
                            is_active = yr == state['selected_year']
                            cls = (
                                'bg-indigo-600 text-white shadow-2xs'
                                if is_active
                                else 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                            )
                            ui.button(
                                str(yr),
                                on_click=lambda y=yr: select_year(y),
                            ).props('unelevated dense no-caps').classes(
                                f'px-3 py-1 rounded-lg text-xs font-bold transition-all {cls}'
                            )

                # Column-Locked CSS Grid (Month labels share the exact column as their week!)
                with ui.element('div').classes('w-full overflow-x-auto heatmap-scroll pb-1'):
                    grid = ui.element('div').classes('libre-heatmap-grid').style(
                        f"--weeks-count: {data['total_weeks']};"
                    )
                    with grid:
                        # ROW 0: Top-left corner spacer + 53 Month Header cells
                        ui.element('div').classes('h-4')
                        for wk in data['weeks_matrix']:
                            with ui.element('div').classes('h-4 relative'):
                                if wk['month_header']:
                                    ui.label(wk['month_header']).classes(
                                        'absolute left-0 top-0 text-[10px] font-semibold text-slate-400 select-none whitespace-nowrap'
                                    )

                        # ROWS 1..7: Day-of-Week Label (Mon..Sun) + 53 Week Cells for that weekday
                        day_labels = ['Mon', '', 'Wed', '', 'Fri', '', 'Sun']
                        for day_idx in range(7):
                            ui.label(day_labels[day_idx]).classes(
                                'text-[10px] font-semibold text-slate-400 select-none leading-none pr-1'
                            )
                            for wk in data['weeks_matrix']:
                                cell = wk['days'][day_idx]
                                if not cell['in_year']:
                                    ui.element('div').classes('w-full aspect-square bg-transparent')
                                else:
                                    date_str = cell['date'].strftime('%a, %b %d, %Y')
                                    if cell['is_future']:
                                        tip = f'Upcoming: {date_str}'
                                        lvl_cls = 'hm-future'
                                    else:
                                        lvl_cls = f"hm-lvl-{cell['level']}"
                                        if cell['logins'] == 0 and cell['pages'] == 0:
                                            tip = f'No activity on {date_str}'
                                        else:
                                            parts = [f"{cell['logins']} login(s)"]
                                            if cell['pages'] > 0:
                                                parts.append(f"{cell['pages']} pages read")
                                            tip = f"{' • '.join(parts)} on {date_str}"

                                    today_cls = 'hm-today' if cell['is_today'] else ''
                                    cell_el = ui.element('div').classes(
                                        f'hm-cell {lvl_cls} {today_cls}'
                                    )
                                    cell_el._props['data-tip'] = tip
                                    cell_el._props['data-active'] = 'true'

                # Footer: Exact Insights + Calibrated Quartile Legend
                with ui.row().classes(
                    'w-full items-center justify-between pt-2 border-t border-slate-100 text-xs text-slate-500 flex-wrap gap-2'
                ):
                    with ui.row().classes('items-center gap-3 flex-wrap'):
                        ui.label(f"Most Active Day: {data['peak_weekday']}").classes(
                            'font-semibold text-slate-700'
                        )
                        ui.label('•').classes('text-slate-300')
                        ui.label(f"Most Active Month: {data['peak_month']}").classes(
                            'font-semibold text-slate-700'
                        )
                        if data['total_pages_year'] > 0:
                            ui.label('•').classes('text-slate-300')
                            ui.label(f"{data['total_pages_year']} pages read in {data['year']}").classes(
                                'font-medium text-emerald-700'
                            )

                    # Dynamic Quartile Legend with Hover Threshold Explanations
                    with ui.row().classes('items-center gap-1.5'):
                        ui.label('Less').classes('text-[11px] text-slate-400 mr-0.5')
                        legend_specs = [
                            ('hm-lvl-0', '0 sessions'),
                            ('hm-lvl-1', f'Low (1–{q1} sessions)'),
                            ('hm-lvl-2', f'Medium ({q1 + 1}–{q2} sessions)'),
                            ('hm-lvl-3', f'High ({q2 + 1}–{q3} sessions)'),
                            ('hm-lvl-4', f'Peak ({q3 + 1}+ sessions)'),
                        ]
                        for cls_name, tip_label in legend_specs:
                            swatch = ui.element('div').classes(f'w-3 h-3 rounded-[3px] {cls_name} hm-cell')
                            swatch._props['data-tip'] = tip_label
                            swatch._props['data-active'] = 'true'
                        ui.label('More').classes('text-[11px] text-slate-400 ml-0.5')

                        ui.element('span').classes('mx-1 text-slate-300').text = '|'
                        with ui.row().classes('items-center gap-1'):
                            ui.element('div').classes(
                                'w-2.5 h-2.5 rounded-[2px] hm-lvl-2 hm-today'
                            )
                            ui.label('Today').classes('text-[11px] font-medium text-indigo-600')

    def select_year(yr: int) -> None:
        state['selected_year'] = yr
        draw_content()

    draw_content()
