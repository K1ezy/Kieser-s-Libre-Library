import asyncio
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.database.mongo_manager import mongo_db

async def main():
    await mongo_db.initialize()
    if mongo_db.db is None:
        print("❌ Could not connect to MongoDB.")
        return

    action = sys.argv[1] if len(sys.argv) > 1 else "list"

    if action == "list":
        users = await mongo_db.db['users'].find({}).to_list(100)
        print(f"Found {len(users)} document(s) in 'users' collection:")
        for idx, u in enumerate(users, 1):
            doc_type = u.get("type", "unknown")
            user_id = u.get("id") or u.get("_id")
            username = u.get("username", "(no username)")
            email = u.get("email", "(no email)")
            role = u.get("role", "N/A")
            print(f"  [{idx}] Type: {doc_type:<8} | Username: {username:<15} | Email: {email:<22} | Role: {role}")

    elif action in ("delete", "delete_all"):
        # Delete all registered credential accounts
        del_res = await mongo_db.db['users'].delete_many({})
        print(f"[OK] Deleted {del_res.deleted_count} document(s) from 'users' collection.")
        
        # Optional: Clean up user tasks in planner
        if 'tasks' in await mongo_db.db.list_collection_names():
            task_res = await mongo_db.db['tasks'].delete_many({})
            print(f"[OK] Cleared {task_res.deleted_count} user planner task(s).")
            
        print("\nAll user records and credentials have been successfully deleted!")
        print("-> The next account you register at /signup will automatically become the ADMIN.")

if __name__ == "__main__":
    asyncio.run(main())
