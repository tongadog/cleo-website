#!/usr/bin/env python3
"""Fast collection of Markdown article bodies, with minimal checks.

Try FDD then the publisher. Reuse existing text; checkpoint each result.
After three FDD 403 responses, skip FDD for the rest of the run. Known
PDF/video sources and other failures go into exceptions.json for later.
Collected does not mean independently verified complete.

Requirements:
    python3 -m pip install beautifulsoup4 lxml

Usage:
    python3 scrape_article_bodies.py
    python3 scrape_article_bodies.py --limit 10
"""

import argparse
import concurrent.futures
import datetime as dt
import json
import re
import subprocess
import sys
import threading
import time
import unicodedata
from pathlib import Path
from urllib.parse import urlparse, urljoin

from bs4 import BeautifulSoup


HERE = Path(__file__).parent
ARTICLES_JS = HERE / "articles.js"
OUT_DIR = HERE / "content" / "articles"
MANIFEST = OUT_DIR / "manifest.json"
HOST_LOCK = threading.Lock()
HOST_NEXT = {}
FDD_BLOCKS = 0

# These two records need a retrieval URL different from the card's source URL.
FETCH_OVERRIDES = {
    "people-vs-ccp-suidani-and-talifilu-fight-the-good-fight": (
        "https://sundayguardianlive.com/editors-choice/people-vs-ccp-suidani-and-talifilu-fight-the-good-fight-135378/"
    ),
    "review-of-canadas-indo-pacific-strategy": (
        "https://www.ourcommons.ca/DocumentViewer/en/45-1/FAAE/meeting-31/evidence"
    ),
    "how-the-uk-is-undermining-us-indo-pacific-security": (
        "https://web.archive.org/web/20260108170255id_/"
        "https://nationalinterest.org/feature/"
        "how-the-uk-is-undermining-us-indo-pacific-security"
    ),
}


def load_articles():
    text = ARTICLES_JS.read_text(encoding="utf-8")
    return json.loads(text[text.index("[") : text.rindex("]") + 1])


def slug_for(article):
    path = urlparse(article["url"]).path.rstrip("/")
    return path.rsplit("/", 1)[-1]


def fetch(url):
    global FDD_BLOCKS
    host = urlparse(url).netloc.lower().removeprefix("www.")
    with HOST_LOCK:
        if host == "fdd.org" and FDD_BLOCKS >= 3:
            raise ValueError("FDD skipped after repeated HTTP 403 responses this run")
        delay = max(0, HOST_NEXT.get(host, 0) - time.monotonic())
        HOST_NEXT[host] = time.monotonic() + delay + 0.6
    if delay:
        time.sleep(delay)
    # This public legacy host has an expired certificate. No cookies/credentials
    # are sent, and redirects are disabled for this narrowly scoped exception.
    tls_options = ["--insecure", "--max-redirs", "0"] if host == "latest.sundayguardianlive.com" else []
    result = subprocess.run(
        [
            "curl", "-L", "--max-time", "25", "--connect-timeout", "10",
            "--max-filesize", "8000000", "--proto", "=https,http",
            "--proto-redir", "=https,http", "-A", "Mozilla/5.0", "-sS",
            "-w", "\nCLEO_FETCH:%{http_code} %{url_effective}", url,
        ] + tls_options,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    body, trailer = result.stdout.rsplit(b"\nCLEO_FETCH:", 1)
    status, final_url = trailer.decode().split(" ", 1)
    if status != "200":
        if host == "fdd.org" and status == "403":
            with HOST_LOCK:
                FDD_BLOCKS += 1
        raise ValueError(f"HTTP {status}: {final_url}")
    if body.startswith(b"%PDF"):
        raise ValueError("PDF: queued for later text extraction")
    return body, final_url


def clean_text(value):
    value = unicodedata.normalize("NFC", value).replace("\xa0", " ")
    value = re.sub(r"\s+", " ", value).strip()
    value = re.sub(r"\s+([,.;:!?%)])", r"\1", value)
    value = re.sub(r"([(])\s+", r"\1", value)
    value = re.sub(r"([“‘])\s+", r"\1", value)
    value = re.sub(r"\s+([”’])", r"\1", value)
    value = re.sub(r"(\d)\s+(st|nd|rd|th)\b", r"\1\2", value)
    return value


def remove_noise(root):
    selectors = (
        "script, style, noscript, iframe, form, ins, .advertisement, .ad, "
        ".sharedaddy, .social-share, .related, .related-posts, .card, "
        ".newsletter, .newsletter-signup, .penci-single-link-pages, "
        "nav, footer, aside, .code-block, .penci-related-posts, "
        ".jp-relatedposts, .social-sharing, .share-buttons"
    )
    for node in root.select(selectors):
        node.decompose()


def markdown_blocks(root):
    """Convert semantic body blocks to simple, stable Markdown."""
    allowed = {"h2", "h3", "h4", "p", "li", "blockquote"}
    blocks = []
    for node in root.find_all(list(allowed)):
        if any(parent.name in allowed for parent in node.parents if parent is not root):
            continue
        value = clean_text(node.get_text(" ", strip=True))
        if not value:
            continue
        if node.name in {"h2", "h3", "h4"}:
            value = "## " + value
        elif node.name == "li":
            value = "- " + value
        elif node.name == "blockquote":
            value = "> " + value
        blocks.append(value)
    return blocks


def extract_sunday_guardian(soup, article):
    root = soup.select_one("#penci-post-entry-inner, .td-post-content")
    if not root:
        raise ValueError("Sunday Guardian body container not found")
    remove_noise(root)
    blocks = markdown_blocks(root)

    # The template repeats the deck as the first paragraph and appends a bio.
    subtitle = clean_text(article.get("subtitle", ""))
    first = blocks[0].removeprefix("## ") if blocks else ""
    if blocks and subtitle and first.rstrip(".") == subtitle.rstrip("."):
        blocks.pop(0)
    injected = {
        "Which Country is Known Has Largest Production of Dry Fruits in the World? Here’s the Answer",
        "Which Country is Known for Largest Production of Almonds in the World? Here’s the Answer",
        "8th Pay Commission: Good News for Employees and Pensioners as Commission Begins Work",
    }
    blocks = [b for b in blocks if b.removeprefix("- ") not in injected]
    bio = next(
        (i for i, b in enumerate(blocks) if re.match(r"^[*-]\s*Cleo Paskal is\b", b)),
        len(blocks),
    )
    blocks = blocks[:bio]
    return blocks, "publisher-article"


def extract_washington_times(soup, _article):
    root = soup.select_one(".article-text")
    if not root:
        raise ValueError("Washington Times body container not found")
    remove_noise(root)
    blocks = markdown_blocks(root)
    blocks = [b for b in blocks if b != "OPINION:"]
    stop = next(
        (i for i, b in enumerate(blocks) if b.startswith("• Alexander B. Gray")),
        len(blocks),
    )
    return blocks[:stop], "publisher-article"


def extract_national_interest(soup, _article):
    root = soup.select_one("main#main")
    if not root:
        raise ValueError("National Interest body container not found")
    remove_noise(root)
    # Article paragraphs are direct children; recommendation cards are nested.
    blocks = [clean_text(p.get_text(" ", strip=True)) for p in root.find_all("p", recursive=False)]
    blocks = [b for b in blocks if b]
    stop = next(
        (i for i, b in enumerate(blocks) if b.startswith("Alexander Gray is")),
        len(blocks),
    )
    return blocks[:stop], "wayback-publisher-article"


def extract_parliament(soup, _article):
    blocks = []
    for intervention in soup.select(".interventionBox"):
        speaker = intervention.select_one(".personSpeaking")
        if not speaker or not clean_text(speaker.get_text(" ", strip=True)).startswith("Cleo Paskal"):
            continue

        statement = []
        for paragraph in intervention.select(".paratext"):
            speaker_copy = paragraph.select_one(".personSpeaking")
            if speaker_copy:
                speaker_copy.decompose()
            value = clean_text(paragraph.get_text(" ", strip=True))
            if value:
                statement.append(value)
        if statement:
            blocks.append("## Cleo Paskal")
            blocks.extend(statement)

    if not blocks:
        raise ValueError("Cleo Paskal interventions not found in evidence transcript")
    return blocks, "speaker-only-official-transcript"


def extract(html, url, article):
    soup = BeautifulSoup(html, "lxml")
    host = urlparse(url).netloc.lower()
    if "sundayguardianlive.com" in host:
        return extract_sunday_guardian(soup, article)
    if "washingtontimes.com" in host:
        return extract_washington_times(soup, article)
    if "web.archive.org" in host:
        return extract_national_interest(soup, article)
    if "ourcommons.ca" in host:
        return extract_parliament(soup, article)
    if host in {"fdd.org", "www.fdd.org"}:
        root = soup.select_one(".paragraph-content")
        if not root:
            raise ValueError("FDD article body missing")
        remove_noise(root)
        return markdown_blocks(root), "fdd-article"
    # Explicit body containers first; broad article containers require review.
    for selector in (
        '[itemprop="articleBody"]', '.entry-content', '.article-content',
        '.article-body', '.article__body', '.post-content', '.story-body',
        '[data-hook="post-description"]', '.td-post-content', 'article',
    ):
        root = soup.select_one(selector)
        if root:
            remove_noise(root)
            blocks = markdown_blocks(root)
            if len(" ".join(blocks).split()) >= 80:
                return blocks, "generic-article"
    raise ValueError("No usable article body found")


def frontmatter(article, source_url, fetched_url, extraction):
    fields = {
        "title": article["title"],
        "date": article["date"],
        "authors": article.get("authors", []),
        "outlet": article.get("outlet", ""),
        "category": article.get("category", ""),
        "source_url": source_url,
        "retrieved_from": fetched_url,
        "retrieved_at": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),
        "extraction": extraction,
    }
    lines = ["---"]
    lines.extend(f"{key}: {json.dumps(value, ensure_ascii=False)}" for key, value in fields.items())
    lines.append("---")
    return "\n".join(lines)


def page_matches(soup, article):
    """One cheap identity check, tolerant of publisher title changes."""
    title_nodes = soup.select("h1, title, meta[property='og:title']")
    headings = " ".join(
        node.get("content", "") if node.name == "meta" else node.get_text(" ", strip=True)
        for node in title_nodes
    )
    tokens = lambda text: set(re.findall(r"[a-z0-9]{3,}", text.lower()))
    wanted = tokens(article["title"])
    if wanted and len(wanted & tokens(headings)) / len(wanted) >= 0.45:
        return True
    excerpt = article.get("excerpt", "")
    if len(excerpt) >= 60:
        opening = tokens(excerpt)
        page = tokens(soup.get_text(" ", strip=True))
        return len(opening & page) / max(1, len(opening)) >= 0.8
    return False


def candidate(url, article):
    if re.search(r"\.pdf(?:[?#]|$)", url, re.I):
        raise ValueError("PDF: queued for later text extraction")
    if any(host in urlparse(url).netloc.lower() for host in
           ("parlvu.parl.gc.ca", "parliamentlive.tv", "youtube.com", "youtu.be")):
        raise ValueError("Video/hearing page: queued for transcript collection")
    html, final_url = fetch(url)
    soup = BeautifulSoup(html, "lxml")
    if not page_matches(soup, article):
        raise ValueError("Page title/opening does not match article")
    blocks, method = extract(html, final_url, article)
    if len(" ".join(blocks).split()) < 80:
        raise ValueError("Too little body text (under 80 words); needs manual check")
    host = urlparse(final_url).netloc.lower()
    root = soup.select_one(".paragraph-content") if host in ("fdd.org", "www.fdd.org") else None
    scope = root or soup.select_one("article") or soup
    excerpt = any(
        re.fullmatch(r"(?:article\s+)?excerpt[:.]?", clean_text(h.get_text(" ", strip=True)), re.I)
        for h in scope.select("h2, h3, h4, strong, b, p")
    )
    body = " ".join(blocks)
    paywall = bool(re.search(
        r"subscribe to (?:read|continue)|sign in to (?:read|continue)|"
        r"already a subscriber|unlock (?:this|the full) article", body, re.I))
    notes = []
    if excerpt:
        notes.append("Explicit excerpt label; full text needed")
    if paywall:
        notes.append("Subscription/continuation prompt in extracted text")
    if method == "generic-article":
        notes.append("Generic extraction; body boundaries not manually checked")
    return {
        "blocks": blocks, "extraction": method, "retrievedFrom": final_url,
        "partial": excerpt or paywall, "notes": notes,
    }


def collect(article, previous):
    slug = slug_for(article)
    output = OUT_DIR / f"{slug}.md"
    source_url = article.get("sourceUrl") or ""
    base = {
        "slug": slug, "title": article["title"], "fddUrl": article["url"],
        "sourceUrl": source_url,
    }
    if output.exists():
        row = dict(previous.get(slug, {}))
        row.update(base)
        row.update({"path": str(output.relative_to(HERE)), "reused": True})
        saved = output.read_text(encoding="utf-8")
        body = saved.split("---\n", 2)[-1]
        row["words"] = len(body.split())
        row["status"] = "needs_review" if "speaker-only-official-transcript" in saved else (
            row.get("status") if row.get("status") in ("collected", "needs_review") else "collected"
        )
        row.setdefault("completeness", "not_checked")
        if "manual-browser-fdd" in saved or row.get("extraction") == "manual-browser-fdd":
            # The prior comparison used web retrieval, not desktop browser capture.
            row["extraction"] = "publisher-text-compared-with-fdd-web-retrieval"
            row["notes"] = ["Existing publisher text compared with FDD through web retrieval; not a desktop browser capture"]
        if "speaker-only-official-transcript" in saved:
            row["notes"] = ["Cleo-only selection; other speakers' questions omitted"]
        return row

    attempts = []
    best = None
    urls = [article["url"]]
    if source_url and source_url != article["url"]:
        urls.append(source_url)
    override = FETCH_OVERRIDES.get(slug)
    if override and override not in urls:
        urls.append(override)
    if urlparse(source_url).netloc.lower() in ("sundayguardianlive.com", "www.sundayguardianlive.com"):
        legacy = "https://latest.sundayguardianlive.com" + urlparse(source_url).path
        urls.append(legacy)
        prior = previous.get(slug, {})
        if prior.get("status") == "unavailable":
            attempts = list(prior.get("attempts", []))
            tried = {a["url"] for a in attempts}
            urls = [u for u in urls if u not in tried]
    for url in urls:
        try:
            result = candidate(url, article)
            attempts.append({"url": url, "result": "partial" if result["partial"] else "extracted"})
            if best is None or (best["partial"] and not result["partial"]):
                best = result
            if not result["partial"]:
                break
        except Exception as error:
            detail = str(error)
            if isinstance(error, subprocess.CalledProcessError):
                detail = error.stderr.decode(errors="replace").strip() or str(error)
            attempts.append({"url": url, "result": "skipped_or_failed", "reason": detail[:500]})
    base["attempts"] = attempts
    if best is None:
        base.update({
            "status": "unavailable", "words": 0,
            "notes": ["No body saved; see attempts for follow-up"],
        })
        return base

    body = "\n\n".join(best["blocks"])
    metadata = frontmatter(article, source_url or article["url"],
                           best["retrievedFrom"], best["extraction"])
    output.write_text(metadata + "\n\n" + body + "\n", encoding="utf-8")
    base.update({
        "status": "needs_review" if best["partial"] or best["notes"] else "collected",
        "completeness": "partial" if best["partial"] else "not_checked",
        "path": str(output.relative_to(HERE)), "words": len(body.split()),
        "extraction": best["extraction"], "retrievedFrom": best["retrievedFrom"],
        "notes": best["notes"],
    })
    if urlparse(best["retrievedFrom"]).netloc == "latest.sundayguardianlive.com":
        base["transportNote"] = "Public legacy publisher host has expired certificate; TLS verification disabled for this host only, without credentials or redirects"
    return base


def write_report(records):
    MANIFEST.write_text(json.dumps(records, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    exceptions = [row for row in records if row["status"] != "collected"]
    (OUT_DIR / "exceptions.json").write_text(
        json.dumps(exceptions, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    saved = sum(bool(row.get("path")) for row in records)
    lines = [
        "# Article text collection", "",
        f"{saved} bodies saved across {len(records)} processed records.",
        f"{len(exceptions)} records need follow-up (including saved text flagged for review).",
        "", "Completeness has not been verified. Collected means text was retrieved, "
        "not that the full article was independently confirmed.", "",
        "| Article | Result | Words | Text |", "|---|---|---:|---|",
    ]
    for row in records:
        link = f"[Open]({Path(row['path']).name})" if row.get("path") else "—"
        lines.append(f"| {row.get('title', row['slug']).replace('|', '/')} | "
                     f"{row['status']} | {row.get('words', 0)} | {link} |")
    lines.extend(["", "## Follow-up", ""])
    for row in exceptions:
        reasons = row.get("notes", []) + [
            attempt["reason"] for attempt in row.get("attempts", []) if attempt.get("reason")
        ]
        lines.append(f"- [{row.get('title', row['slug'])}]({row.get('sourceUrl') or row['fddUrl']}): "
                     + "; ".join(reasons).replace("\n", " "))
    (OUT_DIR / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="Fast FDD-first collection, then publisher fallback.")
    parser.add_argument("--limit", type=int, help="Default: process all records")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--recover-sunday-guardian", action="store_true",
                        help="Only retry unresolved Sunday Guardian entries using moved URLs")
    args = parser.parse_args()
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be positive")
    if not 1 <= args.workers <= 8:
        parser.error("--workers must be between 1 and 8")
    articles = load_articles()[:args.limit]
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    previous = {
        row["slug"]: row for row in json.loads(MANIFEST.read_text(encoding="utf-8"))
    } if MANIFEST.exists() else {}
    if args.recover_sunday_guardian:
        articles = [a for a in articles if a.get("outlet") == "The Sunday Guardian"
                    and previous.get(slug_for(a), {}).get("status") == "unavailable"]
    results = dict(previous)
    order = {slug_for(article): i for i, article in enumerate(load_articles())}
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        pending = {pool.submit(collect, article, previous): article for article in articles}
        for i, future in enumerate(concurrent.futures.as_completed(pending), 1):
            row = future.result()
            results[row["slug"]] = row
            # Checkpoint every result; reruns reuse saved bodies.
            records = sorted(results.values(), key=lambda r: order.get(r["slug"], 999999))
            write_report(records)
            print(f"[{i}/{len(articles)}] {row['status']:12} {row['words']:5} words  "
                  f"{row['slug']}", flush=True)
    print(f"Saved {sum(bool(r.get('path')) for r in results.values())} bodies. "
          f"Report: {OUT_DIR / 'README.md'}")


if __name__ == "__main__":
    main()
