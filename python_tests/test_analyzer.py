from datetime import datetime
from unittest import TestCase

from sentiment.analyzer import analyze_post
from sentiment.collectors import CN_TZ
from sentiment.models import Post


class AnalyzerTests(TestCase):
    def post(self, text: str) -> Post:
        return Post("test", "market", "全市场", text, datetime(2026, 9, 2, 16, tzinfo=CN_TZ), "anon")

    def test_detects_novice_and_fomo(self):
        result = analyze_post(self.post("小白请教，现在还能上车吗？再不买就错过了"))
        self.assertIsNotNone(result)
        assert result is not None
        self.assertGreater(result.signals.novice, 0.6)
        self.assertGreater(result.signals.fomo, 0.5)

    def test_detects_panic_and_bearish_direction(self):
        result = analyze_post(self.post("亏麻了，破位了要不要割肉清仓"))
        self.assertIsNotNone(result)
        assert result is not None
        self.assertGreater(result.signals.panic, 0.7)
        self.assertLess(result.signals.direction, 0)

    def test_filters_promotional_spam(self):
        self.assertIsNone(analyze_post(self.post("扫码进群，老师带单，免费领取内部消息")))
