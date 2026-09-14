import json
from unittest import TestCase
from unittest.mock import patch
from datetime import datetime
from sentiment.topic_discovery import fetch_tags, select_expansion_codes, stock_sample, topic_groups, rank_topics
from sentiment.collectors import CN_TZ
from sentiment.report import assemble_report, measure_members
from python_tests.test_report import fixture


class TopicDiscoveryTests(TestCase):
    def test_business_keyword_without_literal_main_business(self):
        payload = {'ssbk': [{'SECURITY_CODE': '300502', 'BOARD_CODE': '1', 'BOARD_NAME': 'CPO概念', 'BOARD_RANK': 20}],
                   'hxtc': [{'KEYWORD': '光模块的研发、生产和销售', 'MAINPOINT_CONTENT': '公司业务主要涵盖光通信应用'}]}
        with patch('sentiment.topic_discovery.request_text', return_value=json.dumps(payload)):
            self.assertTrue(fetch_tags('300502')[0]['core'])
            with self.assertRaises(ValueError): fetch_tags('300308')

    def test_string_board_rank_is_normalized(self):
        payload = {'ssbk': [{'SECURITY_CODE': '300502', 'BOARD_CODE': '1', 'BOARD_NAME': 'CPO概念', 'BOARD_RANK': '3'}], 'hxtc': []}
        with patch('sentiment.topic_discovery.request_text', return_value=json.dumps(payload)):
            self.assertTrue(fetch_tags('300502')[0]['core'])

    def test_sample_requires_date_and_amount(self):
        timestamp = datetime(2026, 9, 7, 15, tzinfo=CN_TZ).timestamp()
        rows = [{'f12': '300308', 'f6': 100, 'f124': timestamp}, {'f12': '300502', 'f6': 100, 'f124': timestamp - 86400}, {'f12': '000001', 'f6': 0, 'f124': timestamp}]
        universe, sample = stock_sample({'groups': {'stocks': {'rows': rows}}}, '2026-09-07')
        self.assertEqual(set(sample), {'300308'})
        self.assertEqual(universe, sample)

    def test_aliases_merge_but_style_labels_do_not_become_topics(self):
        stocks = {str(i): {'f14': str(i)} for i in range(3)}
        tags = {c: [{'name': n, 'code': n, 'rank': 10, 'core': True} for n in ['光通信模块', 'CPO概念', '东方财富热股']] for c in stocks}
        groups = topic_groups(stocks, tags)
        self.assertEqual([g['name'] for g in groups], ['光模块/CPO'])
        self.assertEqual(len(groups[0]['members']), 3)

    def test_full_day_attribution_and_global_ranking(self):
        groups, feeds, stocks = [], {}, {}
        for i in range(12):
            code = str(i)
            stocks[code] = {'f3': i, 'f8': i}
            groups.append({'id': code, 'name': '题材'+code, 'aliases': [], 'members': [{'code': code, 'core': True}]})
            feeds[code] = {'pages': 1, 'rows': [{'source': 'eastmoney', 'id': f'{i}-{j}', 'author': str(j), 'code': code, 'date': '2026-09-07 22:00:00', 'text': '今天公司业绩增长值得关注', 'replies': j} for j in range(20+i)]}
        rows, chosen, _ = rank_topics(groups, feeds, stocks, '2026-09-07')
        self.assertEqual(len(chosen), 10)
        self.assertEqual(chosen[0]['id'], '11')
        self.assertGreater(chosen[0]['attentionScore'], 95)  # 12 candidates, not 10
        groups[0]['members'][0]['core'] = False
        rows, _, _ = rank_topics(groups, feeds, stocks, '2026-09-07')
        self.assertEqual(rows[0]['authors'], 0)
        self.assertIsNone(rows[0]['attentionScore'])

    def test_partial_feed_is_explicit_and_forwards_are_in_interaction(self):
        groups = [{'id': str(i), 'name': '题材' + str(i), 'aliases': [], 'members': [{'code': str(i), 'core': True}]} for i in range(5)]
        stocks = {str(i): {'f3': 1, 'f8': 1} for i in range(5)}
        feeds = {str(i): {'pages': 1, 'complete': False, 'rows': [{'source': 'eastmoney', 'id': f'{i}-{j}', 'author': f'{i}-{j}', 'code': str(i), 'date': '2026-09-07 10:00:00', 'text': '关注公司', 'replies': 0, 'forwards': 10} for j in range(20)]} for i in range(5)}
        rows, chosen, _ = rank_topics(groups, feeds, stocks, '2026-09-07')
        self.assertEqual(len(chosen), 5)
        self.assertEqual(rows[0]['coverageQuality'], 'partial')
        self.assertEqual(rows[0]['completeSourceCoverage'], 0)
        self.assertGreater(rows[0]['interactionTotal'], 0)
        self.assertEqual(rows[0]['rankingQuality'], 'partial-lower-bound')

    def test_expansion_is_global_round_robin_and_skips_complete_feeds(self):
        rows = [
            {'id': 'a', 'eligible': True, 'attentionScore': 90, 'authors': 50, 'coreMembers': ['1'], 'members': [{'code': str(i)} for i in range(1, 6)]},
            {'id': 'b', 'eligible': True, 'attentionScore': 80, 'authors': 40, 'coreMembers': ['6'], 'members': [{'code': str(i)} for i in range(6, 11)]},
        ]
        stocks = {str(i): {'f6': i} for i in range(1, 11)}
        feeds = {str(i): {'complete': i == 2} for i in range(1, 11)}
        self.assertEqual(select_expansion_codes(rows, stocks, feeds, topic_limit=2, stock_limit=4), ['1', '6', '5', '10'])
        low = {'id': 'low', 'eligible': False, 'sourceCoverage': 1, 'authors': 3, 'members': [{'code': '11'}]}
        self.assertEqual(select_expansion_codes([low], {**stocks, '11': {'f6': 1}}, {**feeds, '11': {'complete': False}}, topic_limit=1, stock_limit=1), ['11'])

    def test_complete_topics_remain_above_partial_lower_bounds(self):
        groups, feeds, stocks = [], {}, {}
        for i in range(5):
            code = str(i)
            stocks[code] = {'f3': i, 'f8': i}
            groups.append({'id': 'complete' + code, 'name': '完整' + code, 'aliases': [], 'members': [{'code': code, 'core': True}]})
            feeds[code] = {'pages': 1, 'complete': True, 'rows': [{'source': 'eastmoney', 'id': f'{code}-{j}', 'author': f'{code}-{j}', 'code': code, 'date': '2026-09-07 10:00:00', 'text': '关注公司', 'replies': 1, 'forwards': 0} for j in range(20)]}
        for i in range(5, 10):
            code = str(i)
            stocks[code] = {'f3': i, 'f8': i}
            groups.append({'id': 'partial' + code, 'name': '部分' + code, 'aliases': [], 'members': [{'code': code, 'core': True}]})
            feeds[code] = {'pages': 1, 'complete': False, 'rows': [{'source': 'eastmoney', 'id': f'{code}-{j}', 'author': f'{code}-{j}', 'code': code, 'date': '2026-09-07 10:00:00', 'text': '关注公司', 'replies': 1000, 'forwards': 0} for j in range(20)]}
        _, chosen, _ = rank_topics(groups, feeds, stocks, '2026-09-07')
        self.assertTrue(all(row['coverageQuality'] == 'complete' for row in chosen[:5]))

    def test_verified_body_is_used_before_behavior_classification(self):
        _, batch = fixture()
        code = next(iter(batch['feeds']))
        post = batch['feeds'][code]['rows'][0]
        batch['profileBodies'] = {post['id']: {'date': post['date'], 'code': code, 'author': post['author'], 'text': '我今天追高买入了，准备继续冲。'}}
        observation = measure_members(batch, [code], '2026-09-04')
        self.assertEqual(observation['bodyObserved'], 1)
        self.assertGreaterEqual(observation['chaseCount'], 1)
        self.assertTrue(any(post['intent'] == '追买自述／意愿' for post in observation['posts']))

    def test_new_capture_preserves_candidate_score_and_old_report_method(self):
        market, batch = fixture()
        from sentiment.report_sources import select_hot_boards
        boards = select_hot_boards(market)
        for b in boards: b.update(attentionScore=72.3, spreadScore=65, coreMembers=[m['code'] for m in batch['members'][b['id']]['members']])
        old = assemble_report(market, batch)
        batch.update(discovery={'note': 'test sample'}, topicBoards=boards, cutoff='23:59:59')
        new = assemble_report(market, batch)
        self.assertEqual(new['sectors'][0]['dimensions']['discussion'], 72.3)
        self.assertEqual(old['meta']['analysisVersion'], 'following-1.0')
        self.assertEqual(new['meta']['analysisVersion'], 'following-topic-2.1')
        for feed in batch['feeds'].values():
            for post in feed['rows']: post['text'] = '公司今日盘面值得继续观察'
        uncertain = assemble_report(market, batch)['sectors'][0]
        self.assertIsNone(uncertain['leekScore']['score'])
        self.assertIsNotNone(uncertain['leekScore']['rawExpressionScore'])

    def test_identical_members_do_not_occupy_two_places(self):
        groups, feeds, stocks = [], {}, {}
        for i in range(6):
            code = str(i)
            stocks[code] = {'f3': 1, 'f8': 1}
            groups.append({'id': code, 'name': '方向'+code, 'aliases': [], 'members': [{'code': code, 'core': True}]})
            feeds[code] = {'pages': 1, 'rows': [{'source': 'eastmoney', 'id': f'{i}-{j}', 'author': str(j), 'code': code, 'date': '2026-09-07 10:00:00', 'text': '今天公司业绩增长值得关注', 'replies': j} for j in range(25)]}
        groups.append({**groups[0], 'id': 'duplicate', 'name': '重复方向'})
        _, chosen, suppressed = rank_topics(groups, feeds, stocks, '2026-09-07')
        self.assertEqual(len(chosen), 6)
        self.assertEqual(len(suppressed), 1)
