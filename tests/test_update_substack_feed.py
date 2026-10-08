import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

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


class FeedDownloadTests(unittest.TestCase):
    def test_browser_fallback_after_http_download_is_blocked(self):
        from curl_cffi import requests

        blocked = requests.Response()
        blocked.status_code = 403
        blocked.ok = False
        feed = b"<rss><channel></channel></rss>"
        with mock.patch("curl_cffi.requests.get", return_value=blocked):
            with mock.patch.object(MODULE.time, "sleep"):
                with mock.patch.object(MODULE, "fetch_feed_in_browser", return_value=feed) as browser:
                    self.assertEqual(MODULE.fetch_feed(MODULE.DEFAULT_FEED_URL, True), feed)
        browser.assert_called_once_with(MODULE.DEFAULT_FEED_URL)

    def test_retries_http_error_then_returns_feed(self):
        from curl_cffi import requests

        blocked = requests.Response()
        blocked.status_code = 403
        blocked.ok = False
        success = requests.Response()
        success.status_code = 200
        success.content = b"<rss><channel></channel></rss>"

        with mock.patch("curl_cffi.requests.get", side_effect=[blocked, success]) as get:
            with mock.patch.object(MODULE.time, "sleep") as sleep:
                self.assertEqual(MODULE.fetch_feed(MODULE.DEFAULT_FEED_URL), success.content)

        self.assertEqual(get.call_count, 2)
        sleep.assert_called_once_with(1)

    def test_download_failure_preserves_existing_data(self):
        from curl_cffi import requests

        blocked = requests.Response()
        blocked.status_code = 403
        blocked.ok = False
        blocked.content = b"<html>Forbidden</html>"

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "substack.js"
            original = "window.SUBSTACK_POSTS = [];\n"
            output.write_text(original, encoding="utf-8")
            with mock.patch.object(sys, "argv", ["update_substack_feed.py", "--output", str(output)]):
                with mock.patch("curl_cffi.requests.get", return_value=blocked) as get:
                    with mock.patch.object(MODULE.time, "sleep"):
                        with self.assertRaises(requests.RequestsError):
                            MODULE.main()

            self.assertEqual(get.call_count, 4)
            self.assertEqual(output.read_text(encoding="utf-8"), original)


if __name__ == "__main__":
    unittest.main()
