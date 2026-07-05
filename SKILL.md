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
   — does **not** launch a new browser, reuses the existing session/cookies.
2. Navigates to `https://investors.sgx.com/market/stock-screener`.
3. Waits for the results table and the "Download as CSV" control to render.
4. Clicks it and captures the triggered download via Playwright's
   `expect_download()`.
5. Saves the file with a `sgx-screener-YYYYMMDD-HHMMSS.csv` name.

## Notes / troubleshooting

- If the click fails with a timeout, the page's DOM structure or button text
  may have changed — re-inspect the selector with a screenshot
  (`page.screenshot(path="debug.png")`) before adjusting `scripts/download_screener.py`.
- If a cookie-consent banner appears on first load, it may block the click.
  The script attempts a best-effort dismiss (see `dismiss_banners()`); extend
  it if SGX changes their banner.
- This reuses your one shared Chrome instance. If another agent/task is using
  it concurrently for something else, this will open a new tab in the same
  browser (not a conflict, just shares the same process/RAM budget).
