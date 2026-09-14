"""Discover topics from a broad stock sample before ranking discussion.

F10 tags describe observed current membership, never a historical universe.
"""
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
import hashlib
import json
import math
import re
import statistics
from .collectors import request_text, CN_TZ
from .market_watch import read_json, atomic_json, percentile
from .measurement import prepare_observations
from .observations import collect_feed

CONFIG = read_json(Path(__file__).resolve().parents[1] / "config/topic-discovery.json", {})
VERSION = CONFIG["version"]
CUTOFF = "23:59:59"
TERMS = {'光模块/CPO': ['光模块', '光通信', 'CPO'], 'PCB/印制电路板': ['PCB', '印制电路', '覆铜板'], '猪肉/养殖': ['生猪', '养猪', '猪肉'], '存储芯片': ['存储芯片', '存储器', '存储控制']}
ALGORITHM_REVISION = 'topic-discovery-1.1-r2'
CONFIG_HASH = hashlib.sha256(json.dumps({"config": CONFIG, "terms": TERMS, "algorithm": ALGORITHM_REVISION}, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:16]

def terms_for(name):
    return TERMS.get(name, [re.sub(r'概念$|板块$', '', name)])


def _rank_value(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _topic_specificity(group):
    """Prefer explicit/specific F10 topics over broad parent labels when members overlap."""
    ranks = [_rank_value(value) for value in group.get('ranks', [])]
    # F10 rank 1-3 are broad industry layers; higher ranks are usually
    # narrower concepts.  Explicit aliases are also useful named themes.
    explicit = group.get('name') in TERMS or any(alias in sum(TERMS.values(), []) for alias in group.get('aliases', []))
    return (1 if explicit else 0, max(ranks or [0]), -len(group.get('members', [])))


def _overlap(a, b):
    left = {m['code'] for m in a.get('members', [])}
    right = {m['code'] for m in b.get('members', [])}
    intersection = len(left & right)
    union = len(left | right)
    minimum = min(len(left), len(right))
    return (intersection / union if union else 0, intersection / minimum if minimum else 0)


def select_expansion_codes(rows, stocks, feeds, *, topic_limit=None, stock_limit=None):
    """Choose a bounded, round-robin set of incomplete feeds for a second pass.

    The first pass samples many stocks. Re-reading every member of the top
    topics would multiply requests and let one broad topic consume the whole
    budget, so the expansion budget is global and distributed across topics.
    Core members are preferred, then larger traded value. Complete feeds are
    skipped because a second read cannot improve their coverage flag.
    """
    topic_limit = topic_limit or CONFIG.get('expansionTopics', 10)
    stock_limit = stock_limit or CONFIG.get('expansionStocks', 60)
    candidates = [r for r in rows if r.get('eligible') or (r.get('sourceCoverage', 0) >= CONFIG.get('minimumSourceCoverage', .8) and r.get('authors', 0) > 0)]
    ranked = sorted(candidates,
                    key=lambda r: (0 if isinstance(r.get('attentionScore'), (int, float)) else 1,
                                   -(r.get('attentionScore') or 0), -r.get('authors', 0), r['id']))[:topic_limit]
    buckets = []
    for topic in ranked:
        core = set(topic.get('coreMembers', []))
        members = [m for m in topic.get('members', []) if not feeds.get(m['code'], {}).get('complete')]
        members.sort(key=lambda m: (m['code'] not in core, -(stocks.get(m['code'], {}).get('f6') or 0), m['code']))
        if members:
            buckets.append(members)
    expanded, seen = [], set()
    while buckets and len(expanded) < stock_limit:
        next_buckets = []
        for bucket in buckets:
            while bucket and bucket[0]['code'] in seen:
                bucket.pop(0)
            if bucket and len(expanded) < stock_limit:
                code = bucket.pop(0)['code']
                seen.add(code)
                expanded.append(code)
            if bucket:
                next_buckets.append(bucket)
        buckets = next_buckets
    return expanded


def _history_for_topic(root, name, day):
    """Return prior same-method cross-sectional attention scores for a topic.

    The score is deliberately optional.  It is a relative historical context,
    not a claim that current F10 membership reconstructs a historical board.
    """
    values = []
    directory = Path(root) / 'work/topic-discovery'
    for path in directory.glob('????-??-??/discovery.json'):
        saved = read_json(path, {})
        if not isinstance(saved, dict):
            continue
        meta = saved.get('meta') if isinstance(saved.get('meta'), dict) else {}
        saved_date = str(saved.get('date', ''))
        if saved_date >= day or meta.get('methodHash') != CONFIG_HASH:
            continue
        topics = saved.get('topics') if isinstance(saved.get('topics'), list) else []
        row = next((item for item in topics if isinstance(item, dict) and item.get('name') == name and item.get('eligible') and isinstance(item.get('attentionScore'), (int, float)) and not isinstance(item.get('attentionScore'), bool) and math.isfinite(item['attentionScore'])), None)
        if row:
            values.append((saved_date, float(row['attentionScore'])))
    return sorted(values)[-CONFIG.get('historicalBaselineDays', 60):]


def stock_sample(raw, day):
    rows = {r['f12']: r for r in raw.get('groups', {}).get('stocks', {}).get('rows', [])
            if re.fullmatch(r'\d{6}', str(r.get('f12', ''))) and isinstance(r.get('f124'), (int, float))
            and datetime.fromtimestamp(r['f124'], CN_TZ).date().isoformat() == day and (r.get('f6') or 0) > 0}
    picked = {}
    for field, count in [('f6', CONFIG['amountStocks']), ('f3', CONFIG['risingStocks']), ('f8', CONFIG['turnoverStocks'])]:
        picked.update({r['f12']: r for r in sorted(rows.values(), key=lambda r: (-(r.get(field) or 0), r['f12']))[:count]})
    others = sorted((r for c, r in rows.items() if c not in picked), key=lambda r: hashlib.sha256((day + r['f12']).encode()).hexdigest())
    picked.update({r['f12']: r for r in others[:CONFIG['explorationStocks']]})
    return rows, picked


def fetch_tags(code):
    prefix = 'SH' if code.startswith(('6', '9')) and not code.startswith('92') else 'BJ' if code.startswith(('4', '8', '92')) else 'SZ'
    url = 'https://emweb.securities.eastmoney.com/PC_HSF10/CoreConception/PageAjax?code=' + prefix + code
    data = json.loads(request_text(url, 'https://emweb.securities.eastmoney.com/', timeout=8, attempts=1))
    tags = data.get('ssbk')
    if not isinstance(tags, list) or not tags: raise ValueError('题材标签缺失')
    if any(str(t.get('SECURITY_CODE')) != code for t in tags): raise ValueError('题材标签证券代码不匹配')
    business = ' '.join(r.get('KEYWORD', '') for r in data.get('hxtc', [])
                        if re.search(r'研发|生产|制造|销售|服务|设计|养殖|种植|存储|光器件', r.get('KEYWORD', ''))
                        and not re.search(r'优势|经营范围', r.get('KEYWORD', '')))
    return [{'code': str(t['BOARD_CODE']), 'name': t['BOARD_NAME'], 'rank': t.get('BOARD_RANK'),
             'core': _rank_value(t.get('BOARD_RANK')) == 3 or any(term.lower() in business.lower() for term in terms_for(CONFIG['aliases'].get(t['BOARD_NAME'], t['BOARD_NAME']))), 'businessEvidence': business[:400]}
            for t in tags if t.get('BOARD_CODE') and t.get('BOARD_NAME')]


def topic_groups(stocks, tags):
    groups = {}
    for code, labels in tags.items():
        for label in labels:
            original = label['name']
            if re.search(CONFIG['excludePattern'], original) or re.search(r'热股$|^题材股$|^趋势股$|^最近|^长江三角$|^西部大开发$|^粤港澳|^京津冀', original): continue
            # Parent broad industries are not an additional independent theme.
            if _rank_value(label.get('rank')) == 1: continue
            name = CONFIG['aliases'].get(original, original)
            key = hashlib.sha256(name.encode()).hexdigest()[:16]
            group = groups.setdefault(key, {'id': 'topic:' + key, 'code': key, 'name': name, 'kind': 'topic', 'provider': 'eastmoney-f10', 'members': {}, 'aliases': set(), 'ranks': set()})
            old = group['members'].get(code, {})
            group['members'][code] = {'code': code, 'name': stocks[code].get('f14', code), 'core': bool(old.get('core') or label.get('core')), 'businessEvidence': label.get('businessEvidence', '')}
            group['aliases'].add(original)
            group['ranks'].add(_rank_value(label.get('rank')))
    return [{**g, 'members': list(g['members'].values()), 'aliases': sorted(g['aliases']), 'ranks': sorted(g['ranks'])} for g in groups.values() if len(g['members']) >= CONFIG['minimumMembers']]


def rank_topics(groups, feeds, stocks, day, root='.'):
    rows = []
    for group in groups:
        codes = [m['code'] for m in group['members']]
        good = [c for c in codes if feeds.get(c, {}).get('pages', 0) > 0 and not feeds[c].get('error')]
        complete = [c for c in good if feeds[c].get('complete')]
        core = {m['code'] for m in group['members'] if m.get('core')}
        terms = terms_for(group['name']) + group['aliases']
        posts = [p for c in good for p in feeds[c]['rows'] if c in core or any(t.lower() in p['text'].lower() for t in terms)]
        observed = prepare_observations(posts, day, CUTOFF)
        authors = observed['observedAuthors']
        interactions = [p for p in observed['analyzed'] if isinstance(p.get('replies'), (int, float)) and p['replies'] >= 0 and isinstance(p.get('forwards', 0), (int, float)) and p.get('forwards', 0) >= 0]
        source_coverage = len(good) / len(codes) if codes else 0
        complete_coverage = len(complete) / len(codes) if codes else 0
        interaction_coverage = len(interactions) / len(observed['analyzed']) if observed['analyzed'] else 0
        eligible = source_coverage >= CONFIG['minimumSourceCoverage'] and authors >= CONFIG['minimumAccounts'] and interaction_coverage >= .8
        rows.append({**group, 'authors': authors, 'sourceCoverage': round(source_coverage, 3), 'completeSourceCoverage': round(complete_coverage, 3), 'interactionCoverage': round(interaction_coverage, 3), 'coverageQuality': 'complete' if complete_coverage >= CONFIG['minimumCompleteSourceCoverage'] else 'partial', 'eligible': eligible,
                     'coreMembers': sorted(core), 'discussionAccounts': authors, 'interactionTotal': sum(math.log1p(p['replies'] + p.get('forwards', 0)) for p in interactions), 'accountDensity': authors / math.sqrt(len(codes)),
                     'interactionDensity': sum(math.log1p(p['replies'] + p.get('forwards', 0)) for p in interactions) / math.sqrt(len(codes)),
                     'changePct': sum(stocks[c].get('f3') or 0 for c in codes) / len(codes),
                     'turnover': sum(stocks[c].get('f8') or 0 for c in codes) / len(codes)})
    usable = [r for r in rows if r['eligible']]
    complete_usable = [r for r in usable if r['completeSourceCoverage'] >= CONFIG['minimumCompleteSourceCoverage']]
    cohort = complete_usable if len(complete_usable) >= CONFIG['minimumRankableTopics'] else usable
    ranking_quality = 'complete' if len(complete_usable) >= CONFIG['minimumRankableTopics'] else 'partial-lower-bound'
    for r in rows:
        r['rankingQuality'] = 'complete' if r['completeSourceCoverage'] >= CONFIG['minimumCompleteSourceCoverage'] else 'partial-lower-bound' if r['eligible'] else 'insufficient'
        r['cohortQuality'] = ranking_quality
        r['attentionScore'] = round(.65 * percentile(r['discussionAccounts'], [v['discussionAccounts'] for v in cohort]) + .35 * percentile(r['interactionTotal'], [v['interactionTotal'] for v in cohort]), 1) if r['eligible'] and len(cohort) >= 5 else None
        history = _history_for_topic(root, r['name'], day)
        r['historicalBaselineDays'] = len(history)
        r['historicalAttentionScore'] = percentile(r['attentionScore'], [value for _, value in history]) if r['attentionScore'] is not None and len(history) >= CONFIG.get('minimumHistoricalDays', 20) else None
        r['historicalAttentionMedian'] = round(statistics.median(value for _, value in history), 1) if history else None
    ranked_eligible = sorted((r for r in rows if r['attentionScore'] is not None), key=lambda r: (-r['attentionScore'], -r['authors'], r['id']))
    # A partial topic is a lower bound.  It can fill an empty slot when there
    # are not ten complete topics, but it must not outrank a complete topic
    # merely because its truncated page happened to contain many posts.
    ranked = ([r for r in ranked_eligible if r['coverageQuality'] == 'complete'] +
              [r for r in ranked_eligible if r['coverageQuality'] != 'complete']) if len(complete_usable) >= CONFIG['minimumRankableTopics'] else ranked_eligible
    chosen, suppressed = [], []
    for r in ranked:
        overlap = next((s for s in chosen if (_overlap(r, s)[0] >= CONFIG['maximumOverlap'] or _overlap(r, s)[1] >= CONFIG.get('maximumContainmentOverlap', .8))), None)
        if overlap:
            preferred = r if _topic_specificity(r) > _topic_specificity(overlap) else overlap
            if preferred is r:
                chosen.remove(overlap)
                chosen.append(r)
                suppressed.append({'name': overlap['name'], 'representedBy': r['name'], 'reason': '成分包含重叠'})
            else:
                suppressed.append({'name': r['name'], 'representedBy': overlap['name'], 'reason': '成分包含重叠'})
        else:
            chosen.append(r)
        if len(chosen) == 10: break
    for r in rows:
        r['selectionScore'] = r['attentionScore']
        r['spreadScore'] = percentile(r['interactionTotal'], [v['interactionTotal'] for v in cohort]) if r['eligible'] and len(cohort) >= 5 else None
        r['relativeActivity'] = percentile(r['turnover'], [v['turnover'] for v in rows])
    def final_key(row):
        # When a complete cohort exists, keep partial lower bounds below it
        # in the displayed rank as well as during slot selection.
        quality = 0 if ranking_quality == 'partial-lower-bound' or row.get('coverageQuality') == 'complete' else 1
        return (quality, -row['attentionScore'], -row['authors'], row['id'])
    return rows, sorted(chosen, key=final_key), suppressed


def discover(root, market, previous):
    root = Path(root); day = market['meta']['tradeDate']
    raw = read_json(root / 'work/market-observations' / f'{day}.json', {})
    universe, stocks = stock_sample(raw, day)
    if not stocks: raise RuntimeError('题材发现缺少已核验的当日个股行情')
    tags, feeds, errors = {}, {}, []
    cache = root / 'work/topic-discovery' / day
    def task(code):
        saved = read_json(cache / 'tags' / f'{code}.json', {})
        labels = saved.get('tags') if saved.get('date') == day and saved.get('schema') == 3 else None
        if not labels:
            labels = fetch_tags(code)
            atomic_json(cache / 'tags' / f'{code}.json', {'date': day, 'schema': 3, 'observedAt': datetime.now(CN_TZ).isoformat(), 'tags': labels})
        feed = collect_feed(code, previous, CONFIG['feedPages'])
        feed['observedAt'] = datetime.now(CN_TZ).isoformat(timespec='seconds')
        return labels, feed
    print(f"题材发现：全A {len(universe)} 股中观察 {len(stocks)} 股；先读取标签和讨论，再选前十。", flush=True)
    with ThreadPoolExecutor(max_workers=CONFIG['workers']) as pool:
        futures = {pool.submit(task, code): code for code in stocks}
        for i, f in enumerate(as_completed(futures), 1):
            code = futures[f]
            try: tags[code], feeds[code] = f.result()
            except Exception as e: errors.append({'code': code, 'error': type(e).__name__})
            if i % 25 == 0 or i == len(stocks): print(f'题材发现 {i}/{len(stocks)}：标签 {len(tags)}，讨论列表 {len(feeds)}', flush=True)
    if len(tags) / len(stocks) < CONFIG['minimumSourceCoverage']: raise RuntimeError('题材映射覆盖不足，保留旧报告')
    groups = topic_groups(stocks, tags)
    rows, selected, suppressed = rank_topics(groups, feeds, stocks, day, root=root)
    expanded_codes = select_expansion_codes(rows, stocks, feeds)
    if expanded_codes and CONFIG.get('expandedFeedPages', CONFIG['feedPages']) > CONFIG['feedPages']:
        candidate_count = sum(bool(r.get('eligible') or (r.get('sourceCoverage', 0) >= CONFIG.get('minimumSourceCoverage', .8) and r.get('authors', 0) > 0)) for r in rows)
        topic_count = min(candidate_count, CONFIG.get('expansionTopics', 10))
        print(f"题材发现：对前 {topic_count} 个候选题材补读 {len(expanded_codes)} 只股票的讨论，最多 {CONFIG['expandedFeedPages']} 页。", flush=True)
        def expand(code):
            return collect_feed(code, previous, CONFIG['expandedFeedPages'])
        with ThreadPoolExecutor(max_workers=CONFIG['workers']) as pool:
            futures = {pool.submit(expand, code): code for code in expanded_codes}
            for i, future in enumerate(as_completed(futures), 1):
                code = futures[future]
                try:
                    candidate = future.result()
                    candidate['observedAt'] = datetime.now(CN_TZ).isoformat(timespec='seconds')
                    old = feeds.get(code, {})
                    if len(candidate.get('rows', [])) > len(old.get('rows', [])) or (candidate.get('complete') and not old.get('complete')):
                        feeds[code] = candidate
                except Exception as exc:
                    errors.append({'code': code, 'error': type(exc).__name__ + ':expanded'})
                if i % 25 == 0 or i == len(futures): print(f'题材补读 {i}/{len(futures)}', flush=True)
        rows, selected, suppressed = rank_topics(groups, feeds, stocks, day, root=root)
    if len(selected) < 5: raise RuntimeError('有效题材不足5个，不能生成关注排名')
    cohort_quality = next((r.get('cohortQuality') for r in rows if r.get('attentionScore') is not None), 'insufficient')
    ranking_quality = 'complete' if selected and all(r.get('coverageQuality') == 'complete' for r in selected) else 'partial-lower-bound'
    selected_partial = sum(r.get('coverageQuality') != 'complete' for r in selected)
    meta = {'version': VERSION, 'methodHash': CONFIG_HASH, 'universeStocks': len(universe), 'sampleStocks': len(stocks), 'tagCoverage': len(tags), 'candidateTopics': len(rows), 'eligibleTopics': sum(r['eligible'] for r in rows), 'completeTopics': sum(r.get('coverageQuality') == 'complete' for r in rows if r.get('eligible')), 'rankingQuality': ranking_quality, 'cohortQuality': cohort_quality, 'selectedPartialTopics': selected_partial, 'expandedStocks': len(expanded_codes), 'historicalBaselineDays': CONFIG.get('minimumHistoricalDays', 20), 'suppressed': suppressed,
            'amountCoverage': sum(s['f6'] for s in stocks.values()) / sum(s['f6'] for s in universe.values()),
            'note': '全A成交额/涨幅/换手活跃样本＋按日期固定抽样；东方财富题材标签与主营业务证据。主营相关股票的讨论或明确提及题材的帖子才归入该题材，不复制所有概念标签。非全市场发言普查；关注分为候选题材内账户规模65%与回复互动35%的相对分位，描述关注总量而非每股讨论密度。达到完整来源门槛才使用完整排名，否则明确标为观测下限；回复和转发均计入互动。全天发言截至采集时间；相近题材按成分包含关系去重。'}
    atomic_json(cache / 'discovery.json', {'meta': meta, 'date': day, 'stocks': stocks, 'tags': tags, 'topics': rows, 'selectedIds': [s['id'] for s in selected], 'errors': errors})
    return meta, selected, feeds
