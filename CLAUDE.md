# CLAUDE.md — project context for Claude Code

This file is read automatically by Claude Code when working in this repo. It captures project conventions, common workflows, and gotchas so I don't have to re-derive them every session.

## What this repo is

GEO Reporter — a Claude Code skill bundle for Generative Engine Optimization (GEO) audits. Highly influenced by, and forked from, [zubair-trabzada/geo-seo-claude](https://github.com/zubair-trabzada/geo-seo-claude); now maintained on its own line of development.

The user-facing entry is the `/geo` slash command. Sub-skills under `skills/geo-*/` cover specific audit dimensions (citability, AI crawler access, schema, technical, content, etc.). Python utilities under `scripts/` do the heavy lifting (page fetching, bot probing, PDF generation).

## Repo layout (the parts that matter)

| Path | What's there |
|---|---|
| `geo/SKILL.md` | Main `/geo` skill orchestrator |
| `skills/geo-*/SKILL.md` | 15 sub-skills, each focused on one audit dimension |
| `agents/geo-*.md` | 5 parallel subagents used by `geo-audit` |
| `scripts/fetch_page.py` | Page fetching, robots.txt parsing, **live AI crawler probe** (`bots` mode) |
| `scripts/citability_scorer.py` | AI citability scoring engine |
| `scripts/brand_scanner.py` | Brand mention detection |
| `scripts/llmstxt_generator.py` | llms.txt validation & generation |
| `scripts/generate_pdf_report.py` | PDF report generator (ReportLab) |
| `tests/` | pytest suite (60 tests at v0.2.0) |
| `.github/workflows/claude-review.yml` | Claude PR review on `needs-review` label |
| `CHANGELOG.md` | Keep a Changelog format, semver |

## Skill scoring conventions

- The `geo-botaccess` skill classifies AI crawlers into 4 classes: `live-retrieval`, `search-index`, `traditional-search`, `training`. Per-class scores; overall score weighted 0.5 retrieval / 0.35 traditional / 0.15 training. The `HEALTHY_PUBLISHER` verdict captures the canonical NYT/WSJ/Reuters/BBC posture (block training, allow retrieval) — do not flag this as a problem.
- Non-scoring checks (Content Signals, RFC 8288 Link headers, Markdown content negotiation in `geo-technical`) surface pass/recommendation but don't move the numeric score. They're emerging-spec signals; penalising absence would be unfair.
- When extending bot lists (e.g. a new lab announces a crawler), add `{ua, class, operator}` in `scripts/fetch_page.py:AI_CRAWLERS`, and update the `BOT_CLASSES` tuple if introducing a genuinely new class.

## Local development workflow

To iterate on a skill or test a PR live in Claude Code without re-installing:

```bash
./dev-link.sh         # replace ~/.claude/skills/geo* with symlinks into this repo
# edit anything in the repo, or check out a different branch
# Claude Code picks up the changes immediately
./dev-unlink.sh       # exit dev mode, install frozen copy from current branch
```

While `dev-link.sh` is active, **whatever branch is checked out is what Claude Code runs**. Don't run `/geo` audits on real client work while sitting on a WIP branch.

To install a clean release-quality copy from the repo:
```bash
./install.sh
```

`install.sh` is repo-aware: if run from this directory, it copies from local files instead of cloning. Both `install.sh` and `dev-unlink.sh` preserve any user-only skills (e.g. `geo-observe`) that aren't part of GEO Reporter.

## Testing

```bash
python -m pytest tests/
```

60/60 should pass on `main`. New Python in `scripts/` should come with matching tests in `tests/`. SKILL.md changes are docs-only; no automated tests for them, but verify by running `/geo <subcommand>` against a real URL after merging.

## Release process

Releases follow [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) + semver:

1. Cut `[Unreleased]` in `CHANGELOG.md` into `[X.Y.Z] — YYYY-MM-DD`
2. Add entries grouped as Added / Changed / Deprecated / Removed / Fixed / Security
3. Update the `[Unreleased]` and `[X.Y.Z]` link refs at the bottom
4. Merge the release PR into main
5. `gh release create vX.Y.Z --title "vX.Y.Z — <theme>" --notes "..."` with the changelog content adapted for release notes

## Claude PR review workflow

`.github/workflows/claude-review.yml` runs Claude on PRs labelled `needs-review`. Triggered manually only — outside contributors cannot self-trigger. Capped at 25 turns, ~$0.20–0.50 per review, 2–5 min. Uses Sonnet for code-review depth.

When you (Claude Code, working in this repo) iterate on the workflow file:

- The trigger is `pull_request_target`, so the workflow file is **read from main**, not the PR branch. Test workflow changes by merging to main, then triggering on a separate PR.
- Required `permissions:` include `id-token: write` for OIDC, `contents: read`, `pull-requests: write`, `issues: write`.
- The action does an OIDC → Claude App token exchange. We pass `github_token: ${{ secrets.GITHUB_TOKEN }}` explicitly to bypass that exchange (it requires the Claude GitHub App installed on the repo with backend propagation; the bypass posts comments as `github-actions[bot]` instead of `Claude[bot]` but works without app dependency).
- `claude_args` must include `--allowedTools "mcp__github_inline_comment__create_inline_comment,Bash(gh pr comment:*),Bash(gh pr diff:*),Bash(gh pr view:*)"` or Claude reviews silently — the comment-posting tools are gated behind that allowlist.
- A custom `prompt:` overrides the action's default review behaviour. If you set one, include explicit instructions on how to post the review (use the inline-comment MCP tool + `gh pr comment` for summary), or it'll run for 6 minutes and post nothing.

Cost-control levers in the workflow:

- `pull_request_target: [labeled]` only (no `opened` / `synchronize`) — the workflow doesn't auto-fire
- `paths:` filter excludes pure-docs PRs even when labelled
- `--max-turns 25` hard cap

## Attribution conventions

When porting commits from upstream (`zubair-trabzada/geo-seo-claude`) or any other fork:

- Cherry-pick to preserve the original `Author:` field on the commit
- @-mention the original author in the porting PR body
- Add a "Contributors" section to the relevant `CHANGELOG.md` release entry
- For ports of automated PRs (e.g. NLPM-generated by xiaolai), the commit author is `claude[bot]` — that's correct; xiaolai gets credit via PR-level @-mention

## Things that should NOT be in this repo

- The `geo-observe` skill — it's a separate parallel implementation that lives only in `~/.claude/skills/geo-observe/`. Don't add it here.
- Per-client audit outputs (e.g. `GEO-CLIENT-REPORT-*.md` / `GEO-REPORT-*.pdf`). The `examples/` dir is for demonstrations; real client work belongs outside the repo.
- API keys, tokens, or `~/.geo-prospects/` data. These live in the user's environment, never in the repo.

## Quick links

- [README.md](README.md) — public-facing project description
- [CONTRIBUTING.md](CONTRIBUTING.md) — contributor-facing flow with this same dev-mode info
- [CHANGELOG.md](CHANGELOG.md) — release history
- [LICENSE](LICENSE) — MIT, with upstream attribution
