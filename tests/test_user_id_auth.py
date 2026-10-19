import unittest
import asyncio
import time
import bcrypt

from core.database.mongo_manager import mongo_db
from core.database.repositories.user_repository import (
    UserRepository,
    validate_user_id,
    is_attempted_institutional_id,
)


class TestUserIdValidation(unittest.TestCase):
    """Verifies strict YY-NNNNN format validation and attempted-ID heuristic detection."""

    def test_validate_user_id_accepts_valid_formats(self):
        valid_ids = ["23-00001", "23-00127", "24-00001", "26-00001", "99-99999"]
        for vid in valid_ids:
            with self.subTest(vid=vid):
                self.assertTrue(validate_user_id(vid), f"Expected {vid} to be valid.")

    def test_validate_user_id_rejects_invalid_formats(self):
        invalid_ids = [
            "23-00000",       # Zero sequence is invalid (must be 00001-99999)
            "2024-3903E",     # Contains letter and 4-digit year
            "FAC-2024-001",   # Prefix letters and multiple hyphens
            "LIB-2024-001",   # Prefix letters
            "ADM-ROOT-001",   # Alpha codes
            "26-0012A",       # Letter in sequence
            "2600001",        # Missing hyphen
            "26-0001",        # Only 4 sequence digits
            "26-000001",      # 6 sequence digits
            "2026-00001",     # 4-digit year
            "26 -00001",      # Contains space
            "26_00001",       # Underscore instead of hyphen
            "696969",         # Pure numbers without hyphen
            "1234",           # Pure numbers
            "",               # Empty string
            None,             # None value
            12345,            # Non-string integer
        ]
        for inv_id in invalid_ids:
            with self.subTest(inv_id=inv_id):
                self.assertFalse(validate_user_id(inv_id), f"Expected {inv_id} to be rejected.")

    def test_is_attempted_institutional_id_heuristic(self):
        # Attempted IDs: should trigger ID validation checks
        attempted = [
            "23-00130",
            "26-00001",
            "26-0012A",
            "FAC-2024-001",
            "2024-3903E",
            "696969",
            "1234",
            "2300001"
        ]
        for att in attempted:
            with self.subTest(att=att):
                self.assertTrue(is_attempted_institutional_id(att), f"Expected {att} to be flagged as attempted ID.")

        # Standard usernames or emails: should NOT trigger ID format validation
        non_attempted = [
            "juandelacruz",
            "student_alpha",
            "admin",
            "test_faculty",
            "user@university.edu",
            "student.2023@lib.edu",
            "",
            None
        ]
        for non_att in non_attempted:
            with self.subTest(non_att=non_att):
                self.assertFalse(is_attempted_institutional_id(non_att), f"Expected {non_att} NOT to be flagged as attempted ID.")


class TestUserIdAuthIntegration(unittest.IsolatedAsyncioTestCase):
    """
    Integration tests with active MongoDB for sequence seeding, annual rollover,
    high-concurrency ID assignment, password verification, and legacy account safety.
    """

    async def asyncSetUp(self):
        await mongo_db.initialize()
        self.repo = mongo_db.users
        self.created_test_user_ids = []

    async def asyncTearDown(self):
        if self.created_test_user_ids and mongo_db.db is not None:
            await mongo_db.db['users'].delete_many(
                {"id": {"$in": self.created_test_user_ids}}
            )

    async def test_sequence_seeding_and_annual_rollover(self):
        """Verifies annual counter seeding from existing accounts and clean year rollover."""
        # 1. 2023 sequence: seed counter to 127 (matching existing 23-00127), so next ID is 23-00128
        await mongo_db.db['counters'].update_one(
            {"_id": "user_seq_23"},
            {"$set": {"year": "23", "seq": 127}},
            upsert=True
        )
        next_2023_id = await self.repo.generate_next_user_id(year=2023)
        self.assertEqual(next_2023_id, "23-00128")

        # 2. Year 2027 rollover: begins cleanly at 27-00001 and advances to 27-00002
        await mongo_db.db['counters'].delete_one({"_id": "user_seq_27"})
        first_2027_id = await self.repo.generate_next_user_id(year=2027)
        second_2027_id = await self.repo.generate_next_user_id(year=2027)
        self.assertEqual(first_2027_id, "27-00001")
        self.assertEqual(second_2027_id, "27-00002")

    async def test_concurrent_user_registrations_produce_unique_contiguous_ids(self):
        """
        Simulates 25 simultaneous user registrations using asyncio.gather.
        Guarantees that all assigned IDs are unique, valid, and contiguous.
        """
        num_concurrent = 25
        target_year = 2028  # Use an isolated test year to guarantee starting sequence
        await mongo_db.db['counters'].delete_one({"_id": "user_seq_28"})

        async def register_worker(idx: int):
            uname = f"test_conc_{int(time.time()*1000)}_{idx}"
            user = await self.repo.create_user(
                full_name=f"Concurrent Test User {idx}",
                username=uname,
                email=f"conc_{idx}_{int(time.time()*1000)}@libre.edu",
                password="SecurePassword123!",
                role="student",
                department="Computer Science",
                registration_year=target_year
            )
            return user

        created_users = await asyncio.gather(*(register_worker(i) for i in range(1, num_concurrent + 1)))

        for u in created_users:
            self.created_test_user_ids.append(u["id"])

        assigned_ids = [u["institutional_id"] for u in created_users]
        self.assertEqual(len(set(assigned_ids)), num_concurrent, "All concurrent IDs must be unique!")

        # Verify contiguous sequence for target year 2028
        sorted_ids = sorted(assigned_ids)
        expected_ids = [f"28-{i:05d}" for i in range(1, num_concurrent + 1)]
        self.assertEqual(sorted_ids, expected_ids, "Assigned IDs must be contiguous!")

    async def test_signin_with_valid_id_and_password_security(self):
        """Tests that a valid ID + right password succeeds, wrong password fails, and malformed ID is rejected."""
        test_uname = f"test_auth_{int(time.time()*1000)}"
        test_email = f"auth_{int(time.time()*1000)}@libre.edu"
        pwd = "CorrectBatteryHorse42!"

        user = await self.repo.create_user(
            full_name="Authentication Test User",
            username=test_uname,
            email=test_email,
            password=pwd,
            registration_year=2026
        )
        self.created_test_user_ids.append(user["id"])
        assigned_id = user["institutional_id"]

        self.assertTrue(validate_user_id(assigned_id))

        # 1. Valid ID + correct password succeeds
        auth_success = await self.repo.authenticate_user(assigned_id, pwd)
        self.assertEqual(auth_success["email"], test_email)
        self.assertEqual(auth_success["institutional_id"], assigned_id)

        # 2. Valid ID + wrong password fails
        with self.assertRaises(ValueError) as ctx_wrong:
            await self.repo.authenticate_user(assigned_id, "WrongPassword999!")
        self.assertIn("Invalid credentials", str(ctx_wrong.exception))

        # 3. Malformed ID with letters is rejected with strict format error
        with self.assertRaises(ValueError) as ctx_fmt:
            await self.repo.authenticate_user("26-0001A", pwd)
        self.assertIn("Invalid ID format", str(ctx_fmt.exception))

    async def test_legacy_accounts_remain_accessible(self):
        """Verifies that legacy accounts with legacy IDs or None remain accessible via username or email."""
        # Create a mock legacy user with non-standard ID
        legacy_uname = f"legacy_alpha_{int(time.time()*1000)}"
        legacy_email = f"legacy_{int(time.time()*1000)}@libre.edu"
        hashed = bcrypt.hashpw(b"LegacySecret123!", bcrypt.gensalt()).decode("utf-8")
        legacy_id = f"mock-uuid-{int(time.time()*1000)}"
        legacy_inst_id = f"2024-LEGACY-{int(time.time()*1000)}"

        await mongo_db.db['users'].insert_one({
            "id": legacy_id,
            "username": legacy_uname,
            "email": legacy_email,
            "hashed_password": hashed,
            "role": "student",
            "institutional_id": legacy_inst_id,  # Legacy non-conforming format
            "student_id": legacy_inst_id,
            "type": "account"
        })
        self.created_test_user_ids.append(legacy_id)

        # 1. Sign in via username succeeds
        auth_by_uname = await self.repo.authenticate_user(legacy_uname, "LegacySecret123!")
        self.assertEqual(auth_by_uname["id"], legacy_id)

        # 2. Sign in via email succeeds
        auth_by_email = await self.repo.authenticate_user(legacy_email, "LegacySecret123!")
        self.assertEqual(auth_by_email["id"], legacy_id)

        # 3. Attempting to use the malformed legacy ID directly as an ID input triggers format validation error
        with self.assertRaises(ValueError) as ctx_legacy:
            await self.repo.authenticate_user(legacy_inst_id, "LegacySecret123!")
        self.assertIn("Invalid ID format", str(ctx_legacy.exception))


if __name__ == "__main__":
    unittest.main()
