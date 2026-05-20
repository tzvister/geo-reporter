---
name: geo-reporter-setup
description: First-time setup for GEO Reporter. Installs Python dependencies required by the audit scripts (fetch_page.py, generate_pdf_report.py, citability_scorer.py, etc.). Run this once after installing the plugin. Triggers on "/geo-reporter:setup", "setup geo reporter", "install geo dependencies", or "geo setup".
allowed-tools: Bash
---

# GEO Reporter — First-Time Setup

Run this skill once after installing the plugin to install Python dependencies.

## Step 1: Check Python version

```bash
python3 --version
```

Python 3.8 or higher is required. If the version is lower than 3.8, stop and tell the user to upgrade Python first.

## Step 2: Install Python dependencies

```bash
pip install -r "${CLAUDE_PLUGIN_ROOT}/requirements.txt"
```

If `pip` fails with a permissions error, try:
```bash
pip install --user -r "${CLAUDE_PLUGIN_ROOT}/requirements.txt"
```

## Step 3: Verify core scripts are importable

```bash
python3 -c "import bs4, requests, validators; print('Core deps OK')"
```

If this fails, report the exact error to the user.

## Step 4: Optional — install Playwright for screenshot support

Playwright is used by `fetch_page.py` to handle JavaScript-rendered pages and Cloudflare-protected sites. It is optional but recommended for accurate bot-access probing.

Ask the user: "Install Playwright for screenshot support? (Adds ~200 MB, enables JS-rendered page analysis)"

If yes:
```bash
pip install playwright && playwright install chromium
```

## Step 5: Report result

Tell the user:
- Which dependencies were installed
- Whether Playwright was installed
- That setup is complete and they can now run `/geo audit <url>`

If any step failed, show the error and suggest: re-run with `--user` flag, check that Python 3.8+ is installed, or file an issue at the repo homepage.
