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
from .collectors import request_text, CN_TZ
from .market_watch import read_json, atomic_json, percentile
from .measurement import prepare_observations
from .observations import collect_feed

CONFIG = read_json(Path(__file__).resolve().parents[1] / "config/topic-discovery.json", {})
VERSION = CONFIG["version"]
CUTOFF = "23:59:59"
TERMS = {'光模块/CPO': ['光模块', '光通信', 'CPO'], 'PCB/印制电路板': ['PCB', '印制电路', '覆铜板'], '猪肉/养殖': ['生猪', '养猪', '猪肉'], '存储芯片': ['存储芯片', '存储器', '存储控制']}

def terms_for(name):
    return TERMS.get(name, [re.sub(r'概念$|板块$', '', name)])


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
             'core': t.get('BOARD_RANK') == 3 or any(term.lower() in business.lower() for term in terms_for(CONFIG['aliases'].get(t['BOARD_NAME'], t['BOARD_NAME']))), 'businessEvidence': business[:400]}
            for t in tags if t.get('BOARD_CODE') and t.get('BOARD_NAME')]


def topic_groups(stocks, tags):
    groups = {}
    for code, labels in tags.items():
        for label in labels:
            original = label['name']
            if re.search(CONFIG['excludePattern'], original) or re.search(r'热股$|^题材股$|^趋势股$|^最近|^长江三角$|^西部大开发$|^粤港澳|^京津冀', original): continue
            # Parent broad industries are not an additional independent theme.
            if label.get('rank') == 1: continue
            name = CONFIG['aliases'].get(original, original)
            key = hashlib.sha256(name.encode()).hexdigest()[:16]
            group = groups.setdefault(key, {'id': 'topic:' + key, 'code': key, 'name': name, 'kind': 'topic', 'provider': 'eastmoney-f10', 'members': {}, 'aliases': set()})
            old = group['members'].get(code, {})
            group['members'][code] = {'code': code, 'name': stocks[code].get('f14', code), 'core': bool(old.get('core') or label.get('core')), 'businessEvidence': label.get('businessEvidence', '')}
            group['aliases'].add(original)
    return [{**g, 'members': list(g['members'].values()), 'aliases': sorted(g['aliases'])} for g in groups.values() if len(g['members']) >= CONFIG['minimumMembers']]


def rank_topics(groups, feeds, stocks, day):
    rows = []
    for group in groups:
        codes = [m['code'] for m in group['members']]
        good = [c for c in codes if feeds.get(c, {}).get('pages', 0) > 0 and not feeds[c].get('error')]
        core = {m['code'] for m in group['members'] if m.get('core')}
        terms = terms_for(group['name']) + group['aliases']
        posts = [p for c in good for p in feeds[c]['rows'] if c in core or any(t.lower() in p['text'].lower() for t in terms)]
        observed = prepare_observations(posts, day, CUTOFF)
        authors = observed['observedAuthors']
        replies = [p['replies'] for p in observed['analyzed'] if isinstance(p.get('replies'), (int, float)) and p['replies'] >= 0]
        eligible = len(good) / len(codes) >= CONFIG['minimumSourceCoverage'] and authors >= CONFIG['minimumAccounts'] and len(replies) >= .8 * len(observed['analyzed'])
        rows.append({**group, 'authors': authors, 'sourceCoverage': len(good) / len(codes), 'eligible': eligible,
                     'coreMembers': sorted(core), 'discussionAccounts': authors, 'interactionTotal': sum(math.log1p(v) for v in replies), 'accountDensity': authors / math.sqrt(len(codes)),
                     'interactionDensity': sum(math.log1p(v) for v in replies) / math.sqrt(len(codes)),
                     'changePct': sum(stocks[c].get('f3') or 0 for c in codes) / len(codes),
                     'turnover': sum(stocks[c].get('f8') or 0 for c in codes) / len(codes)})
    usable = [r for r in rows if r['eligible']]
    for r in rows:
        r['attentionScore'] = round(.65 * percentile(r['discussionAccounts'], [v['discussionAccounts'] for v in usable]) + .35 * percentile(r['interactionTotal'], [v['interactionTotal'] for v in usable]), 1) if r['eligible'] and len(usable) >= 5 else None
    ranked = sorted((r for r in rows if r['attentionScore'] is not None), key=lambda r: (-r['attentionScore'], -r['authors'], r['id']))
    chosen, suppressed = [], []
    for r in ranked:
        codes = {m['code'] for m in r['members']}
        overlap = next((s for s in chosen if len(codes & {m['code'] for m in s['members']}) / len(codes | {m['code'] for m in s['members']}) >= CONFIG['maximumOverlap']), None)
        if overlap:
            suppressed.append({'name': r['name'], 'representedBy': overlap['name']})
        else:
            chosen.append(r)
        if len(chosen) == 10: break
    for r in rows:
        r['selectionScore'] = r['attentionScore']
        r['spreadScore'] = percentile(r['interactionTotal'], [v['interactionTotal'] for v in usable]) if r['eligible'] and len(usable) >= 5 else None
        r['relativeActivity'] = percentile(r['turnover'], [v['turnover'] for v in rows])
    return rows, chosen, suppressed


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
    rows, selected, suppressed = rank_topics(groups, feeds, stocks, day)
    if len(selected) < 5: raise RuntimeError('有效题材不足5个，不能生成关注排名')
    meta = {'version': VERSION, 'universeStocks': len(universe), 'sampleStocks': len(stocks), 'tagCoverage': len(tags), 'candidateTopics': len(rows), 'eligibleTopics': sum(r['eligible'] for r in rows), 'suppressed': suppressed,
            'amountCoverage': sum(s['f6'] for s in stocks.values()) / sum(s['f6'] for s in universe.values()),
            'note': '全A成交额/涨幅/换手活跃样本＋按日期固定抽样；东方财富题材标签与主营业务证据。主营相关股票的讨论或明确提及题材的帖子才归入该题材，不复制所有概念标签。非全市场发言普查；关注分为候选题材内账户规模65%与回复互动35%的相对分位，描述关注总量而非每股讨论密度。全天发言截至采集时间；相近题材去重。'}
    atomic_json(cache / 'discovery.json', {'meta': meta, 'date': day, 'stocks': stocks, 'tags': tags, 'topics': rows, 'selectedIds': [s['id'] for s in selected], 'errors': errors})
    return meta, selected, feeds
