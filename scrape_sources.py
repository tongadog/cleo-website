#!/usr/bin/env python3
"""
Extract the external "source" link (original hearing/video/op-ed) from each FDD
article page and match it back to articles.js.

FDD is behind a Cloudflare bot challenge, so plain requests get 403. This drives a
real browser (Playwright): it loads fdd.org once to clear the challenge, then reuses
that browser context to fetch each article and read the links inside .paragraph-content.

Setup (once):
    python3 -m pip install playwright
    python3 -m playwright install chromium

Usage:
    python3 scrape_sources.py                       # scrape all, write source_links.json
    python3 scrape_sources.py --category "Legislative Testimonies"
    python3 scrape_sources.py --limit 10            # first 10 (smoke test)
    python3 scrape_sources.py --write               # also patch articles.js for HIGH-confidence rows

Output: source_links.json — one row per article with candidates + a confidence flag.
    high   -> exactly one external link, or one with source-y anchor text; safe to auto-apply
    review -> multiple external links (footnote citations); needs a human to pick
    none   -> no external link on the page
"""
import argparse
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).parent
ARTICLES_JS = HERE / "articles.js"
OUT_JSON = HERE / "source_links.json"

SKIP_HOSTS = ("fdd.org", "facebook.com", "twitter.com", "x.com",
              "linkedin.com", "youtube.com", "instagram.com", "t.co")
SOURCE_ANCHORS = {"here", "watch here", "read here", "view", "view source",
                  "watch", "full testimony", "read the full testimony",
                  "read the original", "watch the hearing", "watch it here"}


def load_articles():
    txt = ARTICLES_JS.read_text(encoding="utf-8")
    start = txt.index("[")
    end = txt.rindex("]") + 1
    return json.loads(txt[start:end])


# Runs inside the page (post-Cloudflare). Fetches a URL same-origin and returns
# the external links found in the article body.
PAGE_FN = r"""
async (url) => {
  const res = await fetch(url, { credentials: 'include' });
  if (!res.ok) return { status: res.status, links: [] };
  const doc = new DOMParser().parseFromString(await res.text(), 'text/html');
  const root = doc.querySelector('.paragraph-content');
  if (!root) return { status: res.status, links: [], noBody: true };
  const skip = %s;
  const seen = new Set(), links = [];
  for (const a of root.querySelectorAll('a[href^="http"]')) {
    const href = a.href;
    if (skip.some(h => href.includes(h))) continue;
    if (seen.has(href)) continue;
    seen.add(href);
    links.push({ text: a.textContent.trim().replace(/\s+/g, ' ').slice(0, 80), href });
  }
  return { status: res.status, links };
}
""" % json.dumps(list(SKIP_HOSTS))


def classify(links):
    if not links:
        return "none", None
    if len(links) == 1:
        return "high", links[0]["href"]
    sourcey = [l for l in links if l["text"].lower().rstrip(".") in SOURCE_ANCHORS]
    if len(sourcey) == 1:
        return "high", sourcey[0]["href"]
    return "review", None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--category", help="only articles with this exact category")
    ap.add_argument("--limit", type=int, help="cap number of articles (smoke test)")
    ap.add_argument("--write", action="store_true",
                    help="patch articles.js sourceUrl for HIGH-confidence rows")
    ap.add_argument("--headless", action="store_true",
                    help="run browser headless (Cloudflare may block; default is headed)")
    args = ap.parse_args()

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        sys.exit("playwright not installed. Run:\n"
                 "  python3 -m pip install playwright\n"
                 "  python3 -m playwright install chromium")

    articles = load_articles()
    todo = [a for a in articles if a.get("url", "").startswith("http")]
    if args.category:
        todo = [a for a in todo if a.get("category") == args.category]
    if args.limit:
        todo = todo[:args.limit]
    print(f"Scraping {len(todo)} of {len(articles)} articles...", file=sys.stderr)

    results = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=args.headless)
        page = browser.new_page()
        page.goto("https://www.fdd.org/", wait_until="domcontentloaded")
        page.wait_for_timeout(6000)  # give the Cloudflare challenge time to clear

        for i, a in enumerate(todo, 1):
            url = a["url"]
            try:
                r = page.evaluate(PAGE_FN, url)
                links = r.get("links", [])
                conf, picked = classify(links)
                if r.get("status") not in (200, None):
                    conf = f"http_{r['status']}"
            except Exception as e:
                links, conf, picked = [], f"error:{e}", None
            results.append({"title": a.get("title", ""), "category": a.get("category", ""),
                            "url": url, "confidence": conf, "source": picked,
                            "candidates": links})
            print(f"[{i}/{len(todo)}] {conf:8} {a.get('title','')[:60]}", file=sys.stderr)
            page.wait_for_timeout(400)  # be polite

        browser.close()

    OUT_JSON.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    by = {}
    for r in results:
        by[r["confidence"]] = by.get(r["confidence"], 0) + 1
    print("\nSummary:", dict(sorted(by.items())), file=sys.stderr)
    print(f"Wrote {OUT_JSON}", file=sys.stderr)

    if args.write:
        patched = patch_articles({r["url"]: r["source"] for r in results
                                  if r["confidence"] == "high" and r["source"]})
        print(f"Patched {patched} high-confidence sourceUrl(s) into articles.js", file=sys.stderr)


def patch_articles(url_to_source):
    """Insert sourceUrl into the matching one-line JSON objects. Skips any that already have one."""
    txt = ARTICLES_JS.read_text(encoding="utf-8")
    n = 0
    for url, src in url_to_source.items():
        needle = f'"url":"{url}"}}'
        if needle not in txt:
            continue  # already patched (sourceUrl inserted) or url shifted
        repl = f'"url":"{url}","sourceUrl":{json.dumps(src)}}}'
        txt = txt.replace(needle, repl, 1)
        n += 1
    ARTICLES_JS.write_text(txt, encoding="utf-8")
    return n


if __name__ == "__main__":
    main()
