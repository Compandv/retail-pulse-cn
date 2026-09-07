"use client";
import { useEffect, useRef, useState } from "react";
import { liveFlowRanking, type FlowSource, type FlowKind, type LiveFlowRow, type LiveFlowSnapshot } from "../lib/fund-flow";

const money = (n: number) => `${n > 0 ? "+" : ""}${(n / 1e8).toFixed(2)}亿`;
const dateTime = (s: string) => new Date(s).toLocaleString("zh-CN", { timeZone: "Asia/Shanghai", hour12: false });
function FlowList({ rows, direction, limit, metric }: { rows: LiveFlowRow[]; direction: "in" | "out"; limit: number; metric: string }) {
  const largest = Math.max(1, ...rows.map(r => Math.abs(r.net)));
  return <article className={`flow-column flow-${direction}`}><h3><span className="flow-dot" />{direction === "in" ? "净流入方向" : "净流出方向"}<small>{rows.length}个</small></h3><ol>{rows.slice(0, limit).map((row, i) => <li key={row.code}>
    <div className="flow-row-main"><span className="flow-order">{i + 1}</span><a href={row.sourceUrl} target="_blank" rel="noreferrer">{row.name} ↗</a><strong>{money(row.net)}</strong></div>
    <div className="flow-bar"><span style={{ width: `${Math.abs(row.net) / largest * 100}%` }} /></div>
    <p>{row.diagnosis}<span>涨跌 {row.changePct == null ? "—" : `${row.changePct > 0 ? "+" : ""}${row.changePct.toFixed(2)}%`}{row.ratio == null ? "" : ` · 净占比 ${row.ratio.toFixed(2)}%`}</span></p>
    <details className="flow-structure"><summary>查看资金明细</summary><p>{metric}：{money(row.net)}</p>{row.inflow != null && <p>流入 {money(row.inflow)} · 流出 {money(row.outflow ?? 0)}</p>}{row.extraLarge != null && <p>超大单 {money(row.extraLarge)} · 大单 {row.large == null ? "—" : money(row.large)}</p>}{row.medium != null && <p>中单 {money(row.medium)} · 小单 {row.small == null ? "—" : money(row.small)}</p>}</details>
  </li>)}</ol>{!rows.length && <p className="empty-state">此范围没有已取得的{direction === "in" ? "净流入" : "净流出"}记录。</p>}</article>;
}

export function LiveFundFlows() {
  const [source, setSource] = useState<FlowSource>("eastmoney"), [kind, setKind] = useState<FlowKind>("industry");
  const [snapshot, setSnapshot] = useState<LiveFlowSnapshot | null>(null), [error, setError] = useState(""), [busy, setBusy] = useState(true);
  const [sort, setSort] = useState<"net" | "ratio">("net"), [all, setAll] = useState(false), [reload, setReload] = useState(0);
  const sequence = useRef(0);
  const switchSource = (value: FlowSource) => { if (value !== source) { setSnapshot(null); setError(""); setAll(false); setBusy(true); setSource(value); setSort("net"); } };
  const switchKind = (value: FlowKind) => { if (value !== kind) { setSnapshot(null); setError(""); setAll(false); setBusy(true); setKind(value); } };
  useEffect(() => {
    const controller = new AbortController(), run = ++sequence.current;
    let inFlight = false;
    const refresh = async () => {
      if (inFlight) return;
      inFlight = true;
      try {
        const response = await fetch(`/api/fund-flow?source=${source}&kind=${kind}`, { signal: controller.signal, cache: "no-store" });
        const data = await response.json() as LiveFlowSnapshot & { error?: string };
        if (!response.ok || !Array.isArray(data.rows) || data.source !== source || data.kind !== kind) throw new Error(data.error || "资金数据返回异常");
        if (run === sequence.current) { setSnapshot(data); setError(""); }
      } catch (failure) {
        if (!controller.signal.aborted && run === sequence.current) { setError(failure instanceof Error ? failure.message : "暂时无法读取来源"); setSnapshot(value => value ? { ...value, stale: true } : null); }
      } finally { inFlight = false; if (!controller.signal.aborted && run === sequence.current) setBusy(false); }
    };
    void refresh();
    const timer = setInterval(() => { if (document.visibilityState === "visible" && !inFlight) { setBusy(true); void refresh(); } }, 120000);
    return () => { controller.abort(); clearInterval(timer); };
  }, [source, kind, reload]);
  const incoming = liveFlowRanking(snapshot?.rows ?? [], "in", sort), outgoing = liveFlowRanking(snapshot?.rows ?? [], "out", sort);
  const limit = all ? Math.max(incoming.length, outgoing.length) : 6;
  return <section className="panel report-section live-fund-section"><div className="report-section-heading"><span className="report-step">04</span><div><span className="eyebrow">平台资金榜 · 独立于盘后报告</span><h2>资金正在流向哪些板块？</h2></div><button className="report-expand" disabled={busy} onClick={() => { setBusy(true); setReload(n => n + 1); }}>{busy ? "正在读取平台…" : "检查更新"}</button></div>
    <div className="fund-toolbar"><div className="segmented" role="group" aria-label="资金数据来源">{([["eastmoney", "东方财富"], ["ths", "同花顺"]] as const).map(([key, label]) => <button className={source === key ? "active" : ""} aria-pressed={source === key} key={key} onClick={() => switchSource(key)}>{label}</button>)}</div>
      <div className="segmented" role="group" aria-label="即时资金板块类型">{([["industry", "行业"], ["concept", "概念"]] as const).map(([key, label]) => <button className={kind === key ? "active" : ""} aria-pressed={kind === key} key={key} onClick={() => switchKind(key)}>{label}</button>)}</div>
      <label>排序 <select value={sort} onChange={e => setSort(e.target.value as "net" | "ratio")}><option value="net">净额</option><option value="ratio" disabled={source === "ths"}>主力净占比</option></select></label>
    </div>
    <p className="report-summary">直接读取所选平台的行业／概念分页榜，完整采集后全量排序。{source === "ths" ? "同花顺按“资金净额”展示，不与其他来源主力口径拼接。" : "东方财富按“主力净流入”展示，可展开大小单结构。"}</p>
    {busy && <p role="status" className="fund-status">正在检查平台完整目录与分页…</p>}
    {error && <p role="alert" className="fund-status fund-stale">{source === "ths" ? "同花顺" : "东方财富"}暂不可用：{error}。可切换另一来源；这里不会用旧新浪目录替代。</p>}
    {snapshot && <><div className={`fund-status ${snapshot.stale || !snapshot.complete ? "fund-stale" : ""}`}><strong>{snapshot.stale ? "上次结果 · 本次更新失败" : snapshot.complete ? "平台目录已覆盖" : "部分采集 · 排名仅限已取得范围"}</strong><span>已取得 {snapshot.rows.length}/{snapshot.expected ?? "未知"} 个板块 · {snapshot.metric}</span><span>采集 {dateTime(snapshot.collectedAt)} · {snapshot.sourceTime ? `来源最早时点 ${dateTime(snapshot.sourceTime)}` : "来源页面未标数据时点，不能用采集时间冒充行情时间"}</span></div>
      <p className="report-summary">流入领先：<b className="rise">{incoming.slice(0, 3).map(r => r.name).join("、") || "暂无"}</b>；流出领先：<b className="fall">{outgoing.slice(0, 3).map(r => r.name).join("、") || "暂无"}</b>。</p>
      <div className="fund-flow-grid"><FlowList rows={incoming} direction="in" limit={limit} metric={snapshot.metric} /><FlowList rows={outgoing} direction="out" limit={limit} metric={snapshot.metric} /></div>
      {Math.max(incoming.length, outgoing.length) > 6 && <button className="report-expand" onClick={() => setAll(value => !value)}>{all ? "收起为前六 ↑" : "展开本次取得的完整排序 ↓"}</button>}
      {!!snapshot.errors.length && <details><summary>采集状态</summary>{snapshot.errors.map((item, i) => <p key={i}>{item}</p>)}</details>}
    </>}
    {!snapshot && !busy && !error && <p className="empty-state">等待资金来源返回。</p>}
    <p className="report-footnote">查看期间每2分钟检查更新；平台自身延迟另计。即时榜不随上方历史日期回放。行业与概念、不同平台的板块可能重叠，金额不相加。买卖关系评价不用于认定机构意图。</p>
  </section>;
}
