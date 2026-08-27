"""Provider selection.

The engine must never depend on which vendor supplies the model, and must never
fail because a key or an optional dependency is missing.
"""

from __future__ import annotations

import os
import unittest
import warnings
from contextlib import contextmanager

from symborg_engine.providers import (
    available_providers, resolve_language_model,
)
from symborg_engine.providers.offline import OfflineLanguageModel
from symborg_engine.providers.base import Prompt

_VARS = ("SYMBORG_LLM_PROVIDER", "SYMBORG_LLM_MODEL", "ANTHROPIC_API_KEY", "OPENAI_API_KEY")


@contextmanager
def env(**values):
    """Set exactly the given provider variables, clearing all others."""
    saved = {k: os.environ.get(k) for k in _VARS}
    try:
        for k in _VARS:
            os.environ.pop(k, None)
        for k, v in values.items():
            os.environ[k] = v
        yield
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


class TestResolution(unittest.TestCase):
    def test_no_key_gives_offline(self) -> None:
        with env():
            self.assertIsInstance(resolve_language_model(), OfflineLanguageModel)

    def test_explicit_provider_wins_over_environment(self) -> None:
        class _Stub:
            def complete(self, prompt: Prompt) -> str:
                return "[]"

        stub = _Stub()
        with env(OPENAI_API_KEY="x"):
            self.assertIs(resolve_language_model(stub), stub)

    def test_offline_can_be_forced_despite_a_key(self) -> None:
        """A developer with a key must still be able to work offline."""
        with env(SYMBORG_LLM_PROVIDER="offline", OPENAI_API_KEY="x"):
            self.assertIsInstance(resolve_language_model(), OfflineLanguageModel)

    def test_unknown_provider_warns_and_degrades(self) -> None:
        with env(SYMBORG_LLM_PROVIDER="wishful"):
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always")
                model = resolve_language_model()
            self.assertIsInstance(model, OfflineLanguageModel)
            self.assertTrue(any("not recognised" in str(w.message) for w in caught))

    def test_requested_provider_without_key_warns_and_degrades(self) -> None:
        with env(SYMBORG_LLM_PROVIDER="openai"):
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always")
                model = resolve_language_model()
            self.assertIsInstance(model, OfflineLanguageModel)
            self.assertTrue(any("OPENAI_API_KEY is not set" in str(w.message) for w in caught))

    def test_missing_optional_dependency_never_raises(self) -> None:
        """A key with no SDK installed degrades; it must not break the engine."""
        with env(OPENAI_API_KEY="x", ANTHROPIC_API_KEY="y"):
            with warnings.catch_warnings(record=True):
                warnings.simplefilter("always")
                model = resolve_language_model()
        self.assertTrue(hasattr(model, "complete"))

    def test_available_providers_reports_keys_present(self) -> None:
        with env():
            self.assertEqual(available_providers(), [])
        with env(OPENAI_API_KEY="x"):
            self.assertEqual(available_providers(), ["openai"])
        with env(ANTHROPIC_API_KEY="y", OPENAI_API_KEY="x"):
            self.assertEqual(available_providers(), ["anthropic", "openai"])


class TestNoSecretsLeak(unittest.TestCase):
    def test_key_is_never_placed_in_a_prompt(self) -> None:
        """Guards against a credential ever reaching a prompt through config."""
        from symborg_engine import Session, Transcript
        from symborg_engine.generate.candidates import generate_candidates

        seen: list[Prompt] = []

        class _Capture:
            def complete(self, prompt: Prompt) -> str:
                seen.append(prompt)
                return "[]"

        with env(OPENAI_API_KEY="sk-secret-value", ANTHROPIC_API_KEY="ant-secret-value"):
            transcript = Transcript()
            transcript.add_text("Merhaba")
            generate_candidates(_Capture(), transcript)

        blob = "".join(p.system + p.user for p in seen)
        self.assertNotIn("sk-secret-value", blob)
        self.assertNotIn("ant-secret-value", blob)


if __name__ == "__main__":
    unittest.main()
