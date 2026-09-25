"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { MEASUREMENT } from "../lib/measurement";
import { LineChart } from "./charts";
import { Dashboard as LegacyDashboard } from "./Dashboard";
import type { Snapshot, HistoryPoint } from "./types";
import type { MeasurementSnapshot, ScopeResult } from "./measurement-types";
import { MarketWatch } from "./MarketWatch";
import type { MarketSnapshot } from "./market-types";
import { MarketReport } from "./MarketReport";
import type { DailyReport } from "./report-types";
import { FOLLOWING_EXPLANATION, MEASUREMENT_ANSWER } from "../lib/following-method";
import { SnapshotHealth } from "./SnapshotHealth";

const number = (value: number | null | undefined, digits = 1) => value == null || !Number.isFinite(value) ? "—" : value.toFixed(digits);
const percent = (value: number | null | undefined) => value == null ? "—" : `${number(value)}%`;
const SOURCES: Record<string, string> = { eastmoney: "东方财富", sina: "新浪股吧", taoguba: "淘股吧" };
const kindLabel = (scope: ScopeResult) => scope.kind === "basket" ? `${scope.members.length} 股观察篮子` : scope.kind === "proxy" ? "单股主题代理" : "个股";

function Stat({ title, value, unit, hint }: { title: string; value: number | null; unit: string; hint: string }) {
  return <div className="v4-stat"><span>{title}</span><strong>{number(value)}<small>{value != null ? unit : ""}</small></strong><p>{hint}</p></div>;
}

function MeasurementCards({ scope }: { scope: ScopeResult }) {
  const { attention: a, expressions: e, trading: t } = scope;
  return <><div className="v4-measures">
    <Stat title="社区关注热度" value={a.score} unit=" / 100" hint={a.score == null ? `${a.reason} · ${a.baselineDays}/${a.minimumDays} 个有效历史日` : `高于自身约 ${number(a.score, 0)}% 的可比历史观测`} />
    <Stat title="成交活跃分" value={t.score} unit=" / 100" hint={`${t.baselineCoverage}/${t.total} 股有成交基线 · ${t.score == null ? t.reason : "历史分位的等权均值"}`} />
    <Stat title="追涨表达占比" value={e.chase} unit="%" hint={`追买自述 + 追涨意愿 / ${e.sampleCount} 条有效表达`} />
    <Stat title="恐慌表达占比" value={e.panic} unit="%" hint={`与追涨独立统计${e.thin ? " · 样本较少" : ""}`} />
  </div><div className="v4-facts">
    <span>已观察账户 <b>{a.observedAuthors}</b><small>东方财富 · {a.complete ? "列表窗口已覆盖" : "已观察下限"}</small></span>
    <span>有效讨论 <b>{a.observedPosts}</b><small>限量分析前 · 排除重复与噪声</small></span>
    <span>行情覆盖 <b>{t.coverage}/{t.total}</b><small>{t.up} 涨 / {t.down} 跌 · 上涨率 {percent(t.upRate)}</small></span>
    <span>相对平时讨论人数 <b>{a.growthPct == null ? "—" : `${a.growthPct > 0 ? "+" : ""}${percent(a.growthPct)}`}</b><small>{a.lowBase ? "历史中位数为零，不计算倍数" : a.baselineMedian == null ? "等待完整可比历史" : `前 20 个有效日中位数 ${number(a.baselineMedian, 0)} 人`}</small></span>
  </div><p className="v4-reading">{t.score != null && t.score >= 80 ? `成交处于历史活跃区间；有报价成分 ${t.up}/${t.coverage} 上涨。` : "结合成交历史与上涨范围，判断热闹来自哪里。"}看涨期待与明确追买分别统计，追涨表达较少并不意味着行情冷清。</p></>;
}

function Evidence({ scope }: { scope: ScopeResult }) {
  const [intent, setIntent] = useState("all");
  const shown = scope.posts.filter(post => intent === "all" || post.classification.intent === intent);
  return <section className="v4-evidence"><div className="panel-head"><div><span className="eyebrow">原文证据 · 点击展开</span><h3>把判断放回语境里</h3></div><div className="v4-filters"><label>表达 <select value={intent} onChange={event => setIntent(event.target.value)}><option value="all">全部表达</option>{Object.entries(MEASUREMENT.intentLabels).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></label></div></div>
    <p className="fine-print">展示最近 {scope.posts.length} 条节选；所有比例使用完整的 {scope.expressions.sampleCount} 条分析样本计算，不随下面的筛选变化。语境规则尚未完成独立人审校准。</p>
    <div className="evidence-feed">{shown.slice(0, 40).map(post => <details className="evidence-item" key={`${post.source}:${post.code}:${post.id}`}><summary><span className={`evidence-tone ${post.classification.chase ? "fomo" : post.classification.panic ? "panic" : "neutral"}`}>{post.classification.intentLabel}</span><span className="evidence-title">{post.text.slice(0, 160)}{post.text.length > 160 ? "…" : ""}<small>{SOURCES[post.source] || post.source} · {post.code} · {post.date} · {post.contentKind || "公开文本"}</small></span></summary><div className="evidence-body"><p>{post.text}</p><p>{post.classification.reason}</p><ul>{post.classification.evidence.filter(text => !text.startsWith("表达类型：")).map((text, i) => <li key={i}>{text}</li>)}</ul>{/^https:\/\/guba\.eastmoney\.com\//.test(post.url) && <a href={post.url} target="_blank" rel="noreferrer">核对公开原帖 ↗</a>}</div></details>)}{!shown.length && <div className="empty-state">当前节选中没有符合筛选的表达。</div>}</div>
  </section>;
}

async function shareImage(scope: ScopeResult) {
  await document.fonts?.ready;
  const canvas = document.createElement("canvas"); canvas.width = 1200; canvas.height = 880;
  const ctx = canvas.getContext("2d"); if (!ctx) throw new Error("无法创建图片");
  ctx.fillStyle = "#f3f0e8"; ctx.fillRect(0, 0, canvas.width, canvas.height);
  ctx.fillStyle = "#1c1c1a"; ctx.font = 'bold 42px "Microsoft YaHei", sans-serif'; ctx.fillText(`散户温度计 · ${scope.name}`, 60, 100, 1080);
  ctx.font = '24px "Microsoft YaHei", sans-serif';
  const lines = [scope.dataWindow, `${kindLabel(scope)} · ${scope.members.map(row => row.code).join(" / ")}`,
    `社区关注热度 ${number(scope.attention.score)} / 100 · ${scope.attention.reason}`,
    `成交活跃分 ${number(scope.trading.score)} / 100 · 基线覆盖 ${scope.trading.baselineCoverage}/${scope.trading.total}`,
    `追涨表达 ${percent(scope.expressions.chase)} · 恐慌表达 ${percent(scope.expressions.panic)}`,
    `东方财富已观察账户 ${scope.attention.observedAuthors} · ${scope.attention.complete ? "列表窗口已覆盖" : "仅为已观察下限"}`,
    `分析样本 ${scope.expressions.sampleCount} 条 · 看涨表达 ${percent(scope.expressions.bullish)}`,
    `讨论人数较历史中位数 ${percent(scope.attention.growthPct)}`,
    `${scope.methodVersion} · L1–L5 分级暂缓`, "仅用于公开社区观察，不表示实际持仓、真实买卖人数或未来涨跌。"];
  lines.forEach((line, index) => ctx.fillText(line, 60, 190 + index * 62, 1080));
  const blob = await new Promise<Blob | null>(resolve => canvas.toBlob(resolve, "image/png")); if (!blob) throw new Error("导出失败");
  const url = URL.createObjectURL(blob), link = document.createElement("a"); link.href = url; link.download = `散户观察-${scope.id}-${scope.date}.png`; link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function ScopePanel({ scope, compact = false }: { scope: ScopeResult; compact?: boolean }) {
  const [exportState, setExportState] = useState("");
  return <div className="v4-scope"><div className="panel-head"><div><span className="eyebrow">{kindLabel(scope)} · {scope.market || scope.methodVersion}</span><h2>{scope.name}</h2><p className="fine-print">{scope.dataWindow} · {scope.description}</p></div><button className="v4-button secondary" onClick={async () => { try { await shareImage(scope); setExportState("图片已导出"); } catch { setExportState("图片导出失败，请重试"); } }}>导出观察卡</button></div>{exportState && <p role="status">{exportState}</p>}
    <MeasurementCards scope={scope} />
    {!compact && <><details className="v4-coverage"><summary>数据范围与成分 · {scope.attention.memberCoverage}/{scope.attention.memberTotal} 个股吧覆盖日期窗口</summary><p>{scope.note}</p><p>关注度使用东方财富统一口径；表达来源：{(scope.expressionSources || ["eastmoney"]).map(source => SOURCES[source] || source).join("、")}。当前尚未系统采集完整评论回复，正文不可得时使用标题。</p><p>抓取列表 {scope.attention.rawCount} 条，窗口外排除 {scope.attention.excludedDate} 条，重复／噪声排除 {scope.attention.excludedNoise} 条。未知账户标识帖子 {scope.attention.unknownAuthorPosts} 条。</p><div className="v4-table-scroll"><table className="v4-table"><thead><tr><th>标的 / 范围</th><th>收盘参考价</th><th>涨跌幅</th><th>换手率</th><th>成交量 / 20日均值</th><th>采集覆盖</th></tr></thead><tbody>{scope.members.map(member => { const row = scope.trading.members.find(item => item.code === member.code); const feed = scope.feeds.find(item => item.code === member.code); return <tr key={member.code}><th>{row?.name || member.name}<small>{member.code} · {member.role}</small></th><td>{number(row?.price, 2)}<small>{row?.source || "行情缺失"}</small></td><td className={(row?.changePct || 0) >= 0 ? "rise" : "fall"}>{percent(row?.changePct)}</td><td>{percent(row?.turnover)}</td><td>{row?.volumeRatio == null ? "—" : `${number(row.volumeRatio)} 倍`}</td><td><small>{feed?.pages ?? 0} 页 · {feed?.reason || "未采集"}{feed?.error ? ` · ${feed.error}` : ""}</small></td></tr>; })}</tbody></table></div><p className="fine-print">行情与成交基线只采用所选日期及此前数据。成交活跃分至少要求 70% 成分有足够历史；公开列表覆盖不等于所有市场讨论均被覆盖。</p></details><Evidence scope={scope} /></>}
  </div>;
}

function Query({ snapshot }: { snapshot: MeasurementSnapshot }) {
  const [query, setQuery] = useState("猪肉");
  const [date, setDate] = useState(snapshot.meta.tradeDate);
  const [result, setResult] = useState<ScopeResult | null>(null);
  const [loading, setLoading] = useState(false), [error, setError] = useState("");
  const controller = useRef<AbortController | null>(null), sequence = useRef(0);
  useEffect(() => () => controller.current?.abort(), []);
  const invalidate = () => { sequence.current++; controller.current?.abort(); setResult(null); setError(""); setLoading(false); };
  const run = async (value = query) => {
    if (!value.trim()) return;
    invalidate(); setQuery(value); setLoading(true);
    const id = sequence.current, pending = new AbortController(); controller.current = pending;
    try {
      const response = await fetch(`/api/stock-query?q=${encodeURIComponent(value.trim())}&date=${date}`, { cache: "no-store", signal: pending.signal });
      const payload = await response.json() as ScopeResult & { error?: string };
      if (!response.ok) throw new Error(payload.error || "查询失败");
      if (id === sequence.current) setResult(payload);
    } catch (failure) { if (id === sequence.current && !pending.signal.aborted) setError(failure instanceof Error ? failure.message : "查询失败"); }
    finally { if (id === sequence.current) setLoading(false); }
  };
  return <article className="panel v4-query"><div className="panel-head"><div><span className="eyebrow">指定日期 · 股票 / 多股主题</span><h2>把当天的情绪查清楚</h2></div></div><form className="query-form v4-query-form" onSubmit={event => { event.preventDefault(); void run(); }}><input aria-label="股票代码、名称或主题" value={query} onChange={event => { invalidate(); setQuery(event.target.value); }} placeholder="猪肉 / 920970 / 牧原股份" /><input aria-label="观测交易日" type="date" min="2026-01-01" max={snapshot.meta.tradeDate} value={date} onChange={event => { invalidate(); setDate(event.target.value); }} required /><button type="submit" disabled={loading || !query.trim()}>{loading ? "采集中…" : "查询"}</button></form><div className="question-presets">{["猪肉", "920970", "002714", "黄金"].map(value => <button key={value} onClick={() => void run(value)}>{value}</button>)}</div><p className="fine-print">统一观察北京时间 00:00–15:00。代码和公司名查个股；“猪肉”查 8 股篮子；其余已配置主题会明确标注单股代理。</p>{loading && <p role="status">正在读取各成分的日期窗口与历史成交数据，通常需要数十秒。切换输入可取消本次查询。</p>}{error && <p role="alert" className="query-error">{error}</p>}{result && <ScopePanel key={`${result.id}:${result.date}`} scope={result} />}</article>;
}

function ScopeDialog({ scope, snapshot, onClose }: { scope: ScopeResult; snapshot: MeasurementSnapshot; onClose: () => void }) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => { ref.current?.showModal(); }, []);
  const points = snapshot.scopeHistory.map(day => { const row = day.scopes.find(item => item.id === scope.id); return { date: day.date, fomo: row?.chase ?? null, heat: row?.heat ?? null }; });
  return <dialog ref={ref} className="research-dialog v4-dialog" onClose={onClose} onCancel={onClose}><button className="v4-dialog-close" aria-label="关闭详情" onClick={onClose}>关闭 ×</button><ScopePanel scope={scope} /><h3>追涨表达历史 · %</h3><LineChart points={points} metric="fomo" /></dialog>;
}

function ScopeTable({ scopes, onSelect }: { scopes: ScopeResult[]; onSelect: (scope: ScopeResult) => void }) {
  const [sort, setSort] = useState("authors"), [kind, setKind] = useState("all");
  const rows = useMemo(() => [...scopes].filter(scope => kind === "all" || scope.kind === kind).sort((a, b) => { const value = (scope: ScopeResult) => sort === "growth" ? scope.attention.growthPct : sort === "chase" ? scope.expressions.chase : sort === "activity" ? scope.trading.score : sort === "heat" ? scope.attention.score : scope.attention.observedAuthors; return (value(b) ?? -Infinity) - (value(a) ?? -Infinity); }), [scopes, sort, kind]);
  return <article className="panel"><div className="panel-head"><div><span className="eyebrow">公开社区观察对象</span><h2>讨论集中在哪里</h2></div><div className="v4-filters"><label>范围 <select value={kind} onChange={event => setKind(event.target.value)}><option value="all">全部观察对象</option><option value="basket">多股篮子</option><option value="proxy">单股代理</option></select></label><label>排序 <select value={sort} onChange={event => setSort(event.target.value)}><option value="authors">已观察账户</option><option value="growth">讨论升温幅度</option><option value="chase">追涨表达比例</option><option value="activity">成交活跃分</option><option value="heat">关注热度分</option></select></label></div></div><p className="fine-print">各对象成分覆盖不同，表格比较的是已采样范围，不是全行业人数排名。账户与关注份额统一使用东方财富；同一账户可关注多个对象，份额之和可以超过 100%。</p><div className="v4-table-scroll"><table className="v4-table"><thead><tr><th>观察对象</th><th>已观察账户</th><th>观察池关注份额</th><th>关注热度 / 100</th><th>成交活跃 / 100</th><th>追涨表达</th><th>看涨表达</th><th>讨论升温</th></tr></thead><tbody>{rows.map(scope => <tr key={scope.id}><th><button onClick={() => onSelect(scope)}>{scope.name} ↗</button><small>{kindLabel(scope)} · {scope.members.map(row => row.name).slice(0, 2).join(" / ")}</small></th><td>{scope.attention.observedAuthors}<small>{scope.attention.complete ? "窗口已覆盖" : "仅观察下限"}</small></td><td>{percent(scope.attentionShare)}</td><td>{number(scope.attention.score)}<small>{scope.attention.score == null ? scope.attention.reason : "自身历史分位"}</small></td><td>{number(scope.trading.score)}</td><td className="rise">{percent(scope.expressions.chase)}<small>n={scope.expressions.sampleCount}{scope.expressions.thin ? " · 样本少" : ""}</small></td><td>{percent(scope.expressions.bullish)}</td><td>{percent(scope.attention.growthPct)}</td></tr>)}</tbody></table></div>{!rows.length && <p className="empty-state">此范围暂无观察对象。</p>}</article>;
}

function History({ snapshot, onSelect }: { snapshot: MeasurementSnapshot; onSelect: (scope: ScopeResult) => void }) {
  const [metric, setMetric] = useState<keyof HistoryPoint>("fomo"), [range, setRange] = useState(20), [legacy, setLegacy] = useState(false);
  const points = (legacy ? snapshot.legacy?.history || [] : snapshot.history).slice(-range);
  const days = snapshot.scopeHistory.slice(-30);
  return <><article className="panel"><div className="panel-head"><div><span className="eyebrow">同口径历史</span><h2>热度与情绪如何变化</h2></div><div className="segmented">{([['fomo', '追涨 %'], ['panic', '恐慌 %'], ['heat', '关注热度'], ['profitEffect', '成交活跃'], ['direction', '多空方向']] as Array<[keyof HistoryPoint, string]>).map(([key, label]) => <button key={key} className={metric === key ? "active" : ""} onClick={() => { setLegacy(false); setMetric(key); }}>{label}</button>)}{[10, 20, 60].map(day => <button key={day} className={range === day ? "active" : ""} onClick={() => setRange(day)}>{day}日</button>)}</div></div>{snapshot.legacy && <label className="legacy-toggle"><input type="checkbox" checked={legacy} onChange={event => setLegacy(event.target.checked)} />查看旧版综合分（{snapshot.legacy.methodVersion}，独立展示）</label>}<LineChart points={points} metric={legacy ? "overall" : metric} /><p className="fine-print">{legacy ? "旧版包含不同定义或估算数据，不能与 V4 分数直接比较。" : snapshot.meta.historyNote} 当前显示 {points.length} 个有记录日期。</p></article><article className="panel"><div className="panel-head"><div><span className="eyebrow">对象 × 日期</span><h2>追涨表达日历</h2></div></div><div className="v4-table-scroll"><table className="v4-table v4-calendar"><thead><tr><th>观察对象</th>{days.map(day => <th key={day.date}>{day.date.slice(5)}</th>)}</tr></thead><tbody>{snapshot.scopes.map(scope => <tr key={scope.id}><th><button onClick={() => onSelect(scope)}>{scope.name} ↗</button></th>{days.map(day => { const row = day.scopes.find(item => item.id === scope.id); return <td key={day.date} style={{ background: row?.chase == null ? "transparent" : `rgba(232,84,50,${row.chase / 180})` }}>{percent(row?.chase)}</td>; })}</tr>)}</tbody></table></div><p className="fine-print">单元格为追涨表达占比，不是市场涨跌概率；缺失保持“—”。</p></article></>;
}

function Method() {
  return <article className="panel v4-method"><span className="eyebrow">MVP-4.0 · 可解释的试验方法</span><h2>每个数字回答一个问题</h2><dl><dt>社区关注热度：0–100 历史分位</dt><dd>以东方财富同一观察篮子、同一时段的去重活跃账户数，与此前最多 60 个有效历史日比较；低于当前值计 1，相同计 0.5，再除以历史天数并乘 100。至少需要 20 日；采集不完整、账户标识缺失或历史不足均不出分。80 分不表示 80% 的人看多。</dd><dt>讨论升温：相对自己的日常规模</dt><dd>将当日去重讨论账户数除以最近 20 个可比有效日的账户数中位数，减 1 后乘 100%。当前采集不完整、历史不足或中位数为零时留空。热度分衡量历史位置，升温幅度衡量偏离日常规模的程度。</dd><dt>成交活跃分：行情维度</dt><dd>每只股票的当日成交量相对过去最多 60 个交易日计算分位，至少需要 20 日，再对具备基线的成分等权平均。篮子至少 70% 成分具备基线才显示总分；上涨率按有报价成分计算，另列覆盖数量。这不是散户资金流。</dd><dt>追涨、恐慌：表达比例</dt><dd>先排除广告与同账户重复文本，限定观测日期 00:00–15:00，每个平台每账户最多保留三条。分母是有效分析文本数；追买自述与明确追涨意愿进入追涨比例，单纯盼涨、行情描述、否定、转述、历史回顾和询问分别标注。规则仍可能误判，可展开原文复核。</dd><dt>跟风追涨表达分（当前题材日报）</dt><dd>{FOLLOWING_EXPLANATION} 当前不使用L1–L5等级；旧报告保留原方法。</dd><dt>样本覆盖与旧历史</dt><dd>抓取量、窗口内有效讨论量、限量后的分析样本量分开。公开列表分页有上限；出现重复页、超时或尚未越过日期边界时，数量仅为已观察下限。完整正文和回复目前覆盖有限。旧版综合权重停止用于 V4，旧历史单独保留。</dd></dl><p className="method-notice">这版修复了已知统计口径和语境规则问题，没有宣称复现博主算法，也未完成独立人工标注集上的准确性验证。</p></article>;
}

function QA({ snapshot, onSelect }: { snapshot: MeasurementSnapshot; onSelect: (scope: ScopeResult) => void }) {
  const [question, setQuestion] = useState(""), [answer, setAnswer] = useState("");
  const [links, setLinks] = useState<ScopeResult[]>([]);
  const ask = (text: string) => {
    setQuestion(text); setLinks([]);
    const matched = snapshot.scopes.filter(scope => [scope.name, scope.id, ...scope.members.map(member => member.name)].some(name => name && text.includes(name)) || (scope.id === "pork" && text.includes("猪肉")));
    if (/公式|怎么算|依据/.test(text)) { setAnswer(MEASUREMENT_ANSWER); return; }
    if (matched.length) { setAnswer(matched.map(scope => `${scope.name}：已观察账户 ${scope.attention.observedAuthors}（${scope.attention.complete ? "窗口已覆盖" : "下限"}），关注热度 ${number(scope.attention.score)}，成交活跃 ${number(scope.trading.score)}，追涨表达 ${percent(scope.expressions.chase)}，${scope.expressions.sampleCount} 条分析样本。`).join("\n")); setLinks(matched); return; }
    if (/升温|最热|人数最多/.test(text)) { setAnswer("市场板块榜可按当天涨幅、换手活跃或成交规模排序，候选每日更新。社区表可比较已观察人数和同口径升温；它尚未覆盖市场榜的全部板块。"); return; }
    setAnswer("可输入已配置的主题或股票名称来核对样本，也可询问计算依据。当前数据无法确定真实持仓人数、作者实际经验或未来涨跌。");
  };
  return <article className="panel"><div className="panel-head"><div><span className="eyebrow">基于快照 · 本地问答</span><h2>带着问题核对数据</h2></div></div><form className="query-form" onSubmit={event => { event.preventDefault(); ask(question); }}><input aria-label="向观察快照提问" placeholder="猪肉的追涨表达如何？这个分数怎么算？" value={question} onChange={event => setQuestion(event.target.value)} /><button type="submit">查看分析</button></form>{answer && <div className="research-answer" aria-live="polite"><p>{answer}</p>{links.map(scope => <button className="text-button" key={scope.id} onClick={() => onSelect(scope)}>查看 {scope.name} 的证据 ↗</button>)}</div>}</article>;
}

export function MeasurementDashboard({ initialSnapshot, initialMarket = null, initialReport = null }: { initialSnapshot: unknown; initialMarket?: MarketSnapshot | null; initialReport?: unknown }) {
  const [snapshot, setSnapshot] = useState(initialSnapshot as MeasurementSnapshot);
  const [view, setView] = useState("overview"), [selected, setSelected] = useState<ScopeResult | null>(null);
  useEffect(() => { const controller = new AbortController(); const refresh = async () => { try { const response = await fetch("/data/latest.json", { cache: "no-store", signal: controller.signal }); if (response.ok) { const next = await response.json() as MeasurementSnapshot; if (next.meta?.methodVersion === MEASUREMENT.version) setSnapshot(next); } } catch { /* Preserve the last working snapshot on refresh failure. */ } }; const timer = setInterval(refresh, 300000); return () => { clearInterval(timer); controller.abort(); }; }, []);
  if (snapshot.meta.methodVersion !== MEASUREMENT.version) return <LegacyDashboard initialSnapshot={initialSnapshot as Snapshot} />;
  return <main className="v4-main"><header className="topbar"><Link className="brand" href="/"><span className="brand-mark">温</span><span><strong>散户温度计</strong><small>PUBLIC MARKET OBSERVATORY</small></span></Link><nav aria-label="主导航">{[["overview", "观察总览"], ["scopes", "板块轮动"], ["query", "股票查询"], ["history", "历史"], ["method", "方法"]].map(([key, label]) => <button key={key} aria-current={view === key ? "page" : undefined} className={view === key ? "active" : ""} onClick={() => setView(key)}>{label}</button>)}</nav><div className="asof"><i className="mode-dot live" /><span>{snapshot.meta.tradeDate}<small>截至 15:00 · 北京时间</small></span></div></header><div className="v4-workspace"><div className="v4-intro"><div><span className="eyebrow">动态市场目录 · 公开社区观察</span><h1>看市场轮动，也看讨论升温。</h1><p>把关注规模、成交活跃与追涨表达分开，保留每个判断的证据。</p></div><div className="v4-source-status">{snapshot.meta.sources.map(source => <span key={source.id}>{source.name} · {source.observedEntrances}/{source.totalEntrances} 入口</span>)}</div></div>
    <SnapshotHealth name="社区观察" tradeDate={snapshot.meta.tradeDate} collectedAt={snapshot.meta.collectedAt} methodVersion={snapshot.meta.methodVersion} expectedMethodVersion={MEASUREMENT.version} />
    {view === "overview" && <><MarketReport initialReport={initialReport as DailyReport | null} /><MarketWatch initialSnapshot={initialMarket} /><section className="panel"><ScopePanel scope={snapshot.summary} compact /></section><ScopeTable scopes={snapshot.scopes} onSelect={setSelected} /><Query snapshot={snapshot} /><QA snapshot={snapshot} onSelect={setSelected} /></>}
    {view === "scopes" && <><MarketWatch initialSnapshot={initialMarket} /><ScopeTable scopes={snapshot.scopes} onSelect={setSelected} /><p className="fine-print">市场板块榜每天更新候选；社区表保留已有观察范围，二者覆盖不同。</p></>}
    {view === "query" && <Query snapshot={snapshot} />}
    {view === "history" && <History snapshot={snapshot} onSelect={setSelected} />}
    {view === "method" && <Method />}
    <footer className="v4-footer">{snapshot.meta.methodVersion} · 数据采集于 {snapshot.meta.collectedAt.replace("T", " ").slice(0, 19)} · 本工具用于公开社区观察；表达不等于真实成交，分数不表示未来涨跌。</footer>
  </div>{selected && <ScopeDialog key={selected.id} scope={selected} snapshot={snapshot} onClose={() => setSelected(null)} />}</main>;
}
