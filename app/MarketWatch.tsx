"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { sortedBoards, type BoardSort } from "../lib/market-ranking";
import type { MarketSnapshot, MarketBoard, BoardDetails } from "./market-types";
import { temperatureTone } from "../lib/report-presentation";

const fmt = (value: number | null | undefined, digits = 2) => value == null ? "—" : value.toLocaleString("zh-CN", { maximumFractionDigits: digits });
const pct = (value: number | null | undefined) => value == null ? "—" : `${value > 0 ? "+" : ""}${fmt(value)}%`;
const money = (value: number | null | undefined) => value == null ? "—" : `${fmt(value / 1e8)} 亿`;
const collectedTime = (value: string) => `${new Date(value).toLocaleString("zh-CN", { timeZone: "Asia/Shanghai", hour12: false })} 北京时间`;

function BoardDetail({ board, day, onClose }: { board: MarketBoard; day: string; onClose: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [result, setResult] = useState<BoardDetails | null>(null), [error, setError] = useState("");
  useEffect(() => {
    dialog.current?.showModal();
    const controller = new AbortController();
    const url = board.provider === "sina-tencent" ? `/data/market/members/${day}/${encodeURIComponent(board.code)}.json` : `/api/market-board?code=${board.code}&date=${day}`;
    void fetch(url, { signal: controller.signal }).then(async response => {
      if (!response.ok && board.provider === "sina-tencent") throw new Error("该日成分明细尚未保存");
      const payload = await response.json() as BoardDetails & { error?: string };
      if (!response.ok) throw new Error(payload.error || "成分暂时不可用");
      if (payload.code !== board.code || payload.date !== day || !Array.isArray(payload.members)) throw new Error("成分日期或格式不匹配");
      setResult(payload);
    }).catch(failure => { if (!controller.signal.aborted) setError(failure instanceof Error ? failure.message : "成分读取失败"); });
    return () => controller.abort();
  }, [board.code, board.provider, day]);
  return <dialog ref={dialog} className="research-dialog v4-dialog market-dialog" onClose={onClose} onCancel={onClose}>
    <button className="v4-dialog-close" onClick={onClose} aria-label="关闭板块详情">关闭 ×</button>
    <span className="eyebrow">{board.kind === "industry" ? "行业" : "概念"} · {board.code} · {day}</span><h2>{board.name}</h2>
    <div className="market-detail-facts"><span>板块涨跌 <b>{pct(board.changePct)}</b></span><span>换手率 <b>{board.turnover == null ? "—" : `${fmt(board.turnover)}%`}</b></span><span>成交额 <b>{money(board.amount)}</b></span></div>
    <p className="fine-print">换手活跃 {fmt(board.relativeActivity, 1)} / 100，是当天 {board.relativeCount} 个同类可得板块中的位置。自身历史换手分位 {fmt(board.activityHistory, 1)}，已记录 {board.baselineDays}/20 个先前有效日。两种刻度分别展示。</p>
    <h3>板块成分与行情</h3>
    {!result && !error && <p role="status">正在读取该板块成分…</p>}
    {error && <p role="alert" className="query-error">{error}</p>}
    {!!result?.excludedMembers?.length && <details><summary>查看不在当期 A 股目录的原始成员（{result.excludedMembers.length}）</summary><p className="fine-print">{result.excludedMembers.map(row => `${row.name} ${row.code}`).join("、")}。这些来源旧成员不参与本次板块统计；剔除依据为已完整读取的当期 A 股目录。</p></details>}
    {result && <><p className="fine-print">{result.members.length}/{result.expected} 只成分 · {result.reason} · 采集于 {collectedTime(result.collectedAt)}</p><div className="v4-table-scroll"><table className="v4-table"><thead><tr><th>成分股</th><th>涨跌幅</th><th>换手率</th><th>成交额</th></tr></thead><tbody>{result.members.map(row => <tr key={row.code}><th>{row.name}<small>{row.code}</small></th><td className={(row.changePct ?? 0) >= 0 ? "rise" : "fall"}>{pct(row.changePct)}</td><td>{row.turnover == null ? "—" : `${fmt(row.turnover)}%`}</td><td>{money(row.amount)}</td></tr>)}</tbody></table></div></>}
    <p className="fine-print">{board.provider === "sina-tencent" ? `行情采用有效成分等权涨跌和换手均值；${board.quoteCoverage}/${board.memberCount} 股有当日收盘行情，至少覆盖90%才出值。` : "板块行情来自来源定义的指数，成分明细用于核对范围。"}尚未汇总该板块全部成分的社区讨论，不用领涨股评论代替板块讨论。</p>
    <a href={board.sourceUrl} target="_blank" rel="noreferrer">核对来源板块页面 ↗</a>
  </dialog>;
}

export function MarketWatch({ initialSnapshot }: { initialSnapshot: MarketSnapshot | null }) {
  const [snapshot, setSnapshot] = useState(initialSnapshot);
  const [kind, setKind] = useState("industry"), [query, setQuery] = useState(""), [sort, setSort] = useState<BoardSort>("changePct");
  const [limit, setLimit] = useState(10), [dates, setDates] = useState<string[]>(initialSnapshot ? [initialSnapshot.meta.tradeDate] : []);
  const [selected, setSelected] = useState<MarketBoard | null>(null), [pending, setPending] = useState(false), [error, setError] = useState("");
  const request = useRef<AbortController | null>(null), sequence = useRef(0);
  const latestDate = useRef(initialSnapshot?.meta.tradeDate);
  useEffect(() => { const controller = new AbortController(); void fetch("/data/market/index.json", { signal: controller.signal, cache: "no-store" }).then(async response => response.ok ? await response.json() as { dates?: string[] } : null).then(value => { if (Array.isArray(value?.dates)) setDates(value.dates.filter(date => /^\d{4}-\d{2}-\d{2}$/.test(date))); }).catch(() => {}); return () => { controller.abort(); request.current?.abort(); }; }, []);
  useEffect(() => {
    const controller = new AbortController();
    const refresh = async () => {
      if (request.current) return;
      try {
        const response = await fetch("/data/market/latest.json", { signal: controller.signal, cache: "no-store" });
        if (!response.ok) return;
        const value = await response.json() as MarketSnapshot;
        if (value.meta?.methodVersion !== "market-watch-1.0" || !/^\d{4}-\d{2}-\d{2}$/.test(value.meta.tradeDate) || !Array.isArray(value.boards)) return;
        const previousLatest = latestDate.current;
        // Polling may advance the latest view, but never moves a historical view.
        setSnapshot(current => !current || current.meta.tradeDate === previousLatest ? value : current);
        latestDate.current = value.meta.tradeDate;
        setDates(current => [...new Set([...current, value.meta.tradeDate])].sort());
      } catch { /* Keep the last readable market snapshot. */ }
    };
    const timer = setInterval(() => void refresh(), 300000);
    return () => { clearInterval(timer); controller.abort(); };
  }, []);
  const changeDate = async (date: string) => {
    request.current?.abort(); const controller = new AbortController(); request.current = controller; const id = ++sequence.current;
    setPending(true); setError(""); setSelected(null);
    try {
      const response = await fetch(`/data/market/daily/${date}.json`, { signal: controller.signal, cache: "no-store" });
      if (!response.ok) throw new Error("该日市场快照暂不可用，保留当前结果");
      const value = await response.json() as MarketSnapshot;
      if (value.meta?.methodVersion !== "market-watch-1.0" || value.meta.tradeDate !== date || !Array.isArray(value.boards)) throw new Error("快照日期或版本不匹配");
      if (sequence.current === id) setSnapshot(value);
    } catch (failure) { if (!controller.signal.aborted && sequence.current === id) setError(failure instanceof Error ? failure.message : "读取失败"); }
    finally { if (sequence.current === id) { setPending(false); request.current = null; } }
  };
  const rows = useMemo(() => sortedBoards(snapshot?.boards || [], kind, query, sort), [snapshot, kind, query, sort]);
  if (!snapshot) return <section className="panel"><span className="eyebrow">市场板块</span><h2>今日板块轮动</h2><p className="empty-state">市场行情尚未成功采集。社区观察仍可使用，下次每日更新会重新读取行业和概念目录。</p></section>;
  const source = snapshot.meta.sources.find(row => row.id === kind), market = snapshot.market;
  return <section className="panel market-watch" aria-busy={pending}>
    <div className="panel-head"><div><span className="eyebrow">每天从来源目录发现 · {snapshot.meta.tradeDate}</span><h2>今日板块轮动</h2></div><label className="market-date">行情日期 <select value={snapshot.meta.tradeDate} onChange={event => void changeDate(event.target.value)}>{dates.map(date => <option key={date}>{date}</option>)}</select></label></div>
    <div className="market-facts"><div><span>上涨 / 下跌 / 平盘</span><strong><i className="rise">{market.quoted ? market.up : "—"}</i> / <i className="fall">{market.quoted ? market.down : "—"}</i> / {market.quoted ? market.flat : "—"}</strong><small>{market.quoted}/{market.sourceTotal ?? "未知"} 股有当日涨跌幅</small></div><div><span>{market.amountComplete ? "成交额" : "已覆盖成交额"}</span><strong>{money(market.amount)}</strong><small>{market.amountCoverage} 股 · {market.amountChange == null ? "暂无同范围前日比较" : `较前次 ${money(market.amountChange)}`}</small></div><div><span>个股涨跌中位数</span><strong className={(market.medianChange ?? 0) >= 0 ? "rise" : "fall"}>{pct(market.medianChange)}</strong><small>{market.range}</small></div></div>
    <div className="market-toolbar"><div className="segmented" role="group" aria-label="板块类型">{[["industry", "行业"], ["concept", "概念"]].map(([value, label]) => <button key={value} aria-pressed={kind === value} className={kind === value ? "active" : ""} onClick={() => { setKind(value); setLimit(10); }}>{label}</button>)}</div><input aria-label="搜索市场板块或领涨股" placeholder="搜索板块、代码或领涨股" value={query} onChange={event => { setQuery(event.target.value); setLimit(10); }} /><label>排序 <select value={sort} onChange={event => setSort(event.target.value as BoardSort)}><option value="changePct">涨幅领跑</option><option value="turnover">换手活跃</option><option value="amount">成交规模</option><option value="activityHistory">历史换手分位</option></select></label></div>
    <p className="fine-print">已读取 {source?.observed ?? 0}/{source?.expected ?? "未知"} 个{kind === "industry" ? "行业" : "概念"}，{source?.dated ?? 0} 个具有所选日期行情。{source?.complete ? "目录已完整读取。" : "目录覆盖不完整，下表仅在已取得范围内比较。"} 每日更新候选和排名，不预留固定板块。{snapshot.meta.sourceId === "sina-tencent" && " 备用口径：涨跌与换手为至少覆盖90%成分的等权均值。"}</p>
    {pending && <p role="status">正在切换日期…</p>}{error && <p role="alert">{error}</p>}
    <div className="v4-table-scroll"><table className="v4-table market-table"><thead><tr><th>序位</th><th>板块</th><th>涨跌幅</th><th>换手率</th><th>换手活跃 / 100</th><th>成交额</th><th>上涨 / 下跌</th><th>领涨股</th></tr></thead><tbody>{rows.slice(0, limit).map((row, index) => <tr key={row.id}><td>{index + 1}</td><th><button onClick={() => setSelected(row)}>{row.name} ↗</button><small>{row.code}{row.rankChange != null ? ` · 涨幅名次${row.rankChange > 0 ? `↑${row.rankChange}` : row.rankChange < 0 ? `↓${-row.rankChange}` : "持平"}` : " · 名次变化待积累"}</small></th><td className={(row.changePct ?? 0) >= 0 ? "rise" : "fall"}>{pct(row.changePct)}</td><td>{row.turnover == null ? "—" : `${fmt(row.turnover)}%`}</td><td className={`market-score tone-${temperatureTone(row.relativeActivity).key}`}><strong>{fmt(row.relativeActivity, 1)}</strong><small>当日同类分位</small></td><td>{money(row.amount)}</td><td>{fmt(row.up, 0)} / {fmt(row.down, 0)}</td><td>{row.leader?.name || "—"}<small>{pct(row.leader?.changePct)}</small></td></tr>)}</tbody></table></div>
    {!rows.length && <p className="empty-state">当前范围没有匹配板块。{source?.status === "failed" ? "该来源本次读取失败。" : ""}</p>}
    {rows.length > 10 && <button className="v4-button secondary market-more" onClick={() => setLimit(limit === 10 ? rows.length : 10)}>{limit === 10 ? `查看全部 ${rows.length} 个结果` : "收起至前 10"}</button>}
    <details className="v4-coverage"><summary>排序、分数与数据范围</summary><p>涨幅、换手率和成交额分别排序；换手活跃分按当日同类板块换手率的中位秩分位计算。它不是历史热度、讨论分或上涨概率。搜索和筛选不会重新计算分数。</p><p>同一家公司可能属于多个概念和不同层级行业；板块金额不能相加成全市场成交。市场总览按去重 A 股报价独立汇总。未取得当日时间戳的数据不混入统计。{snapshot.meta.calculation}</p><p>复盘表已采样当天十个热门概念，尚未覆盖所有板块社区；综合过热为试验分。原社区观察池独立展示。L1–L5 已暂缓，后续研究单独记录。</p><p>采集于 {collectedTime(snapshot.meta.collectedAt)} · {snapshot.meta.source}</p>{snapshot.meta.sources.map(item => <p key={item.id}>{item.name}：{item.observed}/{item.expected ?? "未知"} 条，{item.pages} 页 · {item.errors.length ? item.errors.join("；") : item.complete ? "目录完整" : "覆盖未确认"}</p>)}</details>
    {selected && <BoardDetail key={`${selected.id}:${snapshot.meta.tradeDate}`} board={selected} day={snapshot.meta.tradeDate} onClose={() => setSelected(null)} />}
  </section>;
}
