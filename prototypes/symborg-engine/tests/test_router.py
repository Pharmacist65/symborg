"""Two tiers: what runs near the person, and what is worth sending away.

Most of what this engine does is constant, shallow and enormous in volume — every turn
classified and thrown away. A little is rare and deep, and has to be right. Sending both
to the same hosted model means paying deep-model prices for the shallow ninety per cent,
all day, forever.
"""

from __future__ import annotations

import unittest

from symborg_engine.providers.base import Prompt, ProviderError
from symborg_engine.providers.router import Ledger, Tier, TieredModel, _tier_of


class _Named:
    def __init__(self, name: str) -> None:
        self.name = name
        self.calls = 0

    def complete(self, prompt: Prompt) -> str:
        self.calls += 1
        return self.name


class _Failing:
    def __init__(self) -> None:
        self.calls = 0

    def complete(self, prompt: Prompt) -> str:
        self.calls += 1
        raise ProviderError("down")


def _source(name: str) -> str:
    """Read a copilot module by filename.

    Importing it by name gets the function instead — the package re-exports `extract` and
    `look`, and a function has no file to read.
    """
    from pathlib import Path
    from symborg_engine import copilot
    return (Path(copilot.__file__).parent / f"{name}.py").read_text(encoding="utf-8")


def _near(**kw) -> Prompt:
    return Prompt(system="s", user="u", tier="near", **kw)


def _far(**kw) -> Prompt:
    return Prompt(system="s", user="u", tier="far", **kw)


class TestItReadsTheTier(unittest.TestCase):
    """The prompt carries a plain string so base stays stdlib-only, which means the tier
    has to be converted rather than compared — "near" is Tier.NEAR is false even though
    "near" == Tier.NEAR is true, and that identity check silently sent every near-tier
    call far while reporting a perfect saving of zero."""

    def test_a_string_becomes_a_tier(self):
        self.assertIs(_tier_of(_near()), Tier.NEAR)
        self.assertIs(_tier_of(_far()), Tier.FAR)

    def test_case_and_padding_do_not_matter(self):
        self.assertIs(_tier_of(Prompt(system="s", user="u", tier="  NEAR ")), Tier.NEAR)

    def test_an_unknown_tier_goes_far(self):
        """Not a licence to use a smaller model."""
        self.assertIs(_tier_of(Prompt(system="s", user="u", tier="whatever")), Tier.FAR)

    def test_a_prompt_defaults_to_far(self):
        self.assertIs(_tier_of(Prompt(system="s", user="u")), Tier.FAR)


class TestItRoutes(unittest.TestCase):
    def test_near_work_goes_near(self):
        near, far = _Named("near"), _Named("far")
        self.assertEqual(TieredModel(far=far, near=near).complete(_near()), "near")
        self.assertEqual(far.calls, 0)

    def test_deep_work_goes_far(self):
        near, far = _Named("near"), _Named("far")
        self.assertEqual(TieredModel(far=far, near=near).complete(_far()), "far")
        self.assertEqual(near.calls, 0)

    def test_with_no_near_model_everything_goes_far(self):
        far = _Named("far")
        self.assertEqual(TieredModel(far=far).complete(_near()), "far")


class TestTheLedgerDoesNotFlatterUs(unittest.TestCase):
    def test_a_near_prompt_with_nowhere_near_to_go_counts_as_far(self):
        """It did not save anything, and counting it as a saving would be lying."""
        model = TieredModel(far=_Named("far"))
        model.complete(_near())
        self.assertEqual(model.ledger.near_calls, 0)
        self.assertEqual(model.ledger.far_calls, 1)

    def test_a_fallback_is_counted_twice_and_named(self):
        """A near model that fails every call must not look like one that works."""
        model = TieredModel(far=_Named("far"), near=_Failing())
        self.assertEqual(model.complete(_near()), "far")
        self.assertEqual(model.ledger.fallbacks, 1)
        self.assertEqual(model.ledger.near_calls, 1)
        self.assertEqual(model.ledger.far_calls, 1)

    def test_the_fallback_can_be_turned_off_to_find_the_truth(self):
        model = TieredModel(far=_Named("far"), near=_Failing(), fall_back=False)
        with self.assertRaises(ProviderError):
            model.complete(_near())

    def test_an_empty_ledger_claims_nothing(self):
        self.assertEqual(Ledger().near_share, 0.0)

    def test_it_counts_what_was_sent_not_just_how_often(self):
        model = TieredModel(far=_Named("far"), near=_Named("near"))
        model.complete(Prompt(system="x" * 100, user="y" * 200, tier="near"))
        self.assertEqual(model.ledger.near_chars, 300)


class TestTheCallSitesDeclareTheirTier(unittest.TestCase):
    """The split is the cost model. A call site that forgets to say which tier it is
    silently becomes expensive, and nothing fails."""

    def test_the_constant_shallow_work_is_near(self):
        for name in ("extract", "judge", "addressed"):
            with self.subTest(module=name):
                self.assertIn('tier="near"', _source(name))

    def test_the_rare_deep_work_is_far(self):
        for name in ("contradiction", "look", "translate"):
            with self.subTest(module=name):
                source = _source(name)
                self.assertIn('tier="far"', source)
                self.assertNotIn('tier="near"', source)

    def test_every_prompt_in_the_copilot_says_which_tier_it_is(self):
        import ast
        from pathlib import Path
        from symborg_engine import copilot
        missing = []
        for path in Path(copilot.__file__).parent.glob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                        and node.func.id == "Prompt"):
                    if not any(k.arg == "tier" for k in node.keywords):
                        missing.append(f"{path.name}:{node.lineno}")
        self.assertEqual(missing, [], f"prompts with no tier: {missing}")


if __name__ == "__main__":
    unittest.main()
