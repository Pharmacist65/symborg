"""The unit suite runs offline, deliberately.

A test that resolves whatever credentials happen to be exported makes real network
calls, still passes, and quietly stops being deterministic — so a developer with a key
in their shell runs a different suite from CI.

Set SYMBORG_TEST_LIVE=1 to run against real providers on purpose.
"""

from __future__ import annotations

import os

if not os.environ.get("SYMBORG_TEST_LIVE"):
    for _name in [k for k in os.environ
                  if k.endswith("_API_KEY") or k.startswith("SYMBORG_")]:
        os.environ.pop(_name, None)
