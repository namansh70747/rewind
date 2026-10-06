"""Month-1 completeness: record -- python, proofs, mam API surface."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import httpx
from typer.testing import CliRunner

ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "demos" / "week2_mam"
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(DEMO))

from flightrecorder.cli import app  # noqa: E402
from flightrecorder import RunStore  # noqa: E402

from month1_proof import run_month1_proofs  # noqa: E402
from seed import DB_PATH, MANIFEST_PATH, seed  # noqa: E402
from server import _demo_payload  # noqa: E402


def test_month1_proofs_pass() -> None:
    out = run_month1_proofs(spike_verify_n=10, corpus_verify_n=2)
    assert out["status"] == "pass", out
    assert out["corpus"]["n_fixtures"] >= 10
    assert out["corpus"]["faithfulness_pct"] == 100.0
    assert all(s["status"] == "pass" for s in out["spikes"])


def test_seed_includes_month1_and_verify() -> None:
    manifest = seed(verify_n=20)
    assert manifest["month1"]["status"] == "pass"
    assert manifest["verify"]["passed"] is True
    assert manifest["divergence"]["index"] == 2
    assert json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))["month1"]["status"] == "pass"


def test_demo_api_exposes_gates() -> None:
    seed(verify_n=5)
    payload = _demo_payload()
    assert "M0" in payload["month1"]["gates"]
    assert "M1" in payload["month1"]["gates"]
    assert payload["month1"]["corpus"]["n_fixtures"] >= 10


def test_fr_record_unmodified_script(tmp_path: Path) -> None:
    agent = tmp_path / "agent.py"
    agent.write_text(
        "import httpx\n"
        "def main():\n"
        "    r = httpx.get('https://example.test/ping')\n"
        "    print(r.json())\n"
        "if __name__ == '__main__':\n"
        "    main()\n",
        encoding="utf-8",
    )
    db = str(tmp_path / "runs.db")

    def handle(self: httpx.HTTPTransport, request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"ok": True}, request=request)

    httpx.HTTPTransport.handle_request = handle  # type: ignore[method-assign]
    result = CliRunner().invoke(app, ["record", "--db", db, "--", "python", str(agent)])
    assert result.exit_code == 0, result.output
    store = RunStore(db)
    runs = store.list_runs()
    store.close()
    assert len(runs) == 1
    assert runs[0].n_boundaries == 1


def test_static_month1_assets() -> None:
    html = (DEMO / "static" / "index.html").read_text(encoding="utf-8")
    js = (DEMO / "static" / "app.js").read_text(encoding="utf-8")
    assert "Live capture" in html
    assert "Spikes" in html
    assert "Continue with Google" in html
    assert "Skip for demo" in html
    assert "Create account" in html
    assert "btn-verify" in html
    assert "btn-live" in html
    assert "/api/auth/login" in js
    assert "/auth/google" in js
    assert (DEMO / "static" / "app.js").is_file()


def test_demo_accounts_can_login(tmp_path: Path, monkeypatch: object) -> None:
    import auth as auth_mod

    monkeypatch.setattr(auth_mod, "USERS_DB", tmp_path / "users.db")
    issued = auth_mod.ensure_demo_accounts()
    assert issued[0]["email"] == "atyagi1_be24@thapar.edu"
    ok = auth_mod.login_email("atyagi1_be24@thapar.edu", "Rewind@2026")
    assert not isinstance(ok, str)
    _, user = ok
    assert user["name"] == "Aastha Tyagi"
    reviewer = auth_mod.login_email("mam@thapar.edu", "Rewind@2026")
    assert not isinstance(reviewer, str)


def test_email_register_and_login(tmp_path: Path, monkeypatch: object) -> None:
    import auth as auth_mod

    monkeypatch.setattr(auth_mod, "USERS_DB", tmp_path / "users.db")
    created = auth_mod.register_email("Aastha", "aastha@college.edu", "secret123")
    assert not isinstance(created, str)
    uid, user = created
    assert user["email"] == "aastha@college.edu"
    token = auth_mod.create_session(uid)
    assert auth_mod.user_from_token(token)["name"] == "Aastha"
    again = auth_mod.login_email("aastha@college.edu", "secret123")
    assert not isinstance(again, str)
    bad = auth_mod.login_email("aastha@college.edu", "wrongpass")
    assert isinstance(bad, str)
