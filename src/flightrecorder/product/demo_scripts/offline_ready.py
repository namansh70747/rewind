"""Approved release check with all required checks present."""

from flightrecorder import tool


@tool(name="read_release_manifest", mutating=False)
def manifest() -> dict[str, list[str]]:
    return {"checks": ["smoke_tests", "database_backup", "rollback_plan"]}


if __name__ == "__main__":
    missing = {"smoke_tests", "database_backup", "rollback_plan"} - set(manifest()["checks"])
    if missing:
        raise ValueError("Release blocked: " + ", ".join(sorted(missing)))
    print("Result: ready")
