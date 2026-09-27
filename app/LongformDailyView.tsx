"use client";
import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import type { LongformDaily, LongformTopic, FlowRow } from "./longform-types";
import { DIMENSIONS, DimensionBars, ExportButton, Light, Radar, RiskNotice, heatClass, num, pct, signClass, yi } from "./longform-ui";

const INPUT_LABELS: Record<string, string> = {
  discussion: "讨论度（分位）", amount: "题材成交额", amountRank: "资金面（成交额分位）", spread: "传播力（分位）", growth: "讨论升温",
  panicRate: "恐慌表达率 %", panicRank: "恐慌表达分位", previousAmount: "前一交易日成交额", dropValue: "放量下跌值（跌幅绝对值）", dropRank: "放量下跌分",
  reboundRate: "回补表达率 %", reboundCount: "回补表达条数", sampleCount: "有效分析样本", turnover: "换手率 %",
};

const BAND_CLASS: Record<string, string> = { strongUp: "lf-fill-up-strong", up: "lf-fill-up", flat: "lf-fill-flat", down: "lf-fill-down", strongDown: "lf-fill-down-strong" };

function inputValue(key: string, value: number | null) {
  if (value == null) return "—";
  return key === "amount" || key === "previousAmount" ? yi(value) : num(value, key === "reboundCount" || key === "sampleCount" ? 0 : 1);
}

function Header({ data, dates, onDate }: { data: LongformDaily; dates: string[]; onDate: (day: string) => void }) {
  const m = data.market, lm = data.limit?.metrics;
  return <header className="lf-hero">
    <div className="lf-kicker">复盘长图 · {data.meta.tradeDate} · 收盘后 · 方法 {data.meta.dimensionsVersion}</div>
    <h1>{data.narrative.title}</h1>
    <div className="lf-chips">
      <span>红盘率 <b>{num(m.upRate)}%</b></span>
      <span>成交 <b>{yi(m.amount)}</b>{m.amountChange != null && <em className={signClass(m.amountChange)}>{m.amountChange > 0 ? "增" : "减"} {yi(Math.abs(m.amountChange))}</em>}</span>
      <span>涨停 <b>{lm?.limitUp ?? "—"}</b> · 跌停 <b>{lm?.limitDown ?? "—"}</b></span>
      <span>炸板率 <b>{num(lm?.brokenRate)}%</b></span>
      {data.mainline && <span>主线 <b>{data.mainline.name}</b></span>}
    </div>
    <p className="lf-oneliner"><strong>一句话：</strong>{data.narrative.oneLiner}</p>
    <div className="lf-toolbar" data-export-skip="true">
      <label>交易日 <select value={data.meta.tradeDate} onChange={e => onDate(e.target.value)}>{dates.slice().reverse().map(day => <option key={day}>{day}</option>)}</select></label>
      <Link href="/weekly">周报 →</Link>
      <Link href="/">返回看板</Link>
    </div>
    <RiskNotice compact />
  </header>;
}

function Section({ step, eyebrow, title, children }: { step: string; eyebrow: string; title: string; children: React.ReactNode }) {
  return <section className="lf-section"><div className="lf-heading"><span className="report-step">{step}</span><div><span className="eyebrow">{eyebrow}</span><h2>{title}</h2></div></div>{children}</section>;
}

function Thermometers({ data }: { data: LongformDaily }) {
  if (!data.thermometers.length) return <p className="lf-empty">该日没有复盘体温计数据。</p>;
  return <div className="lf-thermo">{data.thermometers.map(t => <div key={t.key} className={heatClass(t.score)} title={t.detail}>
    <span>{t.name}</span><b>{t.score == null ? "—" : `${num(t.score)}${t.unit === "%" ? "%" : ""}`}</b><small>{t.scope}</small>
  </div>)}</div>;
}

function LimitSection({ data }: { data: LongformDaily }) {
  const lm = data.limit?.metrics;
  if (!lm) return <p className="lf-empty">该日没有取得涨停数据（接口只保留约 15 个交易日）。</p>;
  const ladder = lm.ladder ?? {};
  const top = Math.max(1, ...Object.values(ladder));
  const cards: [string, string, string][] = [
    ["涨停", `${lm.limitUp ?? "—"}`, "收盘仍封住"], ["跌停", `${lm.limitDown ?? "—"}`, "收盘跌停"], ["炸板率", `${num(lm.brokenRate)}%`, "炸板 ÷（涨停 + 炸板）"],
    ["连板高度", lm.maxBoards == null ? "—" : `${lm.maxBoards} 板`, lm.maxBoardStocks.map(s => s.name).join("、") || "—"],
    ["晋级率", `${num(lm.promotionRate)}%`, lm.promoted == null ? "—" : `昨日涨停 ${lm.yesterdayLimitUp} 只中 ${lm.promoted} 只今日再涨停`],
    ["昨日涨停今日", pct(lm.yesterdayMean), `中位数 ${pct(lm.yesterdayMedian)}；昨日连板 ${pct(lm.yesterdayStreakMean)}`],
  ];
  return <>
    <div className="lf-cards">{cards.map(([label, value, note]) => <div key={label}><span>{label}</span><b>{value}</b><small>{note}</small></div>)}</div>
    <div className="lf-ladder">{Object.entries(ladder).map(([boards, count]) => <div key={boards}><span>{boards} 板</span><div className="lf-bar-track"><i className="heat-60" style={{ width: `${100 * count / top}%` }} /></div><b>{count}</b></div>)}</div>
    {data.limitTop.length > 0 && <p className="lf-note">连板靠前：{data.limitTop.filter(s => (s.boards ?? 0) >= 2).map(s => `${s.name}（${s.streak ?? `${s.boards}板`}）`).join("、") || "无 2 板以上"}</p>}
    <p className="lf-note">来源：东方财富涨停板行情；{data.limit?.chainCheck ? `与 ${data.limit.chainCheck.previousDate} 涨停池交叉核对 ${num(data.limit.chainCheck.matchRate)}% 一致。` : "无前一交易日可交叉核对。"}描述统计，不做情绪阶段判断。</p>
  </>;
}

function Ranking({ topics }: { topics: LongformTopic[] }) {
  return <ol className="lf-rank">{topics.map((t, i) => <li key={t.id} className={`lf-rank-${t.alert.level}`}>
    <span className="lf-rank-no">#{i + 1}</span>
    <div>
      <strong>{t.name}</strong>
      <span className="shape-tag" title={t.shape.text}>{t.shape.label}</span>
      <Light level={t.alert.level} text={t.alert.text} />
      {t.isNew ? <span className="lf-badge">新进</span> : t.totalChange != null && <span className={`lf-delta ${signClass(t.totalChange)}`}>{t.totalChange > 0 ? "↑" : t.totalChange < 0 ? "↓" : "="}{Math.abs(t.totalChange)}</span>}
      <small>{DIMENSIONS.map(d => `${d.label}${num(t.dimensions[d.key], 0)}`).join(" · ")} · 涨跌 {pct(t.changePct)}{t.limitUpCount ? ` · 涨停 ${t.limitUpCount}` : ""}</small>
      <div className="lf-bar-track"><i className={heatClass(t.total)} style={{ width: `${t.total ?? 0}%` }} /></div>
    </div>
    <b className="lf-total" title={t.missing.length ? `缺少：${t.missing.join("、")}` : "试验总分"}>{t.total == null ? "—" : num(t.total, 0)}<small>/100</small>{t.missing.length > 0 && <small className="lf-missing">缺{t.missing.join("、")}</small>}</b>
  </li>)}</ol>;
}

function Heatmap({ data }: { data: LongformDaily }) {
  const formula = Object.fromEntries(data.meta.dimensions.map(d => [d.key, d.formula]));
  return <div className="report-matrix-scroll"><table className="report-matrix lf-heat">
    <thead><tr><th>题材</th>{DIMENSIONS.map(d => <th key={d.key} title={formula[d.key]}>{d.label}<small>{Math.round(data.meta.weights[d.key] * 100)}%</small></th>)}<th>总分</th><th>追涨表达<small>试验，不计入</small></th><th>形态</th></tr></thead>
    <tbody>{data.topics.map(t => <tr key={t.id}>
      <th>{t.name}</th>
      {DIMENSIONS.map(d => <td key={d.key} className={heatClass(t.dimensions[d.key])} title={t.dimensions[d.key] == null ? `缺失：${formula[d.key]}` : formula[d.key]}>{num(t.dimensions[d.key], 0)}</td>)}
      <td className={heatClass(t.total)} title={t.missing.length ? `缺少：${t.missing.join("、")}` : ""}><b>{num(t.total, 0)}</b></td>
      <td title={`判断覆盖率 ${num(t.chaseTrial.coverage)}%`}>{t.chaseTrial.score == null ? "—" : `${num(t.chaseTrial.score)}%`}<small>覆盖 {num(t.chaseTrial.coverage)}%</small></td>
      <td>{t.shape.label}</td>
    </tr>)}</tbody>
  </table></div>;
}

function TopicCard({ topic, line }: { topic: LongformTopic; line?: string }) {
  return <article className="lf-card">
    <header><strong>{topic.name}</strong><span className={signClass(topic.changePct)}>{pct(topic.changePct)}</span><b>{topic.total == null ? "—" : num(topic.total, 0)}<small>/100</small></b></header>
    <div className="lf-card-body"><Radar dims={topic.dimensions} size={220} /><DimensionBars dims={topic.dimensions} /></div>
    <p className="lf-card-line">{line}</p>
    {topic.missing.length > 0 && <p className="lf-note">总分未出：缺少{topic.missing.join("、")}。</p>}
    {topic.limitUpStocks && topic.limitUpStocks.length > 0 && <p className="lf-note">成分涨停：{topic.limitUpStocks.map(s => s.name + (s.streak ? `（${s.streak}）` : "")).join("、")}</p>}
    <details><summary>输入明细与原帖</summary>
      <table className="lf-inputs"><tbody>{Object.entries(topic.inputs).map(([key, value]) => <tr key={key}><th>{INPUT_LABELS[key] ?? key}</th><td>{inputValue(key, value)}</td></tr>)}</tbody></table>
      {topic.evidence.map((post, i) => <blockquote key={i}>{post.text}<small>{post.date} · {post.intent}{post.url && <> · <a href={post.url} target="_blank" rel="noreferrer">原帖</a></>}</small></blockquote>)}
    </details>
  </article>;
}

function Flows({ data }: { data: LongformDaily }) {
  const column = (title: string, rows: FlowRow[]) => <div className="lf-flow"><h3>{title}</h3>{rows.length ? rows.map(r => <div key={r.boardId}><span>{r.name}</span><b className={signClass(r.net)}>{yi(r.net)}</b><small>{pct(r.changePct)}</small></div>) : <p className="lf-empty">无</p>}</div>;
  return <div className="lf-flows">
    {column("行业 · 净流入", data.flows.industry.inflow)}{column("行业 · 净流出", data.flows.industry.outflow)}
    {column("概念 · 净流入", data.flows.concept.inflow)}{column("概念 · 净流出", data.flows.concept.outflow)}
  </div>;
}

function MarketBase({ data }: { data: LongformDaily }) {
  const d = data.market.diagnostics;
  return <>
    <div className="lf-cards">
      {data.indices.map(i => <div key={i.symbol}><span>{i.name}</span><b className={signClass(i.changePct)}>{pct(i.changePct)}</b><small>收盘 {num(i.close, 2)}</small></div>)}
      <div><span>两融余额</span><b>{yi(data.margin?.total)}</b><small>{data.margin ? `${data.margin.date}（次日公布）· 较前日 ${yi(data.margin.change)}` : "—"}</small></div>
      <div><span>涨跌中位数</span><b className={signClass(data.market.medianChange)}>{pct(data.market.medianChange)}</b><small>{data.market.up} 涨 / {data.market.down} 跌 / {data.market.flat} 平</small></div>
    </div>
    {d?.distribution && <div className="lf-dist">{d.distribution.map(b => <div key={b.key}><span>{b.name}</span><div className="lf-bar-track"><i className={BAND_CLASS[b.key] ?? "heat-20"} style={{ width: `${b.share ?? 0}%` }} /></div><b>{b.count ?? "—"}</b></div>)}</div>}
  </>;
}

export function LongformDailyView({ initial }: { initial: LongformDaily }) {
  const [data, setData] = useState(initial), [dates, setDates] = useState<string[]>([initial.meta.tradeDate]), [error, setError] = useState("");
  const page = useRef<HTMLDivElement>(null);
  useEffect(() => {
    fetch("/data/longform/index.json", { cache: "no-store" }).then(r => r.ok ? r.json() as Promise<{ dates?: string[] }> : null).then(index => { if (index?.dates) setDates(index.dates); }).catch(() => undefined);
    const requested = new URLSearchParams(window.location.search).get("date");
    if (requested && requested !== initial.meta.tradeDate) void load(requested);
  }, [initial.meta.tradeDate]);
  async function load(day: string) {
    setError("");
    try {
      const response = await fetch(`/data/longform/daily/${day}.json`, { cache: "no-store" });
      if (!response.ok) throw new Error();
      setData(await response.json() as LongformDaily);
      window.history.replaceState(null, "", `?date=${day}`);
    } catch {
      setError(`${day} 没有长图数据`);
    }
  }
  return <main className="lf-main">
    <div className="lf-actions" data-export-skip="true"><ExportButton target={page} fileName={`复盘长图-${data.meta.tradeDate}.png`} />{error && <span className="lf-error">{error}</span>}</div>
    <div className="lf-page" ref={page}>
      <Header data={data} dates={dates} onDate={load} />
      <Section step="1" eyebrow="市场体温计" title="五支温度计"><Thermometers data={data} /></Section>
      <Section step="2" eyebrow="涨停生态" title={data.limit ? `涨停 ${data.limit.metrics.limitUp ?? "—"} 家，炸板率 ${num(data.limit.metrics.brokenRate)}%，最高 ${data.limit.metrics.maxBoards ?? "—"} 连板` : "涨停数据未取得"}><LimitSection data={data} /></Section>
      <Section step="3" eyebrow="十强题材排名 · 试验总分" title={data.topics[0]?.total != null ? `${data.topics[0].name} 总分最高（${num(data.topics[0].total, 0)}）` : "十强题材与六维"}>
        <p className="lf-note">总分 = 热度×30% + 扩散力×20% + 动摇度×20% + 回补力×15% + 拥挤度×15%，任一维缺失则不出总分。各维是十强题材之间的相对分位。</p>
        {data.mainline && <p className="lf-note">主线：<b>{data.mainline.name}</b>，成分涨停 {data.mainline.limitUpCount} 家，占全市场涨停 {data.mainline.limitUpTotal} 家的 {num(data.mainline.concentration)}%（涨停集中度）。</p>}
        <Ranking topics={data.topics} />
      </Section>
      <Section step="4" eyebrow="题材 × 维度热力表" title="逐格对比"><Heatmap data={data} /></Section>
      <Section step="5" eyebrow="题材卡片" title="每个题材：雷达、分项与原帖"><div className="lf-card-grid">{data.topics.map(t => <TopicCard key={t.id} topic={t} line={data.narrative.topics[t.id]} />)}</div></Section>
      <Section step="6" eyebrow="资金底账 · 新浪主力口径" title="行业与概念主力净额前五"><Flows data={data} /></Section>
      <Section step="7" eyebrow="市场底账" title="指数、两融与涨跌分布"><MarketBase data={data} /></Section>
      {data.anchors.map(a => <Section key={a.date} step="★" eyebrow={`锚点对比 · ${a.name}`} title={`${a.years} 年前的今天：指数累计变化`}>
        <p className="lf-note">{a.description} 基准为锚点前一交易日收盘。</p>
        <div className="lf-cards">{a.indices.map(i => <div key={i.name}><span>{i.name}</span><b className={signClass(i.changePct)}>{pct(i.changePct)}</b><small>{num(i.base, 2)} → {num(i.close, 2)}</small></div>)}
          <div><span>两融余额</span><b className={signClass(a.margin.changePct)}>{pct(a.margin.changePct, 1)}</b><small>{yi(a.margin.base?.total)} → {yi(a.margin.end?.total)}</small></div></div>
      </Section>)}
      <footer className="lf-footer">
        <h3>口径说明</h3>
        <ul>{data.meta.notes.map(n => <li key={n}>{n}</li>)}
          <li>复盘数据：{data.meta.reportSource === "recomputed" ? "由保存的采集记录按当前代码重算" : data.meta.reportSource === "saved" ? "读取已保存的日报" : "该日无复盘数据"}（{data.meta.reportMethod ?? "—"}）。</li>
          <li>行情采集 {data.meta.marketCollectedAt ?? "—"}；涨停采集 {data.meta.limitCollectedAt ?? "—"}；长图生成 {data.meta.builtAt}。</li>
          <li>文字为{data.narrative.source === "template" ? "模板生成" : "模型生成（数字由程序填入）"}。形态名称与参考图对应：{"高热高动摇=镰刀型、扩散低动摇=风筝型、动摇有回补=吸铁型、降温=泄气型、冷清=佛系"}。</li>
        </ul>
        <RiskNotice />
      </footer>
    </div>
  </main>;
}
