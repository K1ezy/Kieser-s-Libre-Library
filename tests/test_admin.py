"""
Unit tests for Admin Console and ObjectId JSON serialization resilience.
"""

import unittest
from bson import ObjectId
from core.database.repositories.base_repository import BaseRepository, sanitize_mongo_doc
import nicegui.json.orjson_wrapper as nicegui_json


class TestObjectIdSerialization(unittest.TestCase):
    """Verifies that BSON ObjectId fields never crash JSON serialization."""

    def test_sanitize_mongo_doc_converts_objectid(self):
        """sanitize_mongo_doc recursively turns ObjectId instances into str."""
        raw_doc = {
            "_id": ObjectId(),
            "username": "admin",
            "nested": {
                "user_oid": ObjectId(),
                "tags": ["admin", ObjectId()]
            }
        }
        clean = sanitize_mongo_doc(raw_doc)
        self.assertIsInstance(clean["_id"], str)
        self.assertIsInstance(clean["nested"]["user_oid"], str)
        self.assertIsInstance(clean["nested"]["tags"][1], str)

    def test_base_repository_clean_helpers(self):
        """BaseRepository clean_doc and clean_docs return sanitized data."""
        doc = {"_id": ObjectId(), "name": "Test"}
        cleaned = BaseRepository.clean_doc(doc)
        self.assertIsInstance(cleaned["_id"], str)

        docs = [{"_id": ObjectId(), "name": "Item 1"}, {"_id": ObjectId(), "name": "Item 2"}]
        cleaned_list = BaseRepository.clean_docs(docs)
        self.assertEqual(len(cleaned_list), 2)
        self.assertIsInstance(cleaned_list[0]["_id"], str)
        self.assertIsInstance(cleaned_list[1]["_id"], str)

    def test_nicegui_json_serializer_handles_objectid(self):
        """NiceGUI orjson dumps serializes dicts with ObjectId without raising TypeError."""
        # Ensure our patched converter handles ObjectId
        import main  # Trigger serializer registration
        sample = {"_id": ObjectId(), "title": "Libre Library Admin"}
        serialized = nicegui_json.dumps(sample)
        self.assertIn('"_id":', serialized)
        self.assertIsInstance(serialized, str)


if __name__ == '__main__':
    unittest.main()
