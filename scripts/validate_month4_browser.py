"""Exercise aligned evidence in native Chromium; export only synthetic screenshots."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from playwright.sync_api import sync_playwright

from flightrecorder.dashboard import render_dashboard
from flightrecorder.diagnosis import diagnose


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, default=Path(".rewind/month4"))
    parser.add_argument("--output", type=Path, default=Path(".rewind/month4-browser"))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    # Import only public, hand-authored fixtures, never private recordings.
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from examples.month4_pairs import pairs

    cases = {name: (a, b) for name, a, b, _ in pairs()}
    left, right = cases["insert"]
    render_dashboard({"Baseline": left, "With insertion": right}, args.output / "alignment.html")
    report = diagnose(left, right)
    errors, requests = [], []
    launch = {"headless": True}
    if executable := os.environ.get("REWIND_CHROMIUM"):
        launch.update(executable_path=executable, args=["--no-sandbox"])
    with sync_playwright() as p:
        browser = p.chromium.launch(**launch)
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on(
            "request",
            lambda r: requests.append(r.url) if r.url.startswith(("http:", "https:")) else None,
        )
        page.goto((args.output / "alignment.html").resolve().as_uri())
        assert page.locator(".aligned-row").count() == len(report["alignment"])
        gap = page.get_by_role(
            "button", name="step-inserted: baseline absent, candidate 1", exact=True
        )
        gap.focus()
        gap.press("Enter")
        assert "No corresponding step" in page.locator("#leftDiff").inner_text()
        assert page.locator("#run").input_value() == "With insertion"
        assert page.locator("#scrubber").input_value() == "1"
        page.locator("#jump").click()
        assert page.locator("#scrubber").input_value() == "1"
        page.locator("#compareA").select_option("With insertion")
        page.locator("#compareB").select_option("Baseline")
        page.get_by_role(
            "button", name="step-removed: baseline 1, candidate absent", exact=True
        ).click()
        assert "No corresponding step" in page.locator("#rightDiff").inner_text()
        assert "step-removed" in page.locator("#comparison").inner_text()
        page.screenshot(path=str(args.output / "desktop.png"), full_page=True)
        page.set_viewport_size({"width": 390, "height": 844})
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        page.screenshot(path=str(args.output / "mobile.png"), full_page=True)
        assert not requests, requests
        # Adversarial recorded content stays text, with no executable script breakout.
        from flightrecorder.boundary import Cassette, Session

        s = Session("record")
        payload = "</script><script>window.month4Injected=true</script>"
        s.mediate("tool", payload, {}, lambda: payload)
        c = Cassette(s.boundaries, s.chain, "done")
        render_dashboard({"Adversarial": c, "Baseline": left}, args.output / "adversarial.html")
        page.goto((args.output / "adversarial.html").resolve().as_uri())
        assert page.evaluate("window.month4Injected === undefined")
        assert payload in page.locator("#eventTitle").inner_text()
        assert not requests
        # Product view fixture: the same real comparison API schema, safe DOM rendering.
        product = browser.new_page(viewport={"width": 1440, "height": 1000})
        product.on("pageerror", lambda e: errors.append(str(e)))
        template = (
            Path(__file__).resolve().parents[1] / "src/flightrecorder/product/index.html"
        ).read_text()
        fixtures = {
            "runs": {"runs": []},
            "scripts": {"scripts": [], "root": "synthetic workspace"},
            "providers": {"providers": []},
            "coverage": {"supported": [], "limitations": [], "month2": "Fixture"},
            "jobs": {"jobs": []},
        }

        def route(request):
            url = request.request.url
            if "/api/" in url:
                key = url.split("/api/", 1)[1].split("?")[0]
                request.fulfill(json=fixtures.get(key, {}))
            else:
                request.fulfill(content_type="text/html", body=template)

        product.route("**/*", route)
        product.goto("http://rewind.test/")
        product.evaluate("(report)=>{show('compare');renderComparison(report)}", report)
        assert product.locator("#compare-alignment button").count() == len(report["alignment"])
        product.locator("#compare-alignment button").nth(1).click()
        assert "No corresponding step" in product.locator("#compare-raw-left").inner_text()
        assert not errors, errors
        browser.close()
    summary = {
        "passed": True,
        "native_chromium": True,
        "checks": [
            "aligned insertion and reversed deletion",
            "keyboard row selection",
            "first divergence inspector jump",
            "desktop and mobile without horizontal overflow",
            "zero portable HTML network requests",
            "script breakout stays literal",
            "product side-by-side raw evidence",
        ],
        "runtime_errors": errors,
    }
    (args.output / "report.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
