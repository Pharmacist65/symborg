"""Turning a phone into the device.

The phone is not going to be a phone any more. Everything that competes for its battery,
its microphone or its attention comes off, and what is left runs one thing all day.

Nothing here is irreversible, which is the whole design. `pm uninstall --user 0` does not
delete anything — it removes the package for the current user and leaves the APK on the
system partition, so `cmd package install-existing` brings it back. Every action is
written to a journal first, and `--undo` replays it backwards. A factory reset is a
different kind of act and this tool does not do it.

    python3 tools/provision.py                 # what it would do, and nothing else
    python3 tools/provision.py --apply
    python3 tools/provision.py --undo

Read the plan before running with --apply. It is your phone.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

JOURNAL = Path("~/.symborg/provision.jsonl").expanduser()

# --- what comes off ---------------------------------------------------------------
#
# Grouped by what removing it costs, because "safe" is not one thing. Anything whose
# absence changes how the phone behaves is in CAREFUL and off by default, and anything
# that looks like bloat but takes the phone down with it is in NEVER, named, so that
# nobody adds it back later after reading a list on a forum.

BLOAT = [
    # Samsung's own duplicates of things this device does not need at all.
    ("com.samsung.android.bixby.agent", "Bixby"),
    ("com.samsung.android.bixby.wakeup", "Bixby, always listening — competes for the mic"),
    ("com.samsung.android.app.settings.bixby", "Bixby settings"),
    ("com.samsung.android.bixbyvision.framework", "Bixby Vision"),
    ("com.samsung.android.visionintelligence", "Bixby Vision"),
    ("com.samsung.android.app.spage", "Samsung Free / news page"),
    ("com.samsung.android.game.gamehome", "Game Launcher"),
    ("com.samsung.android.game.gametools", "Game Tools"),
    ("com.samsung.android.game.gos", "Game Optimising Service — throttles background work"),
    ("com.samsung.android.arzone", "AR Zone"),
    ("com.samsung.android.aremoji", "AR Emoji"),
    ("com.samsung.android.livestickers", "AR stickers"),
    ("com.samsung.android.app.tips", "Tips"),
    ("com.samsung.android.kidsinstaller", "Kids Mode installer"),
    ("com.samsung.android.themestore", "Theme Store"),
    ("com.samsung.android.app.galaxyfinder", "Finder search"),
    ("com.samsung.android.mateagent", "Wearable helper"),
    ("com.samsung.android.scloud", "Samsung Cloud"),
    ("com.samsung.android.smartswitchassistant", "Smart Switch"),
    ("com.sec.android.easyMover.Agent", "Smart Switch agent"),
    ("com.samsung.android.forest", "Digital Wellbeing"),
    ("com.samsung.android.app.routines", "Modes and Routines — runs things by itself"),

    # Google's, where the device has no use for them and they wake constantly.
    ("com.google.android.apps.tachyon", "Google Meet"),
    ("com.google.android.youtube", "YouTube"),
    ("com.google.android.apps.youtube.music", "YouTube Music"),
    ("com.google.android.apps.magazines", "Google News"),
    ("com.google.android.apps.docs", "Google Drive"),
    ("com.google.android.apps.photos", "Google Photos — uploads everything the camera takes"),
    ("com.google.android.videos", "Google TV"),
    ("com.google.ar.lens", "Google Lens"),

    # Carrier and shop-floor.
    ("com.facebook.katana", "Facebook, preinstalled"),
    ("com.facebook.system", "Facebook system stub"),
    ("com.facebook.appmanager", "Facebook app manager"),
    ("com.facebook.services", "Facebook services"),
    ("com.microsoft.skydrive", "OneDrive"),
    ("com.microsoft.office.officehubrow", "Office"),
    ("com.linkedin.android", "LinkedIn"),
    ("com.netflix.mediaclient", "Netflix"),
    ("com.spotify.music", "Spotify"),
]

CAREFUL = [
    # Removing these works, and changes something you may want back.
    ("com.samsung.android.messaging", "SMS — the phone can no longer receive texts"),
    ("com.samsung.android.dialer", "Phone calls"),
    ("com.samsung.android.email.provider", "Email"),
    ("com.samsung.android.calendar", "Calendar"),
    ("com.sec.android.gallery3d", "Gallery — photos still exist, nothing shows them"),
    ("com.sec.android.app.myfiles", "My Files"),
    ("com.samsung.android.app.contacts", "Contacts"),
]

NEVER = {
    # Named because they look removable and are not. Taking any of these off a Samsung
    # produces a boot loop or a phone with no working input.
    "com.android.systemui": "the entire interface",
    "com.samsung.android.honeyboard": "the keyboard — no way to type anything, including wifi passwords",
    "com.android.settings": "settings",
    "com.sec.android.app.launcher": "the home screen",
    "com.samsung.android.providers.contacts": "the contacts database other things depend on",
    "com.android.providers.settings": "where every setting is stored",
    "com.samsung.android.incallui": "answering calls; its absence hangs the dialer",
    "com.android.permissioncontroller": "permission dialogs — nothing can be granted anything",
    "com.google.android.gms": "Play Services; half the system talks to it",
    "com.android.vending": "the Play Store, which Play Services expects to exist",
}

# --- what gets set ----------------------------------------------------------------

SETTINGS = [
    # (namespace, key, wanted, why)
    ("global", "window_animation_scale", "0", "no animation to render"),
    ("global", "transition_animation_scale", "0", "no animation to render"),
    ("global", "animator_duration_scale", "0", "no animation to render"),
    ("global", "adaptive_battery_management_enabled", "0",
     "adaptive battery is what decides to stop the app it has not seen you open"),
    ("system", "screen_off_timeout", "60000",
     "the screen sleeping is fine; the capture must not sleep with it"),
    ("secure", "screensaver_enabled", "0", "nothing to draw"),
]


@dataclass(slots=True)
class Step:
    """One thing to do, and the thing that undoes it."""

    kind: str
    target: str
    why: str
    do: list[str]
    undo: list[str]
    risk: str = "safe"


def adb(*args: str, check: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(["adb", *args], capture_output=True, text=True, check=check)


def device() -> str | None:
    """The one connected device, or None. Refuses to guess between several."""
    out = adb("devices").stdout.strip().splitlines()[1:]
    ready = [line.split()[0] for line in out if line.strip().endswith("device")]
    if len(ready) == 1:
        return ready[0]
    if len(ready) > 1:
        print(f"  {len(ready)} devices are connected. Unplug all but one.")
    return None


def installed() -> set[str]:
    out = adb("shell", "pm", "list", "packages", "-u").stdout
    return {line.split(":", 1)[1].strip() for line in out.splitlines() if ":" in line}


def plan(remove_careful: bool = False) -> list[Step]:
    here = installed()
    steps: list[Step] = []

    for package, why in BLOAT + (CAREFUL if remove_careful else []):
        if package not in here:
            continue
        if package in NEVER:                    # belt and braces; the lists are hand-kept
            continue
        steps.append(Step(
            kind="uninstall", target=package, why=why,
            do=["shell", "pm", "uninstall", "--user", "0", package],
            undo=["shell", "cmd", "package", "install-existing", package],
            risk="careful" if any(package == p for p, _ in CAREFUL) else "safe",
        ))

    for namespace, key, wanted, why in SETTINGS:
        current = adb("shell", "settings", "get", namespace, key).stdout.strip()
        if current == wanted:
            continue
        # A setting that was never set is undone by deleting it, not by writing "null" —
        # `settings get` prints the word null for an unset key, and putting it back stores
        # that word as the value. The difference is invisible until something reads it.
        if current in ("", "null"):
            undo = ["shell", "settings", "delete", namespace, key]
        else:
            undo = ["shell", "settings", "put", namespace, key, current]
        steps.append(Step(
            kind="setting", target=f"{namespace}/{key}", why=why,
            do=["shell", "settings", "put", namespace, key, wanted], undo=undo,
        ))

    return steps


def show(steps: list[Step]) -> None:
    if not steps:
        print("\n  Nothing to do — already provisioned.\n")
        return
    removals = [s for s in steps if s.kind == "uninstall"]
    settings = [s for s in steps if s.kind == "setting"]

    if removals:
        print(f"\n  Remove {len(removals)} packages (reversible — the APKs stay on the "
              f"system partition):\n")
        for step in removals:
            mark = "  ! " if step.risk == "careful" else "    "
            print(f"{mark}{step.target:52} {step.why}")
    if settings:
        print(f"\n  Change {len(settings)} settings:\n")
        for step in settings:
            print(f"    {step.target:52} {step.why}")
    print(f"\n  {len(steps)} steps. Every one is written to {JOURNAL} and undone by --undo.\n")


def apply(steps: list[Step]) -> int:
    JOURNAL.parent.mkdir(parents=True, exist_ok=True)
    done = failed = 0
    with JOURNAL.open("a", encoding="utf-8") as journal:
        for step in steps:
            # Journal first. A step recorded but not taken is undone harmlessly; a step
            # taken but not recorded is one nobody can reverse.
            journal.write(json.dumps({
                "at": time.strftime("%Y-%m-%d %H:%M:%S"), "kind": step.kind,
                "target": step.target, "undo": step.undo,
            }, ensure_ascii=False) + "\n")
            journal.flush()
            result = adb(*step.do)
            ok = result.returncode == 0 and "Failure" not in result.stdout
            done += ok
            failed += not ok
            print(f"    {'ok  ' if ok else 'FAIL'} {step.target}"
                  + ("" if ok else f"   {result.stdout.strip() or result.stderr.strip()}"))
    print(f"\n  {done} done, {failed} failed.\n")
    return 0 if not failed else 1


def undo() -> int:
    if not JOURNAL.exists():
        print(f"\n  Nothing recorded at {JOURNAL}.\n")
        return 1
    rows = [json.loads(line) for line in
            JOURNAL.read_text(encoding="utf-8").splitlines() if line.strip()]
    print(f"\n  Reversing {len(rows)} steps, newest first.\n")
    failed = 0
    for row in reversed(rows):
        result = adb(*row["undo"])
        ok = result.returncode == 0
        failed += not ok
        print(f"    {'ok  ' if ok else 'FAIL'} {row['target']}")
    JOURNAL.rename(JOURNAL.with_suffix(f".{int(time.time())}.done"))
    print(f"\n  {len(rows) - failed} reversed, {failed} failed. Reboot the phone.\n")
    return 0 if not failed else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Turn a phone into the device.")
    parser.add_argument("--apply", action="store_true", help="Actually do it")
    parser.add_argument("--undo", action="store_true", help="Reverse everything recorded")
    parser.add_argument("--careful", action="store_true",
                        help="Also remove SMS, calls, email, gallery and contacts")
    args = parser.parse_args(argv)

    if adb("version").returncode != 0:
        print("\n  adb is not installed.  brew install --cask android-platform-tools\n")
        return 1

    serial = device()
    if serial is None:
        print("\n  No phone. Plug it in, then on the phone:")
        print("    Settings → About phone → Software information → tap 'Build number' 7×")
        print("    Settings → Developer options → USB debugging → on")
        print("    Accept the dialog that appears when you plug it in.\n")
        return 1

    model = adb("shell", "getprop", "ro.product.model").stdout.strip()
    name = adb("shell", "getprop", "ro.product.name").stdout.strip()
    android = adb("shell", "getprop", "ro.build.version.release").stdout.strip()
    print(f"\n  {model} ({name})   Android {android}   {serial}")

    if args.undo:
        return undo()

    steps = plan(remove_careful=args.careful)
    show(steps)
    if not args.apply:
        print("  This was a dry run. Add --apply to do it.\n")
        return 0
    return apply(steps)


if __name__ == "__main__":
    raise SystemExit(main())
