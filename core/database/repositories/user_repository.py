import re
import time
import uuid
import asyncio
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any

import bcrypt
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from core.database.repositories.base_repository import BaseRepository

logger = logging.getLogger("USER_REPOSITORY")

USER_ID_PATTERN = re.compile(r"^\d{2}-\d{5}$")
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def validate_user_id(id_str: str) -> bool:
    """
    Strictly validates that an Institutional ID follows the YY-NNNNN numeric format.
    Rejects letters, spaces, missing/extra hyphens, and invalid digit counts.
    """
    if not isinstance(id_str, str):
        return False
    if not USER_ID_PATTERN.fullmatch(id_str):
        return False
    # Sequence 00000 is invalid; valid range is 00001 - 99999
    _, seq_part = id_str.split("-")
    return 1 <= int(seq_part) <= 99999


def format_and_clean_user_id(raw_id: Any) -> str:
    """
    Sanitizes, validates, and standardizes an Institutional ID into 'YY-NNNNN' format.
    Accepts:
      - '23-00125' (7 integer numbers separated by a hyphen after the 2-digit year)
      - '2300125'  (7 pure integer numbers, automatically formatted to '23-00125')
    Enforces:
      - Numbers only (no alphabetic characters, spaces, or special symbols).
      - Exactly 7 integer numbers (2 digits for registration year, 5 digits for student sequence no.).
      - Student sequence number must be in range 00001 to 99999 (5 digits maximum capacity).
    Returns formatted ID string (e.g., '23-00125').
    Raises ValueError with descriptive guidance if invalid.
    """
    if raw_id is None:
        raise ValueError("Input registered ID e.g, : (23-00125).")

    cleaned = str(raw_id).strip()
    if not cleaned:
        raise ValueError("Input registered ID e.g, : (23-00125).")

    # Reject letters, spaces, and non-numeric characters (only digits and hyphens allowed)
    if not re.match(r"^[\d-]+$", cleaned):
        raise ValueError("Institutional ID must contain numbers only (e.g., 23-00125).")

    # If entered as pure digits without hyphen (e.g. 7 integer numbers '2300125')
    if cleaned.isdigit():
        if len(cleaned) != 7:
            raise ValueError(
                f"Institutional ID must contain exactly 7 digits (2 for registration year and 5 for student number). Got {len(cleaned)} digits."
            )
        cleaned = f"{cleaned[:2]}-{cleaned[2:]}"

    # Verify standard YY-NNNNN pattern (2 digits, hyphen, 5 digits)
    if not USER_ID_PATTERN.fullmatch(cleaned):
        raise ValueError(
            "Institutional ID must follow the (YY-NNNNN) format, for example: 23-00125 (2 digits for year, 5 digits for student number)."
        )

    year_str, seq_str = cleaned.split("-")
    seq_num = int(seq_str)
    if seq_num < 1 or seq_num > 99999:
        raise ValueError(
            "The 5-digit student registration number must be between 00001 and 99999 (maximum capacity is 5 digits)."
        )

    return f"{year_str}-{seq_num:05d}"


def is_attempted_institutional_id(identifier: str) -> bool:
    """
    Detects whether a sign-in identifier is an attempted Institutional ID rather than
    an email or standard username.
    Triggers if:
    - It does not contain an '@'
    - It contains a hyphen (e.g., '23-0012A', 'FAC-2024-001', '2024-3903E', '23-00130')
    - Or it consists solely of digits (e.g., '1234', '696969', '2300001')
    """
    if not isinstance(identifier, str):
        return False
    cleaned = identifier.strip()
    if not cleaned:
        return False
    if "@" in cleaned:
        return False
    if "-" in cleaned or cleaned.isdigit():
        return True
    return False


class UserRepository(BaseRepository):
    """
    Dedicated repository for user authentication, accounts, roles, profiles,
    security credentials, personal preferences, and administrative diagnostics.
    """

    async def get_user_profile(self, user_id: Optional[str] = None) -> Dict[str, Any]:
        """Gets user profile strictly isolated by user ID with institutional ID, avatar, and cover."""
        if self.db is None: return {}
        try:
            if user_id:
                user = await self.db['users'].find_one({
                    "id": user_id,
                    "$or": [{"type": "account"}, {"type": {"$exists": False}}]
                })
                if user:
                    inst_id = user.get("institutional_id") or user.get("student_id") or user.get("employee_id") or user.get("staff_id") or user.get("admin_id") or f"2024-{str(user_id)[:5].upper()}"
                    return {
                        "id": user_id,
                        "name": user.get("name") or user.get("username", "Library User"),
                        "username": user.get("username", "user"),
                        "email": user.get("email", ""),
                        "role": user.get("role", "student"),
                        "institutional_id": inst_id,
                        "student_id": inst_id,
                        "program": user.get("program") or "BSCS",
                        "year_level": user.get("year_level") or "1st Year",
                        "department": user.get("department") or "",
                        "branch": user.get("branch") or "",
                        "address": user.get("address") or user.get("branch") or "NEMSU Tandag Campus",
                        "admin_code": user.get("admin_code") or "",
                        "headline": user.get("headline", "Student / Researcher"),
                        "bio": user.get("bio", "Exploring knowledge with Libre-Library."),
                        "avatar_url": user.get("avatar_url") or "",
                        "cover_url": user.get("cover_url") or "",
                        "joined_at": user.get("created_at", time.time())
                    }
            return {
                "name": "Library User",
                "username": "user",
                "email": "",
                "role": "student",
                "institutional_id": "2024-00001",
                "student_id": "2024-00001",
                "program": "BSCS",
                "year_level": "1st Year",
                "department": "",
                "branch": "",
                "address": "NEMSU Tandag Campus",
                "admin_code": "",
                "headline": "Student / Researcher",
                "bio": "Exploring knowledge with Libre-Library.",
                "avatar_url": "",
                "cover_url": "",
                "joined_at": time.time()
            }
        except Exception: return {}

    async def update_user_profile(
        self,
        user_id: Optional[str],
        name: str,
        bio: str,
        headline: Optional[str] = None,
        institutional_id: Optional[str] = None,
        student_id: Optional[str] = None,
        program: Optional[str] = None,
        year_level: Optional[str] = None,
        department: Optional[str] = None,
        branch: Optional[str] = None,
        address: Optional[str] = None,
        avatar_url: Optional[str] = None,
        cover_url: Optional[str] = None
    ) -> bool:
        """
        Updates profile strictly isolated to the specified user account.
        SECURITY: Role permissions cannot be modified through profile updates.
        """
        if self.db is None or not user_id: return False
        try:
            updates = {
                "name": name.strip(),
                "bio": bio.strip()
            }
            if headline is not None:
                updates["headline"] = headline.strip()
            effective_id = institutional_id or student_id
            if effective_id is not None:
                clean_id = effective_id.strip()
                updates["institutional_id"] = clean_id
                updates["student_id"] = clean_id
            if program is not None:
                updates["program"] = program.strip().upper()
            if year_level is not None:
                updates["year_level"] = year_level.strip()
            if department is not None:
                updates["department"] = department.strip()
            if branch is not None:
                updates["branch"] = branch.strip()
            if address is not None:
                updates["address"] = address.strip()
            if avatar_url is not None:
                updates["avatar_url"] = avatar_url.strip()
            if cover_url is not None:
                updates["cover_url"] = cover_url.strip()

            result = await self.db['users'].update_one(
                {"id": user_id, "$or": [{"type": "account"}, {"type": {"$exists": False}}]},
                {"$set": updates}
            )
            return result.modified_count > 0 or result.matched_count > 0
        except Exception as e:
            logger.error(f"Update User Profile Error: {e}")
            return False

    async def update_user_media(
        self,
        user_id: str,
        avatar_url: Optional[str] = None,
        cover_url: Optional[str] = None
    ) -> bool:
        """Updates avatar_url or cover_url for user profile."""
        if self.db is None or not user_id: return False
        try:
            updates = {}
            if avatar_url is not None:
                updates["avatar_url"] = avatar_url
            if cover_url is not None:
                updates["cover_url"] = cover_url
            if not updates: return False
            result = await self.db['users'].update_one(
                {"id": user_id, "type": "account"},
                {"$set": updates}
            )
            return result.modified_count > 0 or result.matched_count > 0
        except Exception as e:
            logger.error(f"Update User Media Error: {e}")
            return False

    async def get_total_user_count(self) -> int:
        """Returns total registered user accounts."""
        if self.db is None: return 0
        try:
            return await self.db['users'].count_documents({"type": "account"})
        except Exception:
            return 0

    async def get_library_stats(self, user_id: Optional[str] = None) -> Dict[str, Any]:
        """Calculates real-time library, study and task completion statistics with parallel counts."""
        if self.db is None:
            return {
                "books": 0,
                "tasks_done": 0,
                "total_tasks": 0,
                "reading_count": 0,
                "completed_books": 0,
                "notes_count": 0,
                "attendance_visits": 0,
                "ai_conversations": 0,
            }
        try:
            task_filter: Dict[str, Any] = {"$or": [{"completed": True}, {"status": "done"}]}
            total_filter: Dict[str, Any] = {}
            reading_q: Dict[str, Any] = {}
            completed_q: Dict[str, Any] = {"$or": [{"status": "completed"}, {"progress_percent": {"$gte": 95}}]}
            notes_q: Dict[str, Any] = {}
            attendance_q: Dict[str, Any] = {}
            chat_q: Dict[str, Any] = {}

            if user_id:
                task_filter["user_id"] = user_id
                total_filter["user_id"] = user_id
                reading_q["user_id"] = user_id
                completed_q["user_id"] = user_id
                notes_q["user_id"] = user_id
                attendance_q["$or"] = [{"user_id": user_id}, {"student_id": user_id}]
                chat_q["user_id"] = user_id

            (
                book_count,
                done_tasks,
                total_tasks,
                reading_count,
                completed_books,
                notes_count,
                attendance_visits,
                ai_conversations
            ) = await asyncio.gather(
                self.db['books'].count_documents({}),
                self.db['tasks'].count_documents(task_filter),
                self.db['tasks'].count_documents(total_filter),
                self.db['reading_progress'].count_documents(reading_q),
                self.db['reading_progress'].count_documents(completed_q),
                self.db['annotations'].count_documents(notes_q),
                self.db['attendance_logs'].count_documents(attendance_q),
                self.db['chats'].count_documents(chat_q),
            )

            if done_tasks == 0 and not user_id:
                done_tasks = await self.db['planner'].count_documents({"status": "done"})

            if total_tasks == 0 and not user_id:
                total_tasks = await self.db['planner'].count_documents({})

            return {
                "books": book_count,
                "tasks_done": done_tasks,
                "total_tasks": total_tasks,
                "reading_count": reading_count,
                "completed_books": completed_books,
                "notes_count": notes_count,
                "attendance_visits": attendance_visits,
                "ai_conversations": ai_conversations
            }
        except Exception as e:
            logger.error(f"Stats Error: {e}")
            return {
                "books": 0,
                "tasks_done": 0,
                "total_tasks": 0,
                "reading_count": 0,
                "completed_books": 0,
                "notes_count": 0,
                "attendance_visits": 0,
                "ai_conversations": 0
            }

    async def update_user_role(self, user_id: str, new_role: str) -> bool:
        """Promotes or demotes user role (admin/user)."""
        if self.db is None: return False
        try:
            await self.db['users'].update_one({"id": user_id}, {"$set": {"role": new_role}})
            return True
        except Exception as e:
            logger.error(f"Update User Role Error: {e}")
            return False

    async def delete_user_by_id(self, user_id: str) -> bool:
        """Deletes user account and associated personal study data."""
        if self.db is None: return False
        try:
            await self.db['users'].delete_one({"id": user_id})
            await self.db['tasks'].delete_many({"user_id": user_id})
            await self.db['reading_progress'].delete_many({"user_id": user_id})
            return True
        except Exception as e:
            logger.error(f"Delete User Error: {e}")
            return False

    async def get_system_diagnostics(self) -> Dict[str, Any]:
        """Provides holistic system diagnostic metrics for the Admin Console via parallel counts."""
        if self.db is None: return {}
        try:
            user_count, book_count, task_count, deck_count, chat_count = await asyncio.gather(
                self.db['users'].count_documents({"type": "account"}),
                self.db['books'].count_documents({}),
                self.db['tasks'].count_documents({}),
                self.db['decks'].count_documents({}),
                self.db['chat_history'].count_documents({})
            )
            return {
                "users": user_count,
                "books": book_count,
                "tasks": task_count,
                "decks": deck_count,
                "chat_messages": chat_count
            }
        except Exception as e:
            logger.error(f"System Diagnostics Error: {e}")
            return {}

    async def generate_next_user_id(self, year: Optional[int] = None) -> str:
        """
        Atomically increments and returns the next sequential user ID in YY-NNNNN format.
        Safe under high concurrency via MongoDB find_one_and_update + $inc.
        """
        if self.db is None:
            raise RuntimeError("Database connection is not initialized.")
        if year is None:
            year = datetime.now().year
        year_2digit = f"{year % 100:02d}"
        counter_id = f"user_seq_{year_2digit}"

        counter_doc = await self.db["counters"].find_one_and_update(
            {"_id": counter_id},
            {
                "$inc": {"seq": 1},
                "$setOnInsert": {"year": year_2digit},
            },
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )

        seq_num = counter_doc["seq"]
        if seq_num > 99999:
            raise ValueError(
                f"Maximum registration capacity (99999) reached for year {year_2digit}."
            )

        return f"{year_2digit}-{seq_num:05d}"

    async def create_user(
        self,
        username: Optional[str] = None,
        email: Optional[str] = None,
        hashed_password: Optional[str] = None,
        role: str = "student",
        institutional_id: Optional[str] = None,
        program: Optional[str] = None,
        year_level: Optional[str] = None,
        department: Optional[str] = None,
        branch: Optional[str] = None,
        admin_code: Optional[str] = None,
        name: Optional[str] = None,
        avatar_url: Optional[str] = None,
        cover_url: Optional[str] = None,
        password: Optional[str] = None,
        full_name: Optional[str] = None,
        registration_year: Optional[int] = None,
        **kwargs
    ) -> Optional[Dict[str, Any]]:
        """
        Creates a new user account with a validated Institutional ID.
        If 'institutional_id' is provided, it is sanitized, formatted, and verified for uniqueness.
        If omitted, the next sequential ID in the YY-NNNNN series is generated automatically.
        """
        if self.db is None:
            raise RuntimeError("Database connection is not initialized.")

        # 1. Process Institutional ID
        raw_inst_id = institutional_id or kwargs.pop("institutional_id", None) or kwargs.pop("student_id", None)
        kwargs.pop("employee_id", None)

        if raw_inst_id:
            assigned_id = format_and_clean_user_id(raw_inst_id)
            if await self.get_user_by_identifier(assigned_id):
                raise ValueError(f"An account with Institutional ID '{assigned_id}' already exists.")
            # Synchronize sequence counter with provided ID
            try:
                y_str, s_str = assigned_id.split("-")
                await self.db['counters'].update_one(
                    {"_id": f"user_seq_{y_str}"},
                    {"$max": {"seq": int(s_str), "year": y_str}},
                    upsert=True
                )
            except Exception as counter_err:
                logger.debug(f"Counter update skipped: {counter_err}")
        else:
            assigned_id = await self.generate_next_user_id(year=registration_year)

        clean_username = (username or kwargs.get("username") or "").strip()
        clean_email = (email or kwargs.get("email") or "").strip().lower()
        display_name = (name or full_name or kwargs.get("name") or kwargs.get("full_name") or clean_username).strip()
        prog_val = (program or kwargs.get("course") or kwargs.get("program") or "").strip()
        year_val = (year_level or kwargs.get("year_level") or "").strip()
        dept_val = (department or kwargs.get("department") or "").strip()
        branch_val = (branch or kwargs.get("branch") or "").strip()

        if not clean_username:
            raise ValueError("Username is required.")
        if not clean_email:
            raise ValueError("Email is required.")

        if "-" in clean_username or clean_username.isdigit():
            raise ValueError(
                "Usernames cannot contain hyphens or consist solely of numbers (reserved for Institutional IDs)."
            )

        # 2. Determine and hash password
        raw_password = password or kwargs.get("password")
        if raw_password:
            if len(raw_password) < 6:
                raise ValueError("Password must be at least 6 characters long.")
            hp_str = bcrypt.hashpw(raw_password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
        elif hashed_password:
            hp_str = hashed_password.decode("utf-8") if isinstance(hashed_password, bytes) else str(hashed_password)
            if not hp_str.startswith("$2"):
                hp_str = bcrypt.hashpw(hp_str.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
        else:
            raise ValueError("Password is required.")

        # 3. Collision checks
        if await self.get_user_by_email(clean_email):
            raise ValueError("An account with this email already exists.")
        if await self.get_user_by_identifier(clean_username):
            raise ValueError("This username is already taken. Please choose another.")

        user_id = str(uuid.uuid4())
        user = {
            "id": user_id,
            "username": clean_username,
            "email": clean_email,
            "hashed_password": hp_str,
            "password_hash": hp_str,
            "role": role,
            "name": display_name,
            "full_name": display_name,
            "institutional_id": assigned_id,
            "student_id": assigned_id,
            "employee_id": assigned_id if role in ("faculty", "librarian", "admin") else "",
            "program": prog_val,
            "year_level": year_val,
            "department": dept_val,
            "branch": branch_val,
            "admin_code": (admin_code or "").strip(),
            "avatar_url": (avatar_url or "").strip(),
            "cover_url": (cover_url or "").strip(),
            "created_at": time.time(),
            "last_login": None,
            "type": "account",
            **kwargs
        }

        try:
            result = await self.db['users'].insert_one(user)
            user["_id"] = result.inserted_id
            return self.clean_doc(user)
        except DuplicateKeyError as exc:
            raise ValueError(
                "An account with this email, username, or Institutional ID already exists."
            ) from exc
        except Exception as e:
            logger.error(f"Create User Error: {e}")
            raise

    async def get_user_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        """Case-insensitive search for a user by email."""
        if self.db is None or not email: return None
        try:
            clean = email.strip()
            regex = {"$regex": f"^{re.escape(clean)}$", "$options": "i"}
            doc = await self.db['users'].find_one({"email": regex, "type": "account"})
            if not doc:
                doc = await self.db['users'].find_one({"email": regex})
            return self.clean_doc(doc)
        except Exception as e:
            logger.error(f"Get User By Email Error: {e}")
            return None

    async def get_user_by_identifier(self, identifier: str) -> Optional[Dict[str, Any]]:
        """
        Retrieves a user by Institutional ID (strictly validated if in ID format),
        Email, or Username (preserving login access for legacy accounts via email/username).
        """
        if self.db is None or not identifier or not isinstance(identifier, str):
            return None

        cleaned = identifier.strip()
        if not cleaned:
            return None

        # 1. Email lookup
        if "@" in cleaned:
            return await self.get_user_by_email(cleaned)

        # 2. Institutional ID lookup (if input matches or attempts an ID format)
        if is_attempted_institutional_id(cleaned):
            if not validate_user_id(cleaned):
                raise ValueError(
                    "Invalid ID format. Institutional IDs must be in YY-NNNNN format with numbers only."
                )
            doc = await self.db['users'].find_one({
                "$or": [
                    {"institutional_id": cleaned},
                    {"student_id": cleaned},
                    {"employee_id": cleaned},
                    {"staff_id": cleaned},
                    {"admin_id": cleaned}
                ],
                "type": "account"
            })
            if not doc:
                doc = await self.db['users'].find_one({
                    "$or": [
                        {"institutional_id": cleaned},
                        {"student_id": cleaned},
                        {"employee_id": cleaned},
                        {"staff_id": cleaned},
                        {"admin_id": cleaned}
                    ]
                })
            return self.clean_doc(doc)

        # 3. Username lookup (supports both new and legacy accounts)
        regex = {"$regex": f"^{re.escape(cleaned)}$", "$options": "i"}
        doc = await self.db['users'].find_one({"username": regex, "type": "account"})
        if not doc:
            doc = await self.db['users'].find_one({"username": regex})
        return self.clean_doc(doc)

    async def get_users_by_identifier(self, identifier: str) -> List[Dict[str, Any]]:
        """
        Retrieves all matching user accounts by email, username, or institutional ID.
        """
        if self.db is None or not identifier or not isinstance(identifier, str):
            return []

        cleaned = identifier.strip()
        if not cleaned:
            return []

        if is_attempted_institutional_id(cleaned):
            if not validate_user_id(cleaned):
                raise ValueError(
                    "Invalid ID format. Institutional IDs must be in YY-NNNNN format with numbers only."
                )
            cursor = self.db['users'].find({
                "$or": [
                    {"institutional_id": cleaned},
                    {"student_id": cleaned},
                    {"employee_id": cleaned},
                    {"staff_id": cleaned},
                    {"admin_id": cleaned}
                ],
                "type": "account"
            })
            docs = await cursor.to_list(length=10)
            if not docs:
                cursor = self.db['users'].find({
                    "$or": [
                        {"institutional_id": cleaned},
                        {"student_id": cleaned},
                        {"employee_id": cleaned},
                        {"staff_id": cleaned},
                        {"admin_id": cleaned}
                    ]
                })
                docs = await cursor.to_list(length=10)
            return self.clean_docs(docs)

        if "@" in cleaned:
            regex = {"$regex": f"^{re.escape(cleaned.lower())}$", "$options": "i"}
            cursor = self.db['users'].find({"email": regex, "type": "account"})
            docs = await cursor.to_list(length=10)
            if not docs:
                cursor = self.db['users'].find({"email": regex})
                docs = await cursor.to_list(length=10)
            return self.clean_docs(docs)

        # Username
        regex = {"$regex": f"^{re.escape(cleaned)}$", "$options": "i"}
        cursor = self.db['users'].find({"username": regex, "type": "account"})
        docs = await cursor.to_list(length=10)
        if not docs:
            cursor = self.db['users'].find({"username": regex})
            docs = await cursor.to_list(length=10)
        return self.clean_docs(docs)

    async def authenticate_user(self, identifier: str, password: str) -> Dict[str, Any]:
        """
        Validates identifier format, looks up the account, and strictly verifies the bcrypt password.
        Raises ValueError with user-safe messages on validation or authentication failure.
        """
        if not identifier or not str(identifier).strip():
            raise ValueError("Please enter your Institutional ID, Username, or Email.")
        if not password:
            raise ValueError("Password is required to sign in.")

        # Will raise ValueError if identifier is a malformed Institutional ID
        user = await self.get_user_by_identifier(identifier)
        if not user:
            raise ValueError("Invalid credentials. Please check your identifier and password.")

        stored_hash = user.get("hashed_password") or user.get("password_hash") or user.get("password")
        if not stored_hash:
            raise ValueError("Account authentication configuration is invalid.")

        if isinstance(stored_hash, str):
            stored_hash_bytes = stored_hash.encode("utf-8")
        else:
            stored_hash_bytes = stored_hash

        try:
            is_valid = bcrypt.checkpw(password.encode("utf-8"), stored_hash_bytes)
        except Exception:
            is_valid = False

        if not is_valid:
            raise ValueError("Invalid credentials. Please check your identifier and password.")

        return user

    async def update_user_last_login(self, user_id: str):
        if self.db is None: return
        try:
            await self.db['users'].update_one({"id": user_id}, {"$set": {"last_login": time.time()}})
        except Exception: pass

    async def get_all_users(self) -> List[Dict[str, Any]]:
        if self.db is None: return []
        try:
            cursor = self.db['users'].find({"type": "account"})
            users = await cursor.to_list(length=100)
            return self.clean_docs(users)
        except Exception: return []

    async def normalize_existing_users(self):
        """
        One-time maintenance to normalize whitespace and casing across existing user accounts.
        Also resolves duplicate casing accounts so users have a single unified account with admin privileges.
        """
        if self.db is None: return
        try:
            users = await self.db['users'].find({"type": "account"}).to_list(length=200)
            by_email: Dict[str, List[Dict[str, Any]]] = {}
            for u in users:
                raw_email = u.get('email')
                if not raw_email: continue
                clean = raw_email.strip().lower()
                by_email.setdefault(clean, []).append(u)

            for clean_email, doc_list in by_email.items():
                if len(doc_list) > 1:
                    has_admin = any(d.get('role') == 'admin' for d in doc_list)
                    def _safe_user_ts(d):
                        c = d.get('created_at')
                        if hasattr(c, 'timestamp'): return c.timestamp()
                        try: return float(c or 0)
                        except Exception: return 0.0
                    doc_list.sort(key=_safe_user_ts, reverse=True)
                    keeper = doc_list[0]
                    duplicates = doc_list[1:]

                    dup_ids = [d["_id"] for d in duplicates]
                    await self.db['users'].delete_many({"_id": {"$in": dup_ids}})

                    new_role = "admin" if has_admin else keeper.get('role', 'user')
                    await self.db['users'].update_one(
                        {"_id": keeper["_id"]},
                        {"$set": {
                            "email": clean_email,
                            "username": keeper.get("username", clean_email.split('@')[0]).strip(),
                            "role": new_role
                        }}
                    )
                    logger.info(f"Reconciled duplicate user account for email: {clean_email} (preserved {new_role} role)")
                else:
                    u = doc_list[0]
                    clean_username = (u.get("username") or "").strip() or clean_email.split('@')[0]
                    await self.db['users'].update_one(
                        {"_id": u["_id"]},
                        {"$set": {"email": clean_email, "username": clean_username}}
                    )
            logger.info("User accounts normalized successfully.")
        except Exception as e:
            logger.warning(f"User normalization note: {e}")

    async def get_user_reading_list(self, user_id: str, limit: int = 8) -> List[Dict[str, Any]]:
        """Returns in-progress reading records enriched with book metadata."""
        if self.db is None or not user_id: return []
        try:
            cursor = self.db['reading_progress'].find({"user_id": user_id}).sort("last_read_at", -1).limit(limit)
            progress_items = await cursor.to_list(length=limit)
            enriched = []
            for item in progress_items:
                b_id = item.get('book_id')
                book = await self.db['books'].find_one({"id": b_id})
                if book:
                    enriched.append({
                        "id": b_id,
                        "book_id": b_id,
                        "title": book.get('title', 'Untitled'),
                        "display_author": book.get('display_author') or 'Unknown Author',
                        "cover_image": book.get('cover_image') or f"/static_books/{b_id}/cover.jpg",
                        "cover_url": book.get('cover_image') or f"/static_books/{b_id}/cover.jpg",
                        "file_type": book.get('file_type', 'E-BOOK'),
                        "current_page": item.get('current_page', 1),
                        "total_pages": item.get('total_pages', 1),
                        "progress_percent": item.get('progress_percent', 0),
                        "status": item.get('status', 'reading'),
                        "last_read_at": item.get('last_read_at', time.time())
                    })
            return enriched
        except Exception as e:
            logger.error(f"Get User Reading List Error: {e}")
            return []

    async def toggle_user_favorite(self, user_id: str, book_id: str) -> bool:
        """Toggles bookmark favorite status strictly isolated per user in user_favorites."""
        if self.db is None or not user_id or not book_id:
            return False
        clean_user = str(user_id).strip()
        clean_book = str(book_id).strip()
        try:
            existing = await self.db['user_favorites'].find_one({"user_id": clean_user, "book_id": clean_book})
            if existing:
                await self.db['user_favorites'].delete_one({"user_id": clean_user, "book_id": clean_book})
                return False  # Now unfavorited
            else:
                await self.db['user_favorites'].insert_one({
                    "user_id": clean_user,
                    "book_id": clean_book,
                    "added_at": time.time()
                })
                return True  # Now favorited
        except Exception as e:
            logger.error(f"Toggle User Favorite Error: {e}")
            return False

    async def get_user_favorite_book_ids(self, user_id: str) -> List[str]:
        """Returns list of book IDs favorited by this user."""
        if self.db is None or not user_id:
            return []
        clean_user = str(user_id).strip()
        try:
            cursor = self.db['user_favorites'].find({"user_id": clean_user})
            fav_docs = await cursor.to_list(length=1000)
            return [f["book_id"] for f in fav_docs if f.get("book_id")]
        except Exception as e:
            logger.error(f"Get Favorite Book IDs Error: {e}")
            return []

    async def is_book_favorited(self, user_id: str, book_id: str) -> bool:
        """Checks if a specific book is marked as favorite by this user."""
        if self.db is None or not user_id or not book_id:
            return False
        try:
            doc = await self.db['user_favorites'].find_one({"user_id": str(user_id).strip(), "book_id": str(book_id).strip()})
            return bool(doc)
        except Exception:
            return False

    async def get_user_favorites(self, user_id: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
        """Returns books marked as favorites isolated to the specified user account."""
        if self.db is None: return []
        try:
            if user_id:
                clean_user = str(user_id).strip()
                cursor = self.db['user_favorites'].find({"user_id": clean_user}).sort("added_at", -1).limit(limit)
                fav_docs = await cursor.to_list(length=limit)
                b_ids = [f['book_id'] for f in fav_docs if f.get('book_id')]
                if not b_ids:
                    return []
                b_cursor = self.db['books'].find({"id": {"$in": b_ids}})
                return await b_cursor.to_list(length=limit)
            else:
                cursor = self.db['books'].find({"is_favorite": True}).sort("added_at", -1).limit(limit)
                return await cursor.to_list(length=limit)
        except Exception as e:
            logger.error(f"Get Favorites Error: {e}")
            return []

    async def change_user_password(self, user_id: str, old_pwd: str, new_pwd: str) -> tuple:
        """Verifies current password and updates password hash."""
        if self.db is None or not user_id: return False, "Database unavailable"
        if len(new_pwd.strip()) < 6: return False, "New password must be at least 6 characters"
        try:
            import bcrypt
            user = await self.db['users'].find_one({"id": user_id})
            if not user: return False, "User account not found"

            stored_hash = user.get('hashed_password', '')
            if not stored_hash: return False, "Account has no password configured"

            if not bcrypt.checkpw(old_pwd.strip().encode('utf-8'), stored_hash.encode('utf-8')):
                return False, "Incorrect current password"

            new_hash = bcrypt.hashpw(new_pwd.strip().encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
            await self.db['users'].update_one(
                {"id": user_id},
                {"$set": {"hashed_password": new_hash, "updated_at": time.time()}}
            )
            return True, "Password successfully updated!"
        except Exception as e:
            logger.error(f"Change Password Error: {e}")
            return False, f"Password change error: {e}"

    async def update_user_preferences(self, user_id: str, prefs: Dict[str, Any]) -> bool:
        """Updates user preferences (theme, reading goal, AI tone, avatar icon)."""
        if self.db is None or not user_id: return False
        try:
            await self.db['users'].update_one(
                {"id": user_id},
                {"$set": {"preferences": prefs}}
            )
            return True
        except Exception as e:
            logger.error(f"Update Preferences Error: {e}")
            return False

    async def get_user_preferences(self, user_id: str) -> Dict[str, Any]:
        """Loads user preferences."""
        if self.db is None or not user_id: return {}
        try:
            user = await self.db['users'].find_one({"id": user_id})
            if user:
                return user.get("preferences", {})
            return {}
        except Exception:
            return {}
