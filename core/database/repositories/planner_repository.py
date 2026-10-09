import uuid
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any

from core.database.repositories.base_repository import BaseRepository

logger = logging.getLogger("PLANNER_REPOSITORY")

class PlannerRepository(BaseRepository):
    """
    Dedicated repository for planner tasks, deadlines, priorities,
    and associated flashcard decks.
    """

    async def add_task(
        self,
        title: str,
        user_id: Optional[str] = None,
        due_date: str = "",
        priority: str = "medium",
        subject: str = "",
        linked_book_id: Optional[str] = None,
        linked_book_title: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Creates a planner task indexed by user_id and synchronized across UI."""
        if self.db is None or not title: return None
        try:
            task = {
                "id": str(uuid.uuid4()),
                "user_id": str(user_id) if user_id else "default",
                "title": title.strip(),
                "subject": subject or "General",
                "due_date": due_date or "No date",
                "priority": priority or "medium",
                "completed": False,
                "status": "todo",
                "linked_book_id": linked_book_id,
                "linked_book_title": linked_book_title,
                "created_at": datetime.utcnow()
            }
            await self.db['tasks'].insert_one(task)
            return task
        except Exception as e:
            logger.error(f"Add Task Error: {e}")
            return None

    async def get_tasks(self, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Retrieves tasks for a specific user, with fallback to all tasks or legacy planner."""
        if self.db is None: return []
        try:
            query = {"user_id": user_id} if user_id else {}
            cursor = self.db['tasks'].find(query).sort("created_at", -1)
            tasks = await cursor.to_list(length=300)
            if not tasks:
                # Check legacy planner collection for backward compatibility
                cursor2 = self.db['planner'].find({}).sort("created_at", -1)
                tasks = await cursor2.to_list(length=300)
            return tasks
        except Exception as e:
            logger.error(f"Get Tasks Error: {e}")
            return []

    async def toggle_task_status(self, task_id: str, completed: Optional[bool] = None) -> bool:
        """Toggles or updates completion status on tasks."""
        if self.db is None: return False
        try:
            task = await self.db['tasks'].find_one({"id": task_id})
            target_coll = 'tasks'
            if not task:
                task = await self.db['planner'].find_one({"id": task_id})
                target_coll = 'planner'
            if not task: return False

            new_val = not task.get('completed', False) if completed is None else completed
            new_status = "done" if new_val else "todo"
            await self.db[target_coll].update_one(
                {"id": task_id},
                {"$set": {"completed": new_val, "status": new_status}}
            )
            return True
        except Exception as e:
            logger.error(f"Toggle Task Error: {e}")
            return False

    async def update_task_status(self, task_id: str, new_status: str) -> bool:
        is_done = new_status.lower() in ("done", "completed", "true")
        return await self.toggle_task_status(task_id, completed=is_done)

    async def delete_task(self, task_id: str) -> bool:
        if self.db is None: return False
        try:
            await self.db['tasks'].delete_one({"id": task_id})
            await self.db['planner'].delete_one({"id": task_id})
            await self.delete_deck(task_id)
            return True
        except Exception as e:
            logger.error(f"Delete Task Error: {e}")
            return False

    async def save_deck(self, task_id: str, source_file: str, cards: list) -> bool:
        """Saves a flashcard deck linked to a planner task."""
        if self.db is None: return False
        try:
            deck_document = {
                'id': str(uuid.uuid4()),
                'task_id': task_id,
                'created_at': datetime.utcnow(),
                'source_file': source_file,
                'cards': cards
            }
            await self.db['decks'].delete_many({'task_id': task_id})
            await self.db['decks'].insert_one(deck_document)
            return True
        except Exception as e:
            logger.error(f"Save Deck Error: {e}")
            return False

    async def get_deck(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves flashcard deck for a task."""
        if self.db is None: return None
        try:
            return await self.db['decks'].find_one({'task_id': task_id})
        except Exception: return None

    async def delete_deck(self, task_id: str):
        """Removes a deck by task ID."""
        if self.db is None: return
        try:
            await self.db['decks'].delete_many({'task_id': task_id})
        except Exception: pass
