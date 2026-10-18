import unittest
from unittest.mock import MagicMock, patch
from core.services.chat_service import chat_service
from core.ai_engine.rag_pipeline import TarsArchive
from core.ai_engine.llm_engine import tars_engine


class TestChatGrounding(unittest.TestCase):
    def test_greeting_and_identity_detection(self):
        self.assertTrue(chat_service.is_greeting_or_identity("Hello"))
        self.assertTrue(chat_service.is_greeting_or_identity("Good morning TARS!"))
        self.assertTrue(chat_service.is_greeting_or_identity("Who are you?"))
        self.assertFalse(
            chat_service.is_greeting_or_identity(
                "Hello, can you explain chapter 3 of the database book?"
            )
        )

    def test_greeting_suppresses_focused_book_header(self):
        book = {
            "title": "Clean Architecture",
            "author": "Robert C. Martin",
            "category": "Software Engineering",
        }
        greeting_persona = chat_service.build_system_persona(
            chat_style="Academic", focus_book=book, is_greeting=True
        )
        inquiry_persona = chat_service.build_system_persona(
            chat_style="Academic", focus_book=book, is_greeting=False
        )

        self.assertNotIn("=== CURRENTLY FOCUSED BOOK DETAILS ===", greeting_persona)
        self.assertIn("Do NOT summarize or recite details", greeting_persona)
        self.assertIn("=== CURRENTLY FOCUSED BOOK DETAILS ===", inquiry_persona)

    def test_anti_hallucination_rules_present(self):
        persona = chat_service.build_system_persona()
        self.assertIn("CRITICAL ACCURACY & ANTI-HALLUCINATION RULES:", persona)
        self.assertIn("1. DIRECT ANSWER FIRST:", persona)
        self.assertIn("2. STRICT CLASSIFICATION FIDELITY:", persona)
        self.assertIn("3. GROUNDING & VERIFIED CITATIONS:", persona)
        self.assertIn("4. HONEST REFUSAL:", persona)
        self.assertIn("5. GENERAL INQUIRIES:", persona)

    def test_user_turn_rag_wrapping_and_race_deduplication(self):
        persona = "System Persona"
        # Simulate fast DB write where current_query is already at the tail of history
        history = [
            {"role": "user", "content": "Hi"},
            {"role": "assistant", "content": "Hello! How can I help?"},
            {"role": "user", "content": "What is dependency inversion?"},
        ]
        rag_text = "[DOCUMENT EVIDENCE]\n\nHigh-level modules should not depend on low-level modules.\n[/DOCUMENT EVIDENCE]"

        payload = chat_service.build_messages_payload(
            system_persona=persona,
            history=history,
            current_query="What is dependency inversion?",
            rag_text=rag_text,
            max_turns=4,
        )

        # Should contain: system, user("Hi"), assistant("Hello..."), user(wrapped query)
        self.assertEqual(len(payload), 4)
        self.assertEqual(payload[-1]["role"], "user")
        self.assertIn("[DOCUMENT EVIDENCE]", payload[-1]["content"])
        self.assertIn("[USER INQUIRY]:\nWhat is dependency inversion?", payload[-1]["content"])
        # System prompt must remain free of raw document chunks
        self.assertNotIn("[DOCUMENT EVIDENCE]", payload[0]["content"])

    def test_strict_distance_threshold_filtering(self):
        raw_chroma_output = {
            "documents": [["Relevant chunk", "Noisy irrelevant chunk"]],
            "metadatas": [[{"source": "Book A", "page": 12}, {"source": "Book A", "page": 99}]],
            "distances": [[0.62, 1.18]],
        }
        filtered = TarsArchive._filter_results(raw_chroma_output, max_distance=0.90)
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0]["text"], "Relevant chunk")

        # When all chunks exceed 0.90, returns empty list []
        all_noisy = {
            "documents": [["Unrelated text"]],
            "metadatas": [[{"source": "Book A", "page": 5}]],
            "distances": [[1.15]],
        }
        self.assertEqual(TarsArchive._filter_results(all_noisy, max_distance=0.90), [])

    def test_llm_sampling_and_context_defaults(self):
        self.assertAlmostEqual(tars_engine.temperature, 0.05)
        self.assertAlmostEqual(tars_engine.top_p, 0.90)
        self.assertAlmostEqual(tars_engine.repeat_penalty, 1.15)
        self.assertGreaterEqual(tars_engine.context_window, 4096)


if __name__ == "__main__":
    unittest.main()
