from unittest import TestCase

from sentiment.collectors import eastmoney_posts, sina_posts, taoguba_posts


TARGET = {"id": "consumer", "name": "消费白酒", "eastmoneyCode": "600519"}


class CollectorParserTests(TestCase):
    def test_eastmoney_parser_keeps_plain_user_title(self):
        payload = {"re": [{
            "stockbar_code": "600519", "post_type": 0, "post_title": "还能上车吗",
            "post_publish_time": "2026-09-02 15:40:00", "user_id": "42",
            "user_extendinfos": {"user_accreditinfos": None}, "institution": None,
        }]}
        posts = eastmoney_posts(payload, TARGET)
        self.assertEqual(len(posts), 1)
        self.assertEqual(posts[0].text, "还能上车吗")
        self.assertNotEqual(posts[0].author_key, "42")

    def test_sina_parser_filters_verified_user(self):
        payload = {"data": {"threads": [
            {"content": "普通讨论", "timestamp": 1788334800, "uid": "1", "user": {"verified": False}},
            {"content": "认证观点", "timestamp": 1788334800, "uid": "2", "user": {"verified": True}},
        ]}}
        self.assertEqual(len(sina_posts(payload, TARGET)), 1)

    def test_taoguba_parser_strips_html(self):
        rows = [{
            "deleteFlag": "N", "auth": 0, "subject": "今天能买吗",
            "body": "<b>想上车</b>", "actionDate": "2026-09-02T14:00:00+08:00", "userID": 7,
        }]
        posts = taoguba_posts(rows, TARGET)
        self.assertEqual(posts[0].text, "今天能买吗 想上车")
