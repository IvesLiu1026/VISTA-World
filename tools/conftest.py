"""Repository-wide pytest hooks.

Known failures are listed in tools/tests/known_failures.json and run as
strict xfails, so the suite stays green while the debt stays visible: a listed
test that starts passing fails the run until its entry is removed.
"""

import json
from pathlib import Path

import pytest

_KNOWN_FAILURES = json.loads(
    (Path(__file__).parent / "tests" / "known_failures.json").read_text(encoding="utf-8")
)["tests"]


def pytest_collection_modifyitems(config, items):
    for item in items:
        reason = _KNOWN_FAILURES.get(item.nodeid)
        if reason is not None:
            item.add_marker(pytest.mark.xfail(reason=reason, strict=True))
