"""Capture screenshots of the running dashboard for the project report.

Prerequisites: the Flask API on :5000 and Streamlit on :8501 must be running.

    python scripts/capture_screenshots.py                       # light appearance
    python scripts/capture_screenshots.py --appearance Dark --out docs/screenshots/dark

The script also prints the computed background colour of the app container, which is the
proof that the appearance switch actually took effect (light: rgb(255, 255, 255),
dark: rgb(16, 24, 33)).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

PAGES = [
    ("01_overview.png", "Overview"),
    ("02_airline_performance.png", "Airline performance"),
    ("03_airport_and_routes.png", "Airport and routes"),
    ("04_time_analysis.png", "Time analysis"),
    ("05_delay_causes_and_cancellations.png", "Delay causes and cancellations"),
]

VIEWPORT = {"width": 1680, "height": 1050}
RENDER_TIMEOUT_MS = 120_000
APPEARANCE_RADIO_INDEX = 1
NAV_RADIO_INDEX = 0


def app_background(page) -> str:
    return page.evaluate(
        "() => { const el = document.querySelector('.stApp');"
        " return el ? getComputedStyle(el).backgroundColor : 'not-found'; }"
    )


def capture(base_url: str, out_dir: Path, appearance: str) -> int:
    out_dir.mkdir(parents=True, exist_ok=True)
    failures = 0

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport=VIEWPORT)

        page.goto(base_url, wait_until="load", timeout=RENDER_TIMEOUT_MS)
        page.wait_for_selector('[data-testid="stPlotlyChart"]', timeout=RENDER_TIMEOUT_MS)
        page.wait_for_timeout(2000)

        sidebar = page.locator('[data-testid="stSidebar"]')
        radios = sidebar.locator('[data-testid="stRadio"]')

        if appearance.lower() != "light":
            radios.nth(APPEARANCE_RADIO_INDEX).get_by_text(appearance, exact=True).click()
            page.wait_for_timeout(5000)
            page.wait_for_selector('[data-testid="stPlotlyChart"]', timeout=30_000)

        print(f"appearance={appearance} background={app_background(page)}")

        for filename, label in PAGES:
            try:
                if label != "Overview":
                    radios.nth(NAV_RADIO_INDEX).get_by_text(label, exact=True).click()
                    page.wait_for_timeout(4500)
                    page.wait_for_selector('[data-testid="stPlotlyChart"]', timeout=30_000)
                target = out_dir / filename
                page.screenshot(path=str(target), full_page=True)
                print(f"[ok] {target}")
            except PlaywrightTimeoutError as exc:
                failures += 1
                print(f"[fail] {label}: {exc}")
            except Exception as exc:  # noqa: BLE001 - report and continue with the next page
                failures += 1
                print(f"[fail] {label}: {type(exc).__name__}: {exc}")

        browser.close()
    return failures


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Capture dashboard screenshots with Playwright")
    parser.add_argument("--base-url", default="http://127.0.0.1:8501")
    parser.add_argument("--out", type=Path, default=REPO_ROOT / "docs" / "screenshots")
    parser.add_argument("--appearance", default="Light", choices=["Light", "Dark"])
    args = parser.parse_args(argv)
    failures = capture(args.base_url, args.out, args.appearance)
    print(f"captured {len(PAGES) - failures}/{len(PAGES)} pages ({args.appearance})")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
