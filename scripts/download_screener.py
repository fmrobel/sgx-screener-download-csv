#!/usr/bin/env python3
"""
Download the SGX Stock Screener CSV by driving the existing headless Chrome
(CDP on port 18800) instead of hitting api.sgx.com directly.

The screener's toolbar is rendered in a way that no DOM-based selector,
shadow-DOM search, or accessibility-tree lookup can find (confirmed via
testing) -- so this clicks a fixed pixel coordinate in a fixed-size viewport,
which is fast and reliable as long as the page layout doesn't change.

Usage:
    python3 download_screener.py [--outdir DIR] [--cdp-url URL] [--timeout SECONDS] [--download-xy X,Y]
"""
import argparse
import asyncio
import os
import sys
import time

try:
    from playwright.async_api import async_playwright
except ImportError:
    print("ERROR: playwright not installed. Run: pip install playwright --break-system-packages", file=sys.stderr)
    sys.exit(1)

TARGET_URL = "https://investors.sgx.com/market/stock-screener"
DEFAULT_CDP_URL = "http://127.0.0.1:18800"
DEFAULT_OUTDIR = os.path.expanduser("~/sgx-data/screener")
VIEWPORT = {"width": 1600, "height": 1000}
DEFAULT_DOWNLOAD_XY = (1258, 157)   # position of "Download as CSV" in the toolbar
DEFAULT_CUSTOMISE_XY = (1410, 157)  # position of "Customise" in the toolbar
DEFAULT_DISPLAY_ALL_XY = (1328, 210)  # position of the "Display All" toggle icon in the panel
DEFAULT_APPLY_XY = (1546, 818)       # position of "Apply" button in the panel


async def probe_customise(cdp_url: str, outdir: str, timeout_s: int, customise_xy):
    """Diagnostic-only: open the screener, click Customise, screenshot the
    opened panel, and stop -- so we can measure coordinates for the
    'Display all' icon and 'Apply' button before wiring up the real flow."""
    os.makedirs(outdir, exist_ok=True)
    timeout_ms = timeout_s * 1000
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp(cdp_url)
        context = await browser.new_context(viewport=VIEWPORT)
        page = await context.new_page()
        await page.goto(TARGET_URL, wait_until="networkidle", timeout=timeout_ms)
        await page.wait_for_timeout(6000)
        await page.mouse.click(*customise_xy)
        await page.wait_for_timeout(1500)
        shot_path = os.path.join(outdir, f"customise-panel-{int(time.time())}.png")
        await page.screenshot(path=shot_path, full_page=True)
        print(f"SAVED PROBE SCREENSHOT: {shot_path}")
        await page.close()


async def run(cdp_url: str, outdir: str, timeout_s: int, download_xy, customise_xy, display_all_xy, apply_xy):
    os.makedirs(outdir, exist_ok=True)
    timeout_ms = timeout_s * 1000

    async with async_playwright() as p:
        try:
            browser = await p.chromium.connect_over_cdp(cdp_url)
        except Exception as e:
            print(f"ERROR: could not connect to CDP at {cdp_url}: {e}", file=sys.stderr)
            print("Is the existing headless Chrome session running? See openclaw-browser-setup-runbook.md", file=sys.stderr)
            sys.exit(2)

        context = await browser.new_context(viewport=VIEWPORT)
        page = await context.new_page()

        try:
            await page.goto(TARGET_URL, wait_until="networkidle", timeout=timeout_ms)
            # The screener's canvas-rendered UI needs noticeably longer than
            # networkidle to become fully interactive (click handlers bind
            # after data finishes populating). Wait generously before clicking.
            await page.wait_for_timeout(6000)

            # Step 1: open the Customise panel.
            await page.mouse.click(*customise_xy)
            await page.wait_for_timeout(1200)

            # Step 2: click "Display All" twice (toggles it off then on,
            # which selects every column -- confirmed working via testing).
            await page.mouse.click(*display_all_xy)
            await page.wait_for_timeout(500)
            await page.mouse.click(*display_all_xy)
            await page.wait_for_timeout(500)

            # Step 3: Apply.
            await page.mouse.click(*apply_xy)
            await page.wait_for_timeout(1500)

            download = None
            last_error = None
            for attempt in range(3):
                try:
                    async with page.expect_download(timeout=15000) as download_info:
                        await page.mouse.click(*download_xy)
                    download = await download_info.value
                    break
                except Exception as e:
                    last_error = e
                    await page.wait_for_timeout(4000)  # give it more time before retrying

            if download is None:
                raise last_error

            filepath = os.path.join(outdir, download.suggested_filename)
            await download.save_as(filepath)
            print(f"SAVED: {filepath}")
        except Exception as e:
            debug_path = os.path.join(outdir, f"debug-{int(time.time())}.png")
            try:
                await page.screenshot(path=debug_path, full_page=True)
                print(f"FAILED: {e}\nDebug screenshot saved to: {debug_path}", file=sys.stderr)
            except Exception:
                print(f"FAILED: {e}", file=sys.stderr)
            sys.exit(1)
        finally:
            await page.close()


def main():
    parser = argparse.ArgumentParser(description="Download SGX Stock Screener CSV via existing headless Chrome CDP session.")
    parser.add_argument("--outdir", default=DEFAULT_OUTDIR, help="Directory to save the CSV into")
    parser.add_argument("--cdp-url", default=DEFAULT_CDP_URL, help="Chrome CDP endpoint (default: http://127.0.0.1:18800)")
    parser.add_argument("--timeout", type=int, default=30, help="Timeout in seconds for page/download operations")
    parser.add_argument("--download-xy", default=f"{DEFAULT_DOWNLOAD_XY[0]},{DEFAULT_DOWNLOAD_XY[1]}",
                         help="Pixel coordinates 'x,y' of the Download-as-CSV button in a 1600x1000 viewport")
    parser.add_argument("--customise-xy", default=f"{DEFAULT_CUSTOMISE_XY[0]},{DEFAULT_CUSTOMISE_XY[1]}",
                         help="Pixel coordinates 'x,y' of the Customise button in a 1600x1000 viewport")
    parser.add_argument("--display-all-xy", default=f"{DEFAULT_DISPLAY_ALL_XY[0]},{DEFAULT_DISPLAY_ALL_XY[1]}",
                         help="Pixel coordinates 'x,y' of the Display All toggle icon in the Customise panel")
    parser.add_argument("--apply-xy", default=f"{DEFAULT_APPLY_XY[0]},{DEFAULT_APPLY_XY[1]}",
                         help="Pixel coordinates 'x,y' of the Apply button in the Customise panel")
    parser.add_argument("--probe-customise", action="store_true",
                         help="Diagnostic mode: click Customise, screenshot the opened panel, then exit "
                              "(used to measure coordinates for Display-all / Apply)")
    args = parser.parse_args()

    def parse_xy(s):
        x_str, y_str = s.split(",")
        return (float(x_str.strip()), float(y_str.strip()))

    download_xy = parse_xy(args.download_xy)
    customise_xy = parse_xy(args.customise_xy)
    display_all_xy = parse_xy(args.display_all_xy)
    apply_xy = parse_xy(args.apply_xy)

    if args.probe_customise:
        asyncio.run(probe_customise(args.cdp_url, args.outdir, args.timeout, customise_xy))
    else:
        asyncio.run(run(args.cdp_url, args.outdir, args.timeout, download_xy, customise_xy, display_all_xy, apply_xy))


if __name__ == "__main__":
    main()
