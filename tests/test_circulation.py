import unittest
import asyncio
import time
import uuid

from core.database.mongo_manager import mongo_db


class TestCirculationSystem(unittest.IsolatedAsyncioTestCase):
    """
    Rigorously tests physical book borrowing, faculty 30-day loans and 10-book quotas,
    student 7-day loans and 3-book quotas, renewal policies, returns, and circulation stats.
    """

    async def asyncSetUp(self):
        await mongo_db.initialize()
        self.circ = mongo_db.circulation
        self.test_user_ids = []
        self.test_book_ids = []
        self.test_loan_ids = []

        # Create dummy faculty user
        self.fac_id = f"test_fac_{uuid.uuid4().hex[:6]}"
        self.test_user_ids.append(self.fac_id)
        await mongo_db.db['users'].insert_one({
            "id": self.fac_id,
            "username": self.fac_id,
            "name": "Dr. Alan Turing",
            "role": "faculty",
            "institutional_id": "23-00101",
            "department": "Computer Science",
        })

        # Create dummy student user
        self.stud_id = f"test_stud_{uuid.uuid4().hex[:6]}"
        self.test_user_ids.append(self.stud_id)
        await mongo_db.db['users'].insert_one({
            "id": self.stud_id,
            "username": self.stud_id,
            "name": "Ada Lovelace",
            "role": "student",
            "institutional_id": "24-00202",
            "program": "BSCS",
        })

        # Create a pool of test books
        for i in range(12):
            bid = f"test_circ_book_{uuid.uuid4().hex[:6]}"
            self.test_book_ids.append(bid)
            await mongo_db.db['books'].insert_one({
                "id": bid,
                "title": f"Circulation Test Book {i+1}",
                "display_author": f"Author {i+1}",
                "file_type": "epub",
            })

    async def asyncTearDown(self):
        if mongo_db.db is not None:
            if self.test_user_ids:
                await mongo_db.db['users'].delete_many({"id": {"$in": self.test_user_ids}})
            if self.test_book_ids:
                await mongo_db.db['books'].delete_many({"id": {"$in": self.test_book_ids}})
            if self.test_loan_ids:
                await mongo_db.db['book_loans'].delete_many({"$or": [
                    {"id": {"$in": self.test_loan_ids}},
                    {"user_id": {"$in": self.test_user_ids}}
                ]})

    async def test_faculty_borrow_terms_and_quota(self):
        """Verifies faculty get 30-day loans and can borrow up to 10 books."""
        # 1. Borrow first book
        res = await self.circ.borrow_book(user_id=self.fac_id, book_id=self.test_book_ids[0])
        self.assertTrue(res.get("success"), f"Faculty borrow failed: {res.get('error')}")
        loan = res.get("loan")
        self.test_loan_ids.append(loan["id"])

        self.assertEqual(loan["borrower_role"], "faculty")
        self.assertEqual(loan["loan_days"], 30)
        self.assertEqual(loan["status"], "active")
        # Verify due date is ~30 days in the future
        expected_due_approx = time.time() + (30 * 86400)
        self.assertAlmostEqual(loan["due_date"], expected_due_approx, delta=10)

        # 2. Fill quota up to 10 books
        for i in range(1, 10):
            r = await self.circ.borrow_book(user_id=self.fac_id, book_id=self.test_book_ids[i])
            self.assertTrue(r.get("success"), f"Faculty loan {i+1} failed: {r.get('error')}")
            self.test_loan_ids.append(r["loan"]["id"])

        # 3. 11th book borrow must fail (Quota exceeded)
        res_exceeded = await self.circ.borrow_book(user_id=self.fac_id, book_id=self.test_book_ids[10])
        self.assertFalse(res_exceeded.get("success"))
        self.assertIn("Borrowing quota exceeded", res_exceeded.get("error", ""))

    async def test_student_borrow_terms_and_quota(self):
        """Verifies students get 7-day loans and max quota of 3 books."""
        # 1. First loan
        res = await self.circ.borrow_book(user_id=self.stud_id, book_id=self.test_book_ids[0])
        self.assertTrue(res.get("success"))
        loan = res.get("loan")
        self.test_loan_ids.append(loan["id"])

        self.assertEqual(loan["borrower_role"], "student")
        self.assertEqual(loan["loan_days"], 7)
        expected_due_approx = time.time() + (7 * 86400)
        self.assertAlmostEqual(loan["due_date"], expected_due_approx, delta=10)

        # 2. 2nd and 3rd loan
        for i in range(1, 3):
            r = await self.circ.borrow_book(user_id=self.stud_id, book_id=self.test_book_ids[i])
            self.assertTrue(r.get("success"))
            self.test_loan_ids.append(r["loan"]["id"])

        # 3. 4th loan must fail
        res_exceeded = await self.circ.borrow_book(user_id=self.stud_id, book_id=self.test_book_ids[3])
        self.assertFalse(res_exceeded.get("success"))
        self.assertIn("Borrowing quota exceeded", res_exceeded.get("error", ""))

    async def test_duplicate_active_loan_prevention(self):
        """Verifies a user cannot borrow the exact same book twice while loan is active."""
        res1 = await self.circ.borrow_book(user_id=self.stud_id, book_id=self.test_book_ids[0])
        self.assertTrue(res1.get("success"))
        self.test_loan_ids.append(res1["loan"]["id"])

        # Attempt duplicate
        res2 = await self.circ.borrow_book(user_id=self.stud_id, book_id=self.test_book_ids[0])
        self.assertFalse(res2.get("success"))
        self.assertIn("already have an active loan", res2.get("error", ""))

    async def test_loan_renewal_lifecycle(self):
        """Verifies renewing loans extends due date and enforces 2 renewals max."""
        res = await self.circ.borrow_book(user_id=self.fac_id, book_id=self.test_book_ids[0])
        self.assertTrue(res.get("success"))
        loan = res["loan"]
        lid = loan["id"]
        self.test_loan_ids.append(lid)

        initial_due = loan["due_date"]

        # Renewal 1 (+15 days)
        r1 = await self.circ.renew_loan(lid, extension_days=15)
        self.assertTrue(r1.get("success"))
        self.assertEqual(r1["renewal_count"], 1)
        self.assertAlmostEqual(r1["new_due_date"], initial_due + (15 * 86400), delta=5)

        # Renewal 2 (+15 days)
        r2 = await self.circ.renew_loan(lid, extension_days=15)
        self.assertTrue(r2.get("success"))
        self.assertEqual(r2["renewal_count"], 2)

        # Renewal 3 must fail (Max 2 renewals)
        r3 = await self.circ.renew_loan(lid, extension_days=15)
        self.assertFalse(r3.get("success"))
        self.assertIn("Maximum renewals (2) reached", r3.get("error", ""))

    async def test_book_return_lifecycle(self):
        """Verifies returning a book transitions status and removes it from active list."""
        res = await self.circ.borrow_book(user_id=self.stud_id, book_id=self.test_book_ids[0])
        self.assertTrue(res.get("success"))
        lid = res["loan"]["id"]
        self.test_loan_ids.append(lid)

        # Active loans should have 1 item
        active_before = await self.circ.get_user_active_loans(self.stud_id)
        self.assertEqual(len(active_before), 1)

        # Return book
        ret_res = await self.circ.return_book(lid, notes="Returned in good condition")
        self.assertTrue(ret_res.get("success"))
        returned_loan = ret_res.get("loan")
        self.assertEqual(returned_loan["status"], "returned")
        self.assertIsNotNone(returned_loan["return_date"])

        # Active loans should now be 0
        active_after = await self.circ.get_user_active_loans(self.stud_id)
        self.assertEqual(len(active_after), 0)

        # Complete loan history should still have the returned loan
        history = await self.circ.get_user_loan_history(self.stud_id)
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["status"], "returned")

        # Returning already returned book should fail
        ret_again = await self.circ.return_book(lid)
        self.assertFalse(ret_again.get("success"))
        self.assertIn("already been returned", ret_again.get("error", ""))

    async def test_circulation_stats(self):
        """Verifies operational statistics for circulation desk."""
        res_fac = await self.circ.borrow_book(user_id=self.fac_id, book_id=self.test_book_ids[0])
        res_stud = await self.circ.borrow_book(user_id=self.stud_id, book_id=self.test_book_ids[1])
        self.test_loan_ids.extend([res_fac["loan"]["id"], res_stud["loan"]["id"]])

        stats = await self.circ.get_circulation_stats()
        self.assertGreaterEqual(stats["active_loans"], 2)
        self.assertGreaterEqual(stats["faculty_loans"], 1)
        self.assertGreaterEqual(stats["student_loans"], 1)

        # Return one and verify returned count increases
        await self.circ.return_book(res_fac["loan"]["id"])
        stats2 = await self.circ.get_circulation_stats()
        self.assertGreaterEqual(stats2["returned_loans"], 1)


if __name__ == '__main__':
    unittest.main()
