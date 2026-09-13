from motor.motor_asyncio import AsyncIOMotorClient
import os

# -----------------------------------------------------------------------------
# Database Connection Logic
# -----------------------------------------------------------------------------
class Database:
    client: AsyncIOMotorClient = None

# Singleton instance
db_instance = Database()

async def get_database():
    """
    Returns the AsyncIOMotorDatabase instance.
    Initializes the connection if it hasn't been created yet.
    """
    if db_instance.client is None:
        # Connection String (Default to local)
        mongo_uri = os.getenv("MONGO_URI", "mongodb://localhost:27017")
        
        try:
            db_instance.client = AsyncIOMotorClient(mongo_uri)
            # Send a ping to confirm connection
            await db_instance.client.admin.command('ping')
            print("SYSTEM: MongoDB Connection Verified (Ping Successful).")
        except Exception as e:
            print(f"CRITICAL: Could not connect to MongoDB. Error: {e}")
            return None

    # Return the specific database named 'tars_db'
    return db_instance.client['tars_db']

async def close_database():
    """Closes the database connection."""
    if db_instance.client:
        db_instance.client.close()
        db_instance.client = None
        print("SYSTEM: MongoDB Connection Closed.")