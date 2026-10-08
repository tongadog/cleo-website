#!/usr/bin/env python3
"""Fetch Cleo Paskal's Substack RSS feed and generate browser-ready data."""

import argparse
import html
import json
import os
import tempfile
import time
import xml.etree.ElementTree as ET
from datetime import timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse

DEFAULT_FEED_URL = "https://cleopaskal.substack.com/feed"
DEFAULT_LIMIT = 20


class _TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)


def plain_text(value):
    parser = _TextExtractor()
    parser.feed(html.unescape(value or ""))
    return " ".join("".join(parser.parts).split())


def safe_https_url(value):
    value = (value or "").strip()
    parsed = urlparse(value)
    return value if parsed.scheme == "https" and parsed.netloc else ""


def parse_feed(xml_bytes, limit=DEFAULT_LIMIT):
    root = ET.fromstring(xml_bytes)
    channel = root.find("channel")
    if channel is None:
        raise ValueError("RSS feed is missing a channel element")

    posts = []
    for item in channel.findall("item")[:limit]:
        title = plain_text(item.findtext("title"))
        link = safe_https_url(item.findtext("link"))
        published = (item.findtext("pubDate") or "").strip()
        if not title or not link or not published:
            continue

        dt = parsedate_to_datetime(published)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        date = dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")

        enclosure = item.find("enclosure")
        thumbnail = safe_https_url(enclosure.get("url")) if enclosure is not None else ""
        author = plain_text(item.findtext("{http://purl.org/dc/elements/1.1/}creator"))

        posts.append({
            "title": title,
            "date": date,
            "author": author or "Cleo Paskal",
            "description": plain_text(item.findtext("description")),
            "thumbnail": thumbnail,
            "url": link,
        })

    if not posts:
        raise ValueError("RSS feed did not contain any usable posts")
    return posts


def render_javascript(posts):
    payload = json.dumps(posts, ensure_ascii=False, indent=2)
    return (
        "// Generated from https://cleopaskal.substack.com/feed.\n"
        "// Do not edit by hand; run scripts/update_substack_feed.py.\n"
        f"window.SUBSTACK_POSTS = {payload};\n"
    )


def fetch_feed(url):
    # Keep local --feed-file parsing usable without the network dependency.
    from curl_cffi import requests

    # Substack blocks ordinary HTTP clients on GitHub-hosted runners.
    for attempt in range(4):
        try:
            response = requests.get(url, impersonate="chrome", timeout=60)
            response.raise_for_status()
            return response.content
        except requests.RequestsError:
            if attempt == 3:
                raise
            time.sleep(2 ** attempt)


def atomic_write(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=path.name + ".", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
        os.replace(temp_name, path)
    except Exception:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
        raise


def main():
    repo_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument("--feed-url", default=DEFAULT_FEED_URL)
    parser.add_argument("--feed-file", type=Path, help="Read an RSS file instead of downloading it")
    parser.add_argument("--output", type=Path, default=repo_root / "substack.js")
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    args = parser.parse_args()

    if not 1 <= args.limit <= 100:
        parser.error("--limit must be between 1 and 100")

    xml_bytes = args.feed_file.read_bytes() if args.feed_file else fetch_feed(args.feed_url)
    posts = parse_feed(xml_bytes, args.limit)
    atomic_write(args.output, render_javascript(posts))
    print(f"Wrote {len(posts)} Substack posts to {args.output}")


if __name__ == "__main__":
    main()
