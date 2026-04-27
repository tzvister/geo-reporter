# Changelog

All notable changes to GEO Reporter are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

GEO Reporter is a fork of, and is highly influenced by, [zubair-trabzada/geo-seo-claude](https://github.com/zubair-trabzada/geo-seo-claude). Pre-fork history lives on the upstream repository; this changelog documents work as the project carries forward under its own line of development.

## [Unreleased]

### Added

- **Content Signals check** ([#4](https://github.com/tzvister/geo-reporter/pull/4)) — non-scoring scan for `Content-Signal:` directives in robots.txt (IETF draft `draft-romm-aipref-contentsignals`). Surfaced in `geo-crawlers` Step 6 and `geo-ai-visibility` Step 3. Reuses the already-fetched robots.txt, no extra HTTP request.
- **Agent-readiness signals in `geo-technical`** ([#4](https://github.com/tzvister/geo-reporter/pull/4)) — RFC 8288 `Link:` header parsing for `api-catalog` / `service-doc` / `mcp-server-card` rel types (no extra request, captured in the existing Step 1 fetch), plus an opt-in `Accept: text/markdown` content-negotiation probe (one extra request, non-penalising). Both are non-scoring.
- **`ai-input` recognised as a Content-Signal key** ([#7](https://github.com/tzvister/geo-reporter/pull/7)) — used in production by cloudflare.com alongside the IETF draft's keys. Added to the valid-keys enumeration to avoid false-positive "unknown key" warnings on the canonical reference site.
- **`CONTRIBUTING.md`** ([#6](https://github.com/tzvister/geo-reporter/pull/6)) — review-cadence SLA (~7 days), fork-and-PR flow, attribution policy for ported commits, MIT licensing note. Adapted from upstream PR #44 by @ahernandez-developer with author attribution preserved on the commit.
- **Claude PR review workflow** ([#8](https://github.com/tzvister/geo-reporter/pull/8)) — `.github/workflows/claude-review.yml` auto-reviews PRs from outside contributors and any PR with the `needs-review` label.
- **`needs-review` label** for opting your own PRs into Claude review.

### Changed

- **Report filenames now include the audited domain slug** ([#5](https://github.com/tzvister/geo-reporter/pull/5)) — `GEO-CLIENT-REPORT-<DOMAIN-SLUG>.md` and `GEO-REPORT-<DOMAIN-SLUG>.pdf` (e.g. `acme.com` → `ACME-COM`). Fixes silent overwrites when running multiple audits in the same directory. Convention propagated through `geo/SKILL.md`, `skills/geo-report/SKILL.md`, and `skills/geo-report-pdf/SKILL.md`.

### Fixed

- **Broken `geo-llms-txt` skill reference** ([#3](https://github.com/tzvister/geo-reporter/pull/3) — upstream PR [#50](https://github.com/zubair-trabzada/geo-seo-claude/pull/50)) — `skills/geo-report/SKILL.md` referenced a non-existent skill, silently dropping llms.txt assessment from generated reports. Corrected to `geo-llmstxt`.
- **Pin `rich<14.0.0`** ([#3](https://github.com/tzvister/geo-reporter/pull/3) — upstream PR [#54](https://github.com/zubair-trabzada/geo-seo-claude/pull/54)) — the previous `<15.0.0` constraint allowed silent major-version bumps to rich 14.x.

### Security

- **Disable Flask debug mode by default** ([#3](https://github.com/tzvister/geo-reporter/pull/3) — upstream PR [#51](https://github.com/zubair-trabzada/geo-seo-claude/pull/51)) — `scripts/webapp/app.py` previously hardcoded `debug=True`, exposing the Werkzeug interactive debugger (RCE-equivalent if reachable). Now opt-in via `FLASK_DEBUG=true` env var.
- **Validate URL scheme in `fetch_page()`** ([#3](https://github.com/tzvister/geo-reporter/pull/3) — upstream PR [#52](https://github.com/zubair-trabzada/geo-seo-claude/pull/52)) — reject `file://` / `ftp://` / non-http schemes before any network call. Closes the SSRF vector when caller-supplied URLs reach `requests.get(allow_redirects=True)`.
- **Extend URL-scheme guard to `probe_ai_crawlers()`** ([#3](https://github.com/tzvister/geo-reporter/pull/3)) — same threat model as `fetch_page()`, same defence applied.
- **Domain-pin URLs in `llmstxt_generator`** ([#3](https://github.com/tzvister/geo-reporter/pull/3) — upstream PR [#53](https://github.com/zubair-trabzada/geo-seo-claude/pull/53)) — second-pass description fetcher previously trusted URLs discovered during crawl. Now skips cross-origin URLs (still emits the link in llms-full.txt, just doesn't fetch a description for it).
- **Bound stdin reads in `generate_pdf_report.py`** ([#3](https://github.com/tzvister/geo-reporter/pull/3) — upstream PR [#54](https://github.com/zubair-trabzada/geo-seo-claude/pull/54)) — 10 MB ceiling with overflow detection (`read(N+1)` pattern). Prevents OOM from oversized stdin pipes.

## [0.1.0] — 2026-04-27

Inaugural release of GEO Reporter as a distinct project.

### Added

- **Live AI crawler reachability probe** (`geo-botaccess` skill, `bots` mode of `scripts/fetch_page.py`). Replays the homepage as each AI crawler user-agent, fingerprints the WAF/CDN, detects Cloudflare JS challenges with optional Playwright fallback, and surfaces declared-vs-actual mismatches as critical findings. Detects 16+ WAF/CDN products with product-specific remediation playbooks.
- **Bot-class taxonomy.** AI crawlers are now classified into four classes — `live-retrieval`, `search-index`, `traditional-search`, `training` — so the GEO impact of blocking can be scored accurately. Per-class scores plus a `HEALTHY_PUBLISHER` verdict so the canonical "block training, allow retrieval" publisher posture (NYT/WSJ/Reuters/BBC pattern) reads as healthy.
- **New AI crawler probes:** OAI-SearchBot, Claude-SearchBot, Claude-User, Perplexity-User. Bot count 13 → 17.
- `BOT_CLASSES` constant and `class` + `operator` fields on every probe in the JSON output.
- 8 new tests covering bot-class metadata, canonical class assignments, and verdict-logic across OPEN / HEALTHY_PUBLISHER / PARTIALLY_BLOCKED / MOSTLY_BLOCKED / BLOCKED postures (60 tests total, all passing).
- LICENSE: NOTICE-style preamble explaining the fork relationship; preserves Zubair Trabzada's original copyright (MIT requirement) and adds Tal Oron + contributors.
- README: "Highly influenced by" attribution block linking to the upstream project.
- This `CHANGELOG.md`.

### Changed

- **Project rename: `geo-seo-claude` → `geo-reporter`.** Install URLs, repository URL, banner alt text, sub-skill `author:` frontmatter, and rendered output strings all updated.
- Banner SVG: replaced the "SEO" block-letters row with a "REPORTER" wordmark in the same gradient.
- README description and architecture tree updated for the new project identity.
- `scripts/fetch_page.py`: `AI_CRAWLERS` restructured from `name -> ua` to `name -> {ua, class, operator}`. `AI_SEARCH_BOTS` retained as a derived back-compat alias.
- `scripts/fetch_page.py`: `probe_ai_crawlers()` now emits per-class scores, an overall score weighted `0.5·retrieval + 0.35·traditional + 0.15·training`, and a `verdict` field.
- `geo-botaccess/SKILL.md`: new "Bot classes" section explaining the four-class taxonomy and GEO-impact ranking; per-class report tables; explicit "do not recommend unblocking training" rule; edge-case notes on legacy `anthropic-ai` and signals-only `Google-Extended`/`Applebot-Extended`.
- `geo-technical/SKILL.md`: bot count and output-field references updated.
- User-facing strings in `scripts/generate_pdf_report.py`, `scripts/crm_dashboard.py`, `scripts/brand_scanner.py`, and `scripts/webapp/templates/*.html` rebranded.

### Removed

- Upstream-author Skool community funnel section in README, replaced with a neutral Contributing stub.
- `geo-seo-claude` branding from rendered output across CLI banners, PDF report headers, and webapp page titles.

[Unreleased]: https://github.com/tzvister/geo-reporter/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/tzvister/geo-reporter/releases/tag/v0.1.0
