---
name: geo-botaccess
description: Live AI crawler reachability test. Probes a website with real AI bot user-agents (GPTBot, ClaudeBot, PerplexityBot, Googlebot, Bingbot, etc.) to detect WAF/Cloudflare blocking that static robots.txt analysis cannot see. Use this skill whenever the user asks "can ChatGPT/Claude/Perplexity read my site", "is GPTBot/Googlebot blocked on X", "is Cloudflare blocking AI bots", "WAF blocking AI crawlers", "why isn't my site showing up in AI answers", "test bot access", "re-check after I fixed the WAF rule", or wants any empirical test of AI crawler reachability on a specific URL. Unlike geo-crawlers which reads declared policy, this skill measures what bots actually receive — perfect for the iterative fix-and-retest loop.
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

## How it works

The probe is implemented as the `bots` mode of `scripts/fetch_page.py`. It does the following in one pass:

1. **Browser baseline** — fetches the URL with a normal Chrome user-agent so we know what real content looks like (size, body, headers).
2. **JS challenge detection** — checks the baseline body for Cloudflare challenge markers (`cf-challenge`, `cf-turnstile`, "checking your browser", etc.). If a challenge is detected, the probe transparently falls back to a Playwright headless browser fetch so the comparison baseline is real content rather than a block page. If Playwright isn't installed, the probe degrades gracefully and switches to status-only block detection.
3. **WAF / CDN fingerprinting** — inspects the baseline response headers and `Set-Cookie` to identify which security product is in front of the site. Detects Cloudflare, Akamai, Imperva Incapsula, Sucuri, AWS CloudFront, AWS WAF, AWS ELB, F5 BIG-IP, F5 BIG-IP ASM, Fastly, Azure Front Door, Barracuda, Wallarm, StackPath, Google Frontend. Identifying the specific product matters because remediation differs completely per product — see "Recommendation playbooks" below.
4. **Per-bot probes** — replays the request with each of 13 AI crawler user-agents (GPTBot, ChatGPT-User, ClaudeBot, anthropic-ai, PerplexityBot, Google-Extended, Applebot-Extended, GoogleBot, BingBot, CCBot, Bytespider, Meta-ExternalAgent, cohere-ai). For each bot the probe records HTTP status, body length, and content similarity to the baseline. A bot is considered blocked if any of:
   - status is 403, 406, 429, or 503
   - body matches Cloudflare challenge markers (the "200 OK with a disguised block page" case)
   - body is non-trivially smaller AND content similarity to baseline is suspiciously low (silent content stripping)

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
    {"bot": "GPTBot", "status": 200, "length": 513540, "similarity": 0.85, "blocked": false, "block_reason": null},
    {"bot": "GoogleBot", "status": 403, "length": 673193, "similarity": null, "blocked": true, "block_reason": "http_403"}
  ],
  "errors": []
}
```

Parse this JSON in Bash with `python -c` or `jq`. Don't re-fetch the URL — the JSON is the source of truth.

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

The mismatch case (live blocked + declared allowed) is the most valuable finding this skill produces. It exists *only* because we're doing live probing — static analysis would have missed it entirely.

### Step 3 — Score and verdict

Compute a simple score from the probe results so the user has a single number to track across iterations. Recommended scoring (this is intentionally lightweight — `geo-technical` and `geo-audit` have richer scoring):

- Start at 100
- Subtract 10 for each blocked bot in `AI_SEARCH_BOTS` (GPTBot, ChatGPT-User, ClaudeBot, PerplexityBot, Google-Extended, Applebot-Extended, GoogleBot, BingBot)
- Subtract 3 for each blocked training-only crawler (CCBot, Bytespider, Meta-ExternalAgent, cohere-ai, anthropic-ai)
- Subtract 30 if `js_challenge_detected` is true and `baseline.used_playwright` is false (the site is invisible to non-browser clients and we couldn't even bypass it for the scan)
- Floor at 0

Then assign a verdict:

| Score | Verdict |
|---|---|
| 90–100 | OPEN |
| 70–89 | PARTIALLY BLOCKED |
| 50–69 | MOSTLY BLOCKED |
| 0–49 | BLOCKED |

### Step 4 — Generate recommendations

Recommendations should be concrete and product-specific. Use the WAF fingerprint from `wafs_detected` to give the user the exact dashboard path or config snippet for the product they're actually running.

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

1. A one-line headline: `Score: X/100 — VERDICT`
2. The WAF/CDN line (e.g. `Behind: Cloudflare (cf-ray header)`)
3. A compact table of bots and their results, with `✓` for allowed and `✗` for blocked
4. The "declared vs actual" mismatch section if any mismatches exist
5. Prioritised recommendations (Critical → High → Medium)
6. Suggested next action for the user (e.g. "Want me to draft the Cloudflare WAF rule?", or "Run again after the fix to verify")

Keep it scannable. The user is iterating — they want to see the score change, find the new findings, and act, not read prose.

## Edge cases to mention to the user

- **Bot verification by IP** — some sites correctly reject fake bot user-agents from residential IPs while letting the real Googlebot through via reverse-DNS verification. This probe always comes from the user's machine, so a 403 to "Googlebot" doesn't *definitively* prove the real Googlebot is blocked. It strongly suggests UA-based rules they should audit, but mention this nuance when reporting Googlebot blocks specifically.
- **Rate limiting vs bot blocking** — if the same bot returns 200 on one run and 429 on the next, the site may be rate-limiting rather than bot-blocking. The probe flags 429 as blocked, which is a reasonable simplification but worth mentioning if the pattern looks time-based.
- **JS challenge baseline degradation** — if `js_challenge_detected` is true and `baseline.used_playwright` is false, the similarity-based block detection becomes unreliable (every response is being compared against a challenge page). Status-code detection still works, but warn the user that the report is best-effort.
- **Identical responses across bots** — if every bot returns the same response (whether 200 or 403), it's likely UA-agnostic — either fully open or fully blocked at a layer that doesn't inspect User-Agent (IP-based, geo-based). Mention this so the user looks in the right place.

## Re-running for iteration

This skill is designed for the fix-and-retest loop. When the user reports making a change (e.g. "I added the Cloudflare rule"), simply re-invoke `python scripts/fetch_page.py <url> bots` and diff against the previous run. The score is directly comparable. The fastest user-facing summary is: "Score went from 50 to 90. GPTBot, ClaudeBot, Googlebot all now returning 200. Cloudflare WAF rule is working."
