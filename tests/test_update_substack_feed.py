import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
from scripts import update_substack_feed as MODULE


class FeedParserTests(unittest.TestCase):
    def test_parses_and_sanitizes_rss_item(self):
        xml = b"""<?xml version="1.0"?>
        <rss version="2.0" xmlns:dc="http://purl.org/dc/elements/1.1/">
          <channel>
            <item>
              <title>Test &amp; Update</title>
              <description><![CDATA[<p>A <strong>short</strong> description.</p>]]></description>
              <link>https://cleopaskal.substack.com/p/test</link>
              <dc:creator>Cleo Paskal</dc:creator>
              <pubDate>Fri, 11 Sep 2026 05:05:15 GMT</pubDate>
              <enclosure url="https://example.com/image.jpg" type="image/jpeg" length="0" />
            </item>
          </channel>
        </rss>"""

        posts = MODULE.parse_feed(xml)

        self.assertEqual(len(posts), 1)
        self.assertEqual(posts[0]["title"], "Test & Update")
        self.assertEqual(posts[0]["description"], "A short description.")
        self.assertEqual(posts[0]["date"], "2026-09-11T05:05:15Z")
        self.assertEqual(posts[0]["thumbnail"], "https://example.com/image.jpg")

    def test_rejects_feed_without_usable_items(self):
        with self.assertRaises(ValueError):
            MODULE.parse_feed(b"<rss><channel></channel></rss>")


if __name__ == "__main__":
    unittest.main()
