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
            "department": "College of Computing Studies",
            "year_level": "3rd Year",
            "address": "Brgy. Telaje, Tandag City, Surigao del Sur",
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
            "year_level": "1st Year",
            "address": "NEMSU Tandag Campus",
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
            # Clean up any test book loans
            await mongo_db.db['book_loans'].delete_many({
                "$or": [
                    {"user_id": {"$in": self.test_user_ids}},
                    {"borrower_id": {"$in": ["23-00128", "26-00001"]}}
                ]
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

    async def test_record_scan_returns_full_id_dossier_with_loan_status(self):
        """
        Verifies that scanning an institutional QR code returns the comprehensive ID dossier:
        - Full Name
        - Institutional ID
        - Department / College
        - Year Level
        - Residential Address
        - Role
        - Active & Overdue Loan metrics from circulation
        """
        now = time.time()
        # Seed an active loan and an overdue loan for user 1 (23-00128)
        await mongo_db.db['book_loans'].insert_many([
            {
                "id": "loan_active_test_1",
                "borrower_id": "23-00128",
                "user_id": self.u1_id,
                "status": "active",
                "due_date": now + 86400 * 3,  # Due in 3 days
            },
            {
                "id": "loan_overdue_test_2",
                "borrower_id": "23-00128",
                "user_id": self.u1_id,
                "status": "overdue",
                "due_date": now - 86400 * 2,  # Overdue by 2 days
            }
        ])

        # Execute scan
        res = await self.repo.record_scan(
            identifier="LIBRE-ID:23-00128",
            purpose="Circulation / Book Borrowing",
            now_override=now,
            cooldown_seconds=0
        )

        self.assertTrue(res.get("success"))
        entry = res.get("entry", {})

        # Verify full attendee dossier fields
        self.assertEqual(entry.get("name"), "Mares Susette V. Somogba")
        self.assertEqual(entry.get("institutional_id"), "23-00128")
        self.assertEqual(entry.get("department"), "College of Computing Studies")
        self.assertEqual(entry.get("year_level"), "3rd Year")
        self.assertEqual(entry.get("address"), "Brgy. Telaje, Tandag City, Surigao del Sur")
        self.assertEqual(entry.get("role"), "Student")
        self.assertEqual(entry.get("active_loans_count"), 2)
        self.assertEqual(entry.get("overdue_loans_count"), 1)

    async def test_user_profile_address_persistence(self):
        """
        Verifies that user profile loads and updates the address field
        with graceful fallback to 'NEMSU Tandag Campus'.
        """
        user_repo = mongo_db.users

        # 1. Fetch u1 profile (has explicit address)
        p1 = await user_repo.get_user_profile(self.u1_id)
        self.assertIsNotNone(p1)
        self.assertEqual(p1.get("address"), "Brgy. Telaje, Tandag City, Surigao del Sur")

        # 2. Update address
        updated = await user_repo.update_user_profile(
            user_id=self.u1_id,
            name=p1.get("name", "Mares Susette V. Somogba"),
            bio=p1.get("bio", ""),
            address="Purok 4, Dagocdoc, Tandag City"
        )
        self.assertTrue(updated)

        p1_after = await user_repo.get_user_profile(self.u1_id)
        self.assertEqual(p1_after.get("address"), "Purok 4, Dagocdoc, Tandag City")

        # 3. Create a temporary user without address to verify default fallback
        fallback_uid = f"fallback_{uuid.uuid4().hex[:6]}"
        self.test_user_ids.append(fallback_uid)
        await mongo_db.db['users'].insert_one({
            "id": fallback_uid,
            "username": "fallback_user",
            "name": "Fallback Test",
        })
        p_fallback = await user_repo.get_user_profile(fallback_uid)
        self.assertEqual(p_fallback.get("address"), "NEMSU Tandag Campus")

    async def test_realtime_event_bus_broadcasts_to_attendee(self):
        """
        Verifies that when a librarian or admin scans an attendee's QR code,
        the event is broadcast immediately to the attendee's active subscriber.
        """
        from core.events import attendance_event_bus

        received_events = []

        def attendee_callback(evt):
            received_events.append(evt)

        # Attendee subscribes on their device
        unsub = attendance_event_bus.subscribe("23-00128", attendee_callback)
        try:
            now = time.time()
            # Librarian scans attendee QR
            res_in = await self.repo.record_scan(
                identifier="LIBRE-ID:23-00128",
                purpose="Study / Review",
                now_override=now,
                cooldown_seconds=0
            )
            self.assertTrue(res_in.get("success"))
            self.assertEqual(len(received_events), 1)
            self.assertEqual(received_events[0]["action"], "checkin")
            self.assertEqual(received_events[0]["entry"]["name"], "Mares Susette V. Somogba")

            # Librarian scans attendee out 30m later
            res_out = await self.repo.record_scan(
                identifier="23-00128",
                now_override=now + 1800,
                cooldown_seconds=0
            )
            self.assertTrue(res_out.get("success"))
            self.assertEqual(len(received_events), 2)
            self.assertEqual(received_events[1]["action"], "checkout")
            self.assertEqual(received_events[1]["duration_minutes"], 30)
        finally:
            unsub()

    async def test_get_user_today_attendance_summary(self):
        """
        Verifies that get_user_today_attendance accurately returns attendee's
        real-time status, active check-in record, and visit history.
        """
        now = time.time()
        # 1. Before any scan today
        att_before = await self.repo.get_user_today_attendance(identifier="26-00001")
        self.assertFalse(att_before["is_inside"])
        self.assertEqual(att_before["status"], "Not Visited Today")

        # 2. Check-in
        await self.repo.record_scan("26-00001", purpose="Research / Thesis", now_override=now, cooldown_seconds=0)
        att_during = await self.repo.get_user_today_attendance(identifier="26-00001")
        self.assertTrue(att_during["is_inside"])
        self.assertEqual(att_during["status"], "Checked In")
        self.assertIsNotNone(att_during["active_entry"])
        self.assertEqual(att_during["active_entry"]["purpose"], "Research / Thesis")

        # 3. Check-out 45 minutes later
        await self.repo.record_scan("26-00001", now_override=now + 2700, cooldown_seconds=0)
        att_after = await self.repo.get_user_today_attendance(identifier="26-00001")
        self.assertFalse(att_after["is_inside"])
        self.assertEqual(att_after["status"], "Checked Out")
        self.assertIsNone(att_after["active_entry"])
        self.assertEqual(len(att_after["today_visits"]), 1)
        self.assertEqual(att_after["total_duration_today_minutes"], 45)


    async def test_overnight_session_lazy_close_and_morning_checkin(self):
        """
        Flaw #1 Remediation Test:
        Student leaves Monday at 4:30 PM without scanning out.
        Student arrives Tuesday at 8:30 AM (18.5h later).
        System must lazy-close Monday's unclosed session as Expired,
        and cleanly CHECK IN the student for Tuesday.
        """
        now_dt = datetime.now(PHT_TZ)
        today_midnight = datetime.combine(now_dt.date(), datetime.min.time(), tzinfo=PHT_TZ)
        yesterday_ts = today_midnight.timestamp() - (16 * 3600)  # Yesterday 8:00 AM PHT
        today_morning_ts = today_midnight.timestamp() + (8.5 * 3600)  # Today 8:30 AM PHT

        # 1. Insert unclosed session from yesterday
        yesterday_session_id = f"stale_log_{uuid.uuid4().hex[:6]}"
        await mongo_db.db['attendance_logs'].insert_one({
            "id": yesterday_session_id,
            "institutional_id": "23-00128",
            "name": "Mares Susette V. Somogba",
            "program": "BSCS",
            "purpose": "Study / Review",
            "status": "Checked In",
            "timestamp_in": yesterday_ts,
            "time_in_str": "08:00 AM",
            "timestamp_out": None,
            "time_out_str": "-",
            "duration_minutes": None,
        })

        # 2. Student scans QR code this morning at 8:30 AM
        res = await self.repo.record_scan(
            identifier="23-00128",
            purpose="Study / Review",
            now_override=today_morning_ts,
            cooldown_seconds=15,
        )

        self.assertTrue(res.get("success"))
        # Must be CHECK-IN, NOT check-out!
        self.assertEqual(res.get("action"), "checkin")
        self.assertIn("Welcome", res.get("message"))

        # 3. Verify yesterday's session was lazy-closed as Expired (No Checkout)
        stale_doc = await mongo_db.db['attendance_logs'].find_one({"id": yesterday_session_id})
        self.assertEqual(stale_doc["status"], "Expired (No Checkout)")
        self.assertEqual(stale_doc["time_out_str"], "Auto-Closed")
        self.assertIsNone(stale_doc["duration_minutes"])

    async def test_symmetrical_cooldown_post_checkout_bounce(self):
        """
        Flaw #2 Remediation Test:
        User checks out at t=3600s.
        A camera linger or double-trigger occurs at t=3603s (3s later).
        System must trigger COOLDOWN and NOT re-check the user in.
        """
        t_in = 1700000000.0
        t_out = t_in + 3600.0  # 1 hour later
        t_linger = t_out + 3.0  # 3 seconds later

        # Check-In
        res_in = await self.repo.record_scan(
            identifier="23-00128",
            purpose="Study / Review",
            now_override=t_in,
            cooldown_seconds=15,
        )
        self.assertEqual(res_in.get("action"), "checkin")

        # Check-Out
        res_out = await self.repo.record_scan(
            identifier="23-00128",
            now_override=t_out,
            cooldown_seconds=15,
        )
        self.assertEqual(res_out.get("action"), "checkout")

        # Camera linger bounce 3 seconds later
        res_bounce = await self.repo.record_scan(
            identifier="23-00128",
            now_override=t_linger,
            cooldown_seconds=15,
        )
        self.assertTrue(res_bounce.get("success"))
        self.assertEqual(res_bounce.get("action"), "cooldown")
        self.assertIn("Already checked out 3s ago", res_bounce.get("message"))

        # Verify no open session exists
        active = await mongo_db.db['attendance_logs'].find_one({
            "institutional_id": "23-00128",
            "status": "Checked In",
        })
        self.assertIsNone(active)

    async def test_safe_metadata_backfill_preventing_corruption(self):
        """
        Flaw #3 Remediation Test:
        Non-institutional IDs (e.g., email or username) must NEVER backfill
        institutional_id or student_id.
        Faculty accounts must NEVER have student_id backfilled.
        """
        raw_email = "teststudent@campus.edu.ph"
        student_uid = f"user_test_backfill_{uuid.uuid4().hex[:6]}"
        self.test_user_ids.append(student_uid)
        await mongo_db.db['users'].insert_one({
            "id": student_uid,
            "username": "test_student_clean",
            "email": raw_email,
            "name": "Test Backfill Student",
            "role": "student",
            "institutional_id": None,
            "student_id": None,
        })

        # Manual lookup / scan with email
        res_email = await self.repo.record_scan(identifier=raw_email, cooldown_seconds=0)
        self.assertTrue(res_email.get("success"))

        user_doc = await mongo_db.db['users'].find_one({"id": student_uid})
        # institutional_id and student_id must NOT be corrupted with the email address
        self.assertIsNone(user_doc.get("institutional_id"))
        self.assertIsNone(user_doc.get("student_id"))

        # Valid institutional ID format: 23-99991
        res_valid = await self.repo.record_scan(
            identifier="23-99991",
            user_id=student_uid,
            cooldown_seconds=0,
        )
        user_updated = await mongo_db.db['users'].find_one({"id": student_uid})
        self.assertEqual(user_updated.get("institutional_id"), "23-99991")
        self.assertEqual(user_updated.get("student_id"), "23-99991")

        # Faculty account backfill test: should NOT populate student_id
        faculty_uid = f"user_fac_backfill_{uuid.uuid4().hex[:6]}"
        self.test_user_ids.append(faculty_uid)
        await mongo_db.db['users'].insert_one({
            "id": faculty_uid,
            "username": "dr_leandra",
            "name": "Dr. Leandra",
            "role": "faculty",
            "institutional_id": None,
            "student_id": None,
        })
        await self.repo.record_scan(
            identifier="23-99992",
            user_id=faculty_uid,
            cooldown_seconds=0,
        )
        faculty_doc = await mongo_db.db['users'].find_one({"id": faculty_uid})
        self.assertEqual(faculty_doc.get("institutional_id"), "23-99992")
        self.assertIsNone(faculty_doc.get("student_id"))

    async def test_dynamic_embedded_purpose_in_qr_payload(self):
        """
        Flaw #6 Remediation Test:
        Payload with embedded purpose (LIBRE-ID:23-00128|PURPOSE:Research / Thesis)
        must be extracted and applied without being corrupted by terminal defaults.
        """
        now = time.time()
        res = await self.repo.record_scan(
            identifier="LIBRE-ID:23-00128|PURPOSE:Research / Thesis",
            purpose="Study / Review",  # Terminal default
            now_override=now,
            cooldown_seconds=0,
        )
        self.assertTrue(res.get("success"))
        self.assertEqual(res.get("action"), "checkin")
        self.assertEqual(res["entry"]["purpose"], "Research / Thesis")

    async def test_circulation_standing_checked_on_checkout(self):
        """
        Flaw #7 Remediation Test:
        Circulation audit (overdue loans) must be queried and returned on
        both Check-In and Check-Out.
        """
        now = time.time()
        # Seed an overdue book loan
        loan_id = f"test_loan_{uuid.uuid4().hex[:6]}"
        await mongo_db.db['book_loans'].insert_one({
            "id": loan_id,
            "user_id": self.u1_id,
            "borrower_id": "23-00128",
            "book_title": "Database Systems Concepts",
            "status": "borrowed",
            "due_date": now - 86400,  # 1 day overdue
        })

        try:
            # Check-In
            res_in = await self.repo.record_scan("23-00128", now_override=now, cooldown_seconds=0)
            self.assertTrue(res_in.get("has_circulation_alert"))
            self.assertEqual(res_in["user_dossier"]["overdue_loans_count"], 1)

            # Check-Out 30m later
            res_out = await self.repo.record_scan("23-00128", now_override=now + 1800, cooldown_seconds=0)
            self.assertTrue(res_out.get("has_circulation_alert"))
            self.assertEqual(res_out["user_dossier"]["overdue_loans_count"], 1)
        finally:
            await mongo_db.db['book_loans'].delete_one({"id": loan_id})


if __name__ == '__main__':
    unittest.main()


