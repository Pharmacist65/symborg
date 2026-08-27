"""Trust-store repair for Python installations that ship without one.

The python.org macOS installers do not install root certificates; they ship a
``Install Certificates.command`` the user is expected to run, and most people never do.
The result is that every TLS connection fails with a certificate-verification error,
which looks like a bug in whatever code happened to open the socket.

Requests made through the OpenAI SDK are unaffected because its HTTP client bundles a
trust store. The WebSocket used for live transcription is not: it builds a default SSL
context and inherits the missing one.

This repairs the process environment when, and only when, the configured trust store is
genuinely absent and ``certifi`` can supply one. It is a targeted fix for a known
platform gap, not a way to work around a real certificate problem — nothing here
disables verification, and an existing trust store is never overridden.
"""

from __future__ import annotations

import os
import ssl
from pathlib import Path

__all__ = ["ensure_trust_store", "trust_store_status"]

_ENV_VARS = ("SSL_CERT_FILE", "REQUESTS_CA_BUNDLE")


def _configured_store() -> str | None:
    """The trust store this process would currently use, if it exists on disk."""
    for var in _ENV_VARS:
        value = os.environ.get(var)
        if value and Path(value).exists():
            return value

    paths = ssl.get_default_verify_paths()
    for candidate in (paths.cafile, paths.openssl_cafile):
        if candidate and Path(candidate).exists():
            return candidate

    capath = paths.capath or paths.openssl_capath
    if capath and Path(capath).is_dir() and any(Path(capath).iterdir()):
        return capath

    return None


def ensure_trust_store() -> str | None:
    """Make sure this process can verify TLS certificates.

    Returns:
        The trust store in use, or None if none could be found — in which case the
        caller should let the original certificate error surface rather than
        pretending the connection is safe.
    """
    existing = _configured_store()
    if existing is not None:
        return existing

    try:
        import certifi
    except ImportError:
        return None

    bundle = certifi.where()
    if not Path(bundle).exists():
        return None

    for var in _ENV_VARS:
        os.environ.setdefault(var, bundle)
    return bundle


def trust_store_status() -> str:
    """A line for the configuration doctor."""
    store = _configured_store()
    if store:
        return f"ok · {store}"
    try:
        import certifi
        return f"missing · certifi can repair it ({certifi.where()})"
    except ImportError:
        return "missing · install certifi, or run 'Install Certificates.command'"
