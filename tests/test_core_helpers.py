import os
import unittest

# Safe non-production values so importing the bot package for unit tests never
# depends on a developer's local environment. The bot token is deliberately
# not shaped like a real BotFather credential so secret-scanning tests can
# verify the tracked repository without false positives.
os.environ.setdefault("TELEGRAM_API_ID", "12345")
os.environ.setdefault("TELEGRAM_API_HASH", "0123456789abcdef0123456789abcdef")
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "unit-test-token-not-a-real-credential")
os.environ.setdefault("TELEGRAM_BOT_USERNAME", "ExampleBot")
os.environ.setdefault("OWNER_ID", "1")

from bot.server.error import HTTPError
from bot.server.main import _content_disposition, _parse_byte_range
from bot.modules.parser import parse_telegram_link
from bot.modules.static import format_duration, get_human_size


class RangeParserTests(unittest.TestCase):
    def test_full_response_without_range(self):
        self.assertEqual(_parse_byte_range(None, 1000), (0, 999, False))

    def test_end_is_clamped_to_file(self):
        self.assertEqual(_parse_byte_range("bytes=900-5000", 1000), (900, 999, True))

    def test_open_ended_range(self):
        self.assertEqual(_parse_byte_range("bytes=500-", 1000), (500, 999, True))

    def test_suffix_range(self):
        self.assertEqual(_parse_byte_range("bytes=-100", 1000), (900, 999, True))

    def test_unsatisfiable_range(self):
        with self.assertRaises(HTTPError) as ctx:
            _parse_byte_range("bytes=1000-", 1000)
        self.assertEqual(ctx.exception.status_code, 416)

    def test_multiple_ranges_rejected(self):
        with self.assertRaises(HTTPError) as ctx:
            _parse_byte_range("bytes=0-10,20-30", 1000)
        self.assertEqual(ctx.exception.status_code, 416)


class HeaderTests(unittest.TestCase):
    def test_content_disposition_handles_unicode_and_newlines(self):
        header = _content_disposition('Anime\n"Episode 01" 日本.mkv')
        self.assertNotIn("\n", header)
        self.assertIn("filename*=UTF-8''", header)


class ParserTests(unittest.TestCase):
    def test_private_telegram_link(self):
        self.assertEqual(
            parse_telegram_link("https://t.me/c/1234567890/42"),
            (-1001234567890, 42),
        )

    def test_public_telegram_link(self):
        self.assertEqual(
            parse_telegram_link("https://t.me/example_channel/42"),
            ("example_channel", 42),
        )


class FormattingTests(unittest.TestCase):
    def test_size_and_duration(self):
        self.assertEqual(get_human_size(1024), "1.0 KB")
        self.assertEqual(format_duration(3661), "1:01:01")


if __name__ == "__main__":
    unittest.main()
