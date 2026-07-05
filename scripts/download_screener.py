#!/usr/bin/env python3
"""
Download the SGX Stock Screener CSV by driving the existing headless Chrome
(CDP on port 18800) instead of hitting api.sgx.com directly.

Usage:
    python3 download_screener.py [--outdir DIR] [--cdp-url URL] [--timeout SECONDS]
"""
import argparse
import asyncio
import os
import sys
import time

try:
    from playwright.async_api import async_playwright, TimeoutError as PWTimeoutError
except ImportError:
    print("ERROR: playwright not installed. Run: pip install playwright --break-system-packages", file=sys.stderr)
    sys.exit(1)

TARGET_URL = "https://investors.sgx.com/market/stock-screener"
DEFAULT_CDP_URL = "http://127.0.0.1:18800"
DEFAULT_OUTDIR = os.path.expanduser("~/sgx-data/screener")

# Candidate selectors for the download control -- tried in order.
DOWNLOAD_SELECTORS = [
    "text=Download as CSV",
    "button:has-text('Download as CSV')",
    "[aria-label='Download as CSV']",
    "[aria-label='Download']",
    "svg[data-icon='download']",
    "[class*='download' i] >> visible=true",
]

# Candidate selectors for cookie/consent banners that might block the click.
BANNER_DISMISS_SELECTORS = [
    "button:has-text('Accept')",
    "button:has-text('I Agree')",
    "button:has-text('Accept All')",
    "#onetrust-accept-btn-handler",
]


async def dismiss_banners(page):
    for sel in BANNER_DISMISS_SELECTORS:
        try:
            el = await page.wait_for_selector(sel, timeout=2000)
            if el:
                await el.click()
                await page.wait_for_timeout(500)
        except PWTimeoutError:
            continue
        except Exception:
            continue


async def click_download(page, timeout_ms):
    last_error = None
    for sel in DOWNLOAD_SELECTORS:
        try:
            await page.wait_for_selector(sel, timeout=timeout_ms)
            async with page.expect_download(timeout=timeout_ms) as download_info:
                await page.click(sel)
            return await download_info.value
        except Exception as e:
            last_error = e
            continue
    raise RuntimeError(f"Could not find/click download control. Last error: {last_error}")


async def run(cdp_url: str, outdir: str, timeout_s: int):
    os.makedirs(outdir, exist_ok=True)
    timeout_ms = timeout_s * 1000

    async with async_playwright() as p:
        try:
            browser = await p.chromium.connect_over_cdp(cdp_url)
        except Exception as e:
            print(f"ERROR: could not connect to CDP at {cdp_url}: {e}", file=sys.stderr)
            print("Is the existing headless Chrome session running? See openclaw-browser-setup-runbook.md", file=sys.stderr)
            sys.exit(2)

        # Always create a fresh context with an explicit desktop-sized viewport.
        # Reusing an existing context can inherit a narrow/mobile viewport, which
        # causes the SGX site to render icon-only buttons instead of the
        # text-labeled "Download as CSV" button our selectors look for.
        context = await browser.new_context(viewport={"width": 1600, "height": 1000})
        page = await context.new_page()

        try:
            await page.goto(TARGET_URL, wait_until="networkidle", timeout=timeout_ms)
            await dismiss_banners(page)
            # Give the results table a moment to finish rendering.
            await page.wait_for_timeout(1500)

            download = await click_download(page, timeout_ms)

            filename = f"sgx-screener-{time.strftime('%Y%m%d-%H%M%S')}.csv"
            filepath = os.path.join(outdir, filename)
            await download.save_as(filepath)
            print(f"SAVED: {filepath}")
        except Exception as e:
            debug_path = os.path.join(outdir, f"debug-{int(time.time())}.png")
            try:
                await page.screenshot(path=debug_path)
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
    args = parser.parse_args()

    asyncio.run(run(args.cdp_url, args.outdir, args.timeout))


if __name__ == "__main__":
    main()
