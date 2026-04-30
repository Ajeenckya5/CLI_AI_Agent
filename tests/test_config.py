from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from codecraft_agent.config import load_config


class ConfigTests(unittest.TestCase):
    def test_xai_is_default_provider(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            config = load_config(workspace=".")

        self.assertEqual(config.provider, "xai")
        self.assertEqual(config.base_url, "https://api.x.ai/v1")
        self.assertEqual(config.model, "grok-4.20-reasoning")
        self.assertEqual(config.api_key_env, "XAI_API_KEY")

    def test_openai_provider_defaults_are_still_available(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            config = load_config(workspace=".", provider="openai")

        self.assertEqual(config.provider, "openai")
        self.assertEqual(config.base_url, "https://api.openai.com/v1")
        self.assertEqual(config.model, "gpt-4o-mini")
        self.assertEqual(config.api_key_env, "OPENAI_API_KEY")

    def test_explicit_provider_key_env_is_used(self) -> None:
        with patch.dict(os.environ, {"MY_XAI_KEY": "secret"}, clear=True):
            config = load_config(workspace=".", api_key_env="MY_XAI_KEY")

        self.assertEqual(config.api_key, "secret")
        self.assertEqual(config.api_key_env, "MY_XAI_KEY")


if __name__ == "__main__":
    unittest.main()

