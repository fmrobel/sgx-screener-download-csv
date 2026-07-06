---
name: sgx-screener-download
description: >
  Downloads the SGX Stock Screener CSV export from investors.sgx.com by driving
  the existing headless Chrome (CDP port 18800) to the page and clicking
  "Download as CSV". Use when: (1) user wants fresh SGX screener data,
  (2) the sgx-backfill pipeline needs a new screener snapshot, (3) any request
  to "download the screener", "pull SGX CSV", "update stock screener data".
  This avoids api.sgx.com WAF/TLS-fingerprint blocking entirely by using a real
  browser session against the public investors.sgx.com frontend instead of the
  API directly.
---

# SGX Screener CSV Download

Drives the existing OpenClaw headless Chrome (CDP on `127.0.0.1:18800`) to
`investors.sgx.com/market/stock-screener`, clicks **Download as CSV**, and saves
the resulting file with a timestamped name.

## Prerequisites

- The existing headless Chrome CDP session on port 18800 must already be running
  (per `openclaw-browser-setup-runbook.md`).
- `playwright` Python package installed and pointed at the same Python
  environment OpenClaw uses to run skill scripts.

```bash
pip install playwright --break-system-packages
# Only need the driver, not new browsers -- we connect to the existing Chrome:
python3 -m playwright install-deps chromium 2>/dev/null || true
```

## Usage

```bash
python3 scripts/download_screener.py
# Optional: custom output directory
python3 scripts/download_screener.py --outdir /root/sgx-data/screener
```

On success it prints the saved file path to stdout, e.g.:

```
SAVED: /root/sgx-data/screener/sgx-screener-20260705-143012.csv
```

## How it works

1. Connects to the already-running Chrome via `connect_over_cdp("http://127.0.0.1:18800")`
   � does **not** launch a new browser, reuses the existing session/cookies.
2. Navigates to `https://investors.sgx.com/market/stock-screener` with a fixed
   1600x1000 viewport.
3. Waits for the results table to render.
4. Clicks the **fixed pixel coordinate** where "Download as CSV" sits in the
   toolbar (default `1258,157`) and captures the triggered download.
5. Saves the file with a `sgx-screener-YYYYMMDD-HHMMSS.csv` name.

### Why a coordinate click instead of a normal selector?

Extensive testing (CSS selectors, text matching, shadow-DOM search, and even
the browser's accessibility tree) found **no underlying DOM element** for the
toolbar controls -- the screener's toolbar appears to be rendered in a way
(e.g. canvas) that has no clickable DOM nodes at all. A real mouse click at
the pixel position where the button is visually rendered is the only
approach that reliably works.

## Notes / troubleshooting

- **If the click stops working** (e.g. SGX changes the page layout), the
  coordinate will drift. Re-run with `--download-xy` to try a new position,
  or generate a fresh full-page screenshot to re-measure:
  ```bash
  python3 -c "
  import asyncio
  from playwright.async_api import async_playwright
  async def main():
      async with async_playwright() as p:
          browser = await p.chromium.connect_over_cdp('http://127.0.0.1:18800')
          ctx = await browser.new_context(viewport={'width':1600,'height':1000})
          page = await ctx.new_page()
          await page.goto('https://investors.sgx.com/market/stock-screener', wait_until='networkidle')
          await page.wait_for_timeout(1500)
          await page.screenshot(path='/tmp/screener-layout.png', full_page=True)
  asyncio.run(main())
  "
  ```
  Open `/tmp/screener-layout.png` and measure the pixel position of the
  "Download as CSV" button, then pass it with `--download-xy X,Y`.
- This reuses your one shared Chrome instance. If another agent/task is using
  it concurrently for something else, this will open a new tab in the same
  browser (not a conflict, just shares the same process/RAM budget).
