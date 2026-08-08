"""Scaffolding smoke test.

This is a placeholder that only checks the package imports and exposes a version.
It will be expanded into a real test suite in Phase 0 once product code exists.
"""

import flightrecorder


def test_version_is_non_empty_string() -> None:
    """The package should expose a non-empty, version-looking ``__version__``."""
    version = flightrecorder.__version__
    assert isinstance(version, str)
    assert version
    assert version.count(".") >= 2
