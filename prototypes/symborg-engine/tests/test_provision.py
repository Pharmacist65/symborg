"""Turning a phone into the device.

Nothing here is irreversible, which is the whole design — `pm uninstall --user 0` leaves
the APK on the system partition and `cmd package install-existing` brings it back. These
hold the properties that make that true, because the failure mode is somebody's phone.
"""

from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import provision   # noqa: E402


def _adb(stdout: str = "", returncode: int = 0) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=["adb"], returncode=returncode,
                                       stdout=stdout, stderr="")


class TestItNeverRemovesWhatBreaksThePhone(unittest.TestCase):
    """NEVER exists because these look removable and are not. Taking any of them off a
    Samsung produces a boot loop or a phone with no way to type a wifi password."""

    def test_the_lists_do_not_overlap(self):
        removable = {p for p, _ in provision.BLOAT + provision.CAREFUL}
        self.assertEqual(removable & set(provision.NEVER), set())

    def test_a_never_package_is_dropped_even_if_someone_adds_it(self):
        with mock.patch.object(provision, "BLOAT",
                               [("com.android.systemui", "looks like bloat")]), \
             mock.patch.object(provision, "installed",
                               return_value={"com.android.systemui"}), \
             mock.patch.object(provision, "adb", return_value=_adb()):
            removals = [s for s in provision.plan() if s.kind == "uninstall"]
        self.assertEqual(removals, [])

    def test_every_never_entry_says_what_it_breaks(self):
        for package, why in provision.NEVER.items():
            with self.subTest(package=package):
                self.assertTrue(why and len(why) > 5)


class TestEverythingIsReversible(unittest.TestCase):
    def test_each_removal_carries_its_own_undo(self):
        with mock.patch.object(provision, "installed",
                               return_value={p for p, _ in provision.BLOAT}), \
             mock.patch.object(provision, "adb", return_value=_adb()):
            steps = provision.plan()
        self.assertTrue(steps)
        for step in steps:
            with self.subTest(target=step.target):
                self.assertTrue(step.undo)
                if step.kind == "uninstall":
                    self.assertIn("install-existing", step.undo)

    def test_a_setting_is_restored_to_what_it_was(self):
        with mock.patch.object(provision, "installed", return_value=set()), \
             mock.patch.object(provision, "adb", return_value=_adb("1")):
            steps = provision.plan()
        settings = [s for s in steps if s.kind == "setting"]
        self.assertTrue(settings)
        for step in settings:
            self.assertEqual(step.undo[-1], "1")     # the value read before changing it

    def test_a_setting_that_was_never_set_is_deleted_not_written(self):
        """`settings get` prints the word null for an unset key, and putting it back
        stores that word as the value. The difference is invisible until something
        reads it."""
        for reading in ("null", ""):
            with self.subTest(reading=reading):
                with mock.patch.object(provision, "installed", return_value=set()), \
                     mock.patch.object(provision, "adb", return_value=_adb(reading)):
                    steps = [s for s in provision.plan() if s.kind == "setting"]
                self.assertTrue(steps)
                for step in steps:
                    self.assertIn("delete", step.undo)
                    self.assertNotIn("null", step.undo)

    def test_nothing_already_true_is_touched(self):
        with mock.patch.object(provision, "installed", return_value=set()), \
             mock.patch.object(provision, "adb", return_value=_adb("0")):
            steps = provision.plan()
        # Every setting whose wanted value is "0" is already "0", so only the others remain.
        self.assertTrue(all(s.target != "global/window_animation_scale" for s in steps))


class TestTheJournalComesFirst(unittest.TestCase):
    """A step recorded but not taken is undone harmlessly. A step taken but not recorded
    is one nobody can reverse."""

    def test_the_journal_is_written_before_the_command(self):
        order = []
        step = provision.Step(kind="uninstall", target="com.example", why="t",
                              do=["shell", "pm", "uninstall", "--user", "0", "com.example"],
                              undo=["shell", "cmd", "package", "install-existing",
                                    "com.example"])
        with mock.patch.object(provision, "JOURNAL", Path("/dev/null")):
            real_open = Path.open

            def watched(self, *args, **kwargs):
                order.append("journal")
                return real_open(self, *args, **kwargs)

            def watched_adb(*args, **kwargs):
                order.append("adb")
                return _adb()

            with mock.patch.object(Path, "open", watched), \
                 mock.patch.object(provision, "adb", watched_adb):
                provision.apply([step])
        self.assertEqual(order[:2], ["journal", "adb"])

    def test_undo_reverses_newest_first(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            journal = Path(tmp) / "provision.jsonl"
            journal.write_text("\n".join(json.dumps({
                "at": "now", "kind": "uninstall", "target": f"pkg{i}",
                "undo": ["shell", "cmd", "package", "install-existing", f"pkg{i}"],
            }) for i in range(3)), encoding="utf-8")
            seen = []

            def watched(*args, **kwargs):
                seen.append(args[-1])
                return _adb()

            with mock.patch.object(provision, "JOURNAL", journal), \
                 mock.patch.object(provision, "adb", watched):
                provision.undo()
        self.assertEqual(seen, ["pkg2", "pkg1", "pkg0"])

    def test_a_finished_journal_is_kept_not_deleted(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            journal = Path(tmp) / "provision.jsonl"
            journal.write_text(json.dumps({
                "at": "now", "kind": "uninstall", "target": "pkg",
                "undo": ["shell", "true"]}) + "\n", encoding="utf-8")
            with mock.patch.object(provision, "JOURNAL", journal), \
                 mock.patch.object(provision, "adb", return_value=_adb()):
                provision.undo()
            self.assertFalse(journal.exists())
            self.assertTrue(list(Path(tmp).glob("*.done")))


class TestItRefusesToGuess(unittest.TestCase):
    def test_two_phones_is_not_a_choice_it_makes(self):
        listing = "List of devices attached\nAAAA\tdevice\nBBBB\tdevice\n"
        with mock.patch.object(provision, "adb", return_value=_adb(listing)):
            self.assertIsNone(provision.device())

    def test_one_phone_is_used(self):
        listing = "List of devices attached\nAAAA\tdevice\n"
        with mock.patch.object(provision, "adb", return_value=_adb(listing)):
            self.assertEqual(provision.device(), "AAAA")

    def test_an_unauthorised_phone_is_not_ready(self):
        listing = "List of devices attached\nAAAA\tunauthorized\n"
        with mock.patch.object(provision, "adb", return_value=_adb(listing)):
            self.assertIsNone(provision.device())

    def test_a_dry_run_touches_nothing(self):
        calls = []

        def watched(*args, **kwargs):
            calls.append(args)
            if args[:1] == ("devices",):
                return _adb("List of devices attached\nAAAA\tdevice\n")
            return _adb("")

        with mock.patch.object(provision, "adb", watched):
            provision.main([])
        self.assertFalse(any("uninstall" in a for call in calls for a in call))


class TestCarefulIsOptOut(unittest.TestCase):
    """Removing SMS and calls works and changes what the phone is. That should be a
    decision, not a side effect of running a script."""

    def test_careful_packages_are_not_in_the_default_plan(self):
        careful = {p for p, _ in provision.CAREFUL}
        with mock.patch.object(provision, "installed", return_value=careful), \
             mock.patch.object(provision, "adb", return_value=_adb()):
            self.assertEqual([s for s in provision.plan() if s.kind == "uninstall"], [])

    def test_asking_for_them_includes_them_and_marks_them(self):
        careful = {p for p, _ in provision.CAREFUL}
        with mock.patch.object(provision, "installed", return_value=careful), \
             mock.patch.object(provision, "adb", return_value=_adb()):
            steps = [s for s in provision.plan(remove_careful=True) if s.kind == "uninstall"]
        self.assertEqual(len(steps), len(careful))
        self.assertTrue(all(s.risk == "careful" for s in steps))


if __name__ == "__main__":
    unittest.main()
