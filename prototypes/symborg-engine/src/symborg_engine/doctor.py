"""Configuration check: ``python3 -m symborg_engine.doctor``

Reports which provider the engine will use and why. Deliberately never prints a
credential — only whether one is present, and the last four characters, which is
enough to tell two keys apart and not enough to use one.
"""

from __future__ import annotations

import os
import sys
import warnings

from .providers import _KEYS, _ORDER, available_providers, resolve_language_model
from .tls import trust_store_status

__all__ = ["report", "main"]

_OK, _NO, _WARN = "  ok  ", " none ", " warn "


def _mask(value: str) -> str:
    return f"...{value[-4:]}" if len(value) >= 8 else "(too short to be a key)"


def report() -> int:
    lines: list[str] = ["", "SYMBORG engine — configuration", "=" * 34, ""]

    lines.append("Python")
    lines.append(f"  [{_OK}] {sys.version.split()[0]}")
    status = trust_store_status()
    lines.append(f"  [{_OK if status.startswith('ok') else _WARN}] TLS trust store: {status}")
    lines.append("")

    lines.append("Optional SDKs")
    for name, module in (("anthropic", "anthropic"), ("openai", "openai")):
        try:
            __import__(module)
            lines.append(f"  [{_OK}] {name} installed")
        except ImportError:
            lines.append(f"  [{_NO}] {name} not installed   → pip3 install '.[{name}]'")
    lines.append("")

    lines.append("Credentials (read from the environment only)")
    for name in _ORDER:
        var = _KEYS[name]
        value = os.environ.get(var)
        if value:
            lines.append(f"  [{_OK}] {var} is set  {_mask(value)}")
        else:
            lines.append(f"  [{_NO}] {var} not set")
    lines.append("")

    requested = os.environ.get("SYMBORG_LLM_PROVIDER", "").strip().lower()
    model = os.environ.get("SYMBORG_LLM_MODEL", "")
    lines.append("Selection")
    lines.append(f"  SYMBORG_LLM_PROVIDER : {requested or '(unset — auto-detect)'}")
    lines.append(f"  SYMBORG_LLM_MODEL    : {model or '(unset — provider default)'}")
    lines.append(f"  keys present         : {', '.join(available_providers()) or 'none'}")
    lines.append("")

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        resolved = resolve_language_model()
    name = type(resolved).__name__
    offline = name == "OfflineLanguageModel"
    lines.append("Result")
    lines.append(f"  [{_WARN if offline else _OK}] the engine will use: {name}")
    for w in caught:
        lines.append(f"        ! {w.message}")
    if offline:
        lines.append("")
        lines.append("  The offline provider works and all tests pass with it — this is a")
        lines.append("  supported state, not a broken one. To use a hosted model, install")
        lines.append("  the extra and export the key in the SAME shell.")
    lines.append("")

    print("\n".join(lines))
    return 0


def main() -> int:
    return report()


if __name__ == "__main__":
    raise SystemExit(main())
