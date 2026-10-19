import unittest
from unittest.mock import MagicMock, AsyncMock
from core.utils.media_handler import (
    validate_image,
    save_user_avatar,
    save_user_cover,
    save_user_media,
    extract_upload_file,
    MAX_AVATAR_SIZE,
    MAX_COVER_SIZE
)
from core.database.repositories.user_repository import UserRepository


class TestMediaHandler(unittest.IsolatedAsyncioTestCase):
    """Tests file size, extension, and mime-type validation for avatar and cover uploads."""

    def test_validate_image_success(self):
        valid_bytes = b"fake-png-data" * 10
        valid, err, ext = validate_image("avatar.png", valid_bytes, MAX_AVATAR_SIZE, "image/png")
        self.assertTrue(valid)
        self.assertEqual(err, "")
        self.assertEqual(ext, ".png")

    def test_validate_image_size_exceeded(self):
        oversized_bytes = b"x" * (MAX_AVATAR_SIZE + 1024)
        valid, err, ext = validate_image("avatar.jpg", oversized_bytes, MAX_AVATAR_SIZE)
        self.assertFalse(valid)
        self.assertIn("exceeds maximum allowed size", err)

    def test_validate_image_invalid_extension(self):
        bytes_data = b"malicious content"
        valid, err, ext = validate_image("exploit.exe", bytes_data, MAX_AVATAR_SIZE)
        self.assertFalse(valid)
        self.assertIn("Unsupported file extension", err)

    def test_validate_image_invalid_mime(self):
        bytes_data = b"pdf content"
        valid, err, ext = validate_image("doc.pdf", bytes_data, MAX_AVATAR_SIZE, "application/pdf")
        self.assertFalse(valid)

    def test_save_user_media_avatar(self):
        small_bytes = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
        success, msg, url = save_user_media("test_u1", small_bytes, "photo.png", "avatar")
        self.assertTrue(success)
        self.assertIsNotNone(url)
        self.assertIn("/static/uploads/avatars/", url)

    def test_save_user_media_cover(self):
        small_bytes = b"\xff\xd8\xff" + b"\x00" * 100
        success, msg, url = save_user_media("test_u1", small_bytes, "banner.jpg", "cover")
        self.assertTrue(success)
        self.assertIsNotNone(url)
        self.assertIn("/static/uploads/covers/", url)

    async def test_extract_upload_file_nicegui_v2_upload_event(self):
        from types import SimpleNamespace
        # NiceGUI 2.x UploadEventArguments: has .file (FileUpload), does NOT have .content
        mock_file = SimpleNamespace(name="my_avatar.png", read=AsyncMock(return_value=b"binary-avatar-data"))
        mock_event = SimpleNamespace(file=mock_file)

        name, data = await extract_upload_file(mock_event)
        self.assertEqual(name, "my_avatar.png")
        self.assertEqual(data, b"binary-avatar-data")

    async def test_extract_upload_file_legacy_content_attribute(self):
        from types import SimpleNamespace
        # Legacy event: has .content, does NOT have .file
        mock_content = SimpleNamespace(read=MagicMock(return_value=b"legacy-content-bytes"))
        mock_event = SimpleNamespace(name="legacy.jpg", content=mock_content)

        name, data = await extract_upload_file(mock_event)
        self.assertEqual(name, "legacy.jpg")
        self.assertEqual(data, b"legacy-content-bytes")


class TestRBACIdentifierSystem(unittest.IsolatedAsyncioTestCase):
    """Tests multi-role registration, institutional ID metadata, and identifier queries."""

    async def test_get_user_by_identifier_supports_institutional_ids(self):
        repo = UserRepository()
        repo.db = MagicMock()
        mock_collection = MagicMock()
        repo.db.__getitem__.return_value = mock_collection

        # Mock find_one returning student user
        mock_user = {
            "id": "u-101",
            "type": "account",
            "username": "student_jane",
            "email": "jane@nemsu.edu.ph",
            "role": "student",
            "institutional_id": "24-08841",
            "student_id": "24-08841",
            "program": "BSCS",
            "year_level": "3rd Year",
            "avatar_url": "/static/uploads/avatars/u-101_avatar.png",
            "cover_url": "/static/uploads/covers/u-101_cover.jpg",
        }
        mock_collection.find_one = AsyncMock(return_value=mock_user)

        # Query by institutional ID
        result = await repo.get_user_by_identifier("24-08841")
        self.assertIsNotNone(result)
        self.assertEqual(result["username"], "student_jane")
        self.assertEqual(result["institutional_id"], "24-08841")

        # Verify query had $or clause checking institutional fields
        call_args = mock_collection.find_one.call_args[0][0]
        self.assertIn("$or", call_args)

    async def test_get_user_profile_returns_institutional_fields(self):
        repo = UserRepository()
        repo.db = MagicMock()
        mock_collection = MagicMock()
        repo.db.__getitem__.return_value = mock_collection

        mock_profile = {
            "id": "fac-01",
            "type": "account",
            "username": "prof_alan",
            "name": "Prof. Alan Turing",
            "email": "alan@nemsu.edu.ph",
            "role": "faculty",
            "institutional_id": "FAC-2024-09",
            "department": "Computer Science & Engineering",
            "avatar_url": "/static/uploads/avatars/fac-01_avatar.png",
            "cover_url": "/static/uploads/covers/fac-01_cover.jpg",
            "created_at": 1700000000
        }
        mock_collection.find_one = AsyncMock(return_value=mock_profile)

        profile = await repo.get_user_profile(user_id="fac-01")
        self.assertEqual(profile["name"], "Prof. Alan Turing")
        self.assertEqual(profile["role"], "faculty")
        self.assertEqual(profile["institutional_id"], "FAC-2024-09")
        self.assertEqual(profile["department"], "Computer Science & Engineering")
        self.assertEqual(profile["avatar_url"], "/static/uploads/avatars/fac-01_avatar.png")
        self.assertEqual(profile["cover_url"], "/static/uploads/covers/fac-01_cover.jpg")

    async def test_update_user_media(self):
        repo = UserRepository()
        repo.db = MagicMock()
        mock_collection = MagicMock()
        repo.db.__getitem__.return_value = mock_collection
        mock_collection.update_one = AsyncMock(return_value=MagicMock(modified_count=1, matched_count=1))

        res = await repo.update_user_media("u-test", avatar_url="/new/avatar.png")
        self.assertTrue(res)
        called_update = mock_collection.update_one.call_args[0][1]
        self.assertEqual(called_update["$set"]["avatar_url"], "/new/avatar.png")


if __name__ == '__main__':
    unittest.main()
