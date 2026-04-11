"""
Tests for the live AI crawler probe added to fetch_page.py.

Covers:
  - WAF/CDN fingerprinting (detect_waf) per product family
  - Cloudflare challenge-page detection (is_challenge_page)
  - Content similarity helper (_content_similarity)
  - probe_ai_crawlers() block-detection rules:
      * HTTP 403 / 406 / 429 / 503
      * 200 OK with a disguised challenge body
      * Healthy 200 with high similarity to baseline (allowed)
      * Silent content stripping (low similarity + small body)
  - probe_ai_crawlers() probes every bot in AI_CRAWLERS

Mocking style mirrors test_fetch_page_ssr.py — patch
``fetch_page.requests.get`` with a MagicMock and feed responses via
``side_effect`` so each successive call returns the next mock.
"""

import sys
import os
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from fetch_page import (  # noqa: E402
    AI_CRAWLERS,
    detect_waf,
    is_challenge_page,
    _content_similarity,
    probe_ai_crawlers,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _resp(status=200, text="<html><body>baseline content</body></html>",
          headers=None):
    """Build a minimal mock requests.Response for probe_ai_crawlers/detect_waf."""
    mock = MagicMock()
    mock.status_code = status
    mock.text = text
    mock.headers = headers or {}
    mock.history = []
    mock.url = "http://example.com/"
    return mock


# A reasonably long baseline body so similarity comparisons are meaningful
# and length ratios behave like real-world pages.
BASELINE_HTML = (
    "<!DOCTYPE html><html><head><title>Example</title></head>"
    "<body><h1>Example article</h1>"
    + ("<p>Real server-rendered content paragraph with plenty of words. </p>" * 40)
    + "</body></html>"
)


# ---------------------------------------------------------------------------
# detect_waf — fingerprinting per product
# ---------------------------------------------------------------------------

class TestDetectWaf:
    def test_cloudflare_via_cf_ray_header(self):
        r = _resp(headers={"CF-Ray": "abc123-LHR", "Server": "cloudflare"})
        products = [d["product"] for d in detect_waf(r)]
        assert "Cloudflare" in products

    def test_cloudflare_via_cookie(self):
        r = _resp(headers={"Set-Cookie": "__cf_bm=xyz; Path=/"})
        assert "Cloudflare" in [d["product"] for d in detect_waf(r)]

    def test_aws_cloudfront(self):
        r = _resp(headers={"X-Amz-Cf-Id": "abc"})
        assert "AWS CloudFront" in [d["product"] for d in detect_waf(r)]

    def test_aws_waf(self):
        r = _resp(headers={"x-amzn-waf-action": "block"})
        assert "AWS WAF" in [d["product"] for d in detect_waf(r)]

    def test_akamai_via_server(self):
        r = _resp(headers={"Server": "AkamaiGHost"})
        assert "Akamai" in [d["product"] for d in detect_waf(r)]

    def test_akamai_via_x_akamai_header(self):
        r = _resp(headers={"X-Akamai-Transformed": "9 -"})
        assert "Akamai" in [d["product"] for d in detect_waf(r)]

    def test_imperva_via_x_iinfo(self):
        r = _resp(headers={"X-Iinfo": "1-12345-12345"})
        assert "Imperva Incapsula" in [d["product"] for d in detect_waf(r)]

    def test_imperva_via_cookie(self):
        r = _resp(headers={"Set-Cookie": "incap_ses_123_456=abc"})
        assert "Imperva Incapsula" in [d["product"] for d in detect_waf(r)]

    def test_sucuri(self):
        r = _resp(headers={"Server": "Sucuri/Cloudproxy", "X-Sucuri-ID": "13"})
        assert "Sucuri" in [d["product"] for d in detect_waf(r)]

    def test_f5_bigip_via_cookie(self):
        r = _resp(headers={"Set-Cookie": "BIGipServerpool_app=12345.6789.0000"})
        assert "F5 BIG-IP" in [d["product"] for d in detect_waf(r)]

    def test_fastly(self):
        r = _resp(headers={"X-Fastly-Request-Id": "abc"})
        assert "Fastly" in [d["product"] for d in detect_waf(r)]

    def test_azure_front_door(self):
        r = _resp(headers={"X-Azure-Ref": "0xyz"})
        assert "Azure Front Door" in [d["product"] for d in detect_waf(r)]

    def test_no_waf(self):
        r = _resp(headers={"Server": "nginx/1.21.0"})
        assert detect_waf(r) == []

    def test_stacked_products_returned_together(self):
        r = _resp(headers={
            "CF-Ray": "abc",
            "X-Amz-Cf-Id": "def",
            "Server": "cloudflare",
        })
        products = [d["product"] for d in detect_waf(r)]
        assert "Cloudflare" in products
        assert "AWS CloudFront" in products

    def test_dedupes_same_product(self):
        # Multiple Cloudflare predicates would all match — detect_waf must
        # only report the product once.
        r = _resp(headers={
            "CF-Ray": "abc",
            "Server": "cloudflare",
            "Set-Cookie": "__cf_bm=xyz",
        })
        products = [d["product"] for d in detect_waf(r)]
        assert products.count("Cloudflare") == 1

    def test_broken_predicate_does_not_break_scan(self):
        # response.headers raising on iteration shouldn't kill detection.
        r = MagicMock()
        r.headers = {"Server": "cloudflare"}
        # Should still return Cloudflare via the server-header predicate.
        assert "Cloudflare" in [d["product"] for d in detect_waf(r)]


# ---------------------------------------------------------------------------
# is_challenge_page
# ---------------------------------------------------------------------------

class TestIsChallengePage:
    def test_403_with_cf_marker(self):
        assert is_challenge_page("<html>cf-challenge ray id 123</html>", 403)

    def test_503_with_just_a_moment(self):
        assert is_challenge_page("<html>Just a moment...</html>", 503)

    def test_200_with_turnstile_marker(self):
        assert is_challenge_page("<html>cf-turnstile widget</html>", 200)

    def test_200_clean_page_not_challenge(self):
        assert not is_challenge_page(BASELINE_HTML, 200)

    def test_403_cloudflare_branded_error(self):
        assert is_challenge_page("<html>Cloudflare error page</html>", 403)


# ---------------------------------------------------------------------------
# _content_similarity
# ---------------------------------------------------------------------------

class TestContentSimilarity:
    def test_identical_pages(self):
        assert _content_similarity(BASELINE_HTML, BASELINE_HTML) == 1.0

    def test_completely_different_pages(self):
        assert _content_similarity(BASELINE_HTML, "<html>nothing</html>") < 0.3

    def test_handles_empty_strings(self):
        # Empty vs empty: SequenceMatcher returns 1.0; we just want no crash.
        assert _content_similarity("", "") in (0.0, 1.0)


# ---------------------------------------------------------------------------
# probe_ai_crawlers — end-to-end behaviour with mocked HTTP
# ---------------------------------------------------------------------------

class TestProbeAiCrawlersAllAllowed:
    """Healthy site: baseline 200 + every bot returns the same body."""

    def test_no_bots_blocked(self):
        baseline = _resp(status=200, text=BASELINE_HTML, headers={})
        bot_responses = [
            _resp(status=200, text=BASELINE_HTML, headers={})
            for _ in AI_CRAWLERS
        ]
        with patch("fetch_page.requests.get",
                   side_effect=[baseline] + bot_responses):
            result = probe_ai_crawlers("http://example.com/")

        assert result["baseline"]["status"] == 200
        assert result["js_challenge_detected"] is False
        assert len(result["probes"]) == len(AI_CRAWLERS)
        assert all(p["blocked"] is False for p in result["probes"])

    def test_probes_every_bot_in_AI_CRAWLERS(self):
        baseline = _resp(status=200, text=BASELINE_HTML)
        bot_responses = [_resp(status=200, text=BASELINE_HTML)
                         for _ in AI_CRAWLERS]
        with patch("fetch_page.requests.get",
                   side_effect=[baseline] + bot_responses):
            result = probe_ai_crawlers("http://example.com/")

        probed = {p["bot"] for p in result["probes"]}
        assert probed == set(AI_CRAWLERS.keys())


class TestProbeAiCrawlersBlockedByStatus:
    """A bot that gets a 403/406/429/503 must be flagged."""

    def _run_with_bot_status(self, status):
        baseline = _resp(status=200, text=BASELINE_HTML)
        # First bot (GPTBot) gets the bad status, the rest are 200.
        bot_responses = []
        for i, _ in enumerate(AI_CRAWLERS):
            if i == 0:
                bot_responses.append(_resp(status=status, text="blocked"))
            else:
                bot_responses.append(_resp(status=200, text=BASELINE_HTML))
        with patch("fetch_page.requests.get",
                   side_effect=[baseline] + bot_responses):
            return probe_ai_crawlers("http://example.com/")

    def test_403_flagged(self):
        result = self._run_with_bot_status(403)
        first = result["probes"][0]
        assert first["blocked"] is True
        assert first["block_reason"] == "http_403"

    def test_406_flagged(self):
        result = self._run_with_bot_status(406)
        assert result["probes"][0]["block_reason"] == "http_406"

    def test_429_flagged(self):
        result = self._run_with_bot_status(429)
        assert result["probes"][0]["block_reason"] == "http_429"

    def test_503_flagged(self):
        result = self._run_with_bot_status(503)
        assert result["probes"][0]["block_reason"] == "http_503"

    def test_other_bots_remain_allowed(self):
        result = self._run_with_bot_status(403)
        # All bots except the first (which we forced to 403) should be OK.
        assert all(p["blocked"] is False for p in result["probes"][1:])


class TestProbeAiCrawlersBlockedByChallengeBody:
    """200 OK with a Cloudflare challenge body must be flagged."""

    def test_challenge_body_with_200_status(self):
        baseline = _resp(status=200, text=BASELINE_HTML)
        challenge_body = "<html>Just a moment... cf-challenge ray id 1</html>"
        bot_responses = []
        for i, _ in enumerate(AI_CRAWLERS):
            if i == 0:
                bot_responses.append(_resp(status=200, text=challenge_body))
            else:
                bot_responses.append(_resp(status=200, text=BASELINE_HTML))
        with patch("fetch_page.requests.get",
                   side_effect=[baseline] + bot_responses):
            result = probe_ai_crawlers("http://example.com/")

        first = result["probes"][0]
        assert first["blocked"] is True
        assert first["block_reason"] == "challenge_page"


class TestProbeAiCrawlersBlockedByContentStripping:
    """A 200 with a much smaller, dissimilar body should be flagged."""

    def test_low_similarity_and_small_body(self):
        baseline = _resp(status=200, text=BASELINE_HTML)
        stripped = "<html><body>nothing here</body></html>"
        bot_responses = []
        for i, _ in enumerate(AI_CRAWLERS):
            if i == 0:
                bot_responses.append(_resp(status=200, text=stripped))
            else:
                bot_responses.append(_resp(status=200, text=BASELINE_HTML))
        with patch("fetch_page.requests.get",
                   side_effect=[baseline] + bot_responses):
            result = probe_ai_crawlers("http://example.com/")

        first = result["probes"][0]
        assert first["blocked"] is True
        assert first["block_reason"] == "content_stripped"
        assert first["similarity"] is not None and first["similarity"] < 0.4


class TestProbeAiCrawlersWafFingerprintingIntegration:
    """The probe should populate wafs_detected from the baseline response."""

    def test_cloudflare_recorded_on_baseline(self):
        baseline = _resp(
            status=200,
            text=BASELINE_HTML,
            headers={"CF-Ray": "abc-LHR", "Server": "cloudflare"},
        )
        bot_responses = [_resp(status=200, text=BASELINE_HTML)
                         for _ in AI_CRAWLERS]
        with patch("fetch_page.requests.get",
                   side_effect=[baseline] + bot_responses):
            result = probe_ai_crawlers("http://example.com/")

        products = [d["product"] for d in result["wafs_detected"]]
        assert "Cloudflare" in products


class TestProbeAiCrawlersJsChallengeDetection:
    """If the baseline body looks like a Cloudflare challenge, flag it."""

    def test_js_challenge_detected_on_baseline(self):
        challenge = "<html>Just a moment... cf-challenge ray id 1</html>"
        baseline = _resp(status=200, text=challenge)
        # When the baseline is a challenge and Playwright isn't installed,
        # the probe falls back to status/challenge-marker detection only.
        bot_responses = [_resp(status=200, text=BASELINE_HTML)
                         for _ in AI_CRAWLERS]
        with patch("fetch_page.requests.get",
                   side_effect=[baseline] + bot_responses), \
             patch("fetch_page._playwright_baseline", return_value=None):
            result = probe_ai_crawlers("http://example.com/")

        assert result["js_challenge_detected"] is True
        assert result["baseline"]["used_playwright"] is False

    def test_playwright_fallback_used_when_available(self):
        challenge = "<html>Just a moment... cf-challenge ray id 1</html>"
        baseline = _resp(status=200, text=challenge)
        bot_responses = [_resp(status=200, text=BASELINE_HTML)
                         for _ in AI_CRAWLERS]
        with patch("fetch_page.requests.get",
                   side_effect=[baseline] + bot_responses), \
             patch("fetch_page._playwright_baseline",
                   return_value=(200, BASELINE_HTML)):
            result = probe_ai_crawlers("http://example.com/")

        assert result["js_challenge_detected"] is True
        assert result["baseline"]["used_playwright"] is True
        assert result["baseline"]["length"] == len(BASELINE_HTML)


class TestProbeAiCrawlersErrorHandling:
    """A baseline fetch failure should populate errors and return early."""

    def test_baseline_failure_records_error(self):
        with patch("fetch_page.requests.get",
                   side_effect=Exception("connection refused")):
            result = probe_ai_crawlers("http://example.com/")

        assert result["probes"] == []
        assert any("Baseline fetch failed" in e for e in result["errors"])

    def test_per_bot_request_error_marks_blocked(self):
        baseline = _resp(status=200, text=BASELINE_HTML)
        responses = [baseline]
        # Every bot raises — each should be flagged blocked with request_error.
        for _ in AI_CRAWLERS:
            responses.append(Exception("timeout"))
        with patch("fetch_page.requests.get", side_effect=responses):
            result = probe_ai_crawlers("http://example.com/")

        assert len(result["probes"]) == len(AI_CRAWLERS)
        assert all(p["blocked"] for p in result["probes"])
        assert all(
            p["block_reason"].startswith("request_error")
            for p in result["probes"]
        )
