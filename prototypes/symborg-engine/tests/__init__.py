"""The unit suite runs offline, deliberately.

Without this, every test that builds a Session or Copilot without naming a provider
resolves whatever credentials happen to be exported and makes real network calls. The
tests still pass, so nothing announces it — they just get slower, cost money, and stop
being deterministic. A developer with a key in their shell was running a different
suite from CI.

Set SYMBORG_TEST_LIVE=1 to run against real providers on purpose.
"""

from __future__ import annotations

import os

if not os.environ.get("SYMBORG_TEST_LIVE"):
    for _name in [k for k in os.environ
                  if k.endswith("_API_KEY") or k.startswith("SYMBORG_")]:
        os.environ.pop(_name, None)
