---
name: geo-botaccess
description: Live AI crawler reachability test, classified by bot purpose. Probes a website with 17 AI bot user-agents across four classes — live-retrieval (ChatGPT-User, Claude-User, Perplexity-User), search-index (OAI-SearchBot, Claude-SearchBot, PerplexityBot), traditional-search (Googlebot, Bingbot), and training (GPTBot, ClaudeBot, CCBot, Google-Extended, etc.) — to detect WAF/Cloudflare blocking that static robots.txt analysis cannot see. Reports per-class scores so a publisher posture (block training, allow retrieval) reads as healthy. Use whenever the user asks "can ChatGPT/Claude/Perplexity read my site", "is OAI-SearchBot/GPTBot/Googlebot blocked on X", "is Cloudflare blocking AI bots", "why isn't my site showing up in AI answers / ChatGPT search / Perplexity citations", "test bot access", "re-check after I fixed the WAF rule", or wants any empirical test of AI crawler reachability. Unlike geo-crawlers which reads declared policy, this skill measures what bots actually receive — perfect for the iterative fix-and-retest loop.
version: 1.0.0
author: geo-seo-claude
tags: [geo, ai-crawlers, waf, cloudflare, bot-access, empirical]
allowed-tools: Read, Bash, Write
---

# GEO Bot Access — Live AI Crawler Reachability Probe

## Purpose

`geo-crawlers` reads declared policy: it parses `robots.txt` and meta tags to figure out what a site *says* about AI crawlers. That's necessary but not sufficient. A site can have a permissive `robots.txt` while a Cloudflare bot management rule, an AWS WAF custom rule, or an Imperva bot allowlist silently returns `HTTP 403` to GPTBot, ClaudeBot, and Googlebot. The declared policy looks fine. The live reality is that AI search products see nothing.

This skill closes that gap. It runs a live empirical probe — fetching the site with each AI crawler user-agent and recording what comes back — and surfaces declared-vs-actual mismatches as critical findings.

It's deliberately scoped to be fast enough to run on every iteration of a fix-and-retest loop. When a user makes a Cloudflare WAF rule change or updates their bot management settings, they should be able to invoke this skill to verify the fix without waiting for a full audit.

## When to use this skill

Use it any time the user wants ground-truth AI crawler reachability for a specific URL. Triggering phrases include but are not limited to:

- "Can ChatGPT / Claude / Perplexity read my site?"
- "Is GPTBot blocked on example.com?"
- "Is Cloudflare blocking AI bots?"
- "Why isn't my site showing up in AI answers / ChatGPT search / Perplexity?"
- "Test bot access for X"
- "Re-check after I fixed the WAF rule"
- "Audit AI crawler reachability"
- "Run a bot access scan"

If the user only wants a static review of `robots.txt` directives, prefer `geo-crawlers`. If the user wants the full GEO audit, use `geo-audit` (which calls `geo-technical`, which calls this same probe internally — so the bot check is included automatically).

## Bot classes — why this matters

The probe groups bots into four classes because lab fleets are split by purpose, and the GEO impact of blocking differs sharply between them. A site that blocks training while allowing retrieval (the NYT/WSJ/Reuters/BBC pattern) is the canonical *healthy publisher* posture — flat scoring would mislabel it as "partially blocked".

| Class | Bots | What blocking does to GEO |
|---|---|---|
| **Live-retrieval** | ChatGPT-User, Claude-User, Perplexity-User | **Highest impact.** These fetch a page on demand when a user asks a question. Blocking removes user-triggered citations entirely. |
| **Search-index** | OAI-SearchBot, Claude-SearchBot, PerplexityBot | **High impact.** These index pages for AI search results. Blocking removes the site from ChatGPT Search / Claude / Perplexity citations. Botify 2025 logs show OAI-SearchBot is ~256% more active on news/publishing sites than GPTBot — for publishers, this is the bot that matters. |
| **Traditional search** | GoogleBot, BingBot | **High impact, separate concern.** Blocking these kills regular Google/Bing indexing, which also feeds Google AI Overviews and Bing/Copilot. Almost always unintentional — flag loudly. |
| **Training** | GPTBot, ClaudeBot, anthropic-ai, Google-Extended, Applebot-Extended, CCBot, Bytespider, Meta-ExternalAgent, cohere-ai | **Near-zero GEO impact.** Lab docs explicitly state this content is not used in live answers. Many publishers block these intentionally and still appear in AI citations. **Do not recommend unblocking.** |

The single most valuable finding this skill produces is the asymmetric mismatch: **retrieval/search bots blocked at the WAF while training bots pass cleanly.** That pattern is invisible to flat reachability tools, and it's exactly the configuration that silently removes a site from AI answers while a robots.txt review looks fine.

## How it works

The probe is implemented as the `bots` mode of `scripts/fetch_page.py`. It does the following in one pass:

1. **Browser baseline** — fetches the URL with a normal Chrome user-agent so we know what real content looks like (size, body, headers).
2. **JS challenge detection** — checks the baseline body for Cloudflare challenge markers (`cf-challenge`, `cf-turnstile`, "checking your browser", etc.). If a challenge is detected, the probe transparently falls back to a Playwright headless browser fetch so the comparison baseline is real content rather than a block page. If Playwright isn't installed, the probe degrades gracefully and switches to status-only block detection.
3. **WAF / CDN fingerprinting** — inspects the baseline response headers and `Set-Cookie` to identify which security product is in front of the site. Detects Cloudflare, Akamai, Imperva Incapsula, Sucuri, AWS CloudFront, AWS WAF, AWS ELB, F5 BIG-IP, F5 BIG-IP ASM, Fastly, Azure Front Door, Barracuda, Wallarm, StackPath, Google Frontend. Identifying the specific product matters because remediation differs completely per product — see "Recommendation playbooks" below.
4. **Per-bot probes** — replays the request with each of 17 AI crawler user-agents across the four classes above. For each bot the probe records HTTP status, body length, content similarity to the baseline, **and the bot's class and operator**. A bot is considered blocked if any of:
   - status is 403, 406, 429, or 503
   - body matches Cloudflare challenge markers (the "200 OK with a disguised block page" case)
   - body is non-trivially smaller AND content similarity to baseline is suspiciously low (silent content stripping)
5. **Per-class scoring** — each class scores 0–100 independently based on the share of blocked bots in that class. The overall score weights retrieval (live + search) at 0.5, traditional search at 0.35, and training at 0.15. A JS-challenge-with-no-Playwright penalty (–30) is applied to the retrieval and search classes only, since non-browser bots can't bypass interstitials.

## Workflow

Follow these steps when this skill triggers.

### Step 1 — Run the probe

Invoke the script and capture its JSON output:

```bash
python scripts/fetch_page.py <url> bots
```

The output is a single JSON object with this shape:

```json
{
  "url": "https://example.com/",
  "baseline": {"status": 200, "length": 523601, "used_playwright": true},
  "js_challenge_detected": true,
  "wafs_detected": [{"product": "Cloudflare", "evidence": "cf-ray header"}],
  "probes": [
    {"bot": "GPTBot", "class": "training", "operator": "OpenAI",
     "status": 200, "length": 513540, "similarity": 0.85,
     "blocked": false, "block_reason": null},
    {"bot": "OAI-SearchBot", "class": "search-index", "operator": "OpenAI",
     "status": 403, "length": 673, "similarity": null,
     "blocked": true, "block_reason": "http_403"}
  ],
  "class_scores": {
    "live-retrieval":     {"total": 3, "blocked": 0, "score": 100},
    "search-index":       {"total": 3, "blocked": 3, "score": 0},
    "traditional-search": {"total": 2, "blocked": 0, "score": 100},
    "training":           {"total": 9, "blocked": 9, "score": 0}
  },
  "verdict": "MOSTLY_BLOCKED",
  "overall_score": 60,
  "errors": []
}
```

Parse this JSON in Bash with `python -c` or `jq`. Don't re-fetch the URL — the JSON is the source of truth. The `class` and `operator` fields on each probe are the primary axis for grouping the report.

### Step 2 — Cross-reference declared policy

Run the existing `robots` mode to get static `robots.txt` analysis:

```bash
python scripts/fetch_page.py <url> robots
```

Then walk every entry in `probes[]` from Step 1 and compare against the declared status from Step 2. The four interesting cases are:

| Live result | Declared in robots.txt | Interpretation |
|---|---|---|
| Allowed | Allowed | Healthy. No action. |
| **Blocked** | **Allowed** | **Critical mismatch.** Declared policy says the bot is welcome, but a WAF / bot management rule is overriding it. This is the #1 finding to surface — the user almost certainly didn't intend this. |
| Allowed | Disallowed | Soft mismatch. Site is technically reachable but the bot is supposed to honour robots.txt. Worth mentioning. |
| Blocked | Disallowed | Consistent. Likely intentional. No action unless the user wants to change policy. |

**Prioritise mismatches by class.** A "blocked + allowed" finding for a **search-index or live-retrieval** bot is the headline finding — that's the exact configuration that silently removes a site from AI answers. Mismatches on training bots are footnote-tier; mention them only if the user is doing a deep audit. Mismatches on traditional-search bots (Googlebot/Bingbot) get their own prominent callout regardless of class — see Step 4.

### Step 3 — Read the score and verdict

The probe emits per-class scores and an overall verdict. **Don't recompute them** — they're in the JSON. Use the verdict directly as the headline.

Verdict mapping (from `class_scores.live-retrieval`, `search-index`, `traditional-search`, `training`):

| Verdict | Meaning | When it fires |
|---|---|---|
| `OPEN` | Everything reachable, including training | retrieval ≥ 90 AND traditional ≥ 90 AND training ≥ 70 |
| `HEALTHY_PUBLISHER` | Retrieval and traditional fully open; training blocked deliberately | retrieval ≥ 90 AND traditional ≥ 90 AND training < 70 |
| `PARTIALLY_BLOCKED` | Some retrieval/search bots blocked | retrieval ≥ 70 AND traditional ≥ 70 |
| `MOSTLY_BLOCKED` | Major retrieval or search loss | retrieval ≥ 40 OR traditional ≥ 40 |
| `BLOCKED` | Site invisible to AI search | everything below 40 |

**`HEALTHY_PUBLISHER` is the canonical NYT/WSJ/Reuters/BBC posture and is a *good* result for GEO.** Do not recommend unblocking training bots when this verdict fires — it's intentional and well-supported by 2025 publisher-log analyses (Botify, Cloudflare, TollBit). Mention the posture is healthy and move on to any actual mismatches.

The `overall_score` field is a single number for tracking iteration-over-iteration progress. Use the verdict as the qualitative headline; use the score for diff comparisons.

### Step 4 — Generate recommendations

Recommendations should be concrete and product-specific. Use the WAF fingerprint from `wafs_detected` to give the user the exact dashboard path or config snippet for the product they're actually running.

**Recommend by class, not by bot.** Group blocked bots by class first, then by operator. A user-facing recommendation should read like *"Cloudflare is blocking your live-retrieval bots (ChatGPT-User, Claude-User, Perplexity-User) — this directly removes you from on-demand AI citations"*, not a flat list of 12 bot names. The class context tells the user how much it matters.

**Do not recommend unblocking training bots.** If the only blocked bots are in the `training` class and the verdict is `HEALTHY_PUBLISHER`, the right report is *"Your retrieval and search bots are reachable; training bots are blocked, which is intentional and matches the major-publisher pattern. No action needed."* The 2025 GEO consensus (Aleyda Solis, iPullRank, Ahrefs, Semrush, Cloudflare) treats training-blocking as orthogonal to AI visibility.

#### Recommendation playbooks

**Cloudflare detected + bots blocked:**
> Cloudflare is blocking [bot list]. Fix in the Cloudflare dashboard:
> 1. Security → Bots → Configure Bot Management
> 2. Set "Verified Bots" to **Allow** (this covers GPTBot, ClaudeBot, Googlebot, Bingbot via Cloudflare's verified bot directory)
> 3. If using WAF Custom Rules, add an exception:
>    - Expression: `(cf.client.bot) or (cf.verified_bot_category eq "AI Crawler")`
>    - Action: Skip → All remaining custom rules
> 4. If using Super Bot Fight Mode, set "Verified Bots" to Allow and only challenge "Likely Automated" / "Definitely Automated" categories.

**Cloudflare JS challenge on baseline:**
> Cloudflare is serving a JavaScript interstitial to all non-browser visitors. Non-browser HTTP clients — which is every AI crawler — cannot execute JavaScript and see the challenge page instead of your content. This makes the site invisible to AI search regardless of any robots.txt allowance. Fix in Cloudflare dashboard → Security → Bots → set Verified Bots to Allow so Cloudflare's verified bot directory bypasses the challenge automatically.

**AWS WAF detected + bots blocked:**
> AWS WAF is blocking [bot list]. Fix in the AWS Console:
> 1. AWS WAF → Web ACLs → select your ACL → Rules
> 2. Add a rule with a `ByteMatchStatement` matching `User-Agent` contains the bot name (e.g. `GPTBot`)
> 3. Action: **Allow**
> 4. Place the rule above any blanket bot-blocking rule so it takes precedence.

**Imperva Incapsula detected + bots blocked:**
> Imperva Cloud WAF is blocking [bot list]. Fix in the Cloud WAF console:
> 1. Site Settings → Bot Access Control
> 2. Add the bot's User-Agent to the **Good Bot Allowlist**
> 3. Save and propagate (changes take ~5 minutes)

**Sucuri detected + bots blocked:**
> Sucuri Firewall is blocking [bot list]. Fix:
> 1. Sucuri dashboard → Settings → Whitelist
> 2. Add the bot User-Agent strings under "Whitelist by User-Agent"

**Akamai detected + bots blocked:**
> Akamai Bot Manager is blocking [bot list]. Fix:
> 1. Akamai Control Center → Security → Bot Manager → Custom Bot Categories
> 2. Add the AI search bots to a custom category with action "Allow"
> 3. Or set the relevant Akamai-managed AI bot categories to "Allow"

**No WAF detected, bots blocked:**
> A custom server / application rule is blocking [bot list]. Look in:
> - `.htaccess` (Apache) — search for `BrowserMatch` or `RewriteCond %{HTTP_USER_AGENT}`
> - `nginx.conf` (Nginx) — search for `if ($http_user_agent ...`
> - Application middleware — many CMS plugins (Wordfence, MalCare) maintain bot blocklists

**Googlebot is blocked (any product):**
> Surface this **separately and prominently**, even if the user only asked about AI bots. A Googlebot 403 affects regular Google Search indexing, not just AI search — the site may be deindexing without anyone noticing. This is almost always unintentional.

### Step 5 — Format the output

Present the findings as:

1. A one-line headline: `Verdict: <VERDICT> — overall <X>/100`
2. The WAF/CDN line (e.g. `Behind: Cloudflare (cf-ray header)`)
3. **Per-class score line:** `Live-retrieval 100 · Search-index 0 · Traditional-search 100 · Training 0` — one row, four numbers, so the user sees at a glance which class is in trouble.
4. **Four bot tables, one per class**, in this order: Live-retrieval, Search-index, Traditional-search, Training. Within each table, rows have `bot · operator · status · ✓/✗`. Collapse the Training table to a one-liner (`Training: 9/9 blocked — see "training-blocked is healthy" note above`) when the verdict is `HEALTHY_PUBLISHER`, since the detail isn't actionable.
5. The "declared vs actual" mismatch section, **with retrieval/search mismatches first** and training mismatches last (or omitted when verdict is `HEALTHY_PUBLISHER`).
6. Prioritised recommendations grouped by class (Critical = retrieval/search/traditional blocked → Medium = training mismatches → Info = healthy postures to keep).
7. Suggested next action for the user (e.g. "Want me to draft the Cloudflare WAF rule for OAI-SearchBot?", or "Re-run after the fix to verify").

Keep it scannable. The user is iterating — they want to see the score change, find the new findings, and act, not read prose.

## Edge cases to mention to the user

- **Bot verification by IP** — some sites correctly reject fake bot user-agents from residential IPs while letting the real Googlebot through via reverse-DNS verification. This probe always comes from the user's machine, so a 403 to "Googlebot" doesn't *definitively* prove the real Googlebot is blocked. It strongly suggests UA-based rules they should audit, but mention this nuance when reporting Googlebot blocks specifically.
- **Rate limiting vs bot blocking** — if the same bot returns 200 on one run and 429 on the next, the site may be rate-limiting rather than bot-blocking. The probe flags 429 as blocked, which is a reasonable simplification but worth mentioning if the pattern looks time-based.
- **JS challenge baseline degradation** — if `js_challenge_detected` is true and `baseline.used_playwright` is false, the similarity-based block detection becomes unreliable (every response is being compared against a challenge page). Status-code detection still works, but warn the user that the report is best-effort.
- **Identical responses across bots** — if every bot returns the same response (whether 200 or 403), it's likely UA-agnostic — either fully open or fully blocked at a layer that doesn't inspect User-Agent (IP-based, geo-based). Mention this so the user looks in the right place.
- **Google-Extended and Applebot-Extended are signals, not crawlers.** Google and Apple don't actually issue HTTP requests with these user-agents — they're robots.txt tokens that signal "don't use this content for training." The probe still tests them so the report is complete, but a 200 or 403 here only tells you about WAF UA filtering, not about whether the operator actually honours the opt-out. Treat results as informational.
- **`anthropic-ai` is legacy.** Anthropic's current docs list ClaudeBot, Claude-User, Claude-SearchBot. The `anthropic-ai` user-agent appears deprecated; conservative practice is to keep it blocked regardless. The probe still tests it for backwards-compat with older configurations.
- **Bot-class definitions can drift.** Lab fleets are policy-defined and can shift without announcement (OpenAI revised ChatGPT-User policy mid-2025 without notice). Re-audit lab documentation every ~90 days for the high-stakes classes (live-retrieval, search-index). The four-class structure here matches OpenAI/Anthropic/Perplexity as of 2026 — verify before relying on it.

## Re-running for iteration

This skill is designed for the fix-and-retest loop. When the user reports making a change (e.g. "I added the Cloudflare rule"), simply re-invoke `python scripts/fetch_page.py <url> bots` and diff against the previous run. **Diff per-class scores rather than just the overall** — the most informative deltas are per-class (e.g. "live-retrieval went from 0 to 100, training stayed at 0 (intentional)"). The fastest user-facing summary is: "Live-retrieval 0 → 100, Search-index 0 → 100. ChatGPT-User, Claude-User, Perplexity-User now 200. Cloudflare WAF rule is working."
