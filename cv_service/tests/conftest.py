"""
CV service test configuration.

`main.py` constructs `CVService()` (and thus `BackendAPIClient()`) at module
import time. Since BackendAPIClient is fail-closed and refuses to build
without INTERNAL_API_SECRET (see api/backend_client.py), the secret must be
present in the environment BEFORE any test module imports `main`. pytest
imports this conftest before collecting the test modules alongside it, so we
seed the env here. `setdefault` preserves any value CI already provides.
"""

import os

os.environ.setdefault("INTERNAL_API_SECRET", "test-internal-secret")
