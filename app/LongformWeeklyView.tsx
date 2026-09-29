"use client";
import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import type { LongformWeekly, WeeklyFlow, WeeklyTopic } from "./longform-types";
import { DIMENSIONS, DIMENSION_GUIDE, DimensionBars, ExportButton, Guide, Light, Radar, RiskNotice, heatClass, num, pct, signClass, yi } from "./longform-ui";

// Opening glossary for each section; wording describes the numbers, never what to do with them.
const GUIDE: Record<string, [string, string][]> = {
  key: [
    ["周分最高题材", "本周周分排第一的题材，见第 5 节。"],
    ["最低红盘率", "红盘率 = 当天上涨股票占比；取本周最低的一天，小字为逐日数值。"],
    ["最大净流出行业", "本周主力净额逐日相加后，净流出最多的行业。"],
    ["主线切换", "相邻两个交易日主线题材不同的次数，次数越多说明热点轮动越快。"],
    ["上证周涨跌", "本周最后一个交易日收盘较上周最后一个交易日收盘的涨跌幅。"],
  ],
  timeline: [
    ["红盘率", "当天上涨股票占比。"],
    ["涨停 / 跌停、炸板率", "收盘封住涨停 / 跌停的家数；炸板率 = 碰过涨停却没封住的比例。"],
    ["最高连板", "当天连续涨停天数最多的股票有几板。"],
    ["主线", "十强题材中成分涨停最多的题材，括号内为涨停集中度。"],
    ["总分最高题材", "当天日报里试验总分排第一的题材。"],
  ],
  mainline: [
    ["当日主线", "十强题材中成分涨停最多的题材，并列时取涨幅更高者。"],
    ["涨停集中度", "主线的成分涨停数 ÷ 全市场涨停数，越高说明涨停越集中在一个题材。"],
    ["位置高低", "卡片越靠上，集中度越高。"],
  ],
  limit: [
    ["柱高", "当天涨停家数，本周最高的一天为满格。"],
    ["炸板", "当天炸板率：碰过涨停却没封住的比例。"],
  ],
  rank: [
    ["周分（试验）", "该题材本周出现各天的日总分平均，至少出现 2 天；各维度同样取平均。"],
    ["日总分", "热度 30% + 扩散力 20% + 动摇度 20% + 回补力 15% + 拥挤度 15%，五维含义见第 6 节。"],
    ["形态与灯", "形态为按五维组合给出的描述名；红 / 黄 / 绿灯为拥挤提示（拥挤度与动摇度是否同时偏高）。"],
    ["↑ ↓ / 新进", "周分较上周的变化；“新进”表示上周未上榜。"],
  ],
  heat: [
    ["每一格", "该题材本周该维度的平均分（0–100），颜色越深越高，“—”为缺数据。"],
    ["环比", "周分较上周的变化。"],
    ["拥挤提示", "红 = 拥挤度与动摇度都偏高；黄 = 其一偏高；绿 = 都不突出；灰 = 缺数据。"],
  ],
  leaders: [["每张卡片", "同一个维度下，本周各题材从高到低排列；维度含义见第 6 节。"]],
  indices: [
    ["周涨跌", "本周最后一个交易日收盘较上周最后一个交易日收盘。"],
    ["周内最高", "本周各交易日收盘价中的最高值。"],
  ],
  flows: [
    ["主力净额", "新浪财经口径：大单、超大单主动买盘金额减主动卖盘金额；本周逐日相加。不同网站口径不同，数值不可直接互比。"],
    ["四栏", "行业、概念板块各列本周净流入最多和净流出最多的五个。"],
  ],
};

function Section({ step, eyebrow, title, guide, note, children }: { step: string; eyebrow: string; title: string; guide?: [string, string][]; note?: string; children: React.ReactNode }) {
  return <section className="lf-section"><div className="lf-heading"><span className="report-step">{step}</span><div><span className="eyebrow">{eyebrow}</span><h2>{title}</h2></div></div>{guide && <Guide items={guide} note={note} />}{children}</section>;
}

function KeyCards({ data }: { data: LongformWeekly }) {
  const m = data.market, top = data.topics.find(t => t.total != null), out = data.flows.industry.outflow[0];
  const cards: [string, string, string, string?][] = [
    ["周分最高题材", top ? top.name : "—", top ? `${num(top.total, 0)} 分 · 出现 ${top.appearances} 天` : "题材排名未发布"],
    ["最低红盘率", m.minUpRate == null ? "—" : `${num(m.minUpRate)}%`, m.upRates.map(r => r == null ? "—" : `${num(r)}%`).join(" → ")],
    ["最大净流出行业", out ? out.name : "—", out ? `${yi(out.net)}（${out.days} 天合计）` : "无资金数据", out ? "fall" : undefined],
    ["主线切换", m.mainlineSwitches == null ? "—" : `${m.mainlineSwitches} 次`, m.mainlines.join(" → ") || "无每日主线数据"],
    ["上证周涨跌", pct(m.shChange), `日均涨停 ${num(m.meanLimitUp)} · 最高 ${m.maxBoards ?? "—"} 连板`, signClass(m.shChange)],
  ];
  return <div className="lf-cards">{cards.map(([label, value, note, tone]) => <div key={label}><span>{label}</span><b className={tone}>{value}</b><small>{note}</small></div>)}</div>;
}

function Timeline({ data }: { data: LongformWeekly }) {
  return <div className="report-matrix-scroll"><table className="report-matrix lf-heat lf-timeline">
    <thead><tr><th>日期</th><th>上证</th><th>红盘率</th><th>成交额</th><th>涨停 / 跌停</th><th>炸板率</th><th>最高连板</th><th>主线（涨停集中度）</th><th>总分最高题材</th></tr></thead>
    <tbody>{data.timeline.map(d => <tr key={d.date}>
      <th>{d.date.slice(5)} 周{d.weekday}{!d.hasMarket && <small>无行情快照</small>}</th>
      <td className={signClass(d.shChange)}>{pct(d.shChange)}<small>{num(d.shClose, 2)}</small></td>
      <td>{d.upRate == null ? "—" : `${num(d.upRate)}%`}</td>
      <td>{yi(d.amount)}</td>
      <td>{d.limitUp ?? "—"} / {d.limitDown ?? "—"}</td>
      <td>{d.brokenRate == null ? "—" : `${num(d.brokenRate)}%`}</td>
      <td>{d.maxBoards ?? "—"}</td>
      <td>{d.mainline ? `${d.mainline.name}（${num(d.mainline.concentration)}%）` : "—"}</td>
      <td>{d.topTopic ? `${d.topTopic.name}（${num(d.topTopic.total, 0)}）` : "—"}</td>
    </tr>)}</tbody>
  </table></div>;
}

function LimitSeries({ data }: { data: LongformWeekly }) {
  const top = Math.max(1, ...data.timeline.map(d => d.limitUp ?? 0));
  return <div className="lf-series">{data.timeline.map(d => <div key={d.date}>
    <div className="lf-series-bar"><i className="lf-fill-up" style={{ height: `${100 * (d.limitUp ?? 0) / top}%` }} /></div>
    <b>{d.limitUp ?? "—"}</b><span>{d.date.slice(5)}</span><small>炸板 {d.brokenRate == null ? "—" : `${num(d.brokenRate, 0)}%`}</small>
  </div>)}</div>;
}

function Mainline({ data }: { data: LongformWeekly }) {
  const days = data.timeline.filter(d => d.mainline);
  if (!days.length) return <p className="lf-empty">本周没有可用的每日主线：主线需要当天的十强题材与涨停池同时存在。</p>;
  return <div className="lf-stairs">{days.map(d => <div key={d.date} style={{ marginTop: `${Math.max(0, 60 - (d.mainline?.concentration ?? 0) * 2)}px` }}>
    <b>{num(d.mainline?.concentration)}%</b><strong>{d.mainline?.name}</strong><small>{d.date.slice(5)} · 成分涨停 {d.mainline?.limitUpCount}/{d.mainline?.limitUpTotal}</small>
  </div>)}</div>;
}

function TopicRanking({ topics }: { topics: WeeklyTopic[] }) {
  return <ol className="lf-rank">{topics.map((t, i) => <li key={t.id} className={`lf-rank-${t.alert.level}`}>
    <span className="lf-rank-no">#{i + 1}</span>
    <div>
      <strong>{t.name}</strong><span className="shape-tag" title={t.shape.text}>{t.shape.label}</span><Light level={t.alert.level} text={t.alert.text} />
      {t.isNew ? <span className="lf-badge">新进</span> : t.totalChange != null && <span className={`lf-delta ${signClass(t.totalChange)}`}>{t.totalChange > 0 ? "↑" : t.totalChange < 0 ? "↓" : "="}{Math.abs(t.totalChange)}</span>}
      <small>{DIMENSIONS.map(d => `${d.label}${num(t.dimensions[d.key], 0)}`).join(" · ")} · 出现 {t.appearances} 天（{t.scoredDays} 天有总分）· 成分涨停合计 {t.limitUps}</small>
      <div className="lf-bar-track"><i className={heatClass(t.total)} style={{ width: `${t.total ?? 0}%` }} /></div>
    </div>
    <b className="lf-total">{t.total == null ? "—" : num(t.total, 0)}<small>/100</small>{t.missing.length > 0 && <small className="lf-missing">缺{t.missing.join("、")}</small>}</b>
  </li>)}</ol>;
}

function RadarSwitch({ topics }: { topics: WeeklyTopic[] }) {
  const [selected, setSelected] = useState(topics[0]?.id);
  const topic = topics.find(t => t.id === selected) ?? topics[0];
  if (!topic) return null;
  return <>
    <div className="segmented lf-tabs" role="group" aria-label="选择题材">{topics.map(t => <button key={t.id} type="button" className={t.id === topic.id ? "active" : ""} aria-pressed={t.id === topic.id} onClick={() => setSelected(t.id)}>{t.name}</button>)}</div>
    <div className="lf-card-body lf-radar-wide"><Radar dims={topic.dimensions} size={260} /><div><DimensionBars dims={topic.dimensions} /><p className="lf-card-line">{topic.name}：{topic.shape.text}；拥挤提示：{topic.alert.text}。</p></div></div>
  </>;
}

function DimensionLeaders({ topics }: { topics: WeeklyTopic[] }) {
  return <div className="lf-card-grid lf-leaders">{DIMENSIONS.map(d => {
    const rows = topics.filter(t => t.dimensions[d.key] != null).sort((a, b) => (b.dimensions[d.key] ?? 0) - (a.dimensions[d.key] ?? 0));
    return <div key={d.key} className="lf-card"><header><strong>{d.label}</strong></header>
      {rows.length ? <div className="lf-bars">{rows.map(t => <div key={t.id} className="lf-bar-row"><span>{t.name}</span><div className="lf-bar-track"><i className={heatClass(t.dimensions[d.key])} style={{ width: `${t.dimensions[d.key]}%` }} /></div><b>{num(t.dimensions[d.key], 0)}</b></div>)}</div> : <p className="lf-empty">无数据</p>}
    </div>;
  })}</div>;
}

function Flows({ data }: { data: LongformWeekly }) {
  const column = (title: string, rows: WeeklyFlow[]) => <div className="lf-flow"><h3>{title}</h3>{rows.length ? rows.map(r => <div key={r.boardId}><span>{r.name}</span><b className={signClass(r.net)}>{yi(r.net)}</b><small>{r.days} 天合计</small></div>) : <p className="lf-empty">无</p>}</div>;
  return <>
    <p className="lf-note">资金数据覆盖 {data.flows.days}/{data.flows.totalDays} 个交易日。</p>
    <div className="lf-flows">{column("行业 · 净流入", data.flows.industry.inflow)}{column("行业 · 净流出", data.flows.industry.outflow)}{column("概念 · 净流入", data.flows.concept.inflow)}{column("概念 · 净流出", data.flows.concept.outflow)}</div>
  </>;
}

export function LongformWeeklyView({ initial }: { initial: LongformWeekly }) {
  const [data, setData] = useState(initial), [weeks, setWeeks] = useState<string[]>([initial.meta.week]), [error, setError] = useState("");
  const page = useRef<HTMLDivElement>(null);
  useEffect(() => {
    fetch("/data/weekly/index.json", { cache: "no-store" }).then(r => r.ok ? r.json() as Promise<{ weeks?: string[] }> : null).then(index => { if (index?.weeks) setWeeks(index.weeks); }).catch(() => undefined);
    const requested = new URLSearchParams(window.location.search).get("week");
    if (requested && requested !== initial.meta.week) void load(requested);
  }, [initial.meta.week]);
  async function load(week: string) {
    setError("");
    try {
      const response = await fetch(`/data/weekly/${week}.json`, { cache: "no-store" });
      if (!response.ok) throw new Error();
      setData(await response.json() as LongformWeekly);
      window.history.replaceState(null, "", `?week=${week}`);
    } catch {
      setError(`${week} 没有周报数据`);
    }
  }
  const m = data.meta;
  return <main className="lf-main">
    <div className="lf-actions" data-export-skip="true"><ExportButton target={page} fileName={`周报-${m.week}.png`} />{error && <span className="lf-error">{error}</span>}</div>
    <div className="lf-page" ref={page}>
      <header className="lf-hero">
        <div className="lf-kicker">周报 · {m.week} · {m.startDate} 至 {m.endDate} · {m.sessions.length} 个交易日 · 方法 {m.dimensionsVersion}</div>
        <h1>{data.narrative.title}</h1>
        <div className="lf-chips">
          <span>完整度 <b>{m.longformDays.length}/{m.sessions.length}</b> 天有长图</span>
          <span>上证 <b className={signClass(data.market.shChange)}>{pct(data.market.shChange)}</b></span>
          <span>日均成交 <b>{yi(data.market.meanAmount)}</b></span>
          <span>日均涨停 <b>{num(data.market.meanLimitUp)}</b></span>
          <span>最高连板 <b>{data.market.maxBoards ?? "—"}</b></span>
        </div>
        <p className="lf-oneliner"><strong>一句话：</strong>{data.narrative.oneLiner}</p>
        {data.narrative.conclusions.length > 0 && <ul className="lf-conclusions">{data.narrative.conclusions.map(c => <li key={c}>{c}</li>)}</ul>}
        {m.missingDays.length > 0 && <p className="lf-note">缺少长图数据的交易日：{m.missingDays.join("、")}。{m.topicsPublished ? "" : `少于 ${m.requiredDays} 天，本周不发布题材排名，只展示市场部分。`}</p>}
        <div className="lf-toolbar" data-export-skip="true">
          <label>周次 <select value={m.week} onChange={e => load(e.target.value)}>{weeks.slice().reverse().map(w => <option key={w}>{w}</option>)}</select></label>
          <Link href="/report">日报长图 →</Link><Link href="/">返回看板</Link>
        </div>
        <RiskNotice compact />
      </header>
      <Section step="1" eyebrow="关键数字" title="本周五个数" guide={GUIDE.key}><KeyCards data={data} /></Section>
      <Section step="2" eyebrow="市场时间线" title="逐日行情、涨停与主线" guide={GUIDE.timeline}><Timeline data={data} /></Section>
      <Section step="3" eyebrow="主线轮盘 · 涨停集中度" title={data.market.mainlineSwitches == null ? "每日主线" : `主线切换 ${data.market.mainlineSwitches} 次`} guide={GUIDE.mainline} note="涨停集中度与参考图的“浓度”（散户分级占比）含义不同。">
        <Mainline data={data} />
      </Section>
      <Section step="4" eyebrow="涨停生态周序列" title={`日均涨停 ${num(data.market.meanLimitUp)} 家，最高 ${data.market.maxBoards ?? "—"} 连板`} guide={GUIDE.limit}><LimitSeries data={data} /></Section>
      {m.topicsPublished && data.topics.length > 0 ? <>
        <Section step="5" eyebrow="周九强 · 试验周分" title={`${data.topics[0].name} 周分最高`} guide={GUIDE.rank} note="周分未经历史回测校准，高分表示讨论与交易集中，不是买卖信号。">
          <TopicRanking topics={data.topics} />
        </Section>
        <Section step="6" eyebrow="五维雷达" title="逐题材查看" guide={DIMENSION_GUIDE} note="周报中的每一维是该题材本周各天分数的平均。点上方题材名切换；雷达越往外代表分数越高。"><RadarSwitch topics={data.topics} /></Section>
        <Section step="7" eyebrow="题材 × 维度热力表" title="逐格对比" guide={GUIDE.heat}>
          <div className="report-matrix-scroll"><table className="report-matrix lf-heat"><thead><tr><th>题材</th>{DIMENSIONS.map(d => <th key={d.key}>{d.label}</th>)}<th>周分</th><th>环比</th><th>拥挤提示</th></tr></thead>
            <tbody>{data.topics.map(t => <tr key={t.id}><th>{t.name}<small>出现 {t.appearances} 天</small></th>{DIMENSIONS.map(d => <td key={d.key} className={heatClass(t.dimensions[d.key])}>{num(t.dimensions[d.key], 0)}</td>)}
              <td className={heatClass(t.total)}><b>{num(t.total, 0)}</b></td><td className={signClass(t.totalChange)}>{t.isNew ? "新进" : t.totalChange == null ? "—" : `${t.totalChange > 0 ? "+" : ""}${t.totalChange}`}</td><td><Light level={t.alert.level} text={t.alert.text} /></td></tr>)}</tbody></table></div>
        </Section>
        <Section step="8" eyebrow="分维度排行" title="谁最热、谁最动摇、谁回补最多" guide={GUIDE.leaders}><DimensionLeaders topics={data.topics} /></Section>
      </> : <Section step="5" eyebrow="周题材排名" title="本周不发布题材排名"><p className="lf-empty">本周有长图的交易日为 {m.longformDays.length} 天，少于发布门槛 {m.requiredDays} 天。题材排名需要连续的每日采集；市场部分照常展示。</p></Section>}
      <Section step="9" eyebrow="指数周涨跌" title={`上证指数 ${pct(data.market.shChange)}`} guide={GUIDE.indices}>
        <div className="lf-cards">{data.indices.map(i => <div key={i.symbol}><span>{i.name}</span><b className={signClass(i.changePct)}>{pct(i.changePct)}</b><small>{i.baseDate ? `${num(i.close, 2)}（较 ${i.baseDate} 收盘）· 周内最高 ${num(i.high, 2)}` : "—"}</small></div>)}</div>
      </Section>
      <Section step="10" eyebrow="资金底账 · 新浪主力口径" title="本周主力净额累计前五" guide={GUIDE.flows}><Flows data={data} /></Section>
      {data.recap.length > 0 && <Section step="11" eyebrow={`上周数字回顾 · ${data.previousWeek}`} title="上周与本周，只列事实" guide={[["对照表", "同一指标上周与本周的数值并排列出，只陈述变化，不做评价。"]]}>
        <div className="report-matrix-scroll"><table className="report-matrix lf-recap"><thead><tr><th>指标</th><th>上周</th><th>本周</th></tr></thead>
          <tbody>{data.recap.map(r => <tr key={r.label}><th>{r.label}</th><td>{r.previous}</td><td>{r.current}</td></tr>)}</tbody></table></div>
      </Section>}
      <footer className="lf-footer">
        <h3>口径说明</h3>
        <ul>{m.notes.map(n => <li key={n}>{n}</li>)}<li>文字为{data.narrative.source === "template" ? "模板生成" : "模型生成（数字由程序填入）"}；生成时间 {m.builtAt}。</li></ul>
        <p className="lf-note">{data.narrative.summary}</p>
        <RiskNotice />
      </footer>
    </div>
  </main>;
}
