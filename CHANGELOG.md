# Changelog

All notable changes to GEO Reporter are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

GEO Reporter is a fork of, and is highly influenced by, [zubair-trabzada/geo-seo-claude](https://github.com/zubair-trabzada/geo-seo-claude). Pre-fork history lives on the upstream repository; this changelog documents work as the project carries forward under its own line of development.

## [Unreleased]

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
