#!/usr/bin/env python3
"""
Fetch and parse web pages for GEO analysis.
Extracts HTML, text content, meta tags, headers, and structured data.
"""

import sys
import json
import re
from difflib import SequenceMatcher
from urllib.parse import urljoin, urlparse

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    print("ERROR: Required packages not installed. Run: pip install -r requirements.txt")
    sys.exit(1)

# AI crawler user agents used for live probing.
#
# Each bot carries a "class" tag because the labs themselves split their
# fleets by purpose, and the GEO impact differs sharply by class. Mixing
# them in a single bucket — as earlier versions of this module did —
# produces misleading verdicts: a publisher that blocks training while
# allowing retrieval (NYT, WSJ, Reuters, BBC pattern) is doing the
# right thing for AI visibility, but flat scoring would call them
# "partially blocked".
#
# The four classes:
#
#   training       — bulk-collects content for foundation-model training
#                    (GPTBot, ClaudeBot, CCBot, Google-Extended, etc.).
#                    Lab docs explicitly state this content is not used
#                    in live answers. Blocking has near-zero GEO impact.
#   search-index   — indexes pages for AI search results
#                    (OAI-SearchBot, Claude-SearchBot, PerplexityBot).
#                    Blocking removes the site from AI search citations.
#   live-retrieval — fetched on demand when a user asks a question
#                    (ChatGPT-User, Claude-User, Perplexity-User).
#                    Blocking prevents user-triggered citations.
#   traditional-search — Googlebot, Bingbot. Power Google AI Overviews
#                    and Bing/Copilot. Blocking is almost always a
#                    misconfiguration and worth flagging loudly.
#
# See OpenAI/Anthropic/Perplexity bot docs and the Cloudflare/Botify
# 2025 publisher-log analyses cited in the geo-botaccess SKILL.md.
AI_CRAWLERS = {
    # OpenAI
    "GPTBot": {
        "ua": "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; GPTBot/1.2; +https://openai.com/gptbot)",
        "class": "training",
        "operator": "OpenAI",
    },
    "OAI-SearchBot": {
        "ua": "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; OAI-SearchBot/1.0; +https://openai.com/searchbot)",
        "class": "search-index",
        "operator": "OpenAI",
    },
    "ChatGPT-User": {
        "ua": "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; ChatGPT-User/1.0; +https://openai.com/bot)",
        "class": "live-retrieval",
        "operator": "OpenAI",
    },
    # Anthropic
    "ClaudeBot": {
        "ua": "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; ClaudeBot/1.0; +https://www.anthropic.com/claude-bot)",
        "class": "training",
        "operator": "Anthropic",
    },
    "Claude-SearchBot": {
        "ua": "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; Claude-SearchBot/1.0; +https://www.anthropic.com/claudebot)",
        "class": "search-index",
        "operator": "Anthropic",
    },
    "Claude-User": {
        "ua": "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; Claude-User/1.0; +https://www.anthropic.com/claudebot)",
        "class": "live-retrieval",
        "operator": "Anthropic",
    },
    "anthropic-ai": {
        "ua": "anthropic-ai/1.0",
        "class": "training",
        "operator": "Anthropic",
    },
    # Perplexity
    "PerplexityBot": {
        "ua": "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; PerplexityBot/1.0; +https://perplexity.ai/perplexitybot)",
        "class": "search-index",
        "operator": "Perplexity",
    },
    "Perplexity-User": {
        "ua": "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; Perplexity-User/1.0; +https://perplexity.ai/perplexity-user)",
        "class": "live-retrieval",
        "operator": "Perplexity",
    },
    # Google / Apple training opt-out tokens. These aren't real crawlers
    # — they're robots.txt signals that the operator honours separately.
    # Probing them tests only WAF-side UA filtering; treat results as
    # informational rather than diagnostic of real bot reachability.
    "Google-Extended": {
        "ua": "Mozilla/5.0 (compatible; Google-Extended/1.0; +http://www.google.com/bot.html)",
        "class": "training",
        "operator": "Google",
    },
    "Applebot-Extended": {
        "ua": "Mozilla/5.0 (compatible; Applebot-Extended/1.0)",
        "class": "training",
        "operator": "Apple",
    },
    # Traditional search bots (blocking these is usually a mistake).
    # Surface separately because Googlebot 403 also kills regular
    # Google Search indexing, not just AI Overviews.
    "GoogleBot": {
        "ua": "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)",
        "class": "traditional-search",
        "operator": "Google",
    },
    "BingBot": {
        "ua": "Mozilla/5.0 (compatible; bingbot/2.0; +http://www.bing.com/bingbot.htm)",
        "class": "traditional-search",
        "operator": "Microsoft",
    },
    # Training-only crawlers. Often deliberately blocked by publishers
    # — that posture is GEO-healthy and the report should not penalise it.
    "CCBot": {
        "ua": "CCBot/2.0 (+https://commoncrawl.org/faq/)",
        "class": "training",
        "operator": "Common Crawl",
    },
    "Bytespider": {
        "ua": "Bytespider/1.0",
        "class": "training",
        "operator": "ByteDance",
    },
    "Meta-ExternalAgent": {
        "ua": "Meta-ExternalAgent/1.0 (+https://www.meta.com/)",
        "class": "training",
        "operator": "Meta",
    },
    "cohere-ai": {
        "ua": "cohere-ai/1.0",
        "class": "training",
        "operator": "Cohere",
    },
}

# The four bot classes, in priority order for verdict logic. The
# overall score weights these as 0.5 (retrieval = live + search),
# 0.35 (traditional search), 0.15 (training) — see probe_ai_crawlers().
BOT_CLASSES = (
    "live-retrieval",
    "search-index",
    "traditional-search",
    "training",
)

# Back-compat alias for callers and tests that still reference the
# flat "AI search bots" set. New code should use AI_CRAWLERS[name]["class"].
AI_SEARCH_BOTS = {
    name for name, meta in AI_CRAWLERS.items()
    if meta["class"] in ("search-index", "live-retrieval", "traditional-search")
}

# Substrings that indicate a Cloudflare interstitial / challenge page
# rather than real site content. Used both on the browser baseline
# (to detect that we need a Playwright fallback) and on individual bot
# responses (to detect "200 OK" responses that are actually challenge
# pages disguised as success).
CF_CHALLENGE_MARKERS = (
    "cf-challenge",
    "cf-turnstile",
    "ray id",
    "checking your browser",
    "attention required",
    "just a moment",
    "enable javascript and cookies",
    "cf-chl-bypass",
    "challenge-platform",
)

# WAF / CDN fingerprints. Each entry is (product_name, predicate, evidence)
# where the predicate is called with two pre-normalised arguments:
#
#   headers_lower:  dict[str, str] of response headers, both keys and
#                   values lowercased for case-insensitive matching
#   cookies_blob:   one big lowercase string with all Set-Cookie values
#                   concatenated, for cheap "name in blob" cookie tests
#
# Identifying the specific product matters because remediation differs
# completely per product. "Allow GPTBot in Cloudflare" is a different
# procedure than "Allow GPTBot in Imperva" or "Allow GPTBot in AWS WAF".
# Skills that consume this data give product-specific dashboard paths
# in their recommendations, which is far more actionable than a generic
# "configure your WAF" suggestion.
#
# Multiple products can legitimately stack (e.g. Cloudflare in front of
# AWS ELB), so detect_waf() returns a list rather than a single value.
WAF_FINGERPRINTS = (
    ("Cloudflare", lambda h, c: "cf-ray" in h, "cf-ray header"),
    ("Cloudflare", lambda h, c: "cloudflare" in h.get("server", ""), "server: cloudflare"),
    ("Cloudflare", lambda h, c: any(n in c for n in ("__cf_bm", "cf_clearance", "__cfduid")), "cf_bm/cf_clearance cookie"),
    ("AWS CloudFront", lambda h, c: "x-amz-cf-id" in h, "x-amz-cf-id header"),
    ("AWS WAF", lambda h, c: "x-amzn-waf-action" in h, "x-amzn-waf-action header"),
    ("AWS ELB", lambda h, c: "awselb" in h.get("server", ""), "server: awselb"),
    ("Akamai", lambda h, c: "akamaighost" in h.get("server", "") or "akamai" in h.get("server", ""), "server: AkamaiGHost"),
    ("Akamai", lambda h, c: any(k.startswith("x-akamai") for k in h), "x-akamai-* header"),
    ("Akamai", lambda h, c: "akamai-grn" in h, "akamai-grn header"),
    ("Sucuri", lambda h, c: "sucuri" in h.get("server", ""), "server: sucuri/cloudproxy"),
    ("Sucuri", lambda h, c: "x-sucuri-id" in h or "x-sucuri-cache" in h, "x-sucuri-* header"),
    ("Imperva Incapsula", lambda h, c: "x-iinfo" in h, "x-iinfo header"),
    ("Imperva Incapsula", lambda h, c: "incapsula" in h.get("x-cdn", ""), "x-cdn: Incapsula"),
    ("Imperva Incapsula", lambda h, c: "incap_ses" in c or "visid_incap" in c, "incap_ses cookie"),
    ("F5 BIG-IP", lambda h, c: "big-ip" in h.get("server", "") or "bigip" in h.get("server", ""), "server: BIG-IP"),
    ("F5 BIG-IP", lambda h, c: "bigipserver" in c, "BIGipServer cookie"),
    ("F5 BIG-IP ASM", lambda h, c: "x-waf-event-info" in h, "x-waf-event-info header"),
    ("Fastly", lambda h, c: "x-fastly-request-id" in h, "x-fastly-request-id header"),
    ("Fastly", lambda h, c: "fastly" in h.get("server", ""), "server: fastly"),
    ("Barracuda WAF", lambda h, c: "barra_counter_session" in c, "barra_counter_session cookie"),
    ("Wallarm", lambda h, c: "nginx-wallarm" in h or "wallarm" in h.get("server", ""), "wallarm header"),
    ("Azure Front Door", lambda h, c: "x-azure-ref" in h, "x-azure-ref header"),
    ("StackPath", lambda h, c: any(k.startswith("x-sp-") for k in h), "x-sp-* header"),
    ("Google Frontend", lambda h, c: "google frontend" in h.get("server", ""), "server: Google Frontend"),
)

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate",
}


def fetch_page(url: str, timeout: int = 30) -> dict:
    """Fetch a page and return structured analysis data."""
    result = {
        "url": url,
        "status_code": None,
        "redirect_chain": [],
        "headers": {},
        "meta_tags": {},
        "title": None,
        "description": None,
        "canonical": None,
        "h1_tags": [],
        "heading_structure": [],
        "word_count": 0,
        "text_content": "",
        "internal_links": [],
        "external_links": [],
        "images": [],
        "structured_data": [],
        "has_ssr_content": True,
        "security_headers": {},
        "errors": [],
    }

    parsed_url = urlparse(url)
    if parsed_url.scheme not in ("http", "https"):
        result["errors"].append(f"Unsupported URL scheme: {parsed_url.scheme!r}. Only http and https are allowed.")
        return result

    try:
        response = requests.get(
            url,
            headers=DEFAULT_HEADERS,
            timeout=timeout,
            allow_redirects=True,
        )

        # Track redirects
        if response.history:
            result["redirect_chain"] = [
                {"url": r.url, "status": r.status_code} for r in response.history
            ]

        result["status_code"] = response.status_code
        result["headers"] = dict(response.headers)

        # Security headers check
        security_headers = [
            "Strict-Transport-Security",
            "Content-Security-Policy",
            "X-Frame-Options",
            "X-Content-Type-Options",
            "Referrer-Policy",
            "Permissions-Policy",
        ]
        for header in security_headers:
            result["security_headers"][header] = response.headers.get(header, None)

        # Parse HTML
        soup = BeautifulSoup(response.text, "lxml")

        # Title
        title_tag = soup.find("title")
        result["title"] = title_tag.get_text(strip=True) if title_tag else None

        # Meta tags
        for meta in soup.find_all("meta"):
            name = meta.get("name", meta.get("property", ""))
            content = meta.get("content", "")
            if name and content:
                result["meta_tags"][name.lower()] = content
                if name.lower() == "description":
                    result["description"] = content

        # Canonical
        canonical = soup.find("link", rel="canonical")
        result["canonical"] = canonical.get("href") if canonical else None

        # Headings
        for level in range(1, 7):
            for heading in soup.find_all(f"h{level}"):
                text = heading.get_text(strip=True)
                result["heading_structure"].append({"level": level, "text": text})
                if level == 1:
                    result["h1_tags"].append(text)

        # Structured data (JSON-LD) — extract before decompose() mutates the tree
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string)
                result["structured_data"].append(data)
            except (json.JSONDecodeError, TypeError):
                result["errors"].append("Invalid JSON-LD detected")

        # SSR check — must run BEFORE decompose() mutates the tree
        js_app_roots = soup.find_all(
            id=re.compile(r"(app|root|__next|__nuxt)", re.I)
        )

        # Check SSR by measuring content inside framework root divs
        # before decompose() strips elements from the tree
        ssr_check_results = []
        for root_el in js_app_roots:
            inner_text = root_el.get_text(strip=True)
            ssr_check_results.append({
                "id": root_el.get("id", "unknown"),
                "text_length": len(inner_text),
            })

        # Text content — decompose non-content elements (destructive)
        for element in soup.find_all(["script", "style", "nav", "footer", "header"]):
            element.decompose()
        text = soup.get_text(separator=" ", strip=True)
        result["text_content"] = text
        result["word_count"] = len(text.split())

        # Links
        parsed_url = urlparse(url)
        base_domain = parsed_url.netloc
        for link in soup.find_all("a", href=True):
            href = urljoin(url, link["href"])
            link_text = link.get_text(strip=True)
            parsed_href = urlparse(href)
            if parsed_href.netloc == base_domain:
                result["internal_links"].append({"url": href, "text": link_text})
            elif parsed_href.scheme in ("http", "https"):
                result["external_links"].append({"url": href, "text": link_text})

        # Images
        for img in soup.find_all("img"):
            img_data = {
                "src": img.get("src", ""),
                "alt": img.get("alt", ""),
                "width": img.get("width"),
                "height": img.get("height"),
                "loading": img.get("loading"),
            }
            result["images"].append(img_data)

        # SSR assessment — use pre-decompose measurements + overall content
        if js_app_roots:
            for check in ssr_check_results:
                # Only flag as client-rendered if both the root div has
                # minimal content AND the overall page has little text.
                # Sites using SSR/prerendering (WordPress, LiteSpeed Cache,
                # Prerender.io) will have substantial text despite having
                # framework-style root divs.
                if check["text_length"] < 50 and result["word_count"] < 200:
                    result["has_ssr_content"] = False
                    result["errors"].append(
                        f"Possible client-side only rendering detected: "
                        f"#{check['id']} has minimal server-rendered content "
                        f"({result['word_count']} words on page)"
                    )

    except requests.exceptions.Timeout:
        result["errors"].append(f"Timeout after {timeout} seconds")
    except requests.exceptions.ConnectionError as e:
        result["errors"].append(f"Connection error: {str(e)}")
    except Exception as e:
        result["errors"].append(f"Unexpected error: {str(e)}")

    return result


def fetch_robots_txt(url: str, timeout: int = 15) -> dict:
    """Fetch and parse robots.txt for AI crawler directives."""
    parsed = urlparse(url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"

    ai_crawlers = [
        "GPTBot",
        "OAI-SearchBot",
        "ChatGPT-User",
        "ClaudeBot",
        "anthropic-ai",
        "PerplexityBot",
        "CCBot",
        "Bytespider",
        "cohere-ai",
        "Google-Extended",
        "GoogleOther",
        "Applebot-Extended",
        "FacebookBot",
        "Amazonbot",
    ]

    result = {
        "url": robots_url,
        "exists": False,
        "content": "",
        "ai_crawler_status": {},
        "sitemaps": [],
        "errors": [],
    }

    try:
        response = requests.get(robots_url, headers=DEFAULT_HEADERS, timeout=timeout)

        if response.status_code == 200:
            result["exists"] = True
            result["content"] = response.text

            # Parse for each AI crawler
            lines = response.text.split("\n")
            current_agent = None
            agent_rules = {}

            for line in lines:
                line = line.strip()
                if line.lower().startswith("user-agent:"):
                    current_agent = line.split(":", 1)[1].strip()
                    if current_agent not in agent_rules:
                        agent_rules[current_agent] = []
                elif line.lower().startswith("disallow:") and current_agent:
                    path = line.split(":", 1)[1].strip()
                    agent_rules[current_agent].append(
                        {"directive": "Disallow", "path": path}
                    )
                elif line.lower().startswith("allow:") and current_agent:
                    path = line.split(":", 1)[1].strip()
                    agent_rules[current_agent].append(
                        {"directive": "Allow", "path": path}
                    )
                elif line.lower().startswith("sitemap:"):
                    sitemap_url = line.split(":", 1)[1].strip()
                    # Handle case where "Sitemap:" splits off the "http"
                    if not sitemap_url.startswith("http"):
                        sitemap_url = "http" + sitemap_url
                    result["sitemaps"].append(sitemap_url)

            # Determine status for each AI crawler
            for crawler in ai_crawlers:
                if crawler in agent_rules:
                    rules = agent_rules[crawler]
                    if any(
                        r["directive"] == "Disallow" and r["path"] == "/"
                        for r in rules
                    ):
                        result["ai_crawler_status"][crawler] = "BLOCKED"
                    elif any(
                        r["directive"] == "Disallow" and r["path"] for r in rules
                    ):
                        result["ai_crawler_status"][crawler] = "PARTIALLY_BLOCKED"
                    else:
                        result["ai_crawler_status"][crawler] = "ALLOWED"
                elif "*" in agent_rules:
                    wildcard_rules = agent_rules["*"]
                    if any(
                        r["directive"] == "Disallow" and r["path"] == "/"
                        for r in wildcard_rules
                    ):
                        result["ai_crawler_status"][crawler] = "BLOCKED_BY_WILDCARD"
                    else:
                        result["ai_crawler_status"][crawler] = "ALLOWED_BY_DEFAULT"
                else:
                    result["ai_crawler_status"][crawler] = "NOT_MENTIONED"

        elif response.status_code == 404:
            result["errors"].append("No robots.txt found (404)")
            for crawler in ai_crawlers:
                result["ai_crawler_status"][crawler] = "NO_ROBOTS_TXT"
        else:
            result["errors"].append(
                f"Unexpected status code: {response.status_code}"
            )

    except Exception as e:
        result["errors"].append(f"Error fetching robots.txt: {str(e)}")

    return result


def fetch_llms_txt(url: str, timeout: int = 15) -> dict:
    """Check for llms.txt file."""
    parsed = urlparse(url)
    llms_url = f"{parsed.scheme}://{parsed.netloc}/llms.txt"
    llms_full_url = f"{parsed.scheme}://{parsed.netloc}/llms-full.txt"

    result = {
        "llms_txt": {"url": llms_url, "exists": False, "content": ""},
        "llms_full_txt": {"url": llms_full_url, "exists": False, "content": ""},
        "errors": [],
    }

    for key, check_url in [("llms_txt", llms_url), ("llms_full_txt", llms_full_url)]:
        try:
            response = requests.get(
                check_url, headers=DEFAULT_HEADERS, timeout=timeout
            )
            if response.status_code == 200:
                result[key]["exists"] = True
                result[key]["content"] = response.text
        except Exception as e:
            result["errors"].append(f"Error checking {check_url}: {str(e)}")

    return result


def extract_content_blocks(html: str) -> list:
    """Extract content blocks for citability analysis."""
    soup = BeautifulSoup(html, "lxml")

    # Remove non-content elements
    for element in soup.find_all(
        ["script", "style", "nav", "footer", "header", "aside"]
    ):
        element.decompose()

    blocks = []
    # Extract content sections (between headings)
    current_heading = None
    current_content = []

    for element in soup.find_all(
        ["h1", "h2", "h3", "h4", "h5", "h6", "p", "ul", "ol", "table", "blockquote"]
    ):
        tag = element.name

        if tag.startswith("h"):
            # Save previous block
            if current_content:
                text = " ".join(current_content)
                word_count = len(text.split())
                blocks.append(
                    {
                        "heading": current_heading,
                        "content": text,
                        "word_count": word_count,
                        "tag_types": list(
                            set(
                                [
                                    e.name
                                    for e in element.find_all_previous(
                                        ["p", "ul", "ol", "table"]
                                    )
                                ]
                            )
                        ),
                    }
                )
            current_heading = element.get_text(strip=True)
            current_content = []
        else:
            text = element.get_text(strip=True)
            if text:
                current_content.append(text)

    # Don't forget the last block
    if current_content:
        text = " ".join(current_content)
        blocks.append(
            {
                "heading": current_heading,
                "content": text,
                "word_count": len(text.split()),
            }
        )

    return blocks


def is_challenge_page(html: str, status_code: int) -> bool:
    """Detect a Cloudflare interstitial / WAF block page disguised as content.

    Cloudflare and similar products serve HTML challenge pages that look
    like real responses (sometimes even with a 200 status). The body
    contains characteristic markers like ``cf-challenge`` or
    "Checking your browser". We check the first 8 KB only because the
    markers always appear early in the document and bounding the check
    keeps it cheap on large pages.
    """
    head = (html or "")[:8000].lower()
    if status_code in (403, 503):
        if any(m in head for m in CF_CHALLENGE_MARKERS):
            return True
        # Cloudflare's own error pages are clearly branded — treat any
        # 403/503 served from Cloudflare as a challenge for the purposes
        # of "did this bot reach the real content".
        if "cloudflare" in head:
            return True
    if status_code == 200:
        if any(m in head for m in CF_CHALLENGE_MARKERS):
            return True
    return False


def detect_waf(response) -> list:
    """Fingerprint WAF/CDN products from response headers and cookies.

    Returns a list of ``{"product": str, "evidence": str}`` dicts. Multiple
    products may stack legitimately (e.g. Cloudflare in front of an AWS
    ELB), so the function never short-circuits — it walks the full
    fingerprint table and de-duplicates by product name, keeping the
    first piece of evidence found for each.

    Pure function over the headers, so it's trivial to unit-test by
    constructing a fake response object.
    """
    headers_lower = {k.lower(): str(v).lower() for k, v in response.headers.items()}

    # Some servers send Set-Cookie multiple times. requests exposes them
    # via the underlying response.raw object or via response.cookies, but
    # the cleanest cross-version path is to flatten the headers we already
    # have. We just need a string for substring matching.
    cookie_blob = headers_lower.get("set-cookie", "")

    seen = set()
    detected = []
    for product, predicate, evidence in WAF_FINGERPRINTS:
        if product in seen:
            continue
        try:
            if predicate(headers_lower, cookie_blob):
                detected.append({"product": product, "evidence": evidence})
                seen.add(product)
        except Exception:
            # A broken fingerprint should never break the whole scan.
            # Swallow and continue so a single bad predicate doesn't
            # take out detection for every other product.
            pass
    return detected


def _playwright_baseline(url: str, timeout_ms: int = 30000):
    """Fetch ``url`` with a real headless browser, for JS-challenged sites.

    Returns ``(status, html)`` on success or ``None`` if Playwright isn't
    installed or the fetch fails. We import inside the function so the
    rest of fetch_page.py keeps working when Playwright is missing —
    Playwright is in requirements.txt but graceful degradation matters
    for users on minimal installs.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return None

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            ctx = browser.new_context(user_agent=DEFAULT_HEADERS["User-Agent"])
            page = ctx.new_page()
            resp = page.goto(url, wait_until="networkidle", timeout=timeout_ms)
            status = resp.status if resp else 200
            html = page.content()
            browser.close()
            return status, html
    except Exception:
        return None


def _content_similarity(a: str, b: str) -> float:
    """Cheap text-similarity score in [0, 1] for the first 10 KB of two pages.

    Used to catch the case where a bot receives HTTP 200 with a totally
    different (often stripped or generic) body than the browser baseline.
    SequenceMatcher is good enough here — we don't need linguistic
    analysis, just "are these obviously the same page". The 10 KB cap
    keeps the comparison constant-time on long articles.
    """
    def normalise(text: str) -> str:
        return re.sub(r"\s+", " ", (text or "")[:10000]).strip().lower()
    return SequenceMatcher(None, normalise(a), normalise(b)).ratio()


def probe_ai_crawlers(url: str, timeout: int = 15) -> dict:
    """Live-probe a URL with AI crawler user-agents to detect WAF blocking.

    This is the empirical complement to ``fetch_robots_txt``. Static
    robots.txt analysis tells you what a site *declares*; this function
    tells you what AI bots *actually* receive. The two often disagree:
    a site can have a permissive robots.txt while a Cloudflare bot
    management rule silently returns 403 to GPTBot, ClaudeBot, and
    Googlebot. The declared policy looks fine; the live reality is
    that AI search products see nothing.

    Workflow:

      1. Fetch a browser baseline so we know what real content looks
         like (size, body, headers).
      2. Detect Cloudflare JS challenges on that baseline. If found,
         try a Playwright headless fallback so we have a usable
         reference for similarity comparison. If Playwright is missing,
         we degrade gracefully and rely on status-code / challenge-body
         detection alone.
      3. Fingerprint WAF/CDN products from the baseline headers — this
         drives product-specific remediation in downstream skills.
      4. Replay the request as each AI crawler in AI_CRAWLERS, comparing
         status, body length, and content similarity to the baseline.
         A bot is considered blocked if any of:
            - status is 403, 406, 429, or 503
            - body matches Cloudflare challenge markers (200 with a
              disguised block page)
            - body is non-trivially smaller AND content similarity to
              baseline is suspiciously low (silent content stripping)

    Returns a dict structured for JSON consumption by skills. All
    failures are captured in result["errors"] rather than raised — this
    matches the error-handling pattern used elsewhere in fetch_page.py.
    """
    result = {
        "url": url,
        "baseline": {
            "status": None,
            "length": None,
            "used_playwright": False,
        },
        "js_challenge_detected": False,
        "wafs_detected": [],
        "probes": [],
        "errors": [],
    }

    # --- 1. Browser baseline -------------------------------------------------
    try:
        baseline_resp = requests.get(
            url, headers=DEFAULT_HEADERS, timeout=timeout, allow_redirects=True
        )
    except Exception as e:
        result["errors"].append(f"Baseline fetch failed: {e}")
        return result

    baseline_html = baseline_resp.text or ""
    result["baseline"]["status"] = baseline_resp.status_code
    result["baseline"]["length"] = len(baseline_html)

    # --- 2. JS challenge detection + optional Playwright fallback -----------
    if is_challenge_page(baseline_html, baseline_resp.status_code):
        result["js_challenge_detected"] = True
        pw = _playwright_baseline(url)
        if pw is not None:
            pw_status, pw_html = pw
            if not is_challenge_page(pw_html, pw_status):
                # Playwright successfully bypassed the challenge — use
                # its rendered output as the comparison baseline so the
                # similarity scores below are meaningful.
                baseline_html = pw_html
                result["baseline"]["status"] = pw_status
                result["baseline"]["length"] = len(pw_html)
                result["baseline"]["used_playwright"] = True

    # --- 3. WAF / CDN fingerprinting ----------------------------------------
    # Run on the original requests response — Playwright bypassed the
    # challenge for the body, but the original headers are what tell us
    # which product is in front of the site.
    result["wafs_detected"] = detect_waf(baseline_resp)

    # --- 4. Per-bot probes ---------------------------------------------------
    # If the baseline is itself a challenge page that Playwright couldn't
    # bypass, similarity comparison is meaningless (every bot will look
    # "similar" to a challenge page). In that case we fall back to pure
    # status-code / challenge-marker detection.
    baseline_is_challenge = (
        result["js_challenge_detected"] and not result["baseline"]["used_playwright"]
    )

    for bot_name, meta in AI_CRAWLERS.items():
        bot_ua = meta["ua"]
        probe = {
            "bot": bot_name,
            "user_agent": bot_ua,
            "class": meta["class"],
            "operator": meta["operator"],
            "status": None,
            "length": None,
            "similarity": None,
            "blocked": False,
            "block_reason": None,
        }
        try:
            bot_resp = requests.get(
                url,
                headers={**DEFAULT_HEADERS, "User-Agent": bot_ua},
                timeout=timeout,
                allow_redirects=True,
            )
        except Exception as e:
            probe["blocked"] = True
            probe["block_reason"] = f"request_error: {e}"
            result["probes"].append(probe)
            continue

        bot_html = bot_resp.text or ""
        probe["status"] = bot_resp.status_code
        probe["length"] = len(bot_html)

        # Block detection rules in priority order. We record the first
        # rule that matches so the downstream skill can give a precise
        # explanation in its recommendations.
        if bot_resp.status_code in (403, 406, 429, 503):
            probe["blocked"] = True
            probe["block_reason"] = f"http_{bot_resp.status_code}"
        elif is_challenge_page(bot_html, bot_resp.status_code):
            probe["blocked"] = True
            probe["block_reason"] = "challenge_page"
        elif not baseline_is_challenge:
            # Compare against the real browser baseline. We only flag
            # via similarity when both the body is much smaller AND the
            # similarity is low — either signal alone has too many false
            # positives (mobile-optimised pages, A/B tests, etc.).
            similarity = _content_similarity(baseline_html, bot_html)
            probe["similarity"] = round(similarity, 3)
            length_ratio = (
                probe["length"] / result["baseline"]["length"]
                if result["baseline"]["length"]
                else 1.0
            )
            if similarity < 0.4 and length_ratio < 0.5:
                probe["blocked"] = True
                probe["block_reason"] = "content_stripped"

        result["probes"].append(probe)

    # --- 5. Per-class scoring + overall verdict -----------------------------
    # Scoring is multi-dimensional rather than a single number because the
    # GEO impact of blocking differs sharply by bot class. A site that
    # blocks training but allows retrieval is the canonical healthy
    # publisher posture (NYT, WSJ, Reuters, BBC) — one flat score would
    # mislabel it. We emit a sub-score per class and an overall verdict
    # that weights retrieval reachability heaviest.
    by_class = {cls: {"total": 0, "blocked": 0, "score": 100}
                for cls in BOT_CLASSES}
    for probe in result["probes"]:
        cls = probe["class"]
        by_class[cls]["total"] += 1
        if probe["blocked"]:
            by_class[cls]["blocked"] += 1
    # Each class drops linearly from 100 to 0 as the share of blocked
    # bots in that class goes from 0% to 100%.
    for stats in by_class.values():
        if stats["total"]:
            stats["score"] = max(
                0, round(100 * (1 - stats["blocked"] / stats["total"]))
            )

    # JS-challenge penalty applies to the search-index and live-retrieval
    # classes since non-browser bots can't bypass an interstitial.
    if result["js_challenge_detected"] and not result["baseline"]["used_playwright"]:
        for cls in ("search-index", "live-retrieval"):
            by_class[cls]["score"] = max(0, by_class[cls]["score"] - 30)

    result["class_scores"] = by_class

    retrieval = (by_class["live-retrieval"]["score"] + by_class["search-index"]["score"]) // 2
    traditional = by_class["traditional-search"]["score"]
    training = by_class["training"]["score"]

    # Verdict logic. Retrieval is the headline signal; training is
    # informational. "HEALTHY_PUBLISHER" recognises the NYT/Reuters
    # pattern explicitly so reports don't mislabel it as a problem.
    if retrieval >= 90 and traditional >= 90:
        verdict = "OPEN" if training >= 70 else "HEALTHY_PUBLISHER"
    elif retrieval >= 70 and traditional >= 70:
        verdict = "PARTIALLY_BLOCKED"
    elif retrieval >= 40 or traditional >= 40:
        verdict = "MOSTLY_BLOCKED"
    else:
        verdict = "BLOCKED"

    result["verdict"] = verdict
    result["overall_score"] = round(
        0.5 * retrieval + 0.35 * traditional + 0.15 * training
    )

    return result


def crawl_sitemap(url: str, max_pages: int = 50, timeout: int = 15) -> list:
    """Crawl sitemap.xml to discover pages."""
    parsed = urlparse(url)
    sitemap_urls = [
        f"{parsed.scheme}://{parsed.netloc}/sitemap.xml",
        f"{parsed.scheme}://{parsed.netloc}/sitemap_index.xml",
        f"{parsed.scheme}://{parsed.netloc}/sitemap/",
    ]

    discovered_pages = set()

    for sitemap_url in sitemap_urls:
        try:
            response = requests.get(
                sitemap_url, headers=DEFAULT_HEADERS, timeout=timeout
            )
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, "lxml")

                # Check for sitemap index
                for sitemap in soup.find_all("sitemap"):
                    loc = sitemap.find("loc")
                    if loc:
                        # Fetch child sitemap
                        try:
                            child_resp = requests.get(
                                loc.text.strip(),
                                headers=DEFAULT_HEADERS,
                                timeout=timeout,
                            )
                            if child_resp.status_code == 200:
                                child_soup = BeautifulSoup(child_resp.text, "lxml")
                                for url_tag in child_soup.find_all("url"):
                                    loc_tag = url_tag.find("loc")
                                    if loc_tag:
                                        discovered_pages.add(loc_tag.text.strip())
                                    if len(discovered_pages) >= max_pages:
                                        break
                        except Exception:
                            pass
                    if len(discovered_pages) >= max_pages:
                        break

                # Direct URL entries
                for url_tag in soup.find_all("url"):
                    loc = url_tag.find("loc")
                    if loc:
                        discovered_pages.add(loc.text.strip())
                    if len(discovered_pages) >= max_pages:
                        break

                if discovered_pages:
                    break

        except Exception:
            continue

    return list(discovered_pages)[:max_pages]


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python fetch_page.py <url> [mode]")
        print("Modes: page (default), robots, llms, sitemap, blocks, bots, full")
        sys.exit(1)

    target_url = sys.argv[1]
    mode = sys.argv[2] if len(sys.argv) > 2 else "page"

    if mode == "page":
        data = fetch_page(target_url)
    elif mode == "robots":
        data = fetch_robots_txt(target_url)
    elif mode == "llms":
        data = fetch_llms_txt(target_url)
    elif mode == "sitemap":
        pages = crawl_sitemap(target_url)
        data = {"pages": pages, "count": len(pages)}
    elif mode == "blocks":
        response = requests.get(target_url, headers=DEFAULT_HEADERS, timeout=30)
        data = extract_content_blocks(response.text)
    elif mode == "bots":
        # Live AI crawler reachability probe — empirical complement to
        # the static `robots` mode. See probe_ai_crawlers() for details.
        data = probe_ai_crawlers(target_url)
    elif mode == "full":
        data = {
            "page": fetch_page(target_url),
            "robots": fetch_robots_txt(target_url),
            "llms": fetch_llms_txt(target_url),
            "sitemap": crawl_sitemap(target_url),
            "bots": probe_ai_crawlers(target_url),
        }
    else:
        print(f"Unknown mode: {mode}")
        sys.exit(1)

    print(json.dumps(data, indent=2, default=str))
