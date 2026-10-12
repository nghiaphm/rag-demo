"""Provider-neutral construction tests for the Groq OpenAI-compatible LLM."""

import unittest
from unittest.mock import patch

from app.rag import llm


class LLMFactoryTests(unittest.TestCase):
    def tearDown(self) -> None:
        llm.get_llm.cache_clear()

    def test_factory_uses_groq_key_base_url_and_configured_model(self):
        sentinel = object()
        llm.get_llm.cache_clear()
        with patch("app.rag.llm.ChatOpenAI", return_value=sentinel) as constructor:
            self.assertIs(llm.get_llm(), sentinel)
            self.assertIs(llm.get_llm(), sentinel)

        constructor.assert_called_once_with(
            model=llm.settings.llm_model,
            api_key=llm.settings.groq_api_key.get_secret_value(),
            base_url=llm.settings.openai_base_url,
        )


if __name__ == "__main__":
    unittest.main()
