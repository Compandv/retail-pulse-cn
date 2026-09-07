"use client";
import { useState } from "react";
import type { DailyReport } from "./report-types";
const pct = (n: number | null | undefined) => n == null ? "—" : `${n.toFixed(1)}%`;
const keys = ["following", "chase", "question", "hype"];
const names = ["跟随决策", "明确追涨", "追涨询问", "无依据喊涨"];

export function FollowingComposition({ report }: {report: DailyReport}) {
  const [selected, setSelected] = useState<string | null>(null);
  const rows = [...report.sectors].sort((a,b) => (b.leekScore?.score ?? -1) - (a.leekScore?.score ?? -1));
  const sector = rows.find(r => r.id === selected);
  if (!rows.some(r => r.expressionProfile)) return <section className="panel report-section"><h2>历史方法提示</h2><p>该日期使用旧版分类及评分，不能与新版跟风追涨分直接比较。重新回放该日期数据后可查看新的表达分类。</p></section>;
  return <section className="panel report-section"><div className="report-section-heading"><span className="report-step">03</span><div><span className="eyebrow">跟风追涨表达 · 十强热点</span><h2>哪些板块的跟风追涨更集中？</h2></div></div>
    <p className="report-summary">按韭菜分降序排列。每个账户同项取最高强度，最多使用三条去重发言。标签可以重叠，不是投资者等级，也不是实际买卖记录。</p>
    {rows.some(s => (s.expressionProfile?.unknownRate ?? 0) > 50) && <p className="fund-status fund-stale">部分板块超过半数账户没有识别到明确标签。当前低分只表示已检测到的跟风追涨证据少，不能解释为市场冷清或散户理性；请结合未知比例与命中原文判断。</p>}
    <div className="report-matrix-scroll"><table className="report-matrix"><thead><tr><th>热门板块</th>{names.map(n => <th key={n}>{n}</th>)}<th>韭菜分</th><th>观察账户 / 未知</th></tr></thead><tbody>{rows.map(s => {
      const p = s.expressionProfile;
      return <tr key={s.id}><th><button onClick={() => setSelected(selected === s.id ? null : s.id)} aria-expanded={selected === s.id}>{s.name} · 依据 {selected === s.id ? "−" : "+"}</button></th>{keys.map(k => {
        const rate = p?.labels.find(l => l.key === k)?.rate;
        const band = rate == null ? "missing" : rate >= 80 ? "80" : rate >= 60 ? "60" : rate >= 40 ? "40" : rate >= 20 ? "20" : "0";
        return <td key={k} className={`heat-${band}`}>{p?.eligible ? pct(rate) : "—"}</td>;
      })}<td className="leek-cell">{s.leekScore?.score ?? "—"}</td><td>{p?.observedAccounts ?? "—"}<small>未知 {p?.unknownAccounts ?? "—"} · {pct(p?.unknownRate)}</small></td></tr>;
    })}</tbody></table></div>
    <p className="report-footnote">韭菜分 = 跟随30% + 明确追涨40% + 询问20% + 喊涨10%。自述已追买计1、明确计划计0.7；追涨列为加权表达率。未知账户仍在分母中，低分不等于理性。至少20个观察账户且来源覆盖达标才出分。</p>
    {sector?.expressionProfile && <div className="flow-reading"><h3>{sector.name} · 分类证据</h3>{sector.expressionProfile.labels.map(label => <details key={label.key}><summary>{label.label}：{label.count} 个账户 · {pct(label.rate)}</summary>{label.examples.length ? label.examples.map((e,i) => <article className="profile-example" key={i}><p>{e.text}</p><small>命中片段：{e.evidence} · {e.date}</small>{e.url && <a href={e.url} target="_blank" rel="noreferrer">核对原帖 ↗</a>}</article>) : <p>没有识别到此类证据；不代表不存在这种行为。</p>}</details>)}</div>}
  </section>;
}

export function MarketReading({report}: {report: DailyReport}) {
  const reading = report.llmReading;
  const names: Record<string,string> = {market: "大盘情绪", sectors: "板块轮动", flows: "资金分歧", limitations: "数据局限"};
  return <section className="panel report-section"><div className="report-section-heading"><span className="report-step">05</span><div><span className="eyebrow">模型汇总解读 · {report.meta.tradeDate}</span><h2>把情绪、交易和资金放在一起看</h2></div></div>
    {reading?.status === "complete" && reading.sections ? <><p className="fine-print">{reading.model} · {reading.generatedAt ? new Date(reading.generatedAt).toLocaleString("zh-CN", {timeZone:"Asia/Shanghai"}) : ""} · 基于本日报保存数据，非实时资金解读；模型不修改分数。</p>{Object.entries(reading.sections).map(([key, value]) => <div className="flow-reading" key={key}><h3>{names[key] ?? key}</h3><p>{value.text}</p><details><summary>查看引用数据</summary>{value.factIds.map(id => <pre key={id} style={{whiteSpace:"pre-wrap", overflowWrap:"anywhere"}}>{JSON.stringify(reading.facts?.find(f => f.id === id) ?? {id}, null, 2)}</pre>)}</details></div>)}</> : <p>{reading?.note ?? "本地指标已计算。下次手动运行完整更新时，将对汇总数据调用一次模型生成解读。"}</p>}
  </section>;
}
