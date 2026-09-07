"use client";

import { useEffect, useRef, useState } from "react";
import { METHOD_VERSION, SCORE_LABELS, SCORE_WEIGHTS, scoreBand, type ScoreAxis } from "../lib/scoring";
import type { CommentRow, Sector, SectorHistoryPoint, Snapshot } from "./types";
import { LineChart } from "./charts";
import { answerResearchQuestion } from "../lib/research";

const number = (value: number | null | undefined) => value == null ? "—" : value.toFixed(1);

export function ScoreScale({ value }: { value: number | null | undefined }) {
  const band = scoreBand(value);
  return <div className="score-scale"><div className="score-scale-heading"><strong style={{ color: band.color }}>{band.label}</strong><span>{number(value)} / 100</span></div><div className="score-scale-track" role="meter" aria-label="情绪强度" aria-valuemin={0} aria-valuemax={100} aria-valuenow={value ?? undefined} aria-valuetext={value == null ? "暂无样本" : `${number(value)} 分，${band.label}`}>
    {["cold", "mild", "active", "hot", "extreme"].map(key => <span key={key} className={key} />)}
    {value != null && <i style={{ left: `${Math.max(0, Math.min(100, value))}%` }} />}
  </div><div className="score-scale-ticks">{[0, 20, 40, 60, 80, 100].map(tick => <span key={tick}>{tick}</span>)}</div><p>0–20 冷清 · 20–40 温和 · 40–60 活跃 · 60–80 高热 · 80–100 极热</p></div>;
}

export function ScoreBreakdown({ metrics, version }: { metrics: Partial<Record<ScoreAxis | "overall", number | null>>; version: string }) {
  if (version !== METHOD_VERSION) return <div className="method-notice">这份快照使用 {version}。运行每日更新后生成 V3 分数；旧版分数没有套用新公式。</div>;
  return <div className="score-breakdown"><h3>这个分数怎么来的</h3><p>每个来源独立计算，按有效来源等权合并。样本不足降低置信等级，不把分数拉回 50。</p>
    {(Object.keys(SCORE_WEIGHTS) as ScoreAxis[]).map(key => {
      const weight = SCORE_WEIGHTS[key], value = metrics[key];
      return <div className="contribution-row" key={key}><span>{SCORE_LABELS[key]}<small>{weight * 100}% 权重</small></span><div className="contribution-track"><i style={{ width: `${value ?? 0}%` }} /></div><span>{number(value)} × {weight}</span><strong>{number(value == null ? null : value * weight)} 分</strong></div>;
    })}
    <div className="contribution-total"><span>综合情绪强度</span><strong>{number(metrics.overall)} / 100</strong></div>
    <p className="fine-print">新手／追涨／恐慌分项 = 60% 明显表达占比 + 40% 平均表达强度。分项均为 0–100；方向强度为各来源多空方向绝对值的均值。热度以每来源 80 条样本为满刻度。显示值四舍五入可能相差 0.1 分。</p>
  </div>;
}

export function EvidenceFeed({ comments }: { comments: CommentRow[] }) {
  if (!comments.length) return <div className="empty-state">这个板块暂时没有可展示的表达样本。</div>;
  return <div className="evidence-feed">{comments.map(comment => <details className="evidence-item" key={comment.id}>
    <summary><span className={`evidence-tone ${comment.tone}`}>{comment.intent}</span><span className="evidence-title">{comment.excerpt}<small>{comment.source} · {comment.date}</small></span><strong>{comment.score == null ? "查看依据" : `${number(comment.score)} 分`}</strong></summary>
    <div className="evidence-body"><p>{comment.reasoning || `命中表达：${comment.signals.join("、") || "无明显关键词"}。这条旧版记录未保存详细评分依据。`}</p>
      {comment.evidence?.map(axis => <div className="evidence-axis" key={axis.key}><span>{axis.label}</span><meter min={0} max={100} value={axis.value} aria-label={axis.label} /><b>{number(axis.value)}</b><small>{axis.matched.join("、") || "无关键词命中"}</small></div>)}
      <p className="fine-print">单条分数表示最强表达信号，与板块综合温度含义不同。这里展示匿名节选，不能代表全部讨论。</p>
      {comment.url && /^https:\/\/guba\.eastmoney\.com\//.test(comment.url) && <a href={comment.url} target="_blank" rel="noreferrer">查看公开原帖 ↗</a>}
    </div>
  </details>)}</div>;
}

async function saveSectorImage(sector: Sector, snapshot: Snapshot) {
  if (document.fonts) await document.fonts.ready;
  const canvas = document.createElement("canvas"); canvas.width = 1200; canvas.height = 1050;
  const ctx = canvas.getContext("2d"); if (!ctx) throw new Error("浏览器无法创建图片");
  ctx.fillStyle = "#f3f0e8"; ctx.fillRect(0, 0, 1200, 1050);
  ctx.fillStyle = "#1c1c1a"; ctx.font = 'bold 36px "Microsoft YaHei", sans-serif'; ctx.fillText("散户温度计 · 板块观察", 70, 90);
  ctx.font = 'bold 62px "Microsoft YaHei", sans-serif'; ctx.fillText(sector.name, 70, 205);
  ctx.fillStyle = "#e85432"; ctx.font = 'bold 150px Georgia, serif'; ctx.fillText(number(sector.overall), 65, 390);
  ctx.fillStyle = "#6e6b63"; ctx.font = '30px "Microsoft YaHei", sans-serif'; ctx.fillText(`/ 100 · ${scoreBand(sector.overall).label}`, 520, 380);
  const lines = [`观测交易日 ${snapshot.meta.tradeDate} · ${snapshot.meta.mode === "live" ? "实测快照" : "演示快照"}`, `代表标的：${sector.representative}（主题代理）`, `样本：当日 ${sector.sampleCount} 条 / 近三日 ${sector.sampleCount3d} 条 · 置信 ${sector.confidence}`, `新手 ${number(sector.novice)} · 追涨 ${number(sector.fomo)} · 恐慌 ${number(sector.panic)}`, `热度 ${number(sector.heat)} · 多空方向 ${number(sector.direction)}`, `全市场来源：${snapshot.meta.sources.filter(source => source.sampleCount > 0).map(source => source.name).join(" / ")}`, `方法：${snapshot.meta.methodVersion} · 仅用于社区情绪观察`];
  ctx.font = '26px "Microsoft YaHei", sans-serif'; lines.forEach((line, index) => ctx.fillText(line, 70, 495 + index * 57, 1060));
  ctx.fillStyle = "#1c1c1a"; ctx.font = '24px "Microsoft YaHei", sans-serif'; ctx.fillText("高热可来自追涨或恐慌，不代表未来涨跌，也不是买卖指令。", 70, 990);
  const blob = await new Promise<Blob | null>(resolve => canvas.toBlob(resolve, "image/png")); if (!blob) throw new Error("图片生成失败");
  const url = URL.createObjectURL(blob), link = document.createElement("a"); link.href = url; link.download = `散户温度计-${sector.id}-${snapshot.meta.tradeDate}.png`; link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export function SectorResearchDialog({ sector, snapshot, onClose }: { sector: Sector; snapshot: Snapshot; onClose: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [days, setDays] = useState(20);
  const [metric, setMetric] = useState<"overall" | "heat">("overall");
  const [legacy, setLegacy] = useState(false);
  const [shareState, setShareState] = useState("");
  useEffect(() => { dialog.current?.showModal(); }, []);
  const history = (legacy ? snapshot.legacy?.sectorHistory : snapshot.sectorHistory) ?? [];
  const points = history.map(day => { const row = day.sectors.find(item => item.id === sector.id); return { date: day.date, recordType: day.recordType, overall: row?.overall ?? null, heat: row?.heat ?? null }; }).slice(-days);
  const comments = (snapshot.comments ?? []).filter(comment => comment.sectorId === sector.id);
  return <dialog ref={dialog} onClose={onClose} className="research-dialog" aria-labelledby="research-dialog-title"><div className="research-dialog-header"><div><span className="eyebrow">{sector.group} · {snapshot.meta.tradeDate}</span><h2 id="research-dialog-title">{sector.name}</h2><p>{sector.representative} · 代表标的／主题代理</p></div><button aria-label="关闭板块详情" onClick={() => dialog.current?.close()}>关闭 ×</button></div>
    <div className="research-dialog-content"><div className="research-summary"><ScoreScale value={sector.overall} /><div className="research-meta"><b>置信等级 {sector.confidence}</b><span>当日 {sector.sampleCount} 条 · 近三日 {sector.sampleCount3d} 条</span><span>评分窗口：{sector.dataWindow} · 表达构成：{sector.mixWindow}</span><span>可信度由来源和样本量决定，分数不是准确率。</span><button className="primary-button" disabled={shareState === "正在生成…"} onClick={async () => { setShareState("正在生成…"); try { await saveSectorImage(sector, snapshot); setShareState("图片已生成"); } catch { setShareState("生成失败，请重试"); } }}>保存分享图片</button><small role="status">{shareState}</small></div></div>
    <ScoreBreakdown metrics={sector} version={snapshot.meta.methodVersion} />
    <section className="research-history"><div className="panel-head"><h3>板块历史</h3><div className="segmented">{(["overall", "heat"] as const).map(key => <button key={key} className={metric === key ? "active" : ""} onClick={() => setMetric(key)}>{key === "overall" ? "温度" : "热度"}</button>)}{[10, 20, 60].map(range => <button key={range} className={days === range ? "active" : ""} onClick={() => setDays(range)}>{range} 日</button>)}</div></div>
      {snapshot.legacy?.sectorHistory?.length ? <label className="legacy-toggle"><input type="checkbox" checked={legacy} onChange={event => setLegacy(event.target.checked)} />查看旧版历史（{snapshot.legacy.methodVersion}，不与新分数直接比较）</label> : null}
      <LineChart points={points} metric={metric} /><p className="fine-print">{legacy ? snapshot.legacy?.methodVersion : snapshot.meta.methodVersion} · 缺失观测留空；窗口内 {points.filter(point => point[metric] != null).length} 个有效日期。</p>
    </section><section><h3>代表表达与判定依据</h3><p className="fine-print">按表达强度选择的节选，用于解释规则，不能代表全部样本的占比。</p><EvidenceFeed comments={comments} /></section></div>
  </dialog>;
}

export function SectorCalendar({ snapshot, onSelect }: { snapshot: Snapshot; onSelect: (sector: Sector) => void }) {
  const [legacy, setLegacy] = useState(false);
  const [group, setGroup] = useState("全部");
  const history: SectorHistoryPoint[] = ((legacy ? snapshot.legacy?.sectorHistory : snapshot.sectorHistory) ?? []).slice(-30);
  const sectors = snapshot.sectors.filter(sector => group === "全部" || sector.group === group);
  return <article className="panel calendar-panel"><div className="panel-head"><div><span className="eyebrow">板块 × 日期</span><h2>谁在持续升温</h2></div><label>主题组 <select value={group} onChange={event => setGroup(event.target.value)}>{["全部", ...new Set(snapshot.sectors.map(sector => sector.group))].map(value => <option key={value}>{value}</option>)}</select></label></div>
    {snapshot.legacy?.sectorHistory?.length ? <label className="legacy-toggle"><input type="checkbox" checked={legacy} onChange={event => setLegacy(event.target.checked)} />查看旧版历史（独立刻度）</label> : null}
    {/* eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex -- Focus enables keyboard scrolling of the wide table. */}
    {history.length ? <div className="sector-calendar-scroll" tabIndex={0} role="region" aria-label="可横向滚动的板块情绪日历"><table className="sector-calendar"><caption>{legacy ? snapshot.legacy?.methodVersion : snapshot.meta.methodVersion} · 最近 {history.length} 个有记录日期 · 点击板块查看证据</caption><thead><tr><th scope="col">板块</th>{history.map(day => <th scope="col" key={day.date}>{day.date.slice(5)}</th>)}</tr></thead><tbody>{sectors.map(sector => <tr key={sector.id}><th scope="row"><button onClick={() => onSelect(sector)}>{sector.name} ↗</button></th>{history.map(day => { const row = day.sectors.find(item => item.id === sector.id); const value = row?.sampleCount === 0 ? null : row?.overall; const band = scoreBand(value); return <td key={day.date} className={`calendar-score ${band.key}`} title={`${sector.name} · ${day.date} · ${value == null ? "无观测" : `${number(value)} 分`}`}>{value == null ? "—" : value.toFixed(0)}</td>; })}</tr>)}</tbody></table></div> : <div className="empty-state">新公式历史正在积累。旧版历史可单独查看。</div>}
    <p className="fine-print">0–20 冷清 · 20–40 温和 · 40–60 活跃 · 60–80 高热 · 80–100 极热 · — 无观测。仅展示有记录的日期，不补造缺失交易日。</p>
  </article>;
}

export function ResearchQA({ snapshot, onSelect }: { snapshot: Snapshot; onSelect: (sector: Sector) => void }) {
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState<ReturnType<typeof answerResearchQuestion> | null>(null);
  const ask = (value: string) => { if (!value.trim()) return; setQuestion(value); setAnswer(answerResearchQuestion(value, snapshot)); };
  return <article className="panel research-qa"><div className="panel-head"><div><span className="eyebrow">基于当前快照 · 本地规则问答</span><h2>带着问题看数据</h2></div><span>{snapshot.meta.tradeDate}</span></div><div className="question-presets">{["今天哪些板块升温最快？", "当前最热的板块有哪些？", "半导体设备和黄金有什么差异？", "这个分数是怎么算的？"].map(value => <button key={value} onClick={() => ask(value)}>{value}</button>)}</div>
    <form className="query-form" onSubmit={event => { event.preventDefault(); ask(question); }}><input aria-label="向当前快照提问" value={question} onChange={event => setQuestion(event.target.value)} placeholder="输入板块名、两个板块的比较，或询问评分依据" /><button type="submit">查看分析</button></form>
    {answer && <div className="research-answer" aria-live="polite"><strong>{answer.title}</strong><p>{answer.text}</p><div className="answer-citations">{answer.sectorIds.map(id => { const sector = snapshot.sectors.find(item => item.id === id); return sector ? <button key={id} onClick={() => onSelect(sector)}>查看 {sector.name} 的数据与证据 ↗</button> : null; })}</div><small>依据：{snapshot.meta.tradeDate} 快照 · {snapshot.meta.methodVersion}。回答限于现有数据，不生成行情预测。</small></div>}
  </article>;
}
