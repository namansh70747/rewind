"""Failed recaptures must never qualify stale provider evidence."""

from __future__ import annotations

import json
import runpy
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path


def test_failed_recapture_rejects_previous_success(tmp_path: Path) -> None:
    run = runpy.run_path("examples/month2_close_gates.py")["_run"]
    (tmp_path / "qualification.json").write_text(json.dumps({"passed": True}))
    result = run("nvidia", "fixture-only", tmp_path)
    assert result["exit_code"] != 0
    assert result["passed"] is False
