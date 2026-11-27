"""Apply PostgreSQL migrations and publish reviewed demo bundles."""

import argparse
import json
from pathlib import Path

from flightrecorder.product.hosted import LIMIT, RESOURCE, configuration, connection, save_recording


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("migrate", "publish-demo"))
    parser.add_argument("bundle", type=Path, nargs="?")
    args = parser.parse_args()
    if (args.action == "publish-demo") != (args.bundle is not None):
        parser.error("publish-demo requires a reviewed bundle path")
    with connection(configuration()) as db:
        if args.action == "migrate":
            db.execute("SELECT pg_advisory_xact_lock(628315)")
            db.execute(RESOURCE.joinpath("hosted.sql").read_text(encoding="utf-8"))
        else:
            with args.bundle.open("rb") as stream:
                payload = stream.read(LIMIT + 1)
            if len(payload) > LIMIT:
                parser.error("Bundle exceeds the hosted limit")
            run_id = save_recording(db, json.loads(payload), None)
    if args.action == "publish-demo":
        print(run_id)


if __name__ == "__main__":
    main()
