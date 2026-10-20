import unittest
import time
import uuid
from datetime import datetime, timedelta

from core.database.mongo_manager import mongo_db
from core.database.repositories.attendance_repository import (
    extract_and_validate_id,
    PHT_TZ,
)


class TestAttendanceSystem(unittest.IsolatedAsyncioTestCase):
    """
    Unit & integration tests for the QR-Coded Attendance System (FM-LIBS-009):
    1. Raw and prefixed QR code payload validation.
    2. Malformed identifier rejection.
    3. Arrival (Time-In) and Departure (Time-Out) toggle with exact duration (48m).
    4. Anti-bounce cooldown protection against continuous scanner double-triggering.
    5. Live occupancy counters and program distribution aggregation.
    6. Form FM-LIBS-009 CSV logbook formatting.
    """

    async def asyncSetUp(self):
        await mongo_db.initialize()
        self.repo = mongo_db.attendance
        self.test_user_ids = []
        self.test_log_ids = []

        await mongo_db.db['users'].delete_many({
            "$or": [
                {"username": {"$in": ["mares_cs", "juan_it"]}},
                {"institutional_id": {"$in": ["23-00128", "26-00001"]}},
            ]
        })

        # Seed test user 1 (Mares Susette - BSCS)
        self.u1_id = f"test_att_user_{uuid.uuid4().hex[:6]}"
        self.test_user_ids.append(self.u1_id)
        await mongo_db.db['users'].insert_one({
            "id": self.u1_id,
            "username": "mares_cs",
            "name": "Mares Susette V. Somogba",
            "full_name": "Mares Susette V. Somogba",
            "role": "student",
            "program": "BSCS",
            "department": "BSCS",
            "institutional_id": "23-00128",
            "student_id": "23-00128",
        })

        # Seed test user 2 (Juan Dela Cruz - BSIT)
        self.u2_id = f"test_att_user_{uuid.uuid4().hex[:6]}"
        self.test_user_ids.append(self.u2_id)
        await mongo_db.db['users'].insert_one({
            "id": self.u2_id,
            "username": "juan_it",
            "name": "Juan Dela Cruz",
            "full_name": "Juan Dela Cruz",
            "role": "student",
            "program": "BSIT",
            "department": "BSIT",
            "institutional_id": "26-00001",
            "student_id": "26-00001",
        })

    async def asyncTearDown(self):
        if mongo_db.db is not None:
            if self.test_user_ids:
                await mongo_db.db['users'].delete_many({"id": {"$in": self.test_user_ids}})
            # Clean up attendance logs created for test institutional IDs
            await mongo_db.db['attendance_logs'].delete_many({
                "institutional_id": {"$in": ["23-00128", "26-00001"]}
            })

    def test_extract_and_validate_id_supports_raw_and_prefixed_qr(self):
        """Verifies parsing of raw '23-00128' and prefixed 'LIBRE-ID:23-00128' QR payloads."""
        self.assertEqual(extract_and_validate_id("23-00128"), "23-00128")
        self.assertEqual(extract_and_validate_id("LIBRE-ID:23-00128"), "23-00128")
        self.assertEqual(extract_and_validate_id("  libre-id:26-00001 "), "26-00001")
        self.assertEqual(extract_and_validate_id("99-99999"), "99-99999")

    def test_extract_and_validate_id_rejects_malformed_inputs(self):
        """Rejects malformed, non-numeric, or missing-hyphen identifiers."""
        bad_payloads = [
            "",
            "   ",
            "2024-3903E",
            "FAC-2024-001",
            "23-00000",
            "23-12A45",
            "696969",
            "2600001",
            "26-0001",
            "26-000001",
            None
        ]
        for bad in bad_payloads:
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    extract_and_validate_id(bad)

    async def test_time_in_and_time_out_toggle_calculates_exact_duration(self):
        """
        Tests complete Arrival and Departure cycle:
        1. First scan -> Time-In (Status: Checked In, Currently Inside: 1)
        2. Second scan 48 mins later -> Time-Out (Status: Checked Out, Duration: 48m, Currently Inside: 0)
        """
        t0 = time.time()
        t_48m_later = t0 + (48 * 60)

        # 1. Arrival (Time-In)
        res_in = await self.repo.record_scan(
            identifier="LIBRE-ID:23-00128",
            purpose="Research / Thesis",
            now_override=t0,
            cooldown_seconds=5
        )
        self.assertTrue(res_in.get("success"))
        self.assertEqual(res_in.get("action"), "checkin")
        self.assertEqual(res_in["entry"]["status"], "Checked In")
        self.assertEqual(res_in["entry"]["program"], "BSCS")
        self.assertEqual(res_in["entry"]["purpose"], "Research / Thesis")

        # Live metrics while inside
        metrics_mid = await self.repo.get_live_metrics()
        self.assertGreaterEqual(metrics_mid["visitors_today"], 1)
        self.assertGreaterEqual(metrics_mid["currently_inside"], 1)

        # 2. Departure (Time-Out) 48 minutes later
        res_out = await self.repo.record_scan(
            identifier="23-00128",
            now_override=t_48m_later,
            cooldown_seconds=5
        )
        self.assertTrue(res_out.get("success"))
        self.assertEqual(res_out.get("action"), "checkout")
        self.assertEqual(res_out["entry"]["status"], "Checked Out")
        self.assertEqual(res_out["duration_minutes"], 48)
        self.assertIn("Visit logged: 48m", res_out["message"])

        # Live metrics after departure
        metrics_after = await self.repo.get_live_metrics()
        self.assertGreaterEqual(metrics_after["completed_visits"], 1)
        self.assertGreaterEqual(metrics_after["avg_duration_minutes"], 1.0)

    async def test_double_scan_within_cooldown_window_is_ignored(self):
        """
        Verifies that rapid successive scans (e.g. 2s apart from continuous webcam)
        trigger the anti-bounce cooldown guard instead of prematurely checking the student out.
        """
        t0 = time.time()
        t_bounce = t0 + 2  # 2 seconds later (within 5s cooldown)

        # 1. Check-In
        first = await self.repo.record_scan(
            identifier="23-00128",
            now_override=t0,
            cooldown_seconds=5
        )
        self.assertEqual(first.get("action"), "checkin")

        # 2. Duplicate scan 2s later -> must return cooldown and preserve Checked In
        second = await self.repo.record_scan(
            identifier="23-00128",
            now_override=t_bounce,
            cooldown_seconds=5
        )
        self.assertEqual(second.get("action"), "cooldown")
        self.assertEqual(second.get("status"), "Checked In")
        self.assertIn("Already checked in", second["message"])

    async def test_export_fm_libs_009_csv_format(self):
        """Verifies institutional Form FM-LIBS-009 CSV logbook generation."""
        now = time.time()
        t_in = now - 120
        t_out = now - 60

        # Record check-in and checkout for 23-00128
        await self.repo.record_scan("23-00128", purpose="Study / Review", now_override=t_in, cooldown_seconds=0)
        await self.repo.record_scan("23-00128", now_override=t_out, cooldown_seconds=0)

        # Record check-in for 26-00001
        await self.repo.record_scan("26-00001", purpose="E-Library / Digital OPAC", now_override=t_in, cooldown_seconds=0)

        csv_text = await self.repo.export_fm_libs_009_csv()
        self.assertIn("NORTH EASTERN MINDANAO STATE UNIVERSITY", csv_text)
        self.assertIn("FM-LIBS-009", csv_text)
        self.assertIn("23-00128", csv_text)
        self.assertIn("Mares Susette V. Somogba", csv_text)
        self.assertIn("Checked Out", csv_text)
        self.assertIn("26-00001", csv_text)
        self.assertIn("Checked In", csv_text)


if __name__ == '__main__':
    unittest.main()
