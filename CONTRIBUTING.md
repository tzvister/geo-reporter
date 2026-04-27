# Contributing to GEO Reporter

Thanks for considering a contribution. Bug reports, fixes, new schema templates, platform-readiness updates, and lab-bot reclassifications as the AI search landscape evolves are all in scope and welcome.

## Review cadence

PRs are reviewed within ~7 days. If a week passes without a response, ping the PR — I may have missed the notification.

## How to contribute

### Reporting bugs
- Search [existing issues](https://github.com/tzvister/geo-reporter/issues) first.
- If yours is new, open one with a clear title, a reproducer, and what behaviour you expected vs. what happened. Include the OS, Python version, and Claude Code version when relevant.

### Suggesting features
- Open a feature request issue. A short rationale ("I want this because…") makes triage faster than a long spec.
- For larger ideas, a [Discussion](https://github.com/tzvister/geo-reporter/discussions) is lower-friction than an issue.

### Pull requests
The standard fork-and-PR flow:

1. Fork `tzvister/geo-reporter`, create a topic branch off `main`.
2. Make your change. Keep PRs focused — one logical change per PR.
3. Add or update tests where applicable. Run `python -m pytest tests/` locally.
4. If your change is user-visible, add an entry under `## [Unreleased]` in `CHANGELOG.md`.
5. Open the PR against `main`. Reference any related issue.

## Style guidelines

### Commit messages
- Imperative mood, present tense: "Add X", not "Added X" / "Adds X"
- First line ≤72 chars; blank line; longer body if needed
- Reference issues/PRs in the body, not the subject

### Code
- Match surrounding style. Prefer small, obvious changes over clever ones.
- Don't add abstractions for hypothetical future requirements.

### Skill changes (`skills/*/SKILL.md` and `agents/*.md`)
- Keep the front-matter `name`, `description`, `version`, `allowed-tools` accurate.
- If you're adding scoring logic, document the rubric in the same file.

## Attribution policy

When porting commits from another fork or merging cherry-picks, original authorship is preserved on the commit (`Author:` header). If you're picking up someone else's stalled work, mention them in the PR body so they get credit and a notification.

## Licensing

By submitting a PR, you agree your contribution is licensed under the project's MIT license. The original `zubair-trabzada/geo-seo-claude` upstream copyright is preserved in `LICENSE`; new work is added to that copyright line.

## Questions?

Open a Discussion or email the maintainer (see `git log`).
