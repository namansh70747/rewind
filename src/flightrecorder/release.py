"""Fail-closed release evidence checklist; missing gates never become implicit passes."""

from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path

GATES = {
    "real_provider_replay": "Live OpenAI/Anthropic corpus and 50 replay checks",
    "spike_decision": "Reviewed spikes and go/pivot ADR",
    "corpus_redaction": "Reviewed real corpus secret scan and coverage audit",
    "format_approval": "Merged recording-format ADR and compatibility evidence",
    "real_demo": "Real failing-agent recording, intervention and recovery",
    "viewer_interop": "External Perfetto and OTel viewer acceptance",
    "fleet_quality": "Real fleet coverage and human cluster/neighbor review",
    "classifier_baseline": "Held-out reviewed labels beat independently collected prompted baseline",
    "performance": "Real workload latency/storage within an approved budget",
    "platforms": "Supported Python matrix plus platform smoke evidence",
    "code_owner_review": "Approving Code Owner review on release code",
    "remote_ci": "Green required CI checks on release code",
    "package_publication": "Maintainer verifies package ownership and publisher setup",
}


def release_check(manifest: Path) -> dict[str, Any]:
    """Verify local artifact digests and explicit human attestations.

    Does not validate external URLs/reviewer identity or substitute for GitHub branch
    protections. Publication still requires the protected release environment.
    Paths are confined to the evidence directory; no arbitrary commands execute.
    """
    data = json.loads(manifest.read_text())
    if (
        not isinstance(data, dict)
        or data.get("version") != 1
        or not isinstance(data.get("gates"), dict)
    ):
        raise ValueError("release manifest requires version=1 and a gates object")
    unknown = set(data["gates"]) - set(GATES)
    if unknown:
        raise ValueError("unknown release gates: " + ", ".join(sorted(unknown)))
    root = manifest.parent.resolve()
    rows = []
    for key, description in GATES.items():
        entry = data["gates"].get(key, {})
        status, detail = "blocked", "No reviewed evidence supplied"
        try:
            if not isinstance(entry, dict):
                raise ValueError("gate entry must be an object")
            if entry.get("status") == "passed":
                if not all(
                    isinstance(entry.get(name), str) and entry[name].strip()
                    for name in ("reviewer", "reference", "artifact", "sha256")
                ):
                    raise ValueError("pass requires reviewer, reference, artifact and sha256")
                artifact = (root / entry["artifact"]).resolve()
                if not artifact.is_relative_to(root) or not artifact.is_file():
                    raise ValueError(
                        "evidence artifact must be a file inside the manifest directory"
                    )
                if artifact.stat().st_size > 50 * 1024 * 1024:
                    raise ValueError("evidence artifact exceeds 50 MiB")
                if hashlib.sha256(artifact.read_bytes()).hexdigest() != entry["sha256"]:
                    raise ValueError("evidence artifact digest does not match")
                status, detail = (
                    "attested",
                    "Artifact digest verified; reviewer/reference are submitted attestations",
                )
            elif entry.get("status") not in {None, "blocked"}:
                raise ValueError(
                    "status must be blocked or passed; gates cannot be silently waived"
                )
            else:
                detail = str(entry.get("reason", detail))
        except (ValueError, OSError) as exc:
            detail = str(exc)
        rows.append({"gate": key, "description": description, "status": status, "detail": detail})
    return {
        "checklist_complete": all(row["status"] == "attested" for row in rows),
        "gates": rows,
        "interpretation": "Local evidence/attestation check, not proof of external approval or scientific validity.",
    }
