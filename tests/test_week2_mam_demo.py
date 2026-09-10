"""Week-2 mam demo — first_divergence + verify 100x + API smoke."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "demos" / "week2_mam"
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(DEMO))

from flightrecorder import RunStore, first_divergence  # noqa: E402

from seed import DB_PATH, MANIFEST_PATH, seed  # noqa: E402
from server import _demo_payload  # noqa: E402


def test_seed_bisect_and_verify_100() -> None:
    # Keep stub from seed; verify uses cassette playback (kill-switch).
    manifest = seed(verify_n=100)
    assert manifest["divergence"]["index"] == 2
    assert "same input" in manifest["divergence"]["reason"]
    assert manifest["verify"]["passed"] is True
    assert manifest["verify"]["n"] == 100
    assert manifest["verify"]["unique_fingerprints"] == 1

    store = RunStore(DB_PATH)
    good = store.load(manifest["good_run_id"])
    failed = store.load(manifest["failed_run_id"])
    assert len(good.boundaries) == 3
    assert len(failed.boundaries) == 3
    result = first_divergence(good, failed)
    assert result.diverged
    assert result.index == 2
    store.close()

    assert MANIFEST_PATH.is_file()
    disk = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    assert disk["good_run_id"] == manifest["good_run_id"]


def test_demo_api_payload_shape() -> None:
    seed(verify_n=5)  # faster for API shape; full 100 covered above
    payload = _demo_payload()
    assert payload["good"]["n_boundaries"] == 3
    assert payload["failed"]["n_boundaries"] == 3
    assert payload["divergence"]["index"] == 2
    assert payload["divergence"]["good_summary"] != payload["divergence"]["failed_summary"]
    assert "leave your umbrella" in payload["divergence"]["good_summary"].lower()
    assert "umbrella" in payload["divergence"]["failed_summary"].lower()


def test_static_assets_present() -> None:
    assert (DEMO / "static" / "index.html").is_file()
    assert (DEMO / "static" / "app.js").is_file()
    assert (DEMO / "static" / "styles.css").is_file()
