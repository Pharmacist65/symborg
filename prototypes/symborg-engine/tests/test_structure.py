"""Structural checks that catch whole classes of bug at once.

Everything here exists because the mistake was actually made, more than once, and
found at runtime instead of in a test.
"""

from __future__ import annotations

import ast
import unittest
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src" / "symborg_engine"


def _modules() -> list[Path]:
    return sorted(SRC.rglob("*.py"))


class TestSlotsDataclasses(unittest.TestCase):
    """A slots dataclass cannot grow attributes at runtime.

    Assigning `self._x` in a method of a `@dataclass(slots=True)` class raises
    AttributeError the first time that line runs — which, for a code path that only
    executes when a microphone is open or a session is live, means it fails in front of
    a user rather than in CI. Every attribute must be declared as a field.
    """

    def test_every_assigned_attribute_is_declared(self) -> None:
        offenders: list[str] = []

        for path in _modules():
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if not isinstance(node, ast.ClassDef):
                    continue
                if not any("slots" in ast.dump(d) for d in node.decorator_list):
                    continue

                declared = {
                    n.target.id for n in node.body
                    if isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name)
                }
                assigned = {
                    t.attr
                    for sub in ast.walk(node) if isinstance(sub, ast.Assign)
                    for t in sub.targets
                    if isinstance(t, ast.Attribute)
                    and isinstance(t.value, ast.Name) and t.value.id == "self"
                }
                missing = assigned - declared
                if missing:
                    offenders.append(
                        f"{path.relative_to(SRC)}::{node.name} assigns undeclared "
                        f"{sorted(missing)}"
                    )

        self.assertEqual(offenders, [], "\n".join(offenders))


class TestCoreStaysDependencyFree(unittest.TestCase):
    """Importing the engine must never require an optional extra.

    A missing SDK should degrade the provider, not break the import — otherwise a
    contributor with no keys cannot run anything at all.
    """

    OPTIONAL = {"openai", "anthropic", "sounddevice", "websockets", "whisper", "numpy"}

    def test_no_optional_import_at_module_level(self) -> None:
        offenders: list[str] = []

        for path in _modules():
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in tree.body:                       # module level only
                names: list[str] = []
                if isinstance(node, ast.Import):
                    names = [a.name.split(".")[0] for a in node.names]
                elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                    names = [node.module.split(".")[0]]
                for name in names:
                    if name in self.OPTIONAL:
                        offenders.append(f"{path.relative_to(SRC)} imports {name} at module level")

        self.assertEqual(offenders, [], "\n".join(offenders))

    def test_engine_imports_with_nothing_installed(self) -> None:
        import importlib
        import symborg_engine
        importlib.reload(symborg_engine)
        self.assertTrue(hasattr(symborg_engine, "Session"))


if __name__ == "__main__":
    unittest.main()


class TestTrustStoreRepair(unittest.TestCase):
    """The python.org macOS installers ship without root certificates.

    That gap makes every TLS connection fail in a way that looks like a bug in
    whatever opened the socket, so the repair is targeted and must stay so.
    """

    def test_repair_finds_a_store(self) -> None:
        from symborg_engine.tls import ensure_trust_store
        self.assertIsNotNone(ensure_trust_store())

    def test_an_existing_store_is_not_overridden(self) -> None:
        """Repair must never replace a trust store the operator configured."""
        import os
        from symborg_engine.tls import ensure_trust_store

        marker = __file__            # any path that exists
        previous = os.environ.get("SSL_CERT_FILE")
        os.environ["SSL_CERT_FILE"] = marker
        try:
            self.assertEqual(ensure_trust_store(), marker)
            self.assertEqual(os.environ["SSL_CERT_FILE"], marker)
        finally:
            if previous is None:
                os.environ.pop("SSL_CERT_FILE", None)
            else:
                os.environ["SSL_CERT_FILE"] = previous

    def test_verification_is_never_disabled(self) -> None:
        """A trust-store gap must not become a reason to stop checking certificates."""
        source = (SRC / "tls.py").read_text(encoding="utf-8")
        for forbidden in ("CERT_NONE", "check_hostname = False", "verify=False",
                          "_create_unverified_context"):
            self.assertNotIn(forbidden, source)

    def test_repair_actually_enables_tls(self) -> None:
        import ssl
        from symborg_engine.tls import ensure_trust_store

        store = ensure_trust_store()
        self.assertIsNotNone(store)
        context = ssl.create_default_context(cafile=store if store.endswith(".pem") else None)
        self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
        self.assertTrue(context.check_hostname)
