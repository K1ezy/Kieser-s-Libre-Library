"""
Unit tests for ChatService and SummarizerService.
Validates separation of concerns and business logic correctness.
"""

import unittest
import time
from ui.pages.chat_service import (
    chat_service,
    STYLE_PROMPTS,
    STARTER_PROMPTS_BOOK,
    STARTER_PROMPTS_LIBRARY
)
from ui.pages.summarizer_service import summarizer_service, SUMMARY_MODES


class TestChatService(unittest.TestCase):
    """Verifies ChatService business logic and intent parsing."""

    def test_should_skip_rag_greetings_and_identity(self):
        """Simple greetings and identity inquiries should skip expensive RAG searches."""
        self.assertTrue(chat_service.should_skip_rag("hello"))
        self.assertTrue(chat_service.should_skip_rag("Hi!"))
        self.assertTrue(chat_service.should_skip_rag("hey tars"))
        self.assertTrue(chat_service.should_skip_rag("who are you"))
        self.assertTrue(chat_service.should_skip_rag("What is your function?"))
        self.assertTrue(chat_service.should_skip_rag(""))

    def test_should_not_skip_rag_substantive_questions(self):
        """Content questions should proceed to RAG search."""
        self.assertFalse(chat_service.should_skip_rag("Explain quantum entanglement and its history."))
        self.assertFalse(chat_service.should_skip_rag("What are the key themes in chapter 4?"))
        self.assertFalse(chat_service.should_skip_rag("Summarize machine learning principles."))

    def test_group_sessions_chronologically(self):
        """Verifies session timestamps are grouped into proper chronological buckets."""
        now = time.time()
        sessions = [
            {"id": "s1", "title": "Recent Chat", "timestamp": now - 300},
            {"id": "s2", "title": "Yesterday Chat", "timestamp": now - 90000},
            {"id": "s3", "title": "Last Week Chat", "timestamp": now - (5 * 86400)},
            {"id": "s4", "title": "Old Chat", "timestamp": now - (40 * 86400)},
        ]
        grouped = chat_service.group_sessions_chronologically(sessions)
        self.assertIsInstance(grouped, dict)
        self.assertIn("Today", grouped)
        self.assertEqual(grouped["Today"][0]["id"], "s1")

    def test_build_system_persona(self):
        """Persona prompt includes appropriate instructions based on mode and focus."""
        persona = chat_service.build_system_persona(
            chat_style="Academic",
            focus_book_title="Principles of Physics",
            teaching_mode=True,
            is_review_mode=False,
            inventory="Physics Vol 1",
            rag_text="Gravity formula"
        )
        self.assertIn("TARS, the Digital Librarian", persona)
        self.assertIn(STYLE_PROMPTS["Academic"], persona)
        self.assertIn("Principles of Physics", persona)
        self.assertIn("TEACHING MODE", persona)
        self.assertIn("Gravity formula", persona)

    def test_build_system_persona_with_focus_book_meta(self):
        """Verifies that book metadata and preview synopsis directly ground the LLM persona."""
        meta = {
            "title": "Witcher Crossroadsofravens",
            "display_author": "Andrzej Sapkowski",
            "description": "Geralt embarks on a dangerous journey through the Crossroads of Ravens.",
            "file_type": "EPUB",
            "shelves": ["Fantasy", "Favorites"],
            "genres": ["Dark Fantasy", "Adventure"]
        }
        persona = chat_service.build_system_persona(
            chat_style="Balanced",
            focus_book_title="Witcher Crossroadsofravens",
            inventory="* Witcher Crossroadsofravens (Andrzej Sapkowski) [EPUB]",
            rag_text="",
            focus_book_meta=meta
        )
        self.assertIn("CURRENTLY FOCUSED BOOK DETAILS", persona)
        self.assertIn("Witcher Crossroadsofravens", persona)
        self.assertIn("Andrzej Sapkowski", persona)
        self.assertIn("Geralt embarks on a dangerous journey through the Crossroads of Ravens.", persona)
        self.assertIn("YES, this document is currently saved and available in the library archive (EPUB format)", persona)
        self.assertIn("Fantasy, Favorites", persona)

    def test_export_chat_markdown(self):
        """Verifies chat export outputs structured Markdown with metadata header."""
        messages = [
            {"role": "user", "content": "What is relativity?"},
            {"role": "assistant", "content": "Relativity is a physical theory..."}
        ]
        md = chat_service.export_chat_markdown(messages, "Einstein Physics", "test-session-123")
        self.assertIn("# Conversation with TARS AI", md)
        self.assertIn("Einstein Physics", md)
        self.assertIn("`test-session-123`", md)
        self.assertIn("### 👤 User\n\nWhat is relativity?", md)
        self.assertIn("### 🤖 TARS AI\n\nRelativity is a physical theory...", md)


class TestSummarizerService(unittest.IsolatedAsyncioTestCase):
    """Verifies SummarizerService document chunking and study prompt building."""

    def test_partition_document_text_short(self):
        """Short documents (<24k chars) should be returned unchanged."""
        short_text = "This is a short book with a few paragraphs."
        partitioned = summarizer_service.partition_document_text(short_text)
        self.assertEqual(partitioned, short_text)

    def test_partition_document_text_long(self):
        """Long documents (>24k chars) should be partitioned into 5 key structural sections."""
        long_text = "A" * 50000
        partitioned = summarizer_service.partition_document_text(long_text)
        self.assertIn("=== PART 1: INTRODUCTION & BEGINNING ===", partitioned)
        self.assertIn("=== PART 2: EARLY SECTIONS ===", partitioned)
        self.assertIn("=== PART 3: CORE MIDDLE SECTIONS ===", partitioned)
        self.assertIn("=== PART 4: ADVANCED / LATER TOPICS ===", partitioned)
        self.assertIn("=== PART 5: CONCLUSION & TAKEAWAYS ===", partitioned)

    def test_build_summary_messages_all_modes(self):
        """Verifies prompt generation across all supported study guide modes."""
        for mode in ['detailed', 'brief', 'concepts', 'qa']:
            messages = summarizer_service.build_summary_messages(mode, "Sample Book", "Sample Content")
            self.assertEqual(len(messages), 2)
            self.assertEqual(messages[0]["role"], "system")
            self.assertEqual(messages[1]["role"], "user")
            self.assertIn("Sample Book", messages[1]["content"])
            self.assertIn("Sample Content", messages[1]["content"])

    async def test_tars_engine_generate_response_delegation(self):
        """Verifies tars_engine.generate_response calls create_completion."""
        from unittest.mock import AsyncMock
        from core.ai_engine.llm_engine import tars_engine
        
        with unittest.mock.patch.object(tars_engine, 'create_completion', new_callable=AsyncMock) as mock_comp:
            mock_comp.return_value = "Generated Synopsis"
            res = await tars_engine.generate_response("Test prompt", max_tokens=500)
            self.assertEqual(res, "Generated Synopsis")
            mock_comp.assert_awaited_once_with(
                prompt="Test prompt",
                max_tokens=500,
                temperature=0.3,
                stop=None
            )


if __name__ == '__main__':
    unittest.main()
