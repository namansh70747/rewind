"""Weeks 1-4 mam demo — milestones, bisect, verify 100x, store dedup, tamper."""

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


def test_seed_weeks_1_to_4_and_verify_100() -> None:
    manifest = seed(verify_n=100)
    assert manifest["divergence"]["index"] == 2
    assert "same input" in manifest["divergence"]["reason"]
    assert manifest["verify"]["passed"] is True
    assert manifest["verify"]["n"] == 100
    assert manifest["verify"]["unique_fingerprints"] == 1
    assert manifest["store"]["dedup_ok"] is True
    assert manifest["tamper"]["caught"] is True
    assert manifest["tamper"]["localized"] is True
    assert [m["week"] for m in manifest["milestones"]] == [1, 2, 3, 4]
    assert all(m["status"] == "pass" for m in manifest["milestones"])

    store = RunStore(DB_PATH)
    good = store.load(manifest["good_run_id"])
    failed = store.load(manifest["failed_run_id"])
    assert len(good.boundaries) == 3
    assert first_divergence(good, failed).index == 2
    store.close()
    assert json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))["good_run_id"] == manifest[
        "good_run_id"
    ]


def test_demo_api_includes_milestones_and_store() -> None:
    seed(verify_n=5)
    payload = _demo_payload()
    assert len(payload["milestones"]) == 4
    assert payload["store"]["blob_count"] >= 1
    assert payload["divergence"]["good_summary"] != payload["divergence"]["failed_summary"]
    assert payload["tamper"]["caught"] is True


def test_static_assets_present() -> None:
    assert (DEMO / "static" / "index.html").is_file()
    assert (DEMO / "static" / "app.js").is_file()
    assert (DEMO / "static" / "styles.css").is_file()
