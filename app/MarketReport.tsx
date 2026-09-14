"use client";

import { useEffect, useRef, useState, type CSSProperties } from "react";
import type { DailyReport, DimensionKey, ReportSector, Thermometer, FundFlow } from "./report-types";
import { rankFlows, temperatureTone } from "../lib/report-presentation";
import { FollowingComposition, MarketReading } from "./FollowingComposition";
import { LiveFundFlows } from "./LiveFundFlows";

const fmt = (n: number | null | undefined, digits = 1) => n == null ? "—" : n.toLocaleString("zh-CN", { maximumFractionDigits: digits });
const change = (n: number | null | undefined) => n == null ? "—" : `${n > 0 ? "+" : ""}${fmt(n, 2)}%`;
const time = (value: string) => new Date(value).toLocaleString("zh-CN", { timeZone: "Asia/Shanghai", hour12: false });
const metricInfo: Record<DimensionKey, { name: string; unit: string; description: string }> = {
  discussion: { name: "讨论规模", unit: "分", description: "当日去重讨论账户总数在十强可比样本中的分位，原始人数同时保留。相对排名不代表绝对狂热，也不等于全市场散户总数。旧版日报曾使用每股账户密度，请按方法版本区分。" },
  spread: { name: "传播力", unit: "分", description: "有效分析样本平均每帖回复与转发次数之和，在本表可比热点中计算分位。互动量截至采集时刻，属于传播代理，不等于当日新增传播量。" },
  panic: { name: "恐慌度", unit: "%", description: "明确恐慌表达条数÷有效分析样本数×100%。使用语境规则，低值表示样本中较少出现这种表达。" },
  refill: { name: "补仓表达", unit: "%", description: "明确补仓表达条数÷有效分析样本数×100%。排除否定、询问、转述及历史回顾；表达不能证明实际补仓成交。" },
  crowding: { name: "拥挤度", unit: "分", description: "当日换手率在来源全部可得概念中的分位，是交易拥挤的代理；不代表散户占比，也没有推断持仓人数。" },
  overheat: { name: "综合过热", unit: "分", description: "试验指标：讨论度、传播力、拥挤度与本表追涨表达率分位各占25%。四项齐全才出分，不含L1–L5；尚未经过独立人审与样本外校准，不表示下跌概率。" },
  growth: { name: "讨论升温", unit: "分", description: "同一板块两日均覆盖的成分集合：100×今日账户/(今日+前一交易日账户)。50为持平，66.7约为翻倍；这是当前历史较短时的日环比口径。" },
  chase: { name: "追涨倾向", unit: "%", description: "有本人追买行动／意愿证据的文本数÷有效分析文本数。询问、警示、主力行为描述不自动视为追涨。此列是文本表达占比；韭菜分另外按账户统计，未使用十强分位。" },
  trading: { name: "交易活跃", unit: "分", description: "板块换手率相对全部来源概念的分位。它描述交易活跃，不认证资金属于散户或机构。" },
  leek: { name: "韭菜分", unit: "分", description: "跟风追涨表达试验分：账户跟随决策率30%、明确追涨强度40%、追涨询问率20%、无依据喊涨率10%。每账户同项取最高值，已追买计1、明确计划计0.7。未知仍在分母中；不认证身份，不代表实际成交。" },
};
function metricDescription(key: DimensionKey, report: DailyReport) {
  if (report.meta.discovery && key === "discussion") {
    const quality = report.meta.discovery.rankingQuality === "partial-lower-bound" ? "当前候选源有截断，分数是观测下限；" : report.meta.discovery.rankingQuality === "complete" ? "当前候选源达到完整度门槛；" : "旧版未记录候选源完整度；";
    return `关注热度＝65%×去重账户总数分位＋35%×回复与转发互动总量分位。先在所有达标候选题材中计算，再取前十；${quality}并非绝对热度或全市场讨论占比。`;
  }
  if (report.meta.discovery && key === "spread") return "归属该题材的有效帖逐条计算 log(1+累计回复数+累计转发数)，求和，再在全部达标候选题材中计算分位。不是当日新增互动量。";
  if (report.meta.discovery && key === "trading") return "题材样本股票换手率的等权均值，在本次候选题材中的分位；不是官方板块指数，也不代表散户占比。";
  return metricInfo[key].description;
}
const currentDimensions: DimensionKey[] = ["discussion", "growth", "spread", "chase", "panic", "trading"];
const oldDimensions: DimensionKey[] = ["discussion", "spread", "panic", "refill", "crowding", "overheat"];
const inputNames: Record<string, string> = { following: "跟随决策率", question: "追涨询问率", hype: "无依据喊涨率", l1l2: "L1+L2占比", chase: "明确追涨强度", discussion: "讨论规模分位", growth: "讨论升温", spread: "传播分位", trading: "交易活跃分位", panic: "恐慌表达" };
function metricValue(sector: ReportSector, key: DimensionKey) { return key === "leek" ? sector.leekScore?.score ?? null : sector.dimensions[key]; }
function metricLabel(sector: ReportSector, key: DimensionKey) { return key === "leek" && sector.leekScore?.score == null && sector.leekScore?.range ? sector.leekScore.range.map(n => fmt(n, 0)).join("–") : fmt(metricValue(sector, key)); }

function ThermometerCard({ item, active, onSelect }: { item: Thermometer; active: boolean; onSelect: () => void }) {
  const tone = temperatureTone(item.score);
  const height = item.score == null ? 0 : Math.max(0, Math.min(100, item.score)) * 1.1;
  return <button className={`thermometer-card ${active ? "is-selected" : ""}`} style={{ "--temperature": tone.ink, "--temperature-soft": tone.background } as CSSProperties} aria-expanded={active} onClick={onSelect}>
    <span className="thermometer-state">{tone.name}</span>
    <svg viewBox="0 0 100 185" className="thermometer-svg" aria-hidden="true">
      <path d="M37 133V22a9 9 0 0 1 18 0v111a19 19 0 1 1-18 0Z" fill="#f5f4ef" stroke="#a6aaac" strokeWidth="1.7" />
      <rect x="41" y={132 - height} width="10" height={height} rx="5" fill="currentColor" />
      <circle cx="46" cy="150" r="15" fill={item.score == null ? "#b6bfc6" : "currentColor"} />
      <circle cx="42" cy="145" r="4" fill="white" opacity=".4" />
      {[22, 77, 132].map((y, i) => <g key={y}><path d={`M61 ${y}h5`} stroke="#a6aaac" /><text x="70" y={y + 4} fill="#627080" fontSize="11">{[100, 50, 0][i]}</text></g>)}
    </svg>
    <span className="thermometer-name">{item.name}</span><strong>{fmt(item.score)}<small>{item.score == null ? "" : item.unit}</small></strong>
    <span className="thermometer-scope">{item.scope}</span>
  </button>;
}

function EvidenceDialog({ sector, dimension, report, onClose }: { sector: ReportSector; dimension: DimensionKey; report: DailyReport; onClose: () => void }) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => { ref.current?.showModal(); }, []);
  const info = metricInfo[dimension], observation = sector.observation;
  return <dialog ref={ref} className="research-dialog v4-dialog report-evidence" onCancel={onClose} onClose={onClose}>
    <button className="v4-dialog-close" onClick={onClose}>关闭 ×</button>
    <span className="eyebrow">{report.meta.tradeDate} · 计算与证据</span><h2>{sector.name} · {info.name} {metricLabel(sector, dimension)}{info.unit}</h2>
    <p>{metricDescription(dimension, report)}</p><p className="report-detail-note">采样 {observation.memberObserved}/{observation.memberTotal} 只成分，{observation.memberComplete} 只已读完窗口；观察 {observation.authors} 个账户、{observation.observedPosts} 条讨论，限量后分析 {observation.sampleCount} 条。{observation.bodyObserved ? `补读正文 ${observation.bodyObserved} 条。` : "当前没有补读正文。"}{observation.complete ? "窗口完整。" : "存在截断，计数为已观察下限。"}{sector.historicalAttentionScore != null ? `同口径历史 ${sector.historicalBaselineDays ?? 0} 日相对分位 ${fmt(sector.historicalAttentionScore)}；历史中位关注分 ${fmt(sector.historicalAttentionMedian)}。` : "同口径历史样本不足20日，暂不显示历史分位。"}</p>
    <div className="report-evidence-facts"><span>每股讨论账户 <b>{fmt(observation.density, 2)}</b></span><span>平均每帖互动 <b>{fmt(observation.interactionMean, 2)}</b></span><span>追涨 / 恐慌 / 补仓 <b>{observation.chaseCount} / {observation.panicCount} / {observation.refillCount}</b></span></div>
    {dimension === "overheat" && <p className="report-detail-note">四项输入：讨论 {fmt(sector.overheatInputs.discussion)}、传播 {fmt(sector.overheatInputs.spread)}、拥挤 {fmt(sector.overheatInputs.crowding)}、追涨表达分位 {fmt(sector.overheatInputs.chaseRank)}。这列对应综合观察，不评价投资者经验。</p>}
    {dimension === "growth" && sector.growth && <p>可比成分 {sector.growth.pairedMembers} 只；今日 {sector.growth.today} 个账户，对比 {sector.growth.previousDate} 的 {sector.growth.previous} 个账户。{sector.growth.basis}。</p>}
    {dimension === "leek" && sector.leekScore && <div className="leek-breakdown"><h3>每项输入与权重</h3>{sector.leekScore.rawExpressionScore != null && <p>原始规则表达密度 {fmt(sector.leekScore.rawExpressionScore)}；因未知比例过高，未作为综合分发布。</p>}{Object.entries(sector.leekScore.weights).map(([key, weight]) => <p key={key}><span>{inputNames[key]} · {fmt(weight * 100, 0)}%</span><b>{fmt(sector.leekScore!.inputs[key])}</b></p>)}<p>{sector.leekScore.reason}</p><p>未知账户保留在分母中；低分仅表示规则识别到的跟风追涨表达较少，不表示投资者理性。所有比例按观察账户计算，至少20个账户且来源覆盖达标才出分。</p></div>}
    <h3>代表表达</h3><p className="fine-print">以下仅展示部分证据；比例使用完整分析样本。互动观测时刻：{time(report.meta.interactionAsOf)}（北京时间）。</p>
    <div className="report-posts">{observation.posts.map((post, index) => <article key={`${post.code}:${index}`}><div><span>{post.intent}{post.refill ? " · 补仓表达" : ""}{post.panic ? " · 恐慌表达" : ""}</span><small>{post.date} · {post.code}</small></div><p>{post.text}</p><a href={post.url} target="_blank" rel="noreferrer">核对原帖 ↗</a><small>回复 {fmt(post.replies, 0)} · 转发 {fmt(post.forwards, 0)}</small></article>)}</div>
    {!observation.posts.length && <p>尚无可展示的有效样本。</p>}
  </dialog>;
}

function FlowColumn({ rows, direction, limit, maximum }: { rows: FundFlow[]; direction: "in" | "out"; limit: number; maximum: number }) {
  return <article className={`flow-column flow-${direction}`}><h3><span className="flow-dot" />{direction === "in" ? "主力净流入" : "主力净流出"}<small>{rows.length} 个方向</small></h3>
    <ol>{rows.slice(0, limit).map((row, index) => <li key={row.code}><div className="flow-row-main"><span className="flow-order">{index + 1}</span><a href={row.sourceUrl} target="_blank" rel="noreferrer">{row.name} ↗</a><strong>{direction === "in" ? "+" : "−"}{fmt(Math.abs(row.net) / 1e8, 2)}<small>亿</small></strong></div><div className="flow-bar"><span style={{ width: `${maximum ? Math.abs(row.net) / maximum * 100 : 0}%` }} /></div><p>{row.diagnosis}<span>涨跌 {change(row.changePct)} · 净额占比 {change(row.ratio)}</span></p></li>)}</ol>
    {!rows.length && <p className="empty-state">该范围暂无已核验的{direction === "in" ? "净流入" : "净流出"}记录。</p>}
  </article>;
}

export function MarketReport({ initialReport }: { initialReport: DailyReport | null }) {
  const [report, setReport] = useState(initialReport), [dates, setDates] = useState(initialReport ? [initialReport.meta.tradeDate] : []);
  const [activeMetric, setActiveMetric] = useState<string | null>(null), [flowKind, setFlowKind] = useState("industry"), [limit, setLimit] = useState(6);
  const [selected, setSelected] = useState<{ sector: ReportSector; dimension: DimensionKey } | null>(null);
  const [pending, setPending] = useState(false), [error, setError] = useState("");
  const request = useRef<AbortController | null>(null), sequence = useRef(0), latest = useRef(initialReport?.meta.tradeDate);
  useEffect(() => {
    const controller = new AbortController();
    const refresh = async (initial = false) => {
      try {
        if (initial) {
          const response = await fetch("/data/report/index.json", { signal: controller.signal, cache: "no-store" });
          if (response.ok) { const index = await response.json() as { dates?: string[] }; if (Array.isArray(index.dates)) setDates(index.dates.filter(d => /^\d{4}-\d{2}-\d{2}$/.test(d))); }
        }
        if (request.current) return;
        const response = await fetch("/data/report/latest.json", { signal: controller.signal, cache: "no-store" });
        if (!response.ok) return;
        const value = await response.json() as DailyReport;
        if (value.meta?.version !== "daily-report-1.0" || !Array.isArray(value.sectors) || request.current) return;
        const oldLatest = latest.current;
        setReport(current => !current || current.meta.tradeDate === oldLatest ? value : current);
        latest.current = value.meta.tradeDate;
        setDates(current => [...new Set([...current, value.meta.tradeDate])].sort());
      } catch { /* Preserve the readable report. */ }
    };
    void refresh(true); const timer = setInterval(() => void refresh(), 300000);
    return () => { controller.abort(); request.current?.abort(); clearInterval(timer); };
  }, []);
  const changeDate = async (day: string) => {
    request.current?.abort(); const controller = new AbortController(); request.current = controller; const id = ++sequence.current;
    setPending(true); setError(""); setSelected(null); setActiveMetric(null);
    try {
      const response = await fetch(`/data/report/daily/${day}.json`, { signal: controller.signal, cache: "no-store" });
      if (!response.ok) throw new Error("该日报告读取失败，保留当前报告");
      const value = await response.json() as DailyReport;
      if (value.meta?.tradeDate !== day || value.meta?.version !== "daily-report-1.0") throw new Error("报告日期或版本不匹配");
      if (id === sequence.current) setReport(value);
    } catch (failure) { if (!controller.signal.aborted) setError(failure instanceof Error ? failure.message : "读取失败"); }
    finally { if (id === sequence.current) { setPending(false); request.current = null; } }
  };
  if (!report) return <section className="panel"><h2>市场复盘</h2><p>尚未取得可用报告，现有市场与社区看板仍可查看。</p></section>;
  const metric = report.thermometers.find(row => row.key === activeMetric);
  const dimensions = report.meta.analysisVersion ? [...currentDimensions, "leek" as const] : oldDimensions;
  const incoming = rankFlows(report.flows.rows, flowKind, "in"), outgoing = rankFlows(report.flows.rows, flowKind, "out");
  const coverage = report.flows.coverage.find(row => row.kind === flowKind);
  const maximum = Math.max(0, ...incoming.map(r => r.net), ...outgoing.map(r => -r.net));
  return <div className="daily-report" aria-busy={pending}>
    <div className="report-datebar"><span>盘后复盘 <b>{report.meta.tradeDate.replaceAll("-", ".")}</b><i>{report.meta.discovery ? "收盘行情 · 全天讨论" : "截至收盘"}</i></span><label>报告日期 <select aria-label="报告日期" value={report.meta.tradeDate} onChange={e => void changeDate(e.target.value)}>{dates.map(day => <option key={day}>{day}</option>)}</select></label></div>
    {pending && <p role="status">正在读取所选日报…</p>}{error && <p role="alert">{error}</p>}
    <section className="panel report-section thermometer-section"><div className="report-section-heading"><span className="report-step">01</span><div><span className="eyebrow">市场体温计 · 五个观察角度</span><h2>今天的市场，是热还是冷？</h2></div></div><p className="report-summary">{report.summary}</p>
      <div className="thermometer-grid">{report.thermometers.map(item => <ThermometerCard key={item.key} item={item} active={item.key === activeMetric} onSelect={() => setActiveMetric(activeMetric === item.key ? null : item.key)} />)}</div>
      <div className="temperature-legend">{[10, 30, 50, 70, 90].map(value => { const tone = temperatureTone(value); return <span key={value}><i style={{ background: tone.ink }} />{value - 10}–{value === 90 ? 100 : value + 9} {tone.name}</span>; })}<small>颜色表示数值高低，点击温度计查看含义</small></div>
      {metric && <div className="thermometer-explanation" role="status"><strong>{metric.name} · {metric.scope}</strong><p>{metric.detail}</p>{metric.evidence && <p>{metric.evidence.map(row => `${row.name} ${fmt(row.score)} 分（${row.baselineDays}日基线）`).join("；")}</p>}</div>}
    </section>
    <section className="panel report-section matrix-section"><div className="report-section-heading"><span className="report-step">02</span><div><span className="eyebrow">当天热门概念 · TOP {report.sectors.length}</span><h2>十个热门板块的「六维温度」</h2></div><span className="report-tag">点分数看计算与原帖</span></div>
      <p className="report-summary">{report.meta.selectionNote}</p>{report.meta.discovery && <div className={`report-detail-note ${report.meta.discovery.rankingQuality === "partial-lower-bound" ? "fund-stale" : ""}`}>观察 {report.meta.discovery.sampleStocks}/{report.meta.discovery.universeStocks} 只股票，成交额覆盖 {fmt(report.meta.discovery.amountCoverage * 100)}%；标签成功 {report.meta.discovery.tagCoverage} 只，候选题材 {report.meta.discovery.candidateTopics} 个、达标 {report.meta.discovery.eligibleTopics} 个，达到完整度门槛 {report.meta.discovery.completeTopics ?? "—"} 个；补读扩展 {report.meta.discovery.expandedStocks ?? 0} 只。{report.meta.discovery.rankingQuality === "partial-lower-bound" ? "当前前十使用部分截断来源，关注热度按已观察数据计算，只能作为下限。" : report.meta.discovery.rankingQuality === "complete" ? "当前前十使用达到完整度门槛的来源。" : "此历史日报未记录来源完整度，不能据此判断排名是否完整。"} <details><summary>相近题材去重与样本边界</summary><p>{report.meta.discovery.suppressed.map(r => `${r.name} → ${r.representedBy}${r.reason ? `（${r.reason}）` : ""}`).join("；") || "本次前十未出现达到去重阈值的题材"}</p><p>成分是本次采样股票，不是完整板块成分。主营相关个股发言是题材关注的代理；标签仅与当前采集时间对应。旧日报保留原方法，分数不可直接跨版本比较。至少积累 {report.meta.discovery.historicalBaselineDays ?? 20} 个同口径历史日后才会显示历史分位。</p></details></div>}<div className="heatmap-legend"><span><i className="heat-80" />80–100</span><span><i className="heat-60" />60–79</span><span><i className="heat-40" />40–59</span><span><i className="heat-20" />20–39</span><span><i className="heat-0" />0–19</span><span><i className="heat-missing" />缺失</span></div>
      <div className="report-matrix-scroll"><table className="report-matrix"><thead><tr><th>板块</th>{dimensions.map(key => <th key={key}>{report.meta.discovery && key === "discussion" ? "关注热度" : metricInfo[key].name}<small>{key === "leek" || key === "overheat" ? "试验分 / 范围" : key === "panic" || key === "refill" || key === "chase" ? "表达占比 %" : key === "growth" ? "50为持平" : "分位 / 100"}</small></th>)}<th>形态</th><th>一句话观察</th></tr></thead><tbody>{report.sectors.map((sector, index) => <tr key={sector.id}><th><span className="matrix-rank">{String(index + 1).padStart(2, "0")}</span>{sector.name}<small className={sector.changePct >= 0 ? "rise" : "fall"}>{change(sector.changePct)} · {report.meta.discovery ? "关注热度" : "行情热度"} {fmt(sector.selectionScore)}</small></th>{dimensions.map(key => { const value = metricValue(sector, key); const band = value == null ? "missing" : value >= 80 ? "80" : value >= 60 ? "60" : value >= 40 ? "40" : value >= 20 ? "20" : "0"; return <td className={`heat-${band} ${key === "leek" ? "leek-cell" : ""}`} key={key}><button aria-label={`${sector.name} ${metricInfo[key].name} ${metricLabel(sector, key)}，查看依据`} onClick={() => setSelected({ sector, dimension: key })}>{metricLabel(sector, key)}{key === "leek" && sector.leekScore?.score == null && <small>{sector.leekScore?.range ? "覆盖有限" : "待补数据"}</small>}</button></td>; })}<td><span className="shape-tag">{sector.shape}</span></td><td className="matrix-diagnosis">{sector.diagnosis}<small>{sector.observation.memberObserved}/{sector.observation.memberTotal} {report.meta.discovery ? "样本股" : "股"} · {sector.observation.complete ? "窗口完整" : "部分截断，计数为下限"}{sector.observation.bodyObserved ? ` · 正文 ${sector.observation.bodyObserved} 条` : ""}</small></td></tr>)}</tbody></table></div>
      <p className="report-footnote">六项观察与韭菜分分别展示。分位、日环比和表达比例含义不同；恐慌独立显示，不为跟风过热加分。回复与转发累计至 {time(report.meta.interactionAsOf)}（北京时间），目前传播力仍为累计互动代理。</p>
    </section>
    <FollowingComposition key={report.meta.tradeDate} report={report} />
    <LiveFundFlows />
    <details className="report-archive"><summary>查看 {report.meta.tradeDate} 保存的新浪盘后资金记录</summary><section className="panel report-section fund-section"><div className="report-section-heading"><div><span className="eyebrow">历史归档 · {report.meta.tradeDate}</span><h2>当日保存的资金流向</h2></div><div className="segmented" role="group" aria-label="资金板块口径">{[["industry", "行业"], ["concept", "概念"]].map(([kind, label]) => <button key={kind} aria-pressed={flowKind === kind} className={flowKind === kind ? "active" : ""} onClick={() => { setFlowKind(kind); setLimit(6); }}>{label}</button>)}</div></div>
      <p className="report-summary">净流入领先：<b className="rise">{incoming.slice(0, 3).map(r => r.name).join("、") || "暂无"}</b>；净流出领先：<b className="fall">{outgoing.slice(0, 3).map(r => r.name).join("、") || "暂无"}</b>。已核验 {coverage?.observed ?? 0}/{coverage?.expected ?? "—"} 个{flowKind === "industry" ? "行业" : "概念"}。</p>
      <div className="fund-flow-grid"><FlowColumn direction="in" rows={incoming} limit={limit} maximum={maximum} /><FlowColumn direction="out" rows={outgoing} limit={limit} maximum={maximum} /></div>
      {Math.max(incoming.length, outgoing.length) > 6 && <button className="report-expand" onClick={() => setLimit(limit === 6 ? Math.max(incoming.length, outgoing.length) : 6)}>{limit === 6 ? "展开完整流入 / 流出排序 ↓" : "收起为前六 ↑"}</button>}
      <div className="flow-reading"><strong>如何读这张榜</strong><p>排名依据主力净额。价格上涨而资金净流出时，两项信号存在分歧；净流入也不能单独解释为机构看多。这里的评价只描述已核验的数据关系。</p></div>
      <details className="report-sources"><summary>数据来源、时间与覆盖</summary><p>{report.meta.flowNote}</p><p>资金使用所选日期的来源板块日线；行情表使用已核验成分等权均值，两种板块涨跌口径可能略有差异。资金榜中的涨跌采用资金来源自身口径。</p><p>采集于 {time(report.meta.collectedAt)}（北京时间）。社区入口 {report.meta.feedObserved}/{report.meta.feedExpected}；{report.meta.errors.length ? `${report.meta.errors.length} 项未成功，缺项不计零、不用其他日期补位。` : "全部采集任务返回。"}</p>{report.meta.errors.map((row, i) => <p key={i}>{row.key}：{row.error}</p>)}</details>
    </section></details>
    <MarketReading report={report} />
    {selected && <EvidenceDialog key={`${selected.sector.id}:${selected.dimension}`} {...selected} report={report} onClose={() => setSelected(null)} />}
  </div>;
}
