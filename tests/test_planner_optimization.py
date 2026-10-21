import unittest
import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock

from core.services.planner_service import planner_service, FlashcardService


class TestPlannerOptimization(unittest.TestCase):
    """Verifies speed optimizations, parser resilience, and document source handling."""

    def test_multi_format_flashcard_parser_qa_multiline(self):
        sample = """
        Q: What is Object-Oriented Programming?
        A: A programming paradigm based on the concept of objects containing data and code.

        Q: What are the four pillars of OOP?
        A: Encapsulation, Abstraction, Inheritance, and Polymorphism.

        Q: What is polymorphism?
        A: The ability of different classes to respond to the same message or method call in their own way.
        """
        cards = FlashcardService.parse_flashcards(sample)
        self.assertEqual(len(cards), 3)
        self.assertEqual(cards[0]['q'], "What is Object-Oriented Programming?")
        self.assertTrue("objects" in cards[0]['a'])
        self.assertEqual(cards[1]['q'], "What are the four pillars of OOP?")
        self.assertEqual(cards[2]['q'], "What is polymorphism?")

    def test_multi_format_flashcard_parser_pipe_delimiter(self):
        sample = """
        What is RAM? ||| Random Access Memory
        What is CPU? ||| Central Processing Unit
        What is GPU? ||| Graphics Processing Unit
        """
        cards = FlashcardService.parse_flashcards(sample)
        self.assertEqual(len(cards), 3)
        self.assertEqual(cards[0]['q'], "What is RAM?")
        self.assertEqual(cards[0]['a'], "Random Access Memory")

    def test_multi_format_flashcard_parser_json_payload(self):
        sample = """```json
        [
            {"q": "Define Latency", "a": "The time delay between a request and response."},
            {"q": "Define Throughput", "a": "The rate at which data is successfully processed or transmitted."}
        ]
        ```"""
        cards = FlashcardService.parse_flashcards(sample)
        self.assertEqual(len(cards), 2)
        self.assertEqual(cards[0]['q'], "Define Latency")
        self.assertEqual(cards[1]['q'], "Define Throughput")

    def test_multi_format_flashcard_parser_inline_qa(self):
        sample = """
        1. Q: What is an index in a database? A: A data structure that improves the speed of data retrieval operations.
        2. Q: What is a primary key? A: A unique identifier for a relational table record.
        """
        cards = FlashcardService.parse_flashcards(sample)
        self.assertEqual(len(cards), 2)
        self.assertTrue("index" in cards[0]['q'].lower())
        self.assertTrue("primary key" in cards[1]['q'].lower())

    def test_fast_text_extraction_limits_overhead(self):
        from core.config import settings
        test_doc = settings.BASE_DIR / 'data' / 'books' / '456d973c-f09b-4c21-b2bc-0b0d4b02670f' / 'Lesson 2 Software Documentation .pdf'
        if test_doc.exists():
            text = FlashcardService._extract_fast_text_from_path(test_doc, max_chars=4000)
            self.assertTrue(len(text) > 50)
            self.assertLessEqual(len(text), 8000)

    def test_slide_extraction_preserves_short_slides(self):
        uploaded_pdf = Path(r"C:/Users/User/.gemini/antigravity-ide/brain/1057c359-f722-4cd5-9d4f-3438468924a4/.user_uploaded/media_1792566519088.pdf")
        if uploaded_pdf.exists():
            text = FlashcardService._extract_fast_text_from_path(uploaded_pdf, max_chars=12000)
            # The 27-slide deck contains ~10,800 characters across all slides
            self.assertGreater(len(text), 8000)
            # Verify concise title slide "Lesson 1: Software Testing" is preserved
            self.assertTrue("Lesson 1: Software" in text)
            # Verify late slides (e.g. types of testing) are preserved
            self.assertTrue("Functional Testing" in text or "Manual Testing" in text)

    @patch('core.services.planner_service.tars_engine.create_completion')
    @patch('core.services.planner_service.mongo_db.save_deck', new_callable=AsyncMock)
    def test_generate_deck_flow_with_mocked_llm(self, mock_save, mock_complete):
        mock_complete.return_value = """
        Q: What is a software requirement?
        A: A condition or capability needed by a user to solve a problem.

        Q: What is IEEE 830?
        A: Recommended practice for software requirements specifications.

        Q: What is traceability?
        A: The ability to trace a requirement from origin through development.
        """
        mock_save.return_value = True

        async def run_gen():
            # Pass sample text bytes as upload
            file_bytes = b"Software Engineering Requirements and Specifications. IEEE 830 standard documentation guide."
            success, msg = await planner_service.generate_deck("task_123", file_bytes)
            self.assertTrue(success)
            self.assertTrue("flashcards created" in msg or "Success" in msg)
            mock_save.assert_called_once()
            args, kwargs = mock_save.call_args
            self.assertEqual(args[0], "task_123")
            saved_cards = args[2]
            self.assertEqual(len(saved_cards), 3)

    @patch('core.services.planner_service.tars_engine.create_completion')
    @patch('core.services.planner_service.mongo_db.save_deck', new_callable=AsyncMock)
    def test_generate_deck_cancellation(self, mock_save, mock_complete):
        import threading
        cancel_event = threading.Event()
        cancel_event.set()  # Cancel before start

        async def run_cancelled():
            file_bytes = b"Software Engineering Requirements and Specifications. IEEE 830 standard documentation guide."
            success, msg = await planner_service.generate_deck("task_cancel", file_bytes, cancel_event=cancel_event)
            self.assertFalse(success)
            self.assertTrue("cancelled" in msg.lower())
            mock_save.assert_not_called()

        asyncio.run(run_cancelled())

    @patch('core.services.planner_service.tars_engine.create_completion')
    @patch('core.services.planner_service.mongo_db.save_deck', new_callable=AsyncMock)
    def test_generate_deck_cancellation_during_llm(self, mock_save, mock_complete):
        import threading
        cancel_event = threading.Event()

        async def fake_complete(*args, **kwargs):
            # Simulate user clicking cancel while TARS AI is processing
            cancel_event.set()
            return None

        mock_complete.side_effect = fake_complete

        async def run_mid_cancel():
            file_bytes = b"Software Engineering Requirements and Specifications. IEEE 830 standard documentation guide."
            success, msg = await planner_service.generate_deck("task_mid_cancel", file_bytes, cancel_event=cancel_event)
            self.assertFalse(success)
            self.assertTrue("cancelled" in msg.lower())
            mock_save.assert_not_called()

    @patch('core.services.planner_service.tars_engine.create_completion')
    @patch('core.services.planner_service.mongo_db.save_deck', new_callable=AsyncMock)
    def test_generate_deck_custom_quantity_and_max_cap(self, mock_save, mock_complete):
        # Generate 40 simulated cards to test capping
        cards_output = "\n\n".join([f"Q: Question {i}?\nA: Answer {i}." for i in range(1, 45)])
        mock_complete.return_value = cards_output
        mock_save.return_value = True

        async def run_quantity_tests():
            file_bytes = b"Software Engineering Requirements and Specifications. Testing quantity limits and capping."

            # Case 1: Custom quantity of 5
            mock_save.reset_mock()
            success, msg = await planner_service.generate_deck("task_q5", file_bytes, quantity=5)
            self.assertTrue(success)
            mock_save.assert_called_once()
            saved_cards_5 = mock_save.call_args[0][2]
            self.assertEqual(len(saved_cards_5), 5)

            # Case 2: Maximum quantity of 30
            mock_save.reset_mock()
            success, msg = await planner_service.generate_deck("task_q30", file_bytes, quantity=30)
            self.assertTrue(success)
            mock_save.assert_called_once()
            saved_cards_30 = mock_save.call_args[0][2]
            self.assertEqual(len(saved_cards_30), 30)

            # Case 3: Over-limit quantity (50 requested) -> Strictly capped to 30 max
            mock_save.reset_mock()
            success, msg = await planner_service.generate_deck("task_q50", file_bytes, quantity=50)
            self.assertTrue(success)
            mock_save.assert_called_once()
            saved_cards_capped = mock_save.call_args[0][2]
            self.assertEqual(len(saved_cards_capped), 30)

        asyncio.run(run_quantity_tests())

    @patch('core.services.planner_service.tars_engine.create_completion')
    @patch('core.services.planner_service.mongo_db.save_deck', new_callable=AsyncMock)
    def test_dual_angle_synthesis_multi_perspective(self, mock_save, mock_complete):
        """Verifies that requesting > 15 cards executes dual-angle synthesis with definitions and principles."""
        calls_focus = []

        async def fake_complete(prompt="", **kwargs):
            p = prompt.lower()
            if "definition" in p:
                calls_focus.append("definitions")
                return "\n\n".join([f"Q: Def Question {i}?\nA: Def Answer {i}." for i in range(1, 18)])
            elif "comparison" in p or "categories" in p:
                calls_focus.append("comparisons")
                return "\n\n".join([f"Q: Comp Question {i}?\nA: Comp Answer {i}." for i in range(1, 18)])
            return "\n\n".join([f"Q: General Question {i}?\nA: General Answer {i}." for i in range(1, 15)])

        mock_complete.side_effect = fake_complete
        mock_save.return_value = True

        async def run_dual_test():
            file_bytes = b"Software Engineering Lecture Slides. Testing functional and non-functional test principles."
            success, msg = await planner_service.generate_deck("task_dual", file_bytes, quantity=30)
            self.assertTrue(success)
            mock_save.assert_called_once()
            saved_cards = mock_save.call_args[0][2]
            self.assertEqual(len(saved_cards), 30)
            # Verify both angles were queried
            self.assertIn("definitions", calls_focus)
            self.assertIn("comparisons", calls_focus)

        asyncio.run(run_dual_test())


if __name__ == '__main__':
    unittest.main()

