from unittest import TestCase
from sentiment.measurement import classify_text
from sentiment.retail_profile import expression_tier, refine_behavior, account_profile, leek_score
from python_tests.test_report import fixture
from sentiment.report import assemble_report


def post(text, account="a", number=0):
    return {"author": account, "source": "eastmoney", "id": str(number), "text": text, "url": "https://example.com/post", "date": "2026-09-04 10:00:00", "classification": classify_text(text)}


class TierTests(TestCase):
    def test_full_text_must_match_original_id_date_stock_and_account(self):
        import json
        from sentiment.collectors import anonymous_author
        from sentiment.profile_texts import parse_article
        row = {"id": "123", "date": "2026-09-04 10:00:00", "code": "000001", "author": anonymous_author("eastmoney", "abc")}
        article = {"post_id": 123, "post_publish_time": row["date"], "post_guba": {"stockbar_code": "000001"}, "post_user": {"user_id": "abc"}, "post_content": "<p>中报利润增长33%，但现金流下降。</p>"}
        page = "var post_article=" + json.dumps(article) + ";"
        self.assertIn("现金流下降", parse_article(page, row))
        for key, value in [("id", "124"), ("date", "2026-09-05 10:00:00"), ("code", "000002"), ("author", "wrong")]:
            with self.assertRaises(ValueError): parse_article(page, {**row, key: value})
        with self.assertRaises(ValueError): parse_article("<html>暂不可用</html>", row)

    def test_levels_need_reasoning_not_just_topic_vocabulary(self):
        cases = {
            "还能追吗？": "L1", "还能上车吗？": "L1", "我是小白，什么是股息率": "L1",
            "主力在出货了": "L2", "主力在建仓": "L2", "涨停潮来了": "L2",
            "中报净利润同比增长33%，但扣非下降，因此盈利质量仍需要观察": "L3",
            "十五五规划支持下游扩产，公告显示订单增长20%，将带来营收改善，但需观察现金流": "L4",
            "美联储加息推升美元，汇率传导压缩企业利润；财报显示海外营收占30%，如果需求下滑，订单风险将进一步影响现金流": "L5",
        }
        for text, expected in cases.items():
            with self.subTest(text=text): self.assertEqual(expression_tier(text)[0], expected)
        for text in ["美国加息", "地缘溢价", "十五五规划", "中报净利润+33%", "红利股息率", "哈哈哈哈", "今天能涨停吗", "有人问还能追吗？", "他说“我是小白”", "难道我就是小白吗", "不要梭哈", "我是专业投资者"]:
            with self.subTest(text=text): self.assertIsNone(expression_tier(text)[0])

    def test_observed_misclassifications_are_not_chase_or_panic(self):
        for text in ["追高又得发套", "尾盘抢筹，感觉星期一比较悬", "主力今天打板抢筹", "这个位置太多套牢盘了，要么吃掉，要么洗一洗", "还能追吗？", "我不敢追高", "昨天追高买入了"]:
            result = refine_behavior(post(text))
            self.assertFalse(result["classification"]["chase"], text)
            self.assertFalse(result["classification"]["panic"], text)
        self.assertTrue(refine_behavior(post("今天追高买入了"))["classification"]["chase"])
        self.assertTrue(refine_behavior(post("我已经追高买入了，被套了"))["classification"]["chase"])
        self.assertTrue(refine_behavior(post("取钱不玩了"))["classification"]["panic"])
        for text in ["距离补仓的12.53还需要涨15%", "早盘补仓差几分没到", "任何回踩都是补仓机会", "如果跌了我就补仓"]:
            self.assertFalse(refine_behavior(post(text))["refillExpression"], text)
        self.assertTrue(refine_behavior(post("今天补了仓"))["refillExpression"])

    def test_one_account_one_vote_conflict_and_unknown_are_preserved(self):
        posts = [post("还能追吗？", "a", i) for i in range(50)]
        posts += [post("主力在建仓", "b"), post("哈哈哈哈", "c"), post("还能追吗？", "d"), post("中报净利润同比增长33%，因此我认为估值偏低", "d", 1)]
        p = account_profile(posts, 4, True)
        self.assertEqual(p["classifiedAccounts"], 2)
        self.assertEqual(p["unknownAccounts"], 2)
        self.assertEqual(p["conflictingAccounts"], 1)
        self.assertEqual(p["levels"][0]["count"], 1)
        self.assertEqual(p["levels"][1]["share"], 50)
        self.assertIsNone(p["l1l2Share"])

    def test_score_weights_unknown_bounds_missing_and_panic_independence(self):
        posts = [post("还能追吗？" if i < 10 else "主力在建仓", str(i)) for i in range(20)]
        p = account_profile(posts, 100, True)
        inputs = dict(discussion=50, growth=50, spread=50, chase=50, trading=50, panic=0)
        score = leek_score(p, inputs)
        self.assertIsNone(score["score"])
        self.assertEqual(score["range"], [39.5, 67.5])
        self.assertEqual(leek_score(p, {**inputs, "panic": 100}), {**score, "inputs": {**score["inputs"], "panic": 100}})
        p = account_profile(posts, 20, True)
        self.assertEqual(leek_score(p, inputs)["score"], 67.5)
        self.assertIsNone(leek_score(p, {**inputs, "growth": None})["range"])

    def test_real_report_pipeline_exposes_profiles_but_not_accounts(self):
        market, capture = fixture()
        report = assemble_report(market, capture)
        self.assertEqual(report["meta"]["analysisVersion"], "following-1.0")
        for row in report["sectors"]:
            self.assertIn("expressionProfile", row)
            self.assertNotIn("retailProfile", row)
            self.assertIn("leekScore", row)
            self.assertEqual(row["dimensions"]["growth"], 50)
        import json
        self.assertNotIn('"author"', json.dumps(report))
